import asyncio
import inspect

import orjson
from pydantic import SecretStr
from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPart, TextPartDelta

from app.core.errors import RateLimitAppError
from app.core.settings import Settings
from app.models.chat import ChatRequest, ConversationRecord
from app.services.chat_service import ChatService


class DummyServerError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.conversation = ConversationRecord(id="conv_stream_tests")

    async def create_new(self) -> ConversationRecord:
        return self.conversation

    async def get(self, conversation_id: str) -> ConversationRecord | None:
        if self.conversation.id == conversation_id:
            return self.conversation
        return None

    async def save(self, conversation: ConversationRecord) -> None:
        self.conversation = conversation


def decode_sse_chunks(chunks: list[str]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for chunk in chunks:
        for frame in chunk.split("\n\n"):
            line = frame.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload:
                continue
            if payload == "[DONE]":
                events.append({"type": "done", "data": {}})
                continue
            events.append(orjson.loads(payload))
    return events


def collect_text_deltas(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "text_delta":
            continue
        data = event.get("data")
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            chunks.append(data["text"])
    return "".join(chunks)


def test_chat_service_marks_500_as_transient() -> None:
    settings = Settings(google_api_key=SecretStr("test-key"))
    service = ChatService(settings=settings)

    assert service._is_transient_model_failure(DummyServerError(500)) is True
    assert service._is_transient_model_failure(DummyServerError(503)) is True
    assert service._is_transient_model_failure(DummyServerError(429)) is True
    assert service._is_transient_model_failure(DummyServerError(400)) is False


def test_stream_chat_keeps_text_from_part_start_event() -> None:
    settings = Settings(google_api_key=SecretStr("test-key"))
    repository = InMemoryConversationRepository()
    service = ChatService(settings=settings, repository=repository)

    async def fake_run_stream_events_with_retries(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        yield PartStartEvent(index=0, part=TextPart(content="Hello"))

    service._run_stream_events_with_retries = fake_run_stream_events_with_retries  # type: ignore[method-assign]

    async def run_stream() -> list[str]:
        chunks: list[str] = []
        async for chunk in service.stream_chat(ChatRequest(message="test"), client_id="client_stream"):
            chunks.append(chunk)
        return chunks

    events = decode_sse_chunks(asyncio.run(run_stream()))
    assert collect_text_deltas(events) == "Hello"


def test_stream_chat_keeps_part_start_and_delta_text_order() -> None:
    settings = Settings(google_api_key=SecretStr("test-key"))
    repository = InMemoryConversationRepository()
    service = ChatService(settings=settings, repository=repository)

    async def fake_run_stream_events_with_retries(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        yield PartStartEvent(index=0, part=TextPart(content="Hello"))
        yield PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" world"))

    service._run_stream_events_with_retries = fake_run_stream_events_with_retries  # type: ignore[method-assign]

    async def run_stream() -> list[str]:
        chunks: list[str] = []
        async for chunk in service.stream_chat(ChatRequest(message="test"), client_id="client_stream"):
            chunks.append(chunk)
        return chunks

    events = decode_sse_chunks(asyncio.run(run_stream()))
    assert collect_text_deltas(events) == "Hello world"


def test_request_needs_visual_detects_interactive_follow_ups() -> None:
    settings = Settings(google_api_key=SecretStr("test-key"))
    service = ChatService(settings=settings)

    assert service._request_needs_visual('Make it interactive') is True
    assert service._request_needs_visual('Turn this into a simulation') is True


def test_visual_fallback_context_removes_dense_vs_moe_svg_bias() -> None:
    source = inspect.getsource(ChatService.get_visual_agent)

    assert "Dense vs MoE style comparison prompts" not in source
    assert "interactive controls, not static SVG side-by-sides" in source


def test_recovery_prefers_stronger_fallback_model(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_FALLBACK_MODEL_NAME", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL_NAME", raising=False)
    monkeypatch.delenv("GOOGLE_VISUAL_RECOVERY_MODEL_NAME", raising=False)
    monkeypatch.delenv("GEMINI_VISUAL_RECOVERY_MODEL_NAME", raising=False)
    settings = Settings(
        _env_file=None,
        google_api_key=SecretStr("test-key"),
        google_visual_recovery_model_name="gemini-3.1-pro-preview",
    )
    service = ChatService(settings=settings)

    assert service._resolve_recovery_models("gemini-3-flash-preview") == [
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
    ]


def test_stream_fallback_uses_visual_recovery_when_generic_fallback_matches_primary() -> None:
    settings = Settings(
        _env_file=None,
        google_api_key=SecretStr("test-key"),
        google_fallback_model_name="gemini-3-flash-preview",
        google_visual_recovery_model_name="gemini-3.1-pro-preview",
    )
    service = ChatService(settings=settings)

    assert (
        service._resolve_stream_fallback_model_name("gemini-3-flash-preview")
        == "gemini-3.1-pro-preview"
    )


def test_extract_retry_after_from_retry_info() -> None:
    settings = Settings(google_api_key=SecretStr("test-key"))
    service = ChatService(settings=settings)

    class DummyRateLimitError(Exception):
        status_code = 429
        body = {
            "error": {
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "48s",
                    }
                ]
            }
        }

    assert service._extract_retry_after_seconds(DummyRateLimitError()) == 48


def test_extract_retry_after_from_message_fallback() -> None:
    settings = Settings(google_api_key=SecretStr("test-key"))
    service = ChatService(settings=settings)

    class DummyRateLimitError(Exception):
        status_code = 429

        def __str__(self) -> str:
            return "Quota exceeded. Please retry in 27.5s."

    assert service._extract_retry_after_seconds(DummyRateLimitError()) == 27


def test_visual_recovery_falls_back_when_stronger_model_rate_limited(monkeypatch) -> None:
    settings = Settings(
        google_api_key=SecretStr("test-key"),
        google_visual_recovery_model_name="gemini-3.1-pro-preview",
    )
    service = ChatService(settings=settings)
    conversation = ConversationRecord(id="conv_test")
    deps = service._agent_cache  # type: ignore[assignment]
    del deps  # keep test free of unused local warnings

    from app.services.chat_service import AgentDependencies, StreamEventSink

    agent_bundle = service.agent_registry.get()
    recovery_deps = AgentDependencies(
        agent_id=agent_bundle.config.agent.id,
        config=agent_bundle.config,
        conversation=conversation,
        event_sink=StreamEventSink(),
        wants_visual=True,
        user_message="Compare dense vs MoE visually",
        from_widget=None,
    )

    async def fake_run_stream_events_with_retries(*, model_name, **kwargs):
        if model_name == "gemini-3.1-pro-preview":
            raise RateLimitAppError(37)
        if False:
            yield None

    async def fake_generate_visual_without_tool(*, model_name, **kwargs):
        return []

    monkeypatch.setattr(service, "_run_stream_events_with_retries", fake_run_stream_events_with_retries)
    monkeypatch.setattr(service, "_generate_visual_without_tool", fake_generate_visual_without_tool)

    import asyncio

    result = asyncio.run(
        service._attempt_visual_recovery(
            request=ChatRequest(message="Compare dense vs MoE visually"),
            model_name="gemini-3.1-flash-lite-preview",
            deps=recovery_deps,
            message_history=None,
            client_id="c1",
        )
    )

    assert result.had_widget is False


def test_extract_disallowed_url_hosts_respects_allowlist_and_overrides() -> None:
    settings = Settings(
        google_api_key=SecretStr("test-key"),
        google_allowed_url_domains=["github.com", "*.wikipedia.org"],
        google_extra_allowed_url_domains=["docs.example.com"],
    )
    service = ChatService(settings=settings)

    hosts = service._extract_disallowed_url_hosts(
        "Explain these: "
        "https://github.com/pydantic/pydantic-ai "
        "https://en.wikipedia.org/wiki/Gemini_(chatbot) "
        "https://docs.example.com/guide "
        "https://unknown.example.net/post"
    )

    assert hosts == ["unknown.example.net"]


def test_builtin_google_tools_follow_feature_flags() -> None:
    disabled_settings = Settings(
        google_api_key=SecretStr("test-key"),
        google_enable_web_search=False,
        google_enable_url_context=False,
    )
    disabled_service = ChatService(settings=disabled_settings)
    assert disabled_service._google_builtin_tools == []

    enabled_settings = Settings(
        google_api_key=SecretStr("test-key"),
        google_enable_web_search=True,
        google_enable_url_context=True,
    )
    enabled_service = ChatService(settings=enabled_settings)
    tool_names = {type(tool).__name__ for tool in enabled_service._google_builtin_tools}
    assert tool_names == {"WebSearchTool", "WebFetchTool"}
