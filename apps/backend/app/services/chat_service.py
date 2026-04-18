from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, cast
from urllib.parse import urlparse

import orjson
from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    ModelMessagesTypeAdapter,
    PartDeltaEvent,
    PartStartEvent,
    RunContext,
    TextPartDelta,
    ThinkingPartDelta,
)
from pydantic_ai.builtin_tools import WebFetchTool, WebSearchTool
from pydantic_ai.exceptions import ModelHTTPError, ModelRetry, UnexpectedModelBehavior
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider

from app.agent.config import VisualAgentConfig
from app.agent.svg_preview_renderer import ExternalSvgPreviewRenderer
from app.agent.registry import AgentPromptBundle, AgentRegistry
from app.agent.svg_library import SvgLibraryService
from app.agent.svg_vision_repair import SvgVisionRepairService
from app.agent.widget_validator import (
    build_template_instance_widget_payload,
    build_widget_payload,
)
from app.core.errors import (
    AppError,
    NotFoundAppError,
    RateLimitAppError,
    ServiceUnavailableAppError,
    ValidationAppError,
)
from app.core.settings import Settings, get_settings
from app.models.chat import ChatRequest, ConversationRecord, StreamEvent, WidgetPayload
from app.repositories.conversations import (
    ConversationRepository,
    SqliteConversationRepository,
)
from app.services.model_limits import GeminiRateLimiter, estimate_tokens
from app.services.priority_google_model import PriorityGoogleModel

WEB_SEARCH_MAX_USES_PER_TURN = 2
WEB_FETCH_MAX_USES_PER_TURN = 3
WEB_FETCH_MAX_CONTENT_TOKENS = 4000
logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)
EXTERNAL_SEARCH_KEYWORDS = (
    "latest",
    "current",
    "today",
    "recent",
    "news",
)


def encode_sse(event: StreamEvent) -> str:
    payload = orjson.dumps(event.model_dump()).decode("utf-8")
    return f"data: {payload}\n\n"


@dataclass(slots=True)
class StreamEventSink:
    queue: asyncio.Queue[StreamEvent] = field(default_factory=asyncio.Queue)

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        await self.queue.put(StreamEvent(type=event_type, data=data))

    def drain_nowait(self) -> list[StreamEvent]:
        items: list[StreamEvent] = []
        while True:
            try:
                items.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                return items


@dataclass(slots=True)
class AgentDependencies:
    agent_id: str
    config: VisualAgentConfig
    conversation: ConversationRecord
    event_sink: StreamEventSink
    wants_visual: bool
    user_message: str
    from_widget: str | None
    last_visual_error: str | None = None


@dataclass(slots=True)
class VisualRecoveryResult:
    had_widget: bool
    history: Any
    events: list[StreamEvent] = field(default_factory=list)


class VisualWidgetDraft(BaseModel):
    title: str
    loading_messages: list[str]
    widget_code: str


class ChatService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        repository: ConversationRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or SqliteConversationRepository(self.settings.database_path)
        self._widget_payload_cache: OrderedDict[str, WidgetPayload] = OrderedDict()
        self._widget_payload_cache_max = 100
        self.agent_registry = AgentRegistry(self.settings)
        self.svg_library_service = SvgLibraryService(self.settings.svg_library_root)
        self.svg_vision_repair_service = SvgVisionRepairService(
            api_key=(
                self.settings.google_api_key.get_secret_value()
                if self.settings.google_api_key is not None
                else None
            ),
            model_name=self.settings.google_visual_recovery_model_name,
            service_tier=self.settings.google_service_tier,
            preview_renderer=ExternalSvgPreviewRenderer(
                command_override=self.settings.svg_preview_renderer_command,
                timeout_ms=self.settings.svg_preview_renderer_timeout_ms,
            ),
        )
        self.rate_limiter = GeminiRateLimiter(self.settings)
        self._agent_cache: dict[str, Agent[AgentDependencies, str]] = {}
        self._visual_agent_cache: dict[str, Agent[AgentDependencies, VisualWidgetDraft]] = {}
        self._context_agent_cache: dict[str, Agent[AgentDependencies, str]] = {}
        self._allowed_url_domains = self.settings.resolve_google_allowed_url_domains()
        self._google_builtin_tools = self._build_google_builtin_tools()

    @cached_property
    def provider(self) -> GoogleProvider:
        # PydanticAI GoogleProvider is backed by the official google-genai client for Gemini.
        return GoogleProvider(api_key=self.settings.require_google_api_key())

    def _google_model_settings(self, *, temperature: float) -> GoogleModelSettings:
        return cast(
            GoogleModelSettings,
            {
                "temperature": temperature,
                "max_tokens": self.settings.google_max_output_tokens,
                "google_thinking_config": self.settings.resolve_google_thinking_config(),
                "google_service_tier": self.settings.google_service_tier,
            },
        )

    @staticmethod
    def _cache_key(agent_id: str, model_name: str) -> str:
        return f"{agent_id}:{model_name}"

    def get_agent(self, agent_bundle: AgentPromptBundle, model_name: str) -> Agent[AgentDependencies, str]:
        cache_key = self._cache_key(agent_bundle.config.agent.id, model_name)
        cached_agent = self._agent_cache.get(cache_key)
        if cached_agent is not None:
            return cached_agent

        model = PriorityGoogleModel(
            model_name,
            provider=self.provider,
        )
        model_settings = self._google_model_settings(temperature=self.settings.google_temperature)
        built_agent = Agent[AgentDependencies, str](
            model,
            deps_type=AgentDependencies,
            instructions=agent_bundle.system_prompt,
            model_settings=model_settings,
            retries=2,
            output_retries=2,
        )

        @built_agent.instructions
        async def build_session_context(ctx: RunContext[AgentDependencies]) -> str:
            learner_profile = ctx.deps.conversation.learner_profile
            concepts_seen = ", ".join(learner_profile.concepts_seen) or "none"
            struggling_with = ", ".join(learner_profile.struggling_with) or "none"
            disallowed_hosts = self._extract_disallowed_url_hosts(ctx.deps.user_message)
            lines = [
                f"Conversation subject: {ctx.deps.conversation.subject or 'general'}.",
                f"Concepts already visualized: {concepts_seen}.",
                f"Struggling topics: {struggling_with}.",
                f"Interaction count: {learner_profile.interaction_count}.",
                f"Latest learner request: {ctx.deps.user_message}",
            ]
            if self.settings.google_enable_url_context:
                lines.append(
                    "If the learner asks what a link says, use the URL context tool for allowed domains. "
                    "If a URL domain is not allowed, explicitly say it is outside the allowlist and ask for "
                    "an allowlisted source or domain override."
                )
            if self.settings.google_enable_web_search:
                lines.append(
                    "Use web search for up-to-date context when needed, but prioritize URL context for direct "
                    "link-explainer requests."
                )
            if disallowed_hosts:
                lines.append(
                    "Non-allowlisted URL host(s) detected in this request: "
                    f"{', '.join(disallowed_hosts)}. Do not claim to have read those links."
                )
            if ctx.deps.from_widget:
                lines.append(
                    f"The learner is following up from the '{ctx.deps.from_widget}' visual; "
                    "treat their message in that context."
                )
            if ctx.deps.wants_visual:
                lines.append(
                    "The learner explicitly requested a visual. You must call "
                    "show_widget at least once before finishing unless it is impossible."
                )
            return "\n".join(lines)

        @built_agent.tool
        async def show_widget(
            ctx: RunContext[AgentDependencies],
            title: str,
            loading_messages: list[str],
            widget_code: str,
        ) -> str:
            try:
                cache_key = hashlib.sha256(
                    f"{title}\0{widget_code}".encode("utf-8", errors="replace")
                ).hexdigest()
                payload: WidgetPayload | None = None
                if self.settings.enable_widget_cache:
                    cached = self._widget_payload_cache.get(cache_key)
                    if cached is not None:
                        self._widget_payload_cache.move_to_end(cache_key)
                        payload = cached
                if payload is None:
                    if ctx.deps.agent_id == "svg":
                        payload = build_template_instance_widget_payload(
                            title=title,
                            loading_messages=loading_messages,
                            widget_code=widget_code,
                            tool_config=ctx.deps.config.agent.tool,
                        )
                    else:
                        payload = build_widget_payload(
                            title=title,
                            loading_messages=loading_messages,
                            widget_code=widget_code,
                            tool_config=ctx.deps.config.agent.tool,
                        )
                    if self.settings.enable_widget_cache:
                        self._widget_payload_cache[cache_key] = payload
                        self._widget_payload_cache.move_to_end(cache_key)
                        while len(self._widget_payload_cache) > self._widget_payload_cache_max:
                            self._widget_payload_cache.popitem(last=False)
            except ValidationAppError as exc:
                ctx.deps.last_visual_error = exc.message
                logger.warning(
                    "widget-validation-retry",
                    extra={
                        "extra_data": {
                            "conversation_id": ctx.deps.conversation.id,
                            "title": title,
                            "detail": exc.message,
                            "details": exc.details,
                        }
                    },
                )

                repaired_payload: WidgetPayload | None = None
                if (
                    ctx.deps.agent_id != "svg"
                    and exc.details.get("kind") == "visualizer_raw_svg"
                ):
                    try:
                        repaired_payload = await asyncio.to_thread(
                            self.svg_vision_repair_service.repair_raw_visualizer_svg,
                            error=exc,
                            tool_config=ctx.deps.config.agent.tool,
                        )
                    except Exception as repair_exc:  # pragma: no cover - defensive
                        logger.warning(
                            "visualizer-svg-repair-failed",
                            extra={
                                "extra_data": {
                                    "conversation_id": ctx.deps.conversation.id,
                                    "title": title,
                                    "detail": str(repair_exc),
                                }
                            },
                        )

                if repaired_payload is not None:
                    payload = repaired_payload
                    ctx.deps.last_visual_error = None
                    if self.settings.enable_widget_cache:
                        self._widget_payload_cache[cache_key] = payload
                        self._widget_payload_cache.move_to_end(cache_key)
                        while len(self._widget_payload_cache) > self._widget_payload_cache_max:
                            self._widget_payload_cache.popitem(last=False)
                else:
                    raise ModelRetry(
                        "show_widget validation failed: "
                        f"{exc.message} "
                        "Use snake_case titles, emit a raw SVG/HTML fragment only, and follow "
                        "the strict visual contracts (viewBox 680, style/content/script order, "
                        "no document wrappers/comments, text fits inside its rect, node rects "
                        "do not overlap)."
                    ) from exc

            ctx.deps.last_visual_error = None
            learner_profile = ctx.deps.conversation.learner_profile
            if payload.title not in learner_profile.concepts_seen:
                learner_profile.concepts_seen.append(payload.title)

            await ctx.deps.event_sink.emit(
                "widget_ready",
                {
                    "widget": payload.model_dump(),
                    "followUpChips": ctx.deps.config.agent.follow_up_chips.with_widget,
                },
            )
            return f"Rendered {payload.title}."

        self._agent_cache[cache_key] = built_agent
        return built_agent

    def _build_google_builtin_tools(self) -> list[object]:
        tools: list[object] = []
        if self.settings.google_enable_web_search:
            tools.append(WebSearchTool(max_uses=WEB_SEARCH_MAX_USES_PER_TURN))
        if self.settings.google_enable_url_context:
            tools.append(
                WebFetchTool(
                    max_uses=WEB_FETCH_MAX_USES_PER_TURN,
                    allowed_domains=self._allowed_url_domains or None,
                    enable_citations=True,
                    max_content_tokens=WEB_FETCH_MAX_CONTENT_TOKENS,
                )
            )
        return tools

    @staticmethod
    def _extract_urls(message: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for raw in URL_PATTERN.findall(message):
            cleaned = raw.rstrip(".,;:!?)]}\"")
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                urls.append(cleaned)
        return urls

    @staticmethod
    def _domain_matches_rule(host: str, rule: str) -> bool:
        normalized_host = host.strip().lower().rstrip(".")
        normalized_rule = rule.strip().lower().rstrip(".")
        if not normalized_host or not normalized_rule:
            return False
        if normalized_rule.startswith("*."):
            suffix = normalized_rule[2:]
            return normalized_host == suffix or normalized_host.endswith(f".{suffix}")
        return normalized_host == normalized_rule

    def _is_allowed_url_host(self, host: str) -> bool:
        return any(
            self._domain_matches_rule(host, domain_rule)
            for domain_rule in self._allowed_url_domains
        )

    def _extract_disallowed_url_hosts(self, message: str) -> list[str]:
        hosts: list[str] = []
        seen_hosts: set[str] = set()
        for url in self._extract_urls(message):
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                continue
            host = (parsed.hostname or "").strip().lower().rstrip(".")
            if not host or host in seen_hosts:
                continue
            if self._is_allowed_url_host(host):
                continue
            seen_hosts.add(host)
            hosts.append(host)
        return hosts

    def _should_fetch_external_context(self, message: str) -> bool:
        if not self._google_builtin_tools:
            return False
        if self.settings.google_enable_url_context and self._extract_urls(message):
            return True
        lowered = message.lower()
        return self.settings.google_enable_web_search and any(
            keyword in lowered for keyword in EXTERNAL_SEARCH_KEYWORDS
        )

    @staticmethod
    def _augment_prompt_with_external_context(user_message: str, context_block: str) -> str:
        return (
            f"{user_message}\n\n"
            "External context (use as supporting evidence, do not invent beyond it):\n"
            f"{context_block}"
        )

    def get_context_agent(
        self, agent_bundle: AgentPromptBundle, model_name: str
    ) -> Agent[AgentDependencies, str]:
        cache_key = self._cache_key(agent_bundle.config.agent.id, model_name)
        cached_agent = self._context_agent_cache.get(cache_key)
        if cached_agent is not None:
            return cached_agent

        model = PriorityGoogleModel(
            model_name,
            provider=self.provider,
        )
        model_settings = self._google_model_settings(temperature=0.1)
        built_agent = Agent[AgentDependencies, str](
            model,
            deps_type=AgentDependencies,
            instructions=(
                "Retrieve concise factual context using available built-in tools. "
                "For link requests, prioritize URL context. For freshness requests, use web search. "
                "If a URL is blocked by allowlist, state that clearly."
            ),
            model_settings=model_settings,
            builtin_tools=self._google_builtin_tools,
            retries=1,
            output_retries=1,
        )
        self._context_agent_cache[cache_key] = built_agent
        return built_agent

    async def _fetch_external_context(
        self,
        *,
        user_message: str,
        model_name: str,
        deps: AgentDependencies,
        message_history: Any,
    ) -> str | None:
        if not self._should_fetch_external_context(user_message):
            return None

        agent_bundle = self.agent_registry.get(deps.agent_id)
        context_agent = self.get_context_agent(agent_bundle, model_name)
        prompt = (
            "Gather external context for the learner request. "
            "Return concise bullet points with citations/domains where possible. "
            "If any URL is blocked by allowlist, include that explicitly.\n\n"
            f"Learner request:\n{user_message}"
        )
        try:
            result = await context_agent.run(
                prompt,
                deps=deps,
                message_history=message_history,
            )
        except Exception:
            logger.warning(
                "external-context-fetch-failed",
                extra={
                    "extra_data": {
                        "conversation_id": deps.conversation.id,
                        "model": model_name,
                    }
                },
                exc_info=True,
            )
            return None

        context_text = (result.output or "").strip()
        if not context_text:
            return None
        return context_text[:6000]

    def get_visual_agent(
        self, agent_bundle: AgentPromptBundle, model_name: str
    ) -> Agent[AgentDependencies, VisualWidgetDraft]:
        cache_key = self._cache_key(agent_bundle.config.agent.id, model_name)
        cached_agent = self._visual_agent_cache.get(cache_key)
        if cached_agent is not None:
            return cached_agent

        model = PriorityGoogleModel(
            model_name,
            provider=self.provider,
        )
        model_settings = self._google_model_settings(temperature=0.1)
        built_agent = Agent[AgentDependencies, VisualWidgetDraft](
            model,
            output_type=VisualWidgetDraft,
            deps_type=AgentDependencies,
            instructions=agent_bundle.visual_generation_prompt,
            model_settings=model_settings,
            retries=2,
            output_retries=2,
        )

        @built_agent.instructions
        async def build_visual_context(ctx: RunContext[AgentDependencies]) -> str:
            learner_profile = ctx.deps.conversation.learner_profile
            concepts_seen = ", ".join(learner_profile.concepts_seen[-6:]) or "none"
            lines = [
                f"Conversation subject: {ctx.deps.conversation.subject or 'general'}.",
                f"Concepts already visualized: {concepts_seen}.",
                f"Latest learner request: {ctx.deps.user_message}",
            ]
            if ctx.deps.from_widget:
                lines.append(
                    f"Follow-up concerns widget '{ctx.deps.from_widget}' — align the visual with that."
                )
            lines.extend(
                [
                    "Produce exactly one high-quality visual payload.",
                    "Prefer SVG unless interactivity materially improves understanding.",
                    "For Dense vs MoE style comparison prompts, use a side-by-side comparison SVG.",
                ]
            )
            return "\n".join(lines)

        self._visual_agent_cache[cache_key] = built_agent
        return built_agent

    async def stream_chat(self, request: ChatRequest, *, client_id: str) -> AsyncIterator[str]:
        yield encode_sse(
            StreamEvent(
                type="status",
                data={
                    "stage": "received",
                    "label": "Request received",
                    "detail": "Validating your message and loading conversation state.",
                    "state": "active",
                },
            )
        )
        try:
            if request.conversation_id is not None:
                conversation = await self.repository.get(request.conversation_id)
                if conversation is None:
                    raise NotFoundAppError("Conversation", request.conversation_id)
            else:
                conversation = await self.repository.create_new()
            active_agent_bundle = self.agent_registry.get(request.agent_id)
            self._prepare_conversation(conversation, request, agent_id=active_agent_bundle.config.agent.id)

            yield encode_sse(
                StreamEvent(
                    type="status",
                    data={
                        "stage": "budgeting",
                        "label": "Budgeting tokens",
                        "detail": (
                            "Checking Gemini request "
                            "limits and trimming history if needed."
                        ),
                        "state": "active",
                    },
                )
            )

            history = self._load_history_with_budget(conversation)
            event_sink = StreamEventSink()
            wants_visual = self._request_needs_visual(request.message)
            active_model_name = self._resolve_primary_model_name(
                request.model,
                agent_config=active_agent_bundle.config,
            )
            deps = AgentDependencies(
                agent_id=active_agent_bundle.config.agent.id,
                config=active_agent_bundle.config,
                conversation=conversation,
                event_sink=event_sink,
                wants_visual=wants_visual,
                user_message=request.message,
                from_widget=request.from_widget,
            )
            prompt_for_model = request.message
            if self._should_fetch_external_context(request.message):
                yield encode_sse(
                    StreamEvent(
                        type="status",
                        data={
                            "stage": "gathering_context",
                            "label": "Gathering external context",
                            "detail": "Collecting source context from links/web before drafting.",
                            "state": "active",
                        },
                    )
                )
                external_context = await self._fetch_external_context(
                    user_message=request.message,
                    model_name=active_model_name,
                    deps=deps,
                    message_history=history,
                )
                if external_context is not None:
                    prompt_for_model = self._augment_prompt_with_external_context(
                        request.message,
                        external_context,
                    )

            estimated_input_tokens = self._estimate_request_tokens(
                prompt_for_model,
                history,
                agent_bundle=active_agent_bundle,
            )
            self.rate_limiter.check_and_reserve(estimated_input_tokens, client_id=client_id)

            yield encode_sse(
                StreamEvent(
                    type="conversation",
                    data={
                        "conversationId": conversation.id,
                        "subject": conversation.subject,
                    },
                )
            )

            text_started = False
            assistant_started_emitted = False
            had_widget = False

            yield encode_sse(
                StreamEvent(
                    type="status",
                    data={
                        "stage": "connecting_model",
                        "label": "Connecting to Gemini",
                        "detail": (
                            "Preparing the PydanticAI agent and sending the "
                            "request to Google Gen AI."
                        ),
                        "state": "active",
                    },
                )
            )
            stream_fallback_model = self._resolve_stream_fallback_model_name(active_model_name)
            logger.info(
                "chat-model-primary",
                extra={
                    "extra_data": {
                        "conversation_id": conversation.id,
                        "primary_model": active_model_name,
                        "fallback_model": stream_fallback_model,
                        "wants_visual": wants_visual,
                    }
                },
            )
            yielded_stream_content = False
            final_history = history
            saw_final_result = False
            partial_completion_reason: str | None = None
            yield encode_sse(
                StreamEvent(
                    type="status",
                    data={
                        "stage": "model_selected",
                        "label": "Model selected",
                        "detail": f"Using {active_model_name} for this turn.",
                        "state": "active",
                    },
                )
            )

            try:
                async for event in self._run_stream_events_with_retries(
                    prompt=prompt_for_model,
                    model_name=active_model_name,
                    deps=deps,
                    message_history=history,
                ):
                    if isinstance(event, PartStartEvent):
                        part = event.part
                        part_kind = getattr(part, "part_kind", None)

                        if part_kind == "thinking":
                            content = getattr(part, "content", "")

                            # Signal thinking started to clear "Queued" state
                            if not assistant_started_emitted:
                                yield encode_sse(
                                    StreamEvent(
                                        type="status",
                                        data={
                                            "stage": "streaming_answer",
                                            "label": "Thinking",
                                            "detail": "The model is analyzing your request.",
                                            "state": "active",
                                        },
                                    )
                                )
                                yield encode_sse(StreamEvent(type="assistant_started"))
                                assistant_started_emitted = True

                            if content:
                                yield encode_sse(
                                    StreamEvent(type="thinking_delta", data={"text": content})
                                )
                            continue

                        if part_kind == "tool-call":
                            tool_name = getattr(part, "tool_name", None)
                            if tool_name == "show_widget":
                                yielded_stream_content = True
                                tool_call_id = getattr(part, "tool_call_id", None)
                                yield encode_sse(
                                    StreamEvent(
                                        type="widget_loading",
                                        data={
                                            "toolCallId": tool_call_id,
                                            "loadingMessages": ["Building the visualization…"],
                                        },
                                    )
                                )
                                yield encode_sse(
                                    StreamEvent(
                                        type="status",
                                        data={
                                            "stage": "rendering_visual",
                                            "label": "Rendering visual",
                                            "detail": (
                                                "The agent asked for a visual and is "
                                                "generating the widget code."
                                            ),
                                            "state": "active",
                                        },
                                    )
                                )
                            continue

                        # Treat text and other kinds as the start of standard stream content
                        if not text_started:
                            text_started = True
                            yielded_stream_content = True
                            yield encode_sse(
                                StreamEvent(
                                    type="status",
                                    data={
                                        "stage": "streaming_answer",
                                        "label": "Streaming answer",
                                        "detail": "The model is now writing the explanation.",
                                        "state": "active",
                                    },
                                )
                            )
                            if not assistant_started_emitted:
                                yield encode_sse(StreamEvent(type="assistant_started"))
                                assistant_started_emitted = True

                        part_content = getattr(part, "content", "")
                        if part_content:
                            yielded_stream_content = True
                            yield encode_sse(StreamEvent(type="text_delta", data={"text": part_content}))

                    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                        if not event.delta.content_delta:
                            continue
                        if not text_started:
                            text_started = True
                            yielded_stream_content = True
                            yield encode_sse(
                                StreamEvent(
                                    type="status",
                                    data={
                                        "stage": "streaming_answer",
                                        "label": "Streaming answer",
                                        "detail": "The model is now writing the explanation.",
                                        "state": "active",
                                    },
                                )
                            )
                            if not assistant_started_emitted:
                                yield encode_sse(StreamEvent(type="assistant_started"))
                                assistant_started_emitted = True
                        yield encode_sse(
                            StreamEvent(type="text_delta", data={"text": event.delta.content_delta})
                        )

                    if isinstance(event, PartDeltaEvent) and isinstance(
                        event.delta, ThinkingPartDelta
                    ):
                        if event.delta.content_delta:
                            if not assistant_started_emitted:
                                yield encode_sse(
                                    StreamEvent(
                                        type="status",
                                        data={
                                            "stage": "streaming_answer",
                                            "label": "Thinking",
                                            "detail": "The model is analyzing your request.",
                                            "state": "active",
                                        },
                                    )
                                )
                                yield encode_sse(StreamEvent(type="assistant_started"))
                                assistant_started_emitted = True

                            yield encode_sse(
                                StreamEvent(
                                    type="thinking_delta",
                                    data={"text": event.delta.content_delta},
                                )
                            )

                    if isinstance(event, FunctionToolCallEvent):
                        tool_name = getattr(event.part, "tool_name", None)
                        if tool_name == "show_widget":
                            yield encode_sse(
                                StreamEvent(
                                    type="status",
                                    data={
                                        "stage": "rendering_visual",
                                        "label": "Rendering visual",
                                        "detail": (
                                            "The agent finished generating the widget code and is "
                                            "validating the widget output."
                                        ),
                                        "state": "active",
                                    },
                                )
                            )

                    if isinstance(event, AgentRunResultEvent):
                        saw_final_result = True
                        yield encode_sse(
                            StreamEvent(
                                type="status",
                                data={
                                    "stage": "saving",
                                    "label": "Saving conversation",
                                    "detail": "Persisting the latest turn and follow-up actions.",
                                    "state": "active",
                                },
                            )
                        )
                        final_history = ModelMessagesTypeAdapter.validate_json(
                            event.result.all_messages_json()
                        )

                    for queued_event in event_sink.drain_nowait():
                        if queued_event.type == "widget_ready":
                            had_widget = True
                            yielded_stream_content = True
                            self._log_widget_ready_analytics(queued_event.data)
                        yield encode_sse(queued_event)
            except UnexpectedModelBehavior as exc:
                for queued_event in event_sink.drain_nowait():
                    if queued_event.type == "widget_ready":
                        had_widget = True
                        yielded_stream_content = True
                        self._log_widget_ready_analytics(queued_event.data)
                    yield encode_sse(queued_event)

                if had_widget:
                    partial_completion_reason = (
                        "The visual was produced successfully, but the model skipped its "
                        "closing sentence. Preserving the visual."
                    )
                    logger.warning(
                        "partial-agent-completion",
                        extra={
                            "extra_data": {
                                "reason": str(exc),
                                "conversation_id": conversation.id,
                            }
                        },
                    )
                elif wants_visual:
                    logger.warning(
                        "visual-turn-needs-recovery",
                        extra={
                            "extra_data": {
                                "reason": str(exc),
                                "conversation_id": conversation.id,
                            }
                        },
                    )
                else:
                    raise

            if wants_visual and not had_widget:
                recovery_result = await self._attempt_visual_recovery(
                    request=request,
                    model_name=active_model_name,
                    deps=deps,
                    message_history=final_history,
                    client_id=client_id,
                )
                had_widget = had_widget or recovery_result.had_widget
                final_history = recovery_result.history
                for recovery_event in recovery_result.events:
                    if recovery_event.type == "widget_ready":
                        self._log_widget_ready_analytics(recovery_event.data)
                    yield encode_sse(recovery_event)

            conversation.turn_count += 1
            if final_history is not None:
                conversation.message_history_json = ModelMessagesTypeAdapter.dump_json(
                    final_history
                ).decode("utf-8")
            await self.repository.save(conversation)

            visual_missing = wants_visual and not had_widget and yielded_stream_content
            if visual_missing:
                yield encode_sse(
                    StreamEvent(
                        type="status",
                        data={
                            "stage": "visual_missed",
                            "label": "Visual not produced",
                            "detail": (
                                "The model answered, but it did not successfully produce "
                                "a compliant visual for this turn."
                            ),
                            "state": "error",
                        },
                    )
                )
                yield encode_sse(
                    StreamEvent(
                        type="error",
                        data={
                            "title": "VISUAL_NOT_PRODUCED",
                            "detail": (
                                "The model did not produce a valid visual for this turn. "
                                "Try a shorter prompt or ask for a simpler visual."
                            ),
                        },
                    )
                )
            if (saw_final_result or had_widget or text_started) and not visual_missing:
                yield encode_sse(
                    StreamEvent(
                        type="assistant_done",
                        data={
                            "followUpChips": self._follow_up_chips(
                                had_widget,
                                active_agent_bundle.config,
                            ),
                        },
                    )
                )
            if partial_completion_reason is not None and not visual_missing:
                yield encode_sse(
                    StreamEvent(
                        type="status",
                        data={
                            "stage": "completed_with_partial_finalize",
                            "label": "Completed",
                            "detail": partial_completion_reason,
                            "state": "completed",
                        },
                    )
                )
            if not visual_missing:
                yield encode_sse(
                    StreamEvent(
                        type="status",
                        data={
                            "stage": "completed",
                            "label": "Completed",
                            "detail": "The answer is ready.",
                            "state": "completed",
                        },
                    )
                )
            yield encode_sse(StreamEvent(type="done"))
        except AppError as exc:
            yield encode_sse(
                StreamEvent(
                    type="status",
                    data={
                        "stage": "failed",
                        "label": "Needs attention",
                        "detail": exc.message,
                        "state": "error",
                    },
                )
            )
            logger.warning(
                "app-error",
                extra={"extra_data": exc.to_dict()},
            )
            yield encode_sse(StreamEvent(type="error", data=exc.to_dict()))
        except Exception as exc:
            yield encode_sse(
                StreamEvent(
                    type="status",
                    data={
                        "stage": "failed",
                        "label": "Unexpected failure",
                        "detail": str(exc),
                        "state": "error",
                    },
                )
            )
            logger.exception("chat-stream-failed")
            yield encode_sse(
                StreamEvent(
                    type="error",
                    data={
                        "title": "INTERNAL_ERROR",
                        "detail": str(exc),
                    },
                )
            )

    def _prepare_conversation(
        self,
        conversation: ConversationRecord,
        request: ChatRequest,
        *,
        agent_id: str,
    ) -> None:
        if len(request.message) > self.settings.max_message_chars:
            raise ValidationAppError("Message exceeds the allowed size.")
        if conversation.turn_count >= self.settings.max_conversation_turns:
            raise ValidationAppError("Conversation reached the maximum configured number of turns.")

        conversation.subject = request.subject or conversation.subject
        conversation.agent_id = agent_id
        conversation.learner_profile.interaction_count += 1
        if self.settings.enable_learner_profiles and request.learner_profile is not None:
            conversation.learner_profile = request.learner_profile

        lowered_message = request.message.lower()
        if any(
            phrase in lowered_message
            for phrase in ("i still don't get", "i dont get", "confused", "not understanding")
        ):
            conversation.learner_profile.struggling_with.append(request.message[:80])

    def _follow_up_chips(self, had_widget: bool, agent_config: VisualAgentConfig) -> list[str]:
        if had_widget:
            return agent_config.agent.follow_up_chips.with_widget
        return agent_config.agent.follow_up_chips.without_widget

    @staticmethod
    def _log_widget_ready_analytics(data: dict[str, Any]) -> None:
        widget = data.get("widget")
        title = widget.get("title") if isinstance(widget, dict) else None
        if title:
            logger.info(
                "widget_analytics",
                extra={"extra_data": {"event": "widget_rendered", "title": title}},
            )

    def _load_history_with_budget(self, conversation: ConversationRecord) -> Any:
        if conversation.message_history_json is None:
            return None

        history = ModelMessagesTypeAdapter.validate_json(conversation.message_history_json)
        while (
            history
            and self._estimate_history_tokens(history)
            > self.settings.google_max_history_tokens
        ):
            history = history[2:]
        return history or None

    def _estimate_history_tokens(self, history: Any) -> int:
        history_json = ModelMessagesTypeAdapter.dump_json(history).decode("utf-8")
        return estimate_tokens(history_json)

    def _estimate_request_tokens(
        self,
        message: str,
        history: Any,
        *,
        agent_bundle: AgentPromptBundle,
    ) -> int:
        history_tokens = 0 if history is None else self._estimate_history_tokens(history)
        system_prompt_tokens = estimate_tokens(agent_bundle.system_prompt)
        return history_tokens + system_prompt_tokens + estimate_tokens(message)

    def _resolve_primary_model_name(
        self,
        requested_model: str | None = None,
        *,
        agent_config: VisualAgentConfig,
    ) -> str:
        configured_model = requested_model or agent_config.agent.model
        return self.settings.resolve_google_model_name(configured_model)

    def _resolve_recovery_models(self, primary_model_name: str) -> list[str]:
        fallback_model_name = self.settings.resolve_google_visual_recovery_model_name(primary_model_name)
        if fallback_model_name is None:
            return [primary_model_name]
        return [fallback_model_name, primary_model_name]

    def _resolve_stream_fallback_model_name(self, primary_model_name: str) -> str | None:
        # Prefer the normal chat fallback model; if that is unset/same as primary, fall back
        # to the stronger visual recovery model so 5xx spikes still have a backup path.
        fallback_model_name = self.settings.resolve_google_fallback_model_name(primary_model_name)
        if fallback_model_name is not None:
            return fallback_model_name
        return self.settings.resolve_google_visual_recovery_model_name(primary_model_name)

    def _request_needs_visual(self, message: str) -> bool:
        lowered_message = message.lower()
        triggers = (
            "visual",
            "visually",
            "diagram",
            "draw",
            "show me",
            "compare",
            "architecture",
            "flow",
            "chart",
            "interactive",
            "interactivity",
            "animate",
            "simulation",
            "explore",
        )
        return any(trigger in lowered_message for trigger in triggers)

    async def _attempt_visual_recovery(
        self,
        *,
        request: ChatRequest,
        model_name: str,
        deps: AgentDependencies,
        message_history: Any,
        client_id: str,
    ) -> VisualRecoveryResult:
        recovery_prompt = (
            "You must recover the missed visual from the previous turn. "
            "Call show_widget exactly once. "
            "Do not explain in prose. "
            "Generate one learner-friendly visual that directly answers this request: "
            f"{request.message}"
        )

        estimated_recovery_tokens = self._estimate_request_tokens(
            recovery_prompt,
            message_history,
            agent_bundle=self.agent_registry.get(deps.agent_id),
        )
        self.rate_limiter.check_and_reserve(estimated_recovery_tokens, client_id=client_id)

        had_widget = False
        recovery_history = message_history
        events = [
            StreamEvent(
                type="status",
                data={
                    "stage": "recovering_visual",
                    "label": "Recovering visual",
                    "detail": (
                        "The model answered without a widget. Running a visual-only "
                        "recovery pass."
                    ),
                    "state": "active",
                },
            )
        ]

        candidate_models = self._resolve_recovery_models(model_name)
        fallback_visual_model = candidate_models[-1]

        for candidate_index, candidate_model in enumerate(candidate_models):
            if candidate_index > 0:
                events.append(
                    StreamEvent(
                        type="status",
                        data={
                            "stage": "recovery_model_switch",
                            "label": "Switching model",
                            "detail": (
                                "The previous recovery attempt did not produce a widget. "
                                f"Trying {candidate_model}."
                            ),
                            "state": "active",
                        },
                    )
                )
            try:
                async for event in self._run_stream_events_with_retries(
                    prompt=recovery_prompt,
                    model_name=candidate_model,
                    deps=deps,
                    message_history=message_history,
                ):
                    if isinstance(event, PartStartEvent):
                        part = event.part
                        if getattr(part, "part_kind", None) == "tool-call":
                            tool_name = getattr(part, "tool_name", None)
                            if tool_name == "show_widget":
                                events.append(
                                    StreamEvent(
                                        type="status",
                                        data={
                                            "stage": "rendering_visual",
                                            "label": "Rendering visual",
                                            "detail": (
                                                "The recovery pass is generating the visual."
                                            ),
                                            "state": "active",
                                        },
                                    )
                                )
                                events.append(
                                    StreamEvent(
                                        type="widget_loading",
                                        data={
                                            "toolCallId": getattr(
                                                part,
                                                "tool_call_id",
                                                None,
                                            ),
                                            "loadingMessages": ["Recovering the visual…"],
                                        },
                                    )
                                )

                    if isinstance(event, FunctionToolCallEvent):
                        tool_name = getattr(event.part, "tool_name", None)
                        if tool_name == "show_widget":
                            events.append(
                                StreamEvent(
                                    type="status",
                                    data={
                                        "stage": "rendering_visual",
                                        "label": "Rendering visual",
                                        "detail": (
                                            "The recovery pass finished generating the widget code and is validating."
                                        ),
                                        "state": "active",
                                    },
                                )
                            )

                    if isinstance(event, AgentRunResultEvent):
                        recovery_history = ModelMessagesTypeAdapter.validate_json(
                            event.result.all_messages_json()
                        )

                    for queued_event in deps.event_sink.drain_nowait():
                        if queued_event.type == "widget_ready":
                            had_widget = True
                        events.append(queued_event)

                if had_widget:
                    break
                logger.warning(
                    "recovery-model-no-widget",
                    extra={
                        "extra_data": {
                            "conversation_id": deps.conversation.id,
                            "model": candidate_model,
                        }
                    },
                )
            except UnexpectedModelBehavior:
                if candidate_model == candidate_models[-1]:
                    events.append(
                        StreamEvent(
                            type="status",
                            data={
                                "stage": "visual_recovery_failed",
                                "label": "Visual recovery failed",
                                "detail": (
                                    "The model did not produce a valid widget during the "
                                    "recovery pass."
                                ),
                                "state": "error",
                            },
                        )
                    )
                continue
            except (RateLimitAppError, ServiceUnavailableAppError) as exc:
                fallback_visual_model = candidate_models[min(candidate_index + 1, len(candidate_models) - 1)]
                logger.warning(
                    "recovery-model-error",
                    extra={
                        "extra_data": {
                            "conversation_id": deps.conversation.id,
                            "model": candidate_model,
                            "detail": exc.message,
                            "status_code": exc.status_code,
                        }
                    },
                )
                if candidate_model == candidate_models[-1]:
                    events.append(
                        StreamEvent(
                            type="status",
                            data={
                                "stage": "visual_recovery_failed",
                                "label": "Visual recovery failed",
                                "detail": exc.message,
                                "state": "error",
                            },
                        )
                    )
                continue

        if not had_widget:
            fallback_events = await self._generate_visual_without_tool(
                request=request,
                model_name=fallback_visual_model,
                deps=deps,
                client_id=client_id,
            )
            if any(event.type == "widget_ready" for event in fallback_events):
                had_widget = True
            events.extend(fallback_events)

        return VisualRecoveryResult(
            had_widget=had_widget,
            history=recovery_history,
            events=events,
        )

    async def _generate_visual_without_tool(
        self,
        *,
        request: ChatRequest,
        model_name: str,
        deps: AgentDependencies,
        client_id: str,
    ) -> list[StreamEvent]:
        agent_bundle = self.agent_registry.get(deps.agent_id)
        estimated_tokens = estimate_tokens(request.message) + estimate_tokens(
            agent_bundle.visual_generation_prompt
        )
        self.rate_limiter.check_and_reserve(estimated_tokens, client_id=client_id)

        events = [
            StreamEvent(
                type="status",
                data={
                    "stage": "fallback_visual_generation",
                    "label": "Generating fallback visual",
                    "detail": (
                        "The model skipped the tool call, so a dedicated visual generator "
                        "is producing a renderable widget."
                    ),
                    "state": "active",
                },
            ),
            StreamEvent(
                type="widget_loading",
                data={
                    "toolCallId": f"fallback-{deps.conversation.id}",
                    "loadingMessages": ["Building a fallback visual…"],
                },
            ),
        ]

        try:
            if deps.agent_id == "svg":
                try:
                    library_result = self.svg_library_service.build_widget_for_request(
                        request_message=request.message,
                        tool_config=deps.config.agent.tool,
                    )
                except ValidationAppError as exc:
                    repaired_widget = await asyncio.to_thread(
                        self.svg_vision_repair_service.repair_from_validation_error,
                        error=exc,
                        tool_config=deps.config.agent.tool,
                    )
                    if repaired_widget is None:
                        raise

                    learner_profile = deps.conversation.learner_profile
                    if repaired_widget.title not in learner_profile.concepts_seen:
                        learner_profile.concepts_seen.append(repaired_widget.title)
                    events.append(
                        StreamEvent(
                            type="status",
                            data={
                                "stage": "svg_vision_repair",
                                "label": "Repairing with Gemini",
                                "detail": (
                                    "Static SVG validation was not enough, so a second repair pass used "
                                    "the current SVG plus violation details."
                                ),
                                "state": "completed",
                            },
                        )
                    )
                    events.append(
                        StreamEvent(
                            type="widget_ready",
                            data={
                                "widget": repaired_widget.model_dump(),
                                "followUpChips": deps.config.agent.follow_up_chips.with_widget,
                            },
                        )
                    )
                    return events

                learner_profile = deps.conversation.learner_profile
                if library_result.widget.title not in learner_profile.concepts_seen:
                    learner_profile.concepts_seen.append(library_result.widget.title)
                events.append(
                    StreamEvent(
                        type="status",
                        data={
                            "stage": "svg_template_selected",
                            "label": "Selected SVG template",
                            "detail": (
                                f"Using {library_result.template.relative_path} and validating the cloned "
                                "instance against the source structure."
                            ),
                            "state": "completed",
                        },
                    )
                )
                events.append(
                    StreamEvent(
                        type="widget_ready",
                        data={
                            "widget": library_result.widget.model_dump(),
                            "followUpChips": deps.config.agent.follow_up_chips.with_widget,
                        },
                    )
                )
                return events

            agent = self.get_visual_agent(agent_bundle, model_name)
            result = await agent.run(
                (
                    "Generate one widget payload for this learner request. "
                    "Return only the structured widget fields.\n\n"
                    f"Learner request: {request.message}"
                ),
                deps=deps,
            )
            try:
                payload = build_widget_payload(
                    title=result.output.title,
                    loading_messages=result.output.loading_messages,
                    widget_code=result.output.widget_code,
                    tool_config=deps.config.agent.tool,
                )
            except ValidationAppError as exc:
                if exc.details.get("kind") != "visualizer_raw_svg":
                    raise
                repaired = await asyncio.to_thread(
                    self.svg_vision_repair_service.repair_raw_visualizer_svg,
                    error=exc,
                    tool_config=deps.config.agent.tool,
                )
                if repaired is None:
                    raise
                payload = repaired
                events.append(
                    StreamEvent(
                        type="status",
                        data={
                            "stage": "svg_vision_repair",
                            "label": "Repairing with Gemini",
                            "detail": (
                                "Static geometric validation found text-fit or overlap "
                                "issues, so a repair pass used the failing SVG plus "
                                "violation details."
                            ),
                            "state": "completed",
                        },
                    )
                )
            learner_profile = deps.conversation.learner_profile
            if payload.title not in learner_profile.concepts_seen:
                learner_profile.concepts_seen.append(payload.title)
            events.append(
                StreamEvent(
                    type="widget_ready",
                    data={
                        "widget": payload.model_dump(),
                        "followUpChips": deps.config.agent.follow_up_chips.with_widget,
                    },
                )
            )
            return events
        except Exception as exc:
            deps.last_visual_error = str(exc)
            logger.warning(
                "fallback-visual-generation-failed",
                extra={
                    "extra_data": {
                        "conversation_id": deps.conversation.id,
                        "model": model_name,
                        "detail": str(exc),
                    }
                },
            )
            events.append(
                StreamEvent(
                    type="status",
                    data={
                        "stage": "fallback_visual_failed",
                        "label": "Fallback visual failed",
                        "detail": (
                            "The dedicated visual generator also failed to produce a valid widget."
                        ),
                        "state": "error",
                    },
                )
            )
            return events

    async def _run_stream_events_with_retries(
        self,
        prompt: str,
        *,
        model_name: str,
        deps: AgentDependencies,
        message_history: Any,
    ) -> AsyncIterator[Any]:
        fallback_model_name = self._resolve_stream_fallback_model_name(model_name)
        candidate_models = [model_name]
        if (
            fallback_model_name
            and fallback_model_name != model_name
            and fallback_model_name not in candidate_models
        ):
            candidate_models.append(fallback_model_name)

        last_error: Exception | None = None

        for candidate_index, candidate_model in enumerate(candidate_models):
            for attempt in range(self.settings.google_retry_attempts + 1):
                try:
                    if attempt == 0 and candidate_index > 0:
                        await deps.event_sink.emit(
                            "status",
                            {
                                "stage": "fallback_active",
                                "label": "Using fallback model",
                                "detail": f"Continuing with {candidate_model}.",
                                "state": "active",
                            },
                        )
                    logger.info(
                        "model-attempt-start",
                        extra={
                            "extra_data": {
                                "conversation_id": deps.conversation.id,
                                "model": candidate_model,
                                "attempt": attempt + 1,
                                "max_attempts": self.settings.google_retry_attempts + 1,
                            }
                        },
                    )
                    agent = self.get_agent(self.agent_registry.get(deps.agent_id), candidate_model)
                    async for event in agent.run_stream_events(
                        prompt,
                        deps=deps,
                        message_history=message_history,
                    ):
                        yield event
                    return
                except Exception as exc:
                    if not self._is_transient_model_failure(exc):
                        raise

                    last_error = exc
                    is_rate_limited = self._is_rate_limited_model_failure(exc)
                    retry_after_seconds = (
                        self._extract_retry_after_seconds(exc) if is_rate_limited else None
                    )
                    has_more_attempts = attempt < self.settings.google_retry_attempts
                    # Gemini quota/rate-limit responses usually won't improve with immediate retries.
                    if is_rate_limited:
                        has_more_attempts = False
                    has_fallback = candidate_index < len(candidate_models) - 1
                    status_code = getattr(exc, "status_code", None)
                    logger.warning(
                        "model-transient-error",
                        extra={
                            "extra_data": {
                                "conversation_id": deps.conversation.id,
                                "model": candidate_model,
                                "attempt": attempt + 1,
                                "status_code": status_code,
                                "has_more_attempts": has_more_attempts,
                                "has_fallback": has_fallback,
                                "retry_after_seconds": retry_after_seconds,
                            }
                        },
                    )

                    if has_more_attempts:
                        await deps.event_sink.emit(
                            "status",
                            {
                                "stage": "retrying_model",
                                "label": "Retrying model",
                                "detail": (
                                    f"{candidate_model} returned a transient server error. "
                                    f"Retry {attempt + 1} of {self.settings.google_retry_attempts}."
                                ),
                                "state": "active",
                            },
                        )
                        await asyncio.sleep(self.settings.google_retry_backoff_ms / 1000)
                        continue

                    if has_fallback:
                        switch_reason = (
                            "rate limit"
                            if is_rate_limited
                            else "transient server error"
                        )
                        retry_note = (
                            f" Retry after ~{retry_after_seconds}s."
                            if retry_after_seconds is not None
                            else ""
                        )
                        await deps.event_sink.emit(
                            "status",
                            {
                                "stage": "fallback_model",
                                "label": "Switching model",
                                "detail": (
                                    f"{candidate_model} hit a {switch_reason}. "
                                    f"Switching to {candidate_models[candidate_index + 1]}."
                                    f"{retry_note}"
                                ),
                                "state": "active",
                            },
                        )
                        break

                    if is_rate_limited:
                        raise RateLimitAppError(retry_after_seconds or 60) from exc

                    raise ServiceUnavailableAppError(
                        "Gemini returned a transient server error while generating this "
                        "answer. Please retry the request."
                    ) from exc

        if last_error is not None and self._is_rate_limited_model_failure(last_error):
            raise RateLimitAppError(self._extract_retry_after_seconds(last_error)) from last_error

        raise ServiceUnavailableAppError(
            "Gemini returned a transient server error while generating this answer. "
            "Please retry the request."
        ) from last_error

    def _is_transient_model_failure(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if isinstance(exc, ModelHTTPError):
            return status_code in {429, 500, 502, 503, 504}
        return status_code in {429, 500, 502, 503, 504}

    @staticmethod
    def _is_rate_limited_model_failure(exc: Exception) -> bool:
        return getattr(exc, "status_code", None) == 429

    def _extract_retry_after_seconds(self, exc: Exception) -> int:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error_obj = body.get("error")
            if isinstance(error_obj, dict):
                details = error_obj.get("details")
                if isinstance(details, list):
                    for detail in details:
                        if not isinstance(detail, dict):
                            continue
                        raw_retry = detail.get("retryDelay")
                        parsed = self._parse_retry_delay_seconds(raw_retry)
                        if parsed is not None:
                            return parsed
                parsed = self._parse_retry_delay_seconds(error_obj.get("message"))
                if parsed is not None:
                    return parsed

        parsed = self._parse_retry_delay_seconds(str(exc))
        if parsed is not None:
            return parsed
        return 60

    @staticmethod
    def _parse_retry_delay_seconds(value: object) -> int | None:
        if not isinstance(value, str):
            return None

        text = value.strip().lower()
        direct_match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", text)
        if direct_match:
            return max(1, int(float(direct_match.group(1))))

        retry_match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", text, re.IGNORECASE)
        if retry_match:
            return max(1, int(float(retry_match.group(1))))

        return None
