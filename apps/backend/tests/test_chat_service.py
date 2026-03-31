from pydantic import SecretStr

from app.core.errors import RateLimitAppError
from app.core.settings import Settings
from app.models.chat import ChatRequest, ConversationRecord
from app.services.chat_service import ChatService


class DummyServerError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_chat_service_marks_500_as_transient() -> None:
    settings = Settings(google_api_key=SecretStr("test-key"))
    service = ChatService(settings=settings)

    assert service._is_transient_model_failure(DummyServerError(500)) is True
    assert service._is_transient_model_failure(DummyServerError(503)) is True
    assert service._is_transient_model_failure(DummyServerError(429)) is True
    assert service._is_transient_model_failure(DummyServerError(400)) is False


def test_request_needs_visual_detects_interactive_follow_ups() -> None:
    settings = Settings(google_api_key=SecretStr("test-key"))
    service = ChatService(settings=settings)

    assert service._request_needs_visual('Make it interactive') is True
    assert service._request_needs_visual('Turn this into a simulation') is True


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

    recovery_deps = AgentDependencies(
        config=service.config,
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
