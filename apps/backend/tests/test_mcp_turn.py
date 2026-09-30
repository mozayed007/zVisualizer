"""Tests for reducing ChatService events into a typed visual turn."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.mcp.turn import run_visual_turn
from app.models.chat import ChatRequest, StreamEvent


class FakeChatService:
    def __init__(self, events: list[StreamEvent]) -> None:
        self._events = events

    async def stream_events(self, request: ChatRequest, *, client_id: str) -> AsyncIterator[StreamEvent]:
        del request, client_id
        for event in self._events:
            yield event


def _widget_event() -> StreamEvent:
    return StreamEvent(
        type="widget_ready",
        data={
            "widget": {
                "title": "moes_vs_dense",
                "loading_messages": ["Rendering"],
                "widget_code": "<svg></svg>",
                "kind": "svg",
            },
            "followUpChips": ["Zoom in", "Compare"],
        },
    )


async def test_run_visual_turn_collects_widget_text_and_chips() -> None:
    service = FakeChatService(
        [
            StreamEvent(type="status", data={"stage": "received", "label": "Request received"}),
            StreamEvent(type="conversation", data={"conversationId": "conv-1"}),
            StreamEvent(type="text_delta", data={"text": "Here is "}),
            StreamEvent(type="text_delta", data={"text": "the visual."}),
            StreamEvent(type="widget_loading", data={"loadingMessages": ["Rendering"]}),
            _widget_event(),
            StreamEvent(type="assistant_done", data={"followUpChips": ["Zoom in", "Compare"]}),
            StreamEvent(type="done"),
        ]
    )
    progress: list[str] = []

    async def on_progress(message: str) -> None:
        progress.append(message)

    turn = await run_visual_turn(
        service,  # type: ignore[arg-type]
        ChatRequest(message="draw me MoE routing"),
        client_id="test",
        on_progress=on_progress,
    )

    assert turn.status == "ok"
    assert turn.conversation_id == "conv-1"
    assert turn.title == "moes_vs_dense"
    assert turn.kind == "svg"
    assert turn.widget_code == "<svg></svg>"
    assert turn.assistant_text == "Here is the visual."
    assert turn.follow_up_chips == ["Zoom in", "Compare"]
    assert turn.error is None
    assert any("Visual ready" in message for message in progress)


async def test_run_visual_turn_reports_no_visual_without_hard_error() -> None:
    service = FakeChatService(
        [
            StreamEvent(type="conversation", data={"conversationId": "conv-2"}),
            StreamEvent(type="text_delta", data={"text": "Plain answer."}),
            StreamEvent(
                type="status",
                data={"stage": "visual_missed", "label": "Visual not produced", "state": "error"},
            ),
            StreamEvent(
                type="error",
                data={"title": "VISUAL_NOT_PRODUCED", "detail": "No compliant visual."},
            ),
            StreamEvent(type="done"),
        ]
    )
    turn = await run_visual_turn(
        service,  # type: ignore[arg-type]
        ChatRequest(message="draw me MoE routing"),
        client_id="test",
    )

    assert turn.status == "no_visual"
    assert turn.error is None
    assert turn.assistant_text == "Plain answer."
    assert turn.warnings


async def test_run_visual_turn_surfaces_hard_errors() -> None:
    service = FakeChatService(
        [
            StreamEvent(
                type="error",
                data={"title": "RATE_LIMITED", "detail": "Rate limit exceeded"},
            )
        ]
    )
    turn = await run_visual_turn(
        service,  # type: ignore[arg-type]
        ChatRequest(message="draw"),
        client_id="test",
    )

    assert turn.status == "no_visual"
    assert turn.error is not None
    assert turn.error.title == "RATE_LIMITED"


async def test_run_visual_turn_ignores_widget_event_without_code() -> None:
    service = FakeChatService([StreamEvent(type="widget_ready", data={"widget": {"title": "x", "kind": "svg"}})])
    turn = await run_visual_turn(
        service,  # type: ignore[arg-type]
        ChatRequest(message="draw"),
        client_id="test",
    )
    assert turn.status == "no_visual"
    assert turn.warnings
