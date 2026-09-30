---
name: pydantic-ai-visual-agent
description: Complete PydanticAI agent implementation that replicates claude.ai's on-the-fly visual generation capability. Covers the show_widget tool definition as a Pydantic model with RunContext, the agent system prompt with full routing and SVG/HTML rules, streaming response handling that yields interleaved text and tool call events, user profile as agent dependency, multi-turn conversation wiring, the re-explanation and progressive-disclosure patterns, and a FastAPI streaming integration layer. Use this document to build the PydanticAI agent that generates visual explanations on the fly.
---

# PydanticAI Visual Agent — Complete Implementation

## Why PydanticAI for this use case

PydanticAI gives us:
- **Typed tool parameters** — `WidgetParams` is a Pydantic model; the agent validates before calling the tool
- **Dependency injection** — `AgentContext` (profile, history, subject) flows into the system prompt and tools via `RunContext`
- **Structured streaming** — `.run_stream()` yields typed events; text deltas and tool calls are first-class
- **Model-agnostic** — swap `claude-sonnet-4-20250514` for any provider without changing tool definitions

---

## 1. Dependencies

```bash
pip install pydantic-ai anthropic fastapi uvicorn python-dotenv
```

```toml
# pyproject.toml
[tool.poetry.dependencies]
python = "^3.11"
pydantic-ai = "^0.0.14"     # check latest — API stabilized in 0.0.13+
anthropic = "^0.40.0"
fastapi = "^0.115.0"
uvicorn = {extras = ["standard"], version = "^0.32.0"}
pydantic-settings = "^2.6.0"
```

---

## 2. Models and dependencies

```python
# agent/models.py
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class WidgetParams(BaseModel):
    """
    The structured output of the show_widget tool.
    PydanticAI validates this before the tool function receives it.
    """
    title: str = Field(
        description=(
            "Short snake_case identifier — 'attention_mechanism_transformer' not 'diagram'. "
            "No spaces or special characters."
        )
    )
    loading_messages: list[str] = Field(
        min_length=1,
        max_length=4,
        description=(
            "1-4 short playful messages shown while the visual renders (~5 words each). "
            "Example: ['Drawing the loss surface', 'Rolling the ball downhill']"
        )
    )
    widget_code: str = Field(
        description=(
            "Raw SVG (starting with <svg viewBox='0 0 680 H'>) or HTML fragment "
            "(no DOCTYPE, no <html>). All colors via CSS variables or c-{ramp} classes. "
            "sendPrompt(text) on every clickable element."
        )
    )


class UserProfile(BaseModel):
    """Accumulated knowledge about a user — grows over the session."""
    name: str | None = None
    subject: str = "general science and mathematics"
    topics_visualized: list[str] = Field(default_factory=list)
    unclear_topics: list[str] = Field(default_factory=list)
    widget_clicks: int = 0
    session_turns: int = 0


class AgentContext(BaseModel):
    """
    Injected into every agent run as a dependency.
    Contains everything the system prompt and tools need.
    """
    profile: UserProfile
    conversation_id: str | None = None
    from_widget: str | None = None   # title of diagram the user just clicked in

    model_config = {"arbitrary_types_allowed": True}
```

---

## 3. The system prompt function

```python
# agent/prompts.py
from __future__ import annotations
from agent.models import AgentContext

ROUTING_AND_RULES = """
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

INTERACTIVE HTML when:
- Concept has a manipulable parameter (step size, frequency, temperature)
- Process is cyclic — use HTML stepper, never SVG ring
- Output involves a chart or data plot (Chart.js, D3)
- Animation would show how the system behaves

ILLUSTRATIVE SVG when:
- User needs intuition about a mechanism
- Spatial metaphor explains better than steps:
  - attention = fan of weighted lines between tokens
  - recursion = literal stack of frames growing/shrinking
  - hash map = key falling through funnel into buckets
  - gradient descent = ball rolling down loss surface
  - TCP stream = numbered envelopes in flight between two endpoints

FLOWCHART SVG when:
- User needs to follow sequential steps or decisions
- Output is documentation of a process

STRUCTURAL SVG when:
- Concept involves containment (things inside other things)
- Examples: CPU cache hierarchy, VPC/subnet, cell organelles

MERMAID erDiagram when:
- Database schema or class hierarchy with typed fields

NEVER substitute a flowchart when illustrative is correct.
When user says "I don't understand X" — default to illustrative, not flowchart.

## SVG rules — zero tolerance

viewBox MUST be "0 0 680 H" — 680 IS LOAD-BEARING. Calculate H from content.
ALL colors via c-{ramp} classes or CSS variables. NEVER hardcode hex colors.
Box width = max(title_chars × 8, subtitle_chars × 7) + 24
Arrows NEVER cross box interiors — use L-bend path detours.
ALL <text> elements need dominant-baseline="central"
ALL connector <path> elements need fill="none"
NO DOCTYPE, NO <html>, NO <head>, NO <body>, NO HTML or CSS comments.
Arrow marker in EVERY SVG:
<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>

## HTML widget rules — zero tolerance

Structure order: <style> → content HTML → CDN <script> → logic <script>
No localStorage, sessionStorage, IndexedDB — state in JS variables only
No position:fixed — collapses iframe height
CDN only from: cdnjs.cloudflare.com, esm.sh, cdn.jsdelivr.net, unpkg.com
All numbers shown to users must be rounded (toFixed / Math.round)
All colors via CSS variables — never hardcode
Animations: @keyframes on transform and opacity only

## sendPrompt — the follow-up bridge

Every meaningful diagram element must have:
  onclick="sendPrompt('specific follow-up question about that element')"

Rules:
- SPECIFIC: name what was clicked ("What does the dip tube do?" not "Tell me more")
- ONE LEVEL DEEPER: go beyond the label
- USER-VOICED: phrase as the user would ask it
- NEVER GENERIC: "tell me more about this" is forbidden

## Response structure

For concept explanations:
1. One sentence framing what the visual shows
2. show_widget call
3. One sentence connecting to the next point
4. Optional understanding check question

NEVER stack two show_widget calls without prose between them.
"""

EXPLANATION_PRINCIPLES = """
## Explanation principles

1. ILLUSTRATIVE FIRST: draw mechanisms spatially — spatial metaphor > boxes and arrows.
2. INTERACTIVE OVER STATIC: if the real system has a control, give the diagram that control.
3. PROGRESSIVE DISCLOSURE: start sparse (3-4 nodes), depth lives in sendPrompt clicks.
4. SWITCH REPRESENTATIONS: if user signals confusion, completely different visual type.
5. COMPARISON IS UNDERSTANDING: show X alongside its natural counterpart.
6. PROSE BETWEEN DIAGRAMS: one context sentence before, one transition sentence after.

Tone: warm, encouraging, candid. Ask one follow-up question per response.
"""


def build_system_prompt(ctx: AgentContext) -> str:
    profile = ctx.profile
    lines = [
        f"You are an expert visual companion for {profile.subject}.",
        "",
        "Your mission: make difficult concepts genuinely understandable through precise,",
        "interactive visual explanations — not just verbal descriptions.",
        "",
        ROUTING_AND_RULES,
        EXPLANATION_PRINCIPLES,
    ]

    # Dynamic user context section
    if profile.topics_visualized or profile.unclear_topics or ctx.from_widget:
        lines.append("## Current user context")

        if ctx.from_widget:
            lines.append(
                f"The user just clicked a node in the '{ctx.from_widget}' diagram. "
                "Their question comes from that specific interaction — respond with that context in mind."
            )

        if profile.topics_visualized:
            lines.append(
                f"Topics already visualized this session: {', '.join(profile.topics_visualized)}. "
                "Do not re-explain at the same depth — build on them."
            )

        if profile.unclear_topics:
            lines.append(
                f"User has shown confusion about: {', '.join(profile.unclear_topics)}. "
                "Use a different visual encoding than before for these topics."
            )

    return "\n".join(lines)
```

---

## 4. The PydanticAI agent definition

```python
# agent/visual_agent.py
from __future__ import annotations

import pydantic_ai
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel

from agent.models import WidgetParams, AgentContext
from agent.prompts import build_system_prompt
from app.config import settings


# ── Model setup ─────────────────────────────────────────────────────────────
model = AnthropicModel(
    model_name=settings.ANTHROPIC_MODEL,  # "claude-sonnet-4-20250514"
    api_key=settings.ANTHROPIC_API_KEY,
)


# ── Agent definition ─────────────────────────────────────────────────────────
visual_agent = Agent(
    model=model,
    deps_type=AgentContext,
    system_prompt=build_system_prompt,   # called fresh on every run with current deps
    retries=2,                            # retry on transient API errors
)


# ── The show_widget tool ──────────────────────────────────────────────────────
@visual_agent.tool
async def show_widget(
    ctx: RunContext[AgentContext],
    params: WidgetParams,
) -> str:
    """
    Show visual content — SVG diagrams or interactive HTML widgets — that renders
    inline in the conversation. Use for flowcharts, architecture diagrams,
    interactive explainers, data charts, step-through animations, and any content
    where a visual would meaningfully improve understanding.

    Do NOT use for plain factual answers, code writing, or text editing tasks.
    """
    # Update user profile with what was just shown
    profile = ctx.deps.profile
    if params.title not in profile.topics_visualized:
        profile.topics_visualized.append(params.title)

    # Return a tool result that tells the model the widget was rendered
    # The actual widget code is extracted by the stream consumer from the tool call params
    return f"Widget '{params.title}' rendered successfully."


# ── Optional: validation tool for agent self-checking ───────────────────────
@visual_agent.tool
async def validate_svg_rules(
    ctx: RunContext[AgentContext],
    widget_code: str,
) -> str:
    """
    Internal tool for the agent to validate SVG before finalising.
    Returns a list of rule violations found, or 'valid' if none found.
    Only call this if you are uncertain about coordinate math or color usage.
    """
    violations = []

    if 'viewBox="0 0 680' not in widget_code and "viewBox='0 0 680" not in widget_code:
        violations.append("viewBox is not '0 0 680 H' — width must be 680")

    import re
    hex_colors = re.findall(r'fill="#[0-9a-fA-F]{3,6}"', widget_code)
    hex_colors += re.findall(r'stroke="#[0-9a-fA-F]{3,6}"', widget_code)
    if hex_colors:
        violations.append(f"Hardcoded hex colors found: {hex_colors[:3]} — use c-{{ramp}} classes or CSS variables")

    if '<text ' in widget_code and 'dominant-baseline' not in widget_code:
        violations.append("SVG <text> elements missing dominant-baseline='central'")

    connector_paths = re.findall(r'<path[^>]+>', widget_code)
    for path in connector_paths:
        if 'fill="none"' not in path and "fill='none'" not in path:
            if 'class="arr"' in path or "class='arr'" in path:
                violations.append("Connector <path> missing fill='none'")
                break

    return "valid" if not violations else "; ".join(violations)
```

---

## 5. Streaming run — yielding interleaved text and widget events

```python
# agent/runner.py
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Any
import json

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from agent.models import AgentContext, WidgetParams
from agent.visual_agent import visual_agent


@dataclass
class TextEvent:
    type: Literal["text"] = "text"
    delta: str = ""


@dataclass
class WidgetStartEvent:
    """Emitted as soon as loading_messages are parsed from the stream."""
    type: Literal["widget_start"] = "widget_start"
    loading_messages: list[str] = None


@dataclass
class WidgetReadyEvent:
    """Emitted when the full widget_code is available."""
    type: Literal["widget_ready"] = "widget_ready"
    params: WidgetParams = None


@dataclass
class StreamEndEvent:
    type: Literal["end"] = "end"
    new_messages: list[ModelMessage] = None


AgentEvent = TextEvent | WidgetStartEvent | WidgetReadyEvent | StreamEndEvent


async def run_agent_stream(
    user_message: str,
    deps: AgentContext,
    message_history: list[ModelMessage],
) -> AsyncIterator[AgentEvent]:
    """
    Runs the agent and yields typed events for the FastAPI endpoint to forward.

    The stream yields in document order:
      TextEvent(delta="Here is...") → multiple text deltas
      WidgetStartEvent(loading_messages=[...]) → loading card trigger
      TextEvent(delta="...") → optional prose after widget
      WidgetReadyEvent(params=WidgetParams(...)) → actual widget render
      StreamEndEvent(new_messages=[...]) → full turn for persistence
    """

    async with visual_agent.run_stream(
        user_message,
        deps=deps,
        message_history=message_history,
    ) as result:

        # Track tool calls seen so far so we can emit WidgetStart early
        tool_calls_emitted: set[str] = set()

        async for message in result.stream_events():
            # PydanticAI streaming events

            if isinstance(message, pydantic_ai.messages.PartStartEvent):
                part = message.part
                if isinstance(part, ToolCallPart):
                    # Tool call starting — we'll emit WidgetStart once we have loading_messages
                    pass

            elif isinstance(message, pydantic_ai.messages.PartDeltaEvent):
                delta = message.delta

                # Text delta — forward immediately
                if isinstance(delta, pydantic_ai.messages.TextPartDelta):
                    yield TextEvent(delta=delta.content)

                # Tool args accumulating — try to extract loading_messages early
                elif isinstance(delta, pydantic_ai.messages.ToolCallPartDelta):
                    tool_id = message.part_id
                    if tool_id not in tool_calls_emitted:
                        partial = delta.args_delta or ""
                        msgs = _try_extract_loading_messages(partial)
                        if msgs:
                            tool_calls_emitted.add(tool_id)
                            yield WidgetStartEvent(loading_messages=msgs)

            elif isinstance(message, pydantic_ai.messages.FinalResultEvent):
                pass  # handled via result.all_messages() below

        # After stream completes, extract all tool call results
        all_messages = result.all_messages()
        for msg in all_messages:
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart) and part.tool_name == "show_widget":
                        try:
                            args = part.args_as_dict() if hasattr(part, 'args_as_dict') else {}
                            widget_params = WidgetParams(**args)
                            yield WidgetReadyEvent(params=widget_params)
                        except Exception as e:
                            # Log but don't crash the stream
                            import logging
                            logging.error(f"Failed to parse widget params: {e}")

        yield StreamEndEvent(new_messages=all_messages)


def _try_extract_loading_messages(partial_json: str) -> list[str] | None:
    """
    Attempt to parse loading_messages from incomplete JSON.
    Returns None if not yet available in the partial stream.
    """
    import re
    match = re.search(r'"loading_messages"\s*:\s*(\[[^\]]+\])', partial_json)
    if not match:
        return None
    try:
        msgs = json.loads(match.group(1))
        return msgs if isinstance(msgs, list) and len(msgs) > 0 else None
    except json.JSONDecodeError:
        return None
```

---

## 6. FastAPI integration — streaming endpoint using the agent

```python
# routers/chat.py (using PydanticAI agent)
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic_ai.messages import ModelMessage

from agent.models import AgentContext, UserProfile
from agent.runner import (
    run_agent_stream,
    TextEvent,
    WidgetStartEvent,
    WidgetReadyEvent,
    StreamEndEvent,
)
from app.models.messages import ChatRequest
from app.services.conversation import ConversationService
from app.services.rate_limit import RateLimiter
from app.middleware.auth import get_current_user_id

router = APIRouter(prefix="/api")
rate_limiter = RateLimiter()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    conv_service: ConversationService = Depends(),
) -> StreamingResponse:

    if not await rate_limiter.check(user_id):
        return StreamingResponse(
            iter([f'data: {json.dumps({"type":"error","code":"rate_limited"})}\n\n']),
            media_type="text/event-stream"
        )

    # Build deps from request
    profile = UserProfile(
        subject=request.subject or "general science and mathematics",
        **(request.user_profile or {})
    )
    deps = AgentContext(
        profile=profile,
        conversation_id=request.conversation_id,
        from_widget=getattr(request, "from_widget", None),
    )

    # Load message history
    history: list[ModelMessage] = []
    if request.conversation_id:
        conv = await conv_service.get(request.conversation_id, user_id)
        if conv:
            history = conv.get("pydantic_messages", [])

    # Get the latest user message text
    user_text = _extract_user_text(request.messages)

    async def event_stream() -> AsyncIterator[str]:
        # Create or retrieve conversation_id
        conv_id = request.conversation_id or await conv_service.create(user_id)
        yield f'data: {json.dumps({"type": "conversation_id", "id": conv_id})}\n\n'

        new_messages = []

        async for event in run_agent_stream(user_text, deps, history):
            if isinstance(event, TextEvent):
                # Forward as SSE text delta — same format frontend already handles
                yield f'data: {json.dumps({"type": "text_delta", "text": event.delta})}\n\n'

            elif isinstance(event, WidgetStartEvent):
                # Loading card trigger
                yield f'data: {json.dumps({"type": "widget_start", "loading_messages": event.loading_messages})}\n\n'

            elif isinstance(event, WidgetReadyEvent):
                # Full widget ready — forward params for iframe render
                yield f'data: {json.dumps({"type": "widget_ready", "params": event.params.model_dump()})}\n\n'

            elif isinstance(event, StreamEndEvent):
                new_messages = event.new_messages or []
                # Persist updated profile
                import asyncio
                asyncio.create_task(
                    conv_service.append_pydantic_turn(conv_id, new_messages, deps.profile)
                )

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _extract_user_text(messages) -> str:
    """Get the text of the last user message."""
    for msg in reversed(messages):
        if msg.role == "user":
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "text"):
                        return block.text
    return ""
```

---

## 7. Frontend stream consumer — updated for PydanticAI event format

The PydanticAI backend emits a slightly different event format than the raw Anthropic proxy. Update the frontend consumer:

```typescript
// streamConsumer.ts — updated for PydanticAI backend events
export async function consumePydanticStream(
  response: Response,
  handlers: {
    onConversationId: (id: string) => void;
    onTextDelta: (text: string) => void;
    onWidgetStart: (loadingMessages: string[]) => void;
    onWidgetReady: (params: WidgetParams) => void;
    onStreamEnd: () => void;
    onError: (code: string, message: string) => void;
  }
) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6);
      if (raw === '[DONE]') { handlers.onStreamEnd(); return; }

      let event: Record<string, unknown>;
      try { event = JSON.parse(raw); } catch { continue; }

      switch (event.type) {
        case 'conversation_id':
          handlers.onConversationId(event.id as string);
          break;
        case 'text_delta':
          handlers.onTextDelta(event.text as string);
          break;
        case 'widget_start':
          handlers.onWidgetStart(event.loading_messages as string[]);
          break;
        case 'widget_ready':
          handlers.onWidgetReady(event.params as WidgetParams);
          break;
        case 'error':
          handlers.onError(event.code as string, event.message as string);
          break;
      }
    }
  }
}
```

---

## 8. Agentic patterns with PydanticAI

### Pattern A: Re-explanation on confusion

```python
# agent/patterns.py
from agent.models import AgentContext, UserProfile
from agent.runner import run_agent_stream, AgentEvent
from collections.abc import AsyncIterator
from pydantic_ai.messages import ModelMessage


async def reexplain_with_different_visual(
    concept: str,
    previous_widget_title: str,
    deps: AgentContext,
    history: list[ModelMessage],
) -> AsyncIterator[AgentEvent]:
    """
    Called when user signals confusion. Injects explicit instruction
    to use a different visual encoding.
    """
    # Mark this concept as unclear
    if concept not in deps.profile.unclear_topics:
        deps.profile.unclear_topics.append(concept)

    instruction = (
        f"The user still doesn't understand '{concept}' after seeing the "
        f"'{previous_widget_title}' visual. "
        "Choose a COMPLETELY DIFFERENT visual encoding — "
        "if the previous was flowchart → try illustrative SVG, "
        "if static SVG → try interactive HTML, "
        "if abstract → use a concrete real-world example. "
        "Do not regenerate anything similar to what was shown before."
    )

    async for event in run_agent_stream(instruction, deps, history):
        yield event


async def progressive_explain(
    topic: str,
    deps: AgentContext,
    history: list[ModelMessage],
) -> AsyncIterator[AgentEvent]:
    """
    Two-turn progressive disclosure: sparse overview first, then zoom.
    """
    # Turn 1: overview
    overview_prompt = (
        f"Give me an overview of '{topic}' with at most 3-4 high-level components. "
        "Keep it deliberately sparse — depth lives in the sendPrompt click handlers. "
        "Make every node's onclick question invite zooming into that specific component."
    )
    messages_after_overview: list[ModelMessage] = list(history)

    async for event in run_agent_stream(overview_prompt, deps, messages_after_overview):
        yield event
        if hasattr(event, 'new_messages') and event.new_messages:
            messages_after_overview = list(history) + event.new_messages

    # Turn 2: zoom into most complex component
    zoom_prompt = (
        f"Now zoom into the most important or most commonly misunderstood component of '{topic}'. "
        "The user has seen the overview — assume they have that context."
    )
    async for event in run_agent_stream(zoom_prompt, deps, messages_after_overview):
        yield event
```

### Pattern B: understanding quiz after visual

```python
async def concept_then_quiz(
    concept: str,
    deps: AgentContext,
    history: list[ModelMessage],
) -> AsyncIterator[AgentEvent]:
    """
    Explain with visual, then immediately ask a check question.
    """
    prompt = (
        f"Explain '{concept}' with an appropriate visual. "
        "After the visual, ask one follow-up question to check the user understood "
        "the mechanism — not just the definition. "
        "Phrase the question as if curious, not testing."
    )
    async for event in run_agent_stream(prompt, deps, history):
        yield event
```

---

## 9. Testing the agent

```python
# tests/test_visual_agent.py
import pytest
import asyncio
from agent.models import AgentContext, UserProfile
from agent.runner import run_agent_stream, WidgetReadyEvent, TextEvent


@pytest.mark.asyncio
async def test_agent_generates_widget_for_mechanism_question():
    deps = AgentContext(profile=UserProfile(subject="computer science"))
    events = []

    async for event in run_agent_stream(
        "Explain how attention works in transformers",
        deps=deps,
        message_history=[]
    ):
        events.append(event)

    widget_events = [e for e in events if isinstance(e, WidgetReadyEvent)]
    assert len(widget_events) >= 1, "Expected at least one widget for a mechanism question"

    widget = widget_events[0].params
    assert widget.widget_code, "widget_code must not be empty"
    assert "680" in widget.widget_code, "viewBox must be 680 wide"
    assert "#" not in widget.widget_code.split("fill=")[1][:20] if "fill=" in widget.widget_code else True, \
        "Should not have hardcoded fill hex colors"


@pytest.mark.asyncio
async def test_agent_returns_plain_text_for_factual_question():
    deps = AgentContext(profile=UserProfile(subject="history"))
    events = []

    async for event in run_agent_stream(
        "What year was the Eiffel Tower built?",
        deps=deps,
        message_history=[]
    ):
        events.append(event)

    widget_events = [e for e in events if isinstance(e, WidgetReadyEvent)]
    text_events = [e for e in events if isinstance(e, TextEvent)]

    assert len(widget_events) == 0, "No widget expected for a factual lookup"
    assert len(text_events) > 0, "Should have plain text response"


@pytest.mark.asyncio
async def test_agent_uses_html_for_interactive_concept():
    deps = AgentContext(profile=UserProfile(subject="optimization"))
    events = []

    async for event in run_agent_stream(
        "Show me how step size affects gradient descent convergence",
        deps=deps,
        message_history=[]
    ):
        events.append(event)

    widget_events = [e for e in events if isinstance(e, WidgetReadyEvent)]
    assert len(widget_events) >= 1

    widget = widget_events[0].params
    # Should be HTML (has a slider) not pure SVG
    assert "<input" in widget.widget_code or "<button" in widget.widget_code, \
        "Expected interactive HTML widget with controls for gradient descent"
```

---

## 10. Quick-reference — PydanticAI agent summary

```
visual_agent = Agent(
    model=AnthropicModel("claude-sonnet-4-20250514"),
    deps_type=AgentContext,
    system_prompt=build_system_prompt,   # called with fresh deps each run
    retries=2
)

@visual_agent.tool
async def show_widget(ctx, params: WidgetParams) -> str: ...
  # Validates widget params via Pydantic
  # Updates user profile (adds to topics_visualized)
  # Returns tool result string (actual rendering done by frontend)

run_agent_stream(user_text, deps, history)
  # Yields: TextEvent | WidgetStartEvent | WidgetReadyEvent | StreamEndEvent
  # TextEvent: forward as SSE text delta to browser
  # WidgetStartEvent: trigger loading card (early, from partial JSON)
  # WidgetReadyEvent: full params — browser renders in sandboxed iframe
  # StreamEndEvent: persist all_messages() to conversation store

FastAPI endpoint:
  POST /api/chat → StreamingResponse(event_stream(), media_type="text/event-stream")
  events mapped: text_delta | widget_start | widget_ready | conversation_id | error | [DONE]
```
