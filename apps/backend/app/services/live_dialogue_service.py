from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any

import orjson
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from google import genai
from google.genai import types
from websockets.exceptions import ConnectionClosed

from app.core.errors import AppError, NotFoundAppError
from app.core.settings import Settings, get_settings
from app.models.chat import ChatRequest, StreamEvent
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

INPUT_AUDIO_MIME_TYPE = "audio/pcm;rate=16000"
OUTPUT_AUDIO_MIME_TYPE = "audio/pcm;rate=24000"
MAX_TOOL_WIDGET_CODE_CHARS = 12_000
MAX_TOOL_TEXT_CHARS = 8_000


@dataclass(slots=True)
class LiveSessionState:
    client_id: str
    conversation_id: str | None
    selected_agent_id: str | None
    selected_model: str | None
    subject: str | None = None
    user_audio_turn_open: bool = False
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    background_job_task: asyncio.Task[None] | None = None
    pending_background_notification: str | None = None
    is_session_active: bool = True


class LiveDialogueService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        chat_service: ChatService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.chat_service = chat_service or ChatService(settings=self.settings)
        self.client = genai.Client(api_key=self.settings.require_google_api_key())

    async def handle_websocket(
        self,
        websocket: WebSocket,
        *,
        client_id: str,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        model: str | None = None,
        subject: str | None = None,
    ) -> None:
        state = LiveSessionState(
            client_id=client_id,
            conversation_id=conversation_id,
            selected_agent_id=agent_id or self.settings.default_agent_id,
            selected_model=model,
            subject=subject,
        )
        await websocket.accept()

        config = self._build_live_config(state)

        try:
            async with self.client.aio.live.connect(
                model=self.settings.resolve_google_live_model_name(),
                config=config,
            ) as session:
                await self._send_json(
                    websocket,
                    {
                        "type": "session.ready",
                        "liveModel": self.settings.resolve_google_live_model_name(),
                        "voice": self.settings.google_live_voice_name,
                        "inputAudioMimeType": INPUT_AUDIO_MIME_TYPE,
                        "outputAudioMimeType": OUTPUT_AUDIO_MIME_TYPE,
                        "selectedAgentId": state.selected_agent_id,
                        "selectedModel": state.selected_model,
                        "conversationId": state.conversation_id,
                    },
                )
                await self._send_state(
                    websocket,
                    status="idle",
                    detail="Voice session connected. Start speaking when ready.",
                )

                receive_task = asyncio.create_task(
                    self._forward_live_messages(session=session, websocket=websocket, state=state)
                )
                consume_task = asyncio.create_task(
                    self._consume_client_messages(
                        session=session,
                        websocket=websocket,
                        state=state,
                    )
                )
                try:
                    done, pending = await asyncio.wait(
                        {receive_task, consume_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        await task
                finally:
                    background_task = state.background_job_task
                    if background_task is not None and not background_task.done():
                        background_task.cancel()
                    for task in (receive_task, consume_task):
                        if not task.done():
                            task.cancel()
                    for task in (receive_task, consume_task):
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                    if background_task is not None:
                        with contextlib.suppress(asyncio.CancelledError):
                            await background_task
        except WebSocketDisconnect:
            logger.info("live-websocket-disconnected")
        except Exception:
            logger.exception("live-dialogue-session-failed")
            if websocket.client_state.name.lower() == "connected":
                await self._send_json(
                    websocket,
                    {
                        "type": "error",
                        "detail": "The realtime voice session ended unexpectedly.",
                    },
                )
            if websocket.client_state.name.lower() == "connected":
                with contextlib.suppress(RuntimeError):
                    await websocket.close(code=1011)

    def _build_live_config(self, state: LiveSessionState) -> types.LiveConnectConfig:
        agent_bundle = self.chat_service.agent_registry.get(state.selected_agent_id)
        agent_name = agent_bundle.config.agent.display_name or agent_bundle.config.agent.name
        language_code = self.settings.google_live_language_code
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=self.settings.google_live_voice_name
                )
            ),
            language_code=language_code,
        )
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self._build_system_instruction(agent_name=agent_name),
            speech_config=speech_config,
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
            temperature=0.6,
            max_output_tokens=self.settings.google_max_output_tokens,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            thinking_config=types.ThinkingConfig(
                include_thoughts=False,
                thinking_level=self.settings.google_live_thinking_level,
            ),
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name="delegate_to_agent",
                            description=(
                                "Start a background request in the existing visual chat agent on "
                                "the user's behalf when they ask for a visual explanation, diagram, "
                                "widget, SVG work, or something that should appear "
                                "in the chat canvas. Return immediately so the live conversation "
                                "can continue while the visual agent works."
                            ),
                            parameters_json_schema={
                                "type": "object",
                                "properties": {
                                    "request": {
                                        "type": "string",
                                        "description": (
                                            "A concise, self-contained version of what the user wants "
                                            "the backend chat agent to do."
                                        ),
                                    },
                                    "subject": {
                                        "type": "string",
                                        "description": "Optional subject label for the delegated turn.",
                                    },
                                    "from_widget": {
                                        "type": "string",
                                        "description": (
                                            "Snake_case widget title when the new request follows up "
                                            "from an existing rendered visual."
                                        ),
                                    },
                                    "agent_id": {
                                        "type": "string",
                                        "description": (
                                            "Optional backend agent id override, for example "
                                            "'visualizer' or 'svg'."
                                        ),
                                    },
                                },
                                "required": ["request"],
                            },
                        )
                    ]
                )
            ],
        )

    def _build_system_instruction(self, *, agent_name: str) -> str:
        return "\n".join(
            [
                "You are the realtime voice companion for a visual learning chat.",
                "Speak naturally, warmly, and concisely.",
                "Keep your replies brief while the user is talking live.",
                (
                    f"The currently selected backend visual agent is '{agent_name}'. "
                    "When the user asks to explain something visually, render a widget, "
                    "or edit/generate SVG content, call delegate_to_agent."
                ),
                (
                    "delegate_to_agent starts a background visual job. Do not wait silently for the "
                    "visualizer to finish; briefly tell the user the visual is being prepared while "
                    "the conversation can continue."
                ),
                (
                    "When you call delegate_to_agent, preserve the user's specificity. "
                    "Keep the requested layout intent and desired level of "
                    "visual richness instead of collapsing the request into a generic summary."
                ),
                (
                    "After delegate_to_agent returns, treat the returned assistant text and widget "
                    "metadata/code as the authoritative description of what is now visible in chat. "
                    "Explain the result as if you can see it, but do not invent details beyond the "
                    "tool response."
                ),
                (
                    "Do not claim that a visual is already visible, finalized, or ready unless you "
                    "have explicitly received a background visual update saying the delegated visual "
                    "task finished successfully."
                ),
                (
                    "If the user asks a simple verbal question that does not need the visual chat "
                    "agent, answer directly without calling tools."
                ),
                "Tool calls return quickly with a background-job acknowledgement.",
            ]
        )

    async def _consume_client_messages(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        state: LiveSessionState,
    ) -> None:
        while True:
            payload = await websocket.receive_json()
            message_type = payload.get("type")

            if message_type == "session.update":
                state.selected_agent_id = (
                    self._clean_optional_str(payload.get("agentId")) or state.selected_agent_id
                )
                state.selected_model = (
                    self._clean_optional_str(payload.get("model")) or state.selected_model
                )
                state.conversation_id = self._clean_optional_str(payload.get("conversationId"))
                state.subject = self._clean_optional_str(payload.get("subject"))
                await self._send_json(
                    websocket,
                    {
                        "type": "session.updated",
                        "selectedAgentId": state.selected_agent_id,
                        "selectedModel": state.selected_model,
                        "conversationId": state.conversation_id,
                    },
                )
                continue

            if message_type == "input.text":
                text = self._clean_optional_str(payload.get("text"))
                if not text:
                    continue
                await self._send_state(
                    websocket,
                    status="listening",
                    detail="Sending your live text into Gemini Live.",
                )
                sent = await self._safe_send_realtime_input(
                    session=session,
                    state=state,
                    websocket=websocket,
                    text=text,
                )
                if not sent:
                    return
                continue

            if message_type == "input.audio_start":
                state.user_audio_turn_open = True
                sent = await self._safe_send_realtime_input(
                    session=session,
                    state=state,
                    websocket=websocket,
                    activity_start=types.ActivityStart(),
                )
                if not sent:
                    return
                continue

            if message_type == "input.audio":
                audio_b64 = self._clean_optional_str(payload.get("audio"))
                if not audio_b64:
                    continue
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                except Exception:
                    await self._send_json(
                        websocket,
                        {"type": "error", "detail": "Received an invalid audio chunk."},
                    )
                    continue
                sent = await self._safe_send_realtime_input(
                    session=session,
                    state=state,
                    websocket=websocket,
                    audio=types.Blob(data=audio_bytes, mime_type=INPUT_AUDIO_MIME_TYPE),
                )
                if not sent:
                    return
                continue

            if message_type == "input.audio_end":
                state.user_audio_turn_open = False
                sent = await self._safe_send_realtime_input(
                    session=session,
                    state=state,
                    websocket=websocket,
                    activity_end=types.ActivityEnd(),
                )
                if not sent:
                    return
                await self._flush_pending_background_notification(
                    session=session,
                    websocket=websocket,
                    state=state,
                )
                continue

            if message_type == "close":
                await websocket.close(code=1000)
                return

    async def _forward_live_messages(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        state: LiveSessionState,
    ) -> None:
        while True:
            received_any_message = False

            # The Python SDK's session.receive() yields one complete model turn
            # and returns after turn_complete. Re-enter it so one Live session
            # can carry multiple spoken turns.
            async for message in session.receive():
                received_any_message = True

                if message.setup_complete is not None:
                    await self._send_state(
                        websocket,
                        status="idle",
                        detail="Gemini Live is ready for realtime dialogue.",
                    )

                if message.server_content is not None:
                    await self._handle_server_content(
                        websocket=websocket,
                        server_content=message.server_content,
                    )

                if message.tool_call is not None:
                    await self._handle_tool_call(
                        session=session,
                        websocket=websocket,
                        state=state,
                        tool_call=message.tool_call,
                    )

                if message.tool_call_cancellation is not None:
                    await self._send_state(
                        websocket,
                        status="idle",
                        detail="Gemini cancelled the pending tool request.",
                    )

                if message.go_away is not None:
                    await self._send_json(
                        websocket,
                        {
                            "type": "error",
                            "detail": "Gemini requested that the live session end.",
                        },
                    )
                    return

            if not received_any_message:
                break

        if websocket.client_state.name.lower() == "connected":
            await self._send_json(
                websocket,
                {
                    "type": "error",
                    "detail": "Gemini Live upstream session closed.",
                },
            )
            await websocket.close(code=1011)

    async def _handle_server_content(
        self,
        *,
        websocket: WebSocket,
        server_content: types.LiveServerContent,
    ) -> None:
        if server_content.input_transcription and server_content.input_transcription.text:
            await self._send_json(
                websocket,
                {
                    "type": "transcript",
                    "role": "user",
                    "text": server_content.input_transcription.text,
                    "final": bool(server_content.input_transcription.finished),
                },
            )

        if server_content.output_transcription and server_content.output_transcription.text:
            await self._send_json(
                websocket,
                {
                    "type": "transcript",
                    "role": "assistant",
                    "text": server_content.output_transcription.text,
                    "final": bool(server_content.output_transcription.finished),
                },
            )

        if server_content.interrupted:
            await self._send_json(websocket, {"type": "audio.interrupted"})
            await self._send_state(
                websocket,
                status="listening",
                detail="You interrupted the assistant. Listening to the new turn.",
            )

        if server_content.model_turn is not None:
            for part in server_content.model_turn.parts or []:
                if part.text:
                    await self._send_json(
                        websocket,
                        {"type": "text.output", "text": part.text},
                    )
                if part.inline_data and part.inline_data.data:
                    await self._send_json(
                        websocket,
                        {
                            "type": "audio.output",
                            "audio": base64.b64encode(part.inline_data.data).decode("ascii"),
                            "mimeType": part.inline_data.mime_type or OUTPUT_AUDIO_MIME_TYPE,
                        },
                    )
                    await self._send_state(
                        websocket,
                        status="speaking",
                        detail="Gemini is speaking.",
                    )

        if server_content.turn_complete:
            await self._send_json(
                websocket,
                {
                    "type": "turn.complete",
                    "reason": server_content.turn_complete_reason,
                },
            )
            await self._send_state(
                websocket,
                status="idle",
                detail="Turn complete. You can continue speaking.",
            )

        if server_content.waiting_for_input:
            await self._send_state(
                websocket,
                status="idle",
                detail="Waiting for your next message.",
            )

    async def _handle_tool_call(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        state: LiveSessionState,
        tool_call: types.LiveServerToolCall,
    ) -> None:
        function_responses: list[types.FunctionResponse] = []

        for function_call in tool_call.function_calls or []:
            if function_call.name != "delegate_to_agent":
                function_responses.append(
                    types.FunctionResponse(
                        id=function_call.id,
                        name=function_call.name,
                        response={"ok": False, "error": f"Unknown tool: {function_call.name}"},
                    )
                )
                continue

            response_payload = await self._delegate_to_agent(
                session=session,
                websocket=websocket,
                state=state,
                function_call=function_call,
            )
            function_responses.append(
                types.FunctionResponse(
                    id=function_call.id,
                    name=function_call.name,
                    response=response_payload,
                )
            )

        if function_responses:
            sent = await self._safe_send_tool_response(
                session=session,
                state=state,
                websocket=websocket,
                function_responses=function_responses,
            )
            if not sent:
                return

    async def _delegate_to_agent(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        state: LiveSessionState,
        function_call: types.FunctionCall,
    ) -> dict[str, Any]:
        args = function_call.args if isinstance(function_call.args, dict) else {}
        request_text = self._clean_optional_str(args.get("request"))
        if not request_text:
            return {"ok": False, "error": "delegate_to_agent requires a non-empty request"}

        agent_id = self._clean_optional_str(args.get("agent_id")) or state.selected_agent_id
        subject = self._clean_optional_str(args.get("subject")) or state.subject
        from_widget = self._clean_optional_str(args.get("from_widget"))

        if state.background_job_task is not None and not state.background_job_task.done():
            return {
                "ok": True,
                "accepted": False,
                "background_mode": True,
                "message": (
                    "A background visualizer job is already running. Keep talking with the user and "
                    "wait for the completion update."
                ),
            }

        await self._send_state(
            websocket,
            status="delegating",
            detail="Launching the backend visual chat agent in the background.",
        )
        await self._send_json(
            websocket,
            {
                "type": "agent.turn_started",
                "userMessage": request_text,
                "agentId": agent_id,
                "model": state.selected_model,
                "conversationId": state.conversation_id,
            },
        )

        state.background_job_task = asyncio.create_task(
            self._run_background_agent_turn(
                session=session,
                websocket=websocket,
                state=state,
                request_text=request_text,
                subject=subject,
                agent_id=agent_id,
                from_widget=from_widget,
            )
        )
        return {
            "ok": True,
            "accepted": True,
            "background_mode": True,
            "request": request_text,
            "message": (
                "The visualizer is now working in the background. Keep talking naturally; "
                "the app will notify you when the visual is ready."
            ),
        }

    async def _run_background_agent_turn(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        state: LiveSessionState,
        request_text: str,
        subject: str | None,
        agent_id: str | None,
        from_widget: str | None,
    ) -> None:
        assistant_text_parts: list[str] = []
        thinking_text_parts: list[str] = []
        widgets: list[dict[str, Any]] = []
        seen_widget_signatures: set[str] = set()
        final_error: str | None = None

        try:
            async for chunk in self.chat_service.stream_chat(
                ChatRequest(
                    conversation_id=state.conversation_id,
                    message=request_text,
                    subject=subject,
                    agent_id=agent_id,
                    model=state.selected_model,
                    from_widget=from_widget,
                ),
                client_id=state.client_id,
            ):
                for event in self._parse_stream_chunk_events(chunk):
                    if event.type == "conversation":
                        conversation_id = event.data.get("conversationId")
                        if isinstance(conversation_id, str):
                            state.conversation_id = conversation_id
                    if event.type == "text_delta":
                        text = event.data.get("text")
                        if isinstance(text, str):
                            assistant_text_parts.append(text)
                    if event.type == "thinking_delta":
                        thinking_text = event.data.get("text")
                        if isinstance(thinking_text, str):
                            thinking_text_parts.append(thinking_text)
                    if event.type == "widget_ready":
                        widget = event.data.get("widget")
                        if isinstance(widget, dict):
                            widget_summary = self._summarize_widget(widget)
                            widget_signature = self._widget_signature(widget_summary)
                            if widget_signature in seen_widget_signatures:
                                continue
                            seen_widget_signatures.add(widget_signature)
                            widgets.append(widget_summary)
                    if event.type == "error":
                        detail = event.data.get("detail")
                        if isinstance(detail, str):
                            final_error = detail
                    await self._send_json(
                        websocket,
                        {
                            "type": "agent.event",
                            "event": event.model_dump(by_alias=False),
                        },
                    )
        except asyncio.CancelledError:
            raise
        except (AppError, NotFoundAppError) as exc:
            final_error = exc.message
        except Exception as exc:
            logger.exception("delegate-to-agent-failed")
            final_error = str(exc)
        finally:
            state.background_job_task = None

        assistant_text = "".join(assistant_text_parts).strip()
        thinking_text = "".join(thinking_text_parts).strip()
        result_payload = {
            "ok": final_error is None,
            "request": request_text,
            "conversation_id": state.conversation_id,
            "assistant_text": assistant_text[:MAX_TOOL_TEXT_CHARS],
            "assistant_text_truncated": len(assistant_text) > MAX_TOOL_TEXT_CHARS,
            "thinking_text": thinking_text[:MAX_TOOL_TEXT_CHARS],
            "thinking_text_truncated": len(thinking_text) > MAX_TOOL_TEXT_CHARS,
            "widgets": widgets,
            "primary_widget": widgets[-1] if widgets else None,
            "visual_ready": bool(widgets),
            "background_mode": True,
        }
        if final_error is not None:
            result_payload["error"] = final_error

        await self._send_json(
            websocket,
            {
                "type": "agent.result",
                **result_payload,
            },
        )

        notification_text = self._build_background_completion_notification(result_payload)
        if notification_text is not None:
            if state.user_audio_turn_open:
                state.pending_background_notification = notification_text
                await self._send_json(
                    websocket,
                    {
                        "type": "agent.notice",
                        "detail": "The visual is ready. Gemini will use it as soon as your current speech turn ends.",
                    },
                )
            else:
                sent = await self._safe_send_realtime_input(
                    session=session,
                    state=state,
                    websocket=websocket,
                    text=notification_text,
                )
                if sent:
                    await self._send_json(
                        websocket,
                        {
                            "type": "agent.notice",
                            "detail": "The visual is ready. Gemini now has the finished result and can explain it.",
                        },
                    )

    @staticmethod
    def _summarize_widget(widget: dict[str, Any]) -> dict[str, Any]:
        widget_code = widget.get("widget_code")
        widget_code_text = widget_code if isinstance(widget_code, str) else ""
        excerpt = widget_code_text[:MAX_TOOL_WIDGET_CODE_CHARS]
        return {
            "title": widget.get("title"),
            "kind": widget.get("kind"),
            "loading_messages": widget.get("loading_messages"),
            "widget_code_excerpt": excerpt,
            "widget_code_truncated": len(widget_code_text) > len(excerpt),
        }

    @staticmethod
    def _parse_stream_chunk_events(chunk: str) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        for frame in chunk.split("\n\n"):
            stripped = frame.strip()
            if not stripped.startswith("data:"):
                continue
            payload = stripped[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                events.append(StreamEvent.model_validate(orjson.loads(payload)))
            except Exception:
                continue
        return events

    @staticmethod
    def _widget_signature(widget: dict[str, Any]) -> str:
        title = widget.get("title")
        kind = widget.get("kind")
        excerpt = widget.get("widget_code_excerpt")
        return f"{title}|{kind}|{excerpt}"

    def _build_background_completion_notification(
        self, result_payload: dict[str, Any]
    ) -> str | None:
        if result_payload.get("error"):
            error_text = result_payload.get("error")
            if isinstance(error_text, str) and error_text.strip():
                return (
                    "Background visual update: the delegated visual task failed. "
                    f"Error: {error_text.strip()}"
                )
            return None

        assistant_text = result_payload.get("assistant_text")
        thinking_text = result_payload.get("thinking_text")
        primary_widget = result_payload.get("primary_widget")
        if not isinstance(assistant_text, str) or not assistant_text.strip():
            return None

        lines = [
            "Background visual update: the delegated visual task has finished successfully.",
            (
                "Use this as authoritative context for future replies. If the user is not actively "
                "speaking, briefly tell them the visual is ready and offer to explain it. If they "
                "are already talking, wait and use this when they ask about the generated visual."
            ),
            f"Final answer: {assistant_text.strip()}",
        ]
        if isinstance(thinking_text, str) and thinking_text.strip():
            lines.append(f"Reasoning summary: {thinking_text.strip()}")
        if isinstance(primary_widget, dict):
            title = primary_widget.get("title")
            kind = primary_widget.get("kind")
            excerpt = primary_widget.get("widget_code_excerpt")
            if isinstance(title, str) and title.strip():
                lines.append(f"Visual title: {title.strip()}")
            if isinstance(kind, str) and kind.strip():
                lines.append(f"Visual kind: {kind.strip()}")
            if isinstance(excerpt, str) and excerpt.strip():
                lines.append(f"Visual code excerpt: {excerpt.strip()}")
        return "\n".join(lines)

    async def _flush_pending_background_notification(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        state: LiveSessionState,
    ) -> None:
        notification_text = state.pending_background_notification
        if not notification_text:
            return
        state.pending_background_notification = None
        sent = await self._safe_send_realtime_input(
            session=session,
            state=state,
            websocket=websocket,
            text=notification_text,
        )
        if sent:
            await self._send_json(
                websocket,
                {
                    "type": "agent.notice",
                    "detail": "Gemini now has the finished visual context and can explain it.",
                },
            )

    @staticmethod
    async def _send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
        if websocket.client_state.name.lower() != "connected":
            return
        try:
            await websocket.send_json(payload)
        except (RuntimeError, WebSocketDisconnect):
            return

    async def _safe_send_realtime_input(
        self,
        *,
        session: Any,
        state: LiveSessionState,
        websocket: WebSocket,
        **payload: Any,
    ) -> bool:
        try:
            # Check if session is still active before sending
            # The 1007 "Precondition check failed" error can occur if the session
            # is closed or in an invalid state when sending realtime input
            if not state.is_session_active:
                logger.warning(
                    "live-dialogue-session-inactive-while-sending-input",
                    extra={"extra_data": {"payload_keys": list(payload.keys())}},
                )
                return False
            async with state.send_lock:
                await session.send_realtime_input(**payload)
            return True
        except ConnectionClosed:
            logger.warning("live-dialogue-upstream-closed-while-sending-input", exc_info=True)
            await self._notify_upstream_closed(websocket)
            return False
        except Exception as e:
            # Catch 1007 and other protocol errors to prevent crash
            logger.warning(
                "live-dialogue-send-input-failed",
                exc_info=True,
                extra={"extra_data": {"error_type": type(e).__name__, "error_message": str(e)}},
            )
            state.is_session_active = False
            await self._notify_upstream_closed(websocket)
            return False

    async def _safe_send_tool_response(
        self,
        *,
        session: Any,
        state: LiveSessionState,
        websocket: WebSocket,
        function_responses: list[types.FunctionResponse],
    ) -> bool:
        try:
            async with state.send_lock:
                await session.send_tool_response(function_responses=function_responses)
            return True
        except ConnectionClosed:
            logger.warning(
                "live-dialogue-upstream-closed-while-sending-tool-response", exc_info=True
            )
            await self._notify_upstream_closed(websocket)
            return False

    async def _notify_upstream_closed(self, websocket: WebSocket) -> None:
        if websocket.client_state.name.lower() != "connected":
            return
        await self._send_json(
            websocket,
            {
                "type": "error",
                "detail": "Gemini Live ended the upstream audio session. Start voice again.",
            },
        )
        await websocket.close(code=1011)

    async def _send_state(self, websocket: WebSocket, *, status: str, detail: str) -> None:
        await self._send_json(
            websocket,
            {
                "type": "state",
                "status": status,
                "detail": detail,
            },
        )

    @staticmethod
    def _clean_optional_str(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None
