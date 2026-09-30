"""Consume ChatService events into a typed visual turn result.

`ChatService.stream_events` yields typed `StreamEvent`s; this module is the only
place that knows how to reduce them into "what did this turn produce" for the
MCP surface. No SSE parsing, no Gemini calls in tests.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from app.models.chat import ChatRequest, StreamEvent
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]

_VISUAL_MISSED_TITLE = "VISUAL_NOT_PRODUCED"


@dataclass(slots=True)
class TurnError:
    title: str
    detail: str


@dataclass(slots=True)
class VisualTurn:
    status: Literal["ok", "no_visual"]
    conversation_id: str | None = None
    title: str | None = None
    kind: Literal["svg", "html"] | None = None
    widget_code: str | None = None
    loading_messages: list[str] = field(default_factory=list)
    assistant_text: str = ""
    follow_up_chips: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: TurnError | None = None


def _text_from_delta(event: StreamEvent) -> str:
    value = event.data.get("text")
    return value if isinstance(value, str) else ""


def _chips_from_data(data: dict[str, object]) -> list[str]:
    chips = data.get("followUpChips")
    if isinstance(chips, list):
        return [str(chip) for chip in chips]
    return []


async def run_visual_turn(
    chat_service: ChatService,
    request: ChatRequest,
    *,
    client_id: str,
    on_progress: ProgressCallback | None = None,
) -> VisualTurn:
    text_parts: list[str] = []
    turn = VisualTurn(status="no_visual")
    recovery_warning_added = False

    async for event in chat_service.stream_events(request, client_id=client_id):
        event_type = event.type

        if event_type == "conversation":
            conversation_id = event.data.get("conversationId")
            if isinstance(conversation_id, str) and conversation_id:
                turn.conversation_id = conversation_id

        elif event_type == "text_delta":
            text_parts.append(_text_from_delta(event))

        elif event_type == "widget_loading":
            if on_progress is not None:
                await on_progress("The agent is generating the visual code.")

        elif event_type == "widget_ready":
            widget = event.data.get("widget")
            if isinstance(widget, dict):
                turn.status = "ok"
                turn.title = str(widget.get("title") or "") or None
                kind = widget.get("kind")
                turn.kind = kind if kind in ("svg", "html") else None
                code = widget.get("widget_code")
                turn.widget_code = code if isinstance(code, str) else None
                messages = widget.get("loading_messages")
                if isinstance(messages, list):
                    turn.loading_messages = [str(message) for message in messages]
            chips = _chips_from_data(event.data)
            if chips:
                turn.follow_up_chips = chips
            if on_progress is not None and turn.title:
                await on_progress(f"Visual ready: {turn.title}")

        elif event_type == "assistant_done":
            chips = _chips_from_data(event.data)
            if chips:
                turn.follow_up_chips = chips

        elif event_type == "status":
            stage = str(event.data.get("stage") or "")
            label = str(event.data.get("label") or "")
            if stage == "visual_missed" and not recovery_warning_added:
                turn.warnings.append("The agent answered without producing a compliant visual for this turn.")
                recovery_warning_added = True
            if on_progress is not None and label and stage not in {"completed", "failed"}:
                await on_progress(label)

        elif event_type == "error":
            title = str(event.data.get("title") or "ERROR")
            detail = str(event.data.get("detail") or "")
            if title == _VISUAL_MISSED_TITLE:
                if not recovery_warning_added:
                    turn.warnings.append(detail or _VISUAL_MISSED_TITLE)
                    recovery_warning_added = True
            else:
                turn.error = TurnError(title=title, detail=detail)

    turn.assistant_text = "".join(text_parts).strip()
    if turn.status == "ok" and turn.widget_code is None:
        # Defensive: a widget_ready without usable code is a no-visual turn.
        turn.status = "no_visual"
        turn.warnings.append("The widget event payload was missing widget_code.")

    if turn.error is not None:
        logger.warning(
            "mcp-visual-turn-error",
            extra={
                "extra_data": {
                    "conversation_id": turn.conversation_id,
                    "title": turn.error.title,
                }
            },
        )

    return turn
