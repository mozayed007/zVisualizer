---
name: current-agent-runtime-reference
description: Exact runtime reference for the visualizer agent, including identity, prompt context, preloaded documents, model-visible tools, validation rules, streaming events, and host-side behavior.
---

# Current Agent Runtime Reference

## What the agent is

The agent in this repository is a **backend PydanticAI agent** that uses the **Gemini Developer API** through PydanticAI's Google integration, which is backed by the official `google-genai` SDK, to answer learner questions with:

- normal explanatory text
- optionally one validated visual widget
- follow-up suggestion chips

It is not a frontend agent and it is not a multi-tool general assistant. The browser only renders what the backend agent produces.

The main runtime lives in:

- `apps/backend/app/services/chat_service.py`
- `apps/backend/app/agent/prompt.py`
- `apps/backend/app/agent/widget_validator.py`
- `config/agent.visual.yaml`

## Agent identity

The agent identity comes from `config/agent.visual.yaml`:

- Name: `visual-learning-companion`
- Provider: `google-gla`
- Default configured model: `gemini-3.1-flash-lite-preview`
- Subject area: `computer science, mathematics, data, and systems thinking`
- Tone: `warm, direct, encouraging, and Socratic`

Response-style defaults:

- ask at most one comprehension check question
- prefer a visual when it materially helps
- never stack visuals without connecting prose

## Model configuration

The agent uses Google Gemini models via the Gemini Developer API. Models are discovered dynamically from `https://generativelanguage.googleapis.com/v1beta/models` and cached for 5 minutes.

### Default model

Configured in `config/agent.visual.yaml`:
- Default: `gemini-3.1-flash-lite-preview`

Environment overrides (in order of precedence):
1. `GOOGLE_MODEL_NAME` / `GEMINI_MODEL_NAME` env var
2. `model` field in `config/agent.visual.yaml`
3. Fallback: `gemini-3.1-flash-lite-preview`

### Available Gemini models (as of April 2026)

The following models are available through the Gemini API and discovered dynamically:

| Model | Description |
|-------|-------------|
| `gemini-3.1-flash-lite-preview` | Fast, cost-effective default |
| `gemini-3.1-flash-preview` | Balanced performance |
| `gemini-3.1-pro-preview` | Highest quality, used for fallback/recovery |

New Gemini models are automatically available once Google adds them to the API.

### Fallback and recovery models

Environment variables configure fallback behavior:

- `GOOGLE_FALLBACK_MODEL_NAME` - Used when primary model returns 5xx errors (default: `gemini-3.1-pro-preview`)
- `GOOGLE_VISUAL_RECOVERY_MODEL_NAME` - Stronger model for visual generation recovery (default: `gemini-3.1-pro-preview`)

### Gemma 4 models (edge/on-device)

**Important:** Gemma 4 models (E2B - 2B parameters, E4B - 4B parameters) are **not** available through the Gemini API. They are open-weights models designed for on-device inference via:

- [LiteRT-LM](https://ai.google.dev/edge/litert-lm) - Local inference library
- [Google AI Edge Gallery](https://github.com/google-ai-edge/gallery) - Mobile app for experimenting
- Android AICore - System-wide on-device model access

To use Gemma 4 models, you would need to:
1. Run models locally via LiteRT-LM (Raspberry Pi 5, mobile devices, desktop)
2. Set up a local inference endpoint
3. Configure the agent to use that local endpoint instead of the Gemini API

See: https://ai.google.dev/edge for more information on edge deployment.

## What the agent does

At runtime, the main chat agent can:

- answer in plain text
- decide whether a visual is needed
- call `show_widget(...)` to emit one SVG or HTML teaching widget
- update learner state like `concepts_seen`
- stream text, reasoning, status, and widget events over SSE
- recover if a visual was requested but the main pass failed to produce one

There is also a second, narrower agent used only for fallback visual generation. That one returns structured widget data instead of prose.

## Model-visible tools

The main chat agent exposes exactly **one tool** to the model:

- `show_widget(title, loading_messages, widget_code)`

Tool contract:

- `title` must be short `snake_case`
- `loading_messages` must contain 1 to 4 short strings
- `widget_code` must be raw SVG or raw HTML fragment

Important distinction:

- The **LLM/tool surface** is only `show_widget`
- The **host platform** later renders the widget in a sandboxed iframe
- The iframe also gets `sendPrompt()` and `openLink()` injected, but those are widget-runtime bridge functions, not LLM tools

The fallback visual agent exposes **no callable tool**. It returns a structured `VisualWidgetDraft` object that is validated server-side before being sent to the frontend.

## What context is preloaded before each run

The agent gets context from three layers.

### 1. Static compiled prompt

Built in `apps/backend/app/agent/prompt.py` from:

- `config/agent.visual.yaml`
- hard-coded runtime rules in `prompt.py`
- excerpted lines from configured source docs

This compiled prompt includes:

- agent identity and tone
- visual-routing rules
- SVG rules
- HTML widget rules
- design-token rules
- pedagogy rules
- `show_widget` usage instructions
- source-doc excerpts by default, or full `docs/skill/*.md` bodies when `AGENT_LOAD_FULL_SKILL_DOCS_ON_SESSION_START=true`
- Google-specific thinking config with `include_thoughts=true` so Gemini reasoning deltas can stream when the model supports them

The compiled prompt is built from the active backend settings when `ChatService` starts, so prompt/config/env edits still require a process restart to reliably take effect.

### 2. Source-doc loading

Configured source docs:

- `docs/skill/SKILL.md`
- `docs/skill/design-system.md`
- `docs/skill/svg-generation.md`
- `docs/skill/html-widgets.md`
- `docs/skill/visual-routing.md`
- `docs/skill/agent-prompts.md`
- `docs/PLATFORM-REQUIREMENTS.md`

Important nuance:

- the config says source docs are mandatory
- by default the runtime does **not** inject full documents
- `prompt.py` extracts **keyword-filtered excerpts** from each file
- the main system prompt takes up to **12 lines per file**
- the fallback visual prompt takes up to **8 lines per file**
- if `AGENT_LOAD_FULL_SKILL_DOCS_ON_SESSION_START=true`, files under `docs/skill/*.md` are embedded as full text in both compiled prompts
- non-skill source docs such as `docs/PLATFORM-REQUIREMENTS.md` stay on the excerpt path

So excerpt mode is the default, and full-text loading is an opt-in path for skill markdown only.

### 3. Dynamic per-request context

Injected at runtime in `ChatService.get_agent()`:

- conversation subject
- `concepts_seen`
- `struggling_with`
- learner `interaction_count`
- latest user message
- `from_widget` if the user clicked a widget follow-up
- whether the request heuristically requires a visual

The visual-needed heuristic currently triggers on words like:

- `visual`
- `diagram`
- `show me`
- `compare`
- `architecture`
- `flow`
- `interactive`
- `simulation`

### 4. Conversation history

The agent also receives persisted multi-turn message history from SQLite:

- stored as PydanticAI message JSON
- trimmed to fit the configured history token budget before each run

## What is enforced outside the model

The backend does not trust raw tool output. Every widget is validated in `apps/backend/app/agent/widget_validator.py`.

Server-side validation enforces:

- snake_case titles
- loading message count limits
- max widget size
- no document wrappers like `<html>` or `<!doctype>`
- no HTML comments
- SVG width must be `100%`
- SVG `viewBox` must be `0 0 680 H`
- SVG must include arrow defs
- every SVG `<text>` must use `dominant-baseline='central'`
- SVG text must use injected classes `t`, `ts`, or `th`
- HTML must begin with `<style>`
- HTML order must be style, content, CDN scripts, then inline logic
- only approved CDN hosts are allowed
- no `localStorage`, `sessionStorage`, `IndexedDB`, or `position: fixed`
- only approved design tokens and `c-{ramp}` classes may be used

If validation fails, the tool call is rejected with `ModelRetry`, and the model gets a corrective error message telling it to regenerate a compliant widget.

## Frontend/host responsibilities

The frontend is responsible for rendering, not reasoning.

Key host behavior:

- `POST /api/chat` streams SSE events
- frontend accumulates `text_delta`, `thinking_delta`, `widget_loading`, `widget_ready`, `assistant_done`, and `status`
- widgets render in `WidgetFrame`
- each widget is loaded into a sandboxed iframe
- the iframe receives injected design tokens plus bridge functions

Injected bridge functions:

- `sendPrompt(text)`
- `openLink(url)`

Widget messages sent back to the parent include:

- `prompt`
- `iframe_resize`
- `open_link`
- `widget_error`

## Runtime flow

1. Frontend sends `ChatRequest` to `POST /api/chat`.
2. Backend loads or creates a conversation.
3. Backend builds the request context and trims history.
4. Main PydanticAI agent streams text/thinking/tool activity.
5. If `show_widget` is called, the backend validates the widget payload.
6. Backend emits `widget_ready` with the validated widget plus follow-up chips.
7. Frontend renders the widget in a sandboxed iframe.
8. If the model failed to produce a required visual, recovery runs.
9. Conversation history is persisted.

## SSE events the frontend sees

Common events emitted by the backend:

- `status`
- `conversation`
- `assistant_started`
- `thinking_delta`
- `text_delta`
- `widget_loading`
- `widget_ready`
- `assistant_done`
- `error`
- `done`

## Follow-up chips

Configured in `config/agent.visual.yaml`.

If a widget was rendered:

- Add a control that maps to a real parameter
- Show a real-world example
- What breaks if this goes wrong?
- Ask me a question about this
- Zoom into the most complex part

If no widget was rendered:

- Show me this visually
- Walk me through step by step
- Compare to something I know
- Step through this one stage at a time
- Zoom into the most complex part

## Recovery and fallback behavior

If a user clearly asked for a visual and the main run did not produce one:

- the service runs a visual-recovery pass that tells the main agent to call `show_widget` exactly once
- if that still fails, it can switch to a stronger fallback model
- if that still fails, a dedicated visual-only agent generates a structured widget draft
- the same validator is applied before anything reaches the frontend

## What the agent is not

This runtime agent does **not** currently have:

- filesystem tools
- web browsing tools
- shell tools
- MCP tool access
- arbitrary code execution
- database query tools exposed to the model

Those capabilities may exist for developers working on the repo, but they are **not** part of the model-visible runtime tool surface in this app.

## Known caveats

- The YAML flags `source_docs_are_mandatory`, `source_docs_override_defaults`, and `never_treat_skill_docs_as_optional` are defined in config, but the runtime behavior is mostly expressed through prompt text rather than separate branching logic.
- The phrase "load all skill files" is stronger than the actual implementation; the runtime injects filtered excerpts, not full file contents.
- Compiled prompts are cached, so prompt/config updates are not hot-reloaded inside the same process.

## Source of truth

If this document and the code ever disagree, trust these files first:

- `config/agent.visual.yaml`
- `apps/backend/app/agent/prompt.py`
- `apps/backend/app/services/chat_service.py`
- `apps/backend/app/agent/widget_validator.py`
- `apps/backend/app/core/settings.py`
- `apps/frontend/src/App.tsx`
- `apps/frontend/src/components/WidgetFrame.tsx`
