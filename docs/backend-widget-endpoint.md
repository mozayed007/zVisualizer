---
name: backend-widget-endpoint
description: Python / FastAPI implementation guide for the widget request-response cycle. Covers the SSE streaming endpoint that proxies Anthropic API responses, the tool call extraction and forwarding pattern, conversation history management on the server, the show_widget tool schema as a Pydantic model, rate limiting, error handling with SSE error events, conversation persistence, and the exact event format the frontend stream consumer expects. Use this document when building the backend chat endpoint.
---

# Backend Widget Endpoint — Python / FastAPI Implementation

## Overview

The backend is a thin, trusted proxy between the browser and the Anthropic API. Its jobs are:
1. Hold the API key securely
2. Validate and sanitise incoming messages
3. Forward the streaming response verbatim to the browser
4. Persist conversation history
5. Apply rate limiting

The backend does **not** parse `widget_code` — that is the frontend's job. It forwards tool call events exactly as Anthropic sends them.

---

## 1. Project structure

```
app/
├── main.py              — FastAPI app, CORS, startup
├── routers/
│   └── chat.py          — /api/chat SSE endpoint
├── models/
│   ├── messages.py      — Pydantic request/response models
│   └── tools.py         — show_widget tool definition
├── services/
│   ├── anthropic.py     — Anthropic client wrapper
│   ├── conversation.py  — conversation CRUD
│   └── rate_limit.py    — per-user rate limiting
├── middleware/
│   └── auth.py          — JWT verification
└── config.py            — settings from environment
```

---

## 2. Pydantic models

```python
# models/messages.py
from __future__ import annotations
from typing import Literal, Union, Any
from pydantic import BaseModel, Field, field_validator
import re


class TextContent(BaseModel):
    type: Literal["text"]
    text: str


class ToolUseContent(BaseModel):
    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, Any]


class ToolResultContent(BaseModel):
    type: Literal["tool_result"]
    tool_use_id: str
    content: str


MessageContent = Union[str, list[Union[TextContent, ToolUseContent, ToolResultContent]]]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: MessageContent

    @field_validator("content")
    @classmethod
    def sanitise_content(cls, v: MessageContent) -> MessageContent:
        if isinstance(v, str):
            # Cap individual message length
            if len(v) > 50_000:
                raise ValueError("Message content exceeds 50,000 character limit")
            # Strip any script injection attempts in user text
            v = re.sub(r'<script[^>]*>.*?</script>', '', v, flags=re.DOTALL | re.IGNORECASE)
        return v


class ChatRequest(BaseModel):
    conversation_id: str | None = None   # None = start new conversation
    messages: list[Message] = Field(..., min_length=1, max_length=200)
    subject: str | None = None           # e.g. "optimization", "calculus"
    user_profile: dict[str, Any] | None = None

    @field_validator("messages")
    @classmethod
    def no_system_messages(cls, msgs: list[Message]) -> list[Message]:
        for m in msgs:
            if m.role not in ("user", "assistant"):
                raise ValueError(f"Invalid role: {m.role}")
        return msgs
```

```python
# models/tools.py
from anthropic.types import ToolParam
from pydantic import BaseModel


class WidgetParams(BaseModel):
    """Matches the show_widget tool's input schema — used for validation and storage."""
    title: str
    loading_messages: list[str]
    widget_code: str


SHOW_WIDGET_TOOL: ToolParam = {
    "name": "show_widget",
    "description": (
        "Show visual content — SVG diagrams or interactive HTML widgets — that renders "
        "inline in the conversation. Use for flowcharts, architecture diagrams, "
        "interactive explainers, data charts, step-through animations, and any content "
        "where a visual would meaningfully improve understanding. "
        "Do NOT use for plain factual answers, code writing, or text editing tasks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "Short snake_case identifier — 'attention_mechanism_transformer' not 'diagram'. "
                    "No spaces or special characters."
                ),
            },
            "loading_messages": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 4,
                "description": (
                    "1-4 short playful messages shown while the visual renders. "
                    "~5 words each. Example: ['Drawing the loss surface', 'Rolling the ball downhill']"
                ),
            },
            "widget_code": {
                "type": "string",
                "description": (
                    "Raw SVG (starting with <svg>) or HTML fragment (no DOCTYPE, no <html>). "
                    "viewBox='0 0 680 H' for SVG. All colors via CSS variables or c-{ramp} classes. "
                    "sendPrompt(text) for clickable follow-up triggers."
                ),
            },
        },
        "required": ["title", "loading_messages", "widget_code"],
    },
}
```

---

## 3. System prompt builder

```python
# services/system_prompt.py
from typing import Any

BASE_SYSTEM_PROMPT = """You are an expert visual companion for {subject}.

Your users are readers who want to genuinely understand, not just skim.

Your mission is to make difficult concepts understandable through precise, interactive visual
explanations — not just verbal descriptions.

## Visual routing rules

Call show_widget when the user's question involves:
- A mechanism, process, or system ("how does X work")
- A comparison or contrast ("what's the difference between X and Y")
- A sequence of steps ("walk me through X")
- Spatial or relational structure ("what's the architecture of X")
- A concept with an interactive parameter ("show me what changes when I adjust X")
- Data that should be charted or graphed

Do NOT call show_widget for:
- Direct factual lookups ("what year was X invented")
- Single-sentence definitions
- Code debugging or writing tasks
- When the user explicitly asks for text only

## Visual type selection

INTERACTIVE HTML: concept has a manipulable parameter, cyclic processes, charts, animations
ILLUSTRATIVE SVG: spatial metaphor for mechanism (attention=fan of lines, recursion=stack frames)
FLOWCHART SVG: sequential steps or decision trees the user needs to follow
STRUCTURAL SVG: containment — things inside other things
MERMAID erDiagram: database schemas or class hierarchies only

NEVER use flowchart when illustrative is the right choice.

## SVG rules — strictly enforced

viewBox MUST be "0 0 680 H" — 680 is load-bearing. Calculate H from content.
All colors via c-{{ramp}} classes ONLY. Never hardcode hex.
Box width = max(title_chars × 8, subtitle_chars × 7) + 24
Arrows must not cross box interiors — use L-bend path detours.
Every <text> needs dominant-baseline="central"
Every connector <path> needs fill="none"
No DOCTYPE, no <html>, no <head>, no <body>, no comments.
Arrow marker ALWAYS in <defs>: <defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>

## HTML widget rules — strictly enforced

Structure: <style> → content HTML → CDN <script> → logic <script>
No localStorage/sessionStorage — state in JS variables only
No position:fixed — collapses iframe height
CDN only from: cdnjs.cloudflare.com, esm.sh, cdn.jsdelivr.net, unpkg.com
All numbers shown to users must be rounded (toFixed/Math.round)
Colors via CSS variables only — never hardcode

## sendPrompt — the follow-up bridge

Every diagram node that could lead to deeper understanding must have:
  onclick="sendPrompt('specific follow-up question about that node')"

Rules: specific, one level deeper, user-voiced, never generic "tell me more".

## Explanation principles

1. ILLUSTRATIVE FIRST: draw mechanisms spatially — not boxes and arrows.
2. INTERACTIVE OVER STATIC: if the system has a control, give the diagram that control.
3. PROGRESSIVE DISCLOSURE: start 3-4 nodes max, depth lives in sendPrompt clicks.
4. SWITCH REPRESENTATIONS: if user signals confusion, switch visual type entirely.
5. PROSE BETWEEN DIAGRAMS: never stack visuals — one sentence before, one after.

## Tone: warm, encouraging, candid. Ask one check question per response.
"""


def build_system_prompt(
    subject: str | None,
    user_profile: dict[str, Any] | None
) -> str:
    subject_str = subject or "computer science, mathematics, and science"
    prompt = BASE_SYSTEM_PROMPT.format(subject=subject_str)

    if user_profile:
        topics_visualized: list[str] = user_profile.get("topics_visualized", [])
        unclear_topics: list[str] = user_profile.get("unclear_topics", [])

        if topics_visualized:
            prompt += f"\n\n## User session context\n"
            prompt += f"Topics already visualized: {', '.join(topics_visualized)}\n"
            prompt += "Do not re-explain these at the same depth — build on them.\n"

        if unclear_topics:
            prompt += f"User has shown confusion about: {', '.join(unclear_topics)}\n"
            prompt += "Use different visual encodings for these topics.\n"

    return prompt
```

---

## 4. The SSE streaming endpoint

```python
# routers/chat.py
from __future__ import annotations

import json
import asyncio
from typing import AsyncIterator

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.config import settings
from app.models.messages import ChatRequest, Message
from app.models.tools import SHOW_WIDGET_TOOL
from app.services.anthropic import get_anthropic_client
from app.services.conversation import ConversationService
from app.services.rate_limit import RateLimiter
from app.middleware.auth import get_current_user_id

router = APIRouter(prefix="/api")
rate_limiter = RateLimiter()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    client: anthropic.AsyncAnthropic = Depends(get_anthropic_client),
    conv_service: ConversationService = Depends(),
) -> StreamingResponse:

    # Rate limiting
    if not await rate_limiter.check(user_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Load or create conversation
    if request.conversation_id:
        conversation = await conv_service.get(request.conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # Merge stored history with incoming messages
        # (frontend sends only new messages; server appends to stored history)
        messages = conversation.messages + [m.model_dump() for m in request.messages]
    else:
        messages = [m.model_dump() for m in request.messages]

    system_prompt = build_system_prompt(request.subject, request.user_profile)

    async def event_stream() -> AsyncIterator[str]:
        """
        Yields SSE-formatted events.
        Forwards Anthropic events verbatim so the frontend stream consumer works unchanged.
        Also yields bookkeeping events (conversation_id, error) that Anthropic doesn't send.
        """
        conversation_id = request.conversation_id or await conv_service.create(user_id)

        # Yield conversation_id first so frontend knows where to persist
        yield f"data: {json.dumps({'type': 'conversation_id', 'id': conversation_id})}\n\n"

        full_response_blocks: list[dict] = []
        current_tool_json = ""
        in_tool_block = False

        try:
            async with client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=settings.MAX_TOKENS,
                system=system_prompt,
                tools=[SHOW_WIDGET_TOOL],
                messages=truncate_history(messages),
            ) as stream:

                async for event in stream:
                    # Forward every event verbatim as SSE — frontend handles all types
                    event_dict = event.model_dump() if hasattr(event, "model_dump") else dict(event)
                    yield f"data: {json.dumps(event_dict)}\n\n"

                    # Also track what we need to persist
                    if hasattr(event, "type"):
                        if event.type == "content_block_start":
                            if event.content_block.type == "tool_use":
                                in_tool_block = True
                                current_tool_json = ""
                        elif event.type == "content_block_delta":
                            if in_tool_block and event.delta.type == "input_json_delta":
                                current_tool_json += event.delta.partial_json or ""
                        elif event.type == "content_block_stop" and in_tool_block:
                            in_tool_block = False
                            try:
                                tool_params = json.loads(current_tool_json)
                                full_response_blocks.append({
                                    "type": "tool_use",
                                    "name": "show_widget",
                                    "input": tool_params
                                })
                            except json.JSONDecodeError:
                                pass

                # Get final message for persistence
                final_message = await stream.get_final_message()

        except anthropic.RateLimitError:
            yield f"data: {json.dumps({'type': 'error', 'code': 'rate_limited', 'message': 'API rate limit reached, please wait a moment'})}\n\n"
            return
        except anthropic.APIStatusError as e:
            yield f"data: {json.dumps({'type': 'error', 'code': 'api_error', 'message': str(e.message)})}\n\n"
            return
        except asyncio.CancelledError:
            # Client disconnected mid-stream — normal, just stop
            return
        finally:
            yield "data: [DONE]\n\n"

        # Persist the complete assistant turn asynchronously (don't block the response)
        if final_message:
            asyncio.create_task(
                conv_service.append_turn(
                    conversation_id=conversation_id,
                    user_messages=[m.model_dump() for m in request.messages],
                    assistant_content=final_message.content,
                )
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Access-Control-Allow-Origin": settings.FRONTEND_ORIGIN,
        },
    )


def truncate_history(messages: list[dict], max_chars: int = 400_000) -> list[dict]:
    """
    Keep the most recent messages that fit within the character budget.
    Always preserve the first user message.
    Rough estimate: 4 chars ≈ 1 token; 400k chars ≈ 100k tokens.
    """
    if not messages:
        return messages

    total = 0
    kept = []
    for msg in reversed(messages):
        content = msg.get("content", "")
        chars = len(content) if isinstance(content, str) else len(json.dumps(content))
        total += chars
        if total > max_chars and len(kept) > 0:
            break
        kept.insert(0, msg)

    # Always include first message
    if messages[0] not in kept:
        kept.insert(0, messages[0])

    return kept
```

---

## 5. Conversation persistence

```python
# services/conversation.py
from __future__ import annotations
import json
import uuid
from datetime import datetime, UTC
from typing import Any

import asyncpg  # or use SQLAlchemy async


class ConversationService:
    """
    Manages conversation history in PostgreSQL.
    Schema: see migration below.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, user_id: str) -> str:
        conv_id = str(uuid.uuid4())
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (id, user_id, created_at, updated_at, messages)
                VALUES ($1, $2, $3, $3, '[]'::jsonb)
                """,
                conv_id, user_id, datetime.now(UTC)
            )
        return conv_id

    async def get(self, conv_id: str, user_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM conversations WHERE id=$1 AND user_id=$2",
                conv_id, user_id
            )
        if not row:
            return None
        return dict(row) | {"messages": json.loads(row["messages"])}

    async def append_turn(
        self,
        conversation_id: str,
        user_messages: list[dict],
        assistant_content: list[Any],
    ) -> None:
        """
        Append a complete user+assistant turn to the conversation.
        assistant_content is a list of Anthropic ContentBlock objects.
        """
        # Serialize assistant content to JSON-safe dicts
        assistant_blocks = []
        for block in assistant_content:
            if hasattr(block, "model_dump"):
                assistant_blocks.append(block.model_dump())
            else:
                assistant_blocks.append(dict(block))

        new_messages = [
            *user_messages,
            {"role": "assistant", "content": assistant_blocks}
        ]

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE conversations
                SET messages = messages || $1::jsonb,
                    updated_at = $2
                WHERE id = $3
                """,
                json.dumps(new_messages),
                datetime.now(UTC),
                conversation_id,
            )


# Migration — run once
MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    subject     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    messages    JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id
    ON conversations (user_id);

CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
    ON conversations (updated_at DESC);

-- Prune conversations older than 90 days (run as a cron job)
-- DELETE FROM conversations WHERE updated_at < NOW() - INTERVAL '90 days';
"""
```

---

## 6. Rate limiting

```python
# services/rate_limit.py
from __future__ import annotations
import time
from collections import defaultdict
import asyncio

# In production use Redis — this is an in-memory fallback for single-instance
class RateLimiter:
    """
    Token bucket rate limiter.
    In production: replace with Redis INCR + EXPIRE pattern.
    """

    LIMITS = {
        "anonymous": (10, 3600),    # 10 requests per hour
        "free":      (50, 3600),    # 50 per hour
        "paid":      (500, 3600),   # 500 per hour
        "admin":     (10000, 3600),
    }

    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, user_id: str, tier: str = "free") -> bool:
        limit, window = self.LIMITS.get(tier, self.LIMITS["free"])
        now = time.time()

        async with self._lock:
            # Remove timestamps outside the window
            self._buckets[user_id] = [
                t for t in self._buckets[user_id] if now - t < window
            ]

            if len(self._buckets[user_id]) >= limit:
                return False

            self._buckets[user_id].append(now)
            return True
```

---

## 7. Config and environment

```python
# config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    MAX_TOKENS: int = 8192

    DATABASE_URL: str
    REDIS_URL: str = ""

    FRONTEND_ORIGIN: str = "http://localhost:3000"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
```

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import anthropic

from app.config import settings
from app.routers.chat import router as chat_router

app = FastAPI(title="Visual Companion API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(chat_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## 8. SSE event format reference

The frontend stream consumer expects these exact event types from the `/api/chat` endpoint:

```
# Bookkeeping events (added by our proxy)
data: {"type": "conversation_id", "id": "conv_abc123"}

# Forwarded verbatim from Anthropic
data: {"type": "message_start", "message": {...}}
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", ...}}
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "..."}}
data: {"type": "content_block_stop", "index": 0}
data: {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_...", "name": "show_widget", ...}}
data: {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"title\":"}}
data: {"type": "content_block_stop", "index": 1}
data: {"type": "message_delta", "delta": {"stop_reason": "tool_use", ...}}
data: {"type": "message_stop"}

# Error event (added by our proxy on failure)
data: {"type": "error", "code": "rate_limited", "message": "..."}

# End sentinel
data: [DONE]
```

The frontend only needs to watch for `content_block_start` (detect `tool_use` type), `content_block_delta` (accumulate `input_json_delta`), and `content_block_stop` (finalize tool params). All other events are for text streaming.

---

## 9. Nginx configuration for SSE

```nginx
location /api/chat {
    proxy_pass          http://backend:8000;
    proxy_http_version  1.1;
    proxy_set_header    Connection '';
    proxy_set_header    Host $host;
    proxy_set_header    X-Real-IP $remote_addr;
    proxy_buffering     off;           # CRITICAL: disable buffering for SSE
    proxy_cache         off;
    proxy_read_timeout  300s;          # allow long-running streams
    chunked_transfer_encoding on;
}
```
