# SSE stream protocol — visualizer-agent backend

This document is the **authoritative contract** for `POST /api/chat` when `Content-Type: text/event-stream`. It describes the JSON envelope this app emits (Gemini + PydanticAI), not the raw Anthropic Messages API stream.

## Transport

- Each event is one SSE frame: `data: <JSON>\n\n`
- The stream **always** ends with a terminal sentinel: `data: [DONE]\n\n` (compatible with common SSE clients and [PLATFORM-REQUIREMENTS.md](PLATFORM-REQUIREMENTS.md))
- Clients should still handle connection close if the sentinel is missing (e.g. abrupt disconnect)

## Request body (`ChatRequest`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | yes | Latest user message (trimmed, non-empty) |
| `conversation_id` | string \| null | no | Omit or null to start a new conversation |
| `subject` | string \| null | no | Optional subject hint |
| `learner_profile` | object \| null | no | Merged when `ENABLE_LEARNER_PROFILES` is true |
| `from_widget` | string \| null | no | Snake_case widget `title` when the turn is a follow-up from that visual (chips / `sendPrompt`) |

If `conversation_id` is set but unknown, the server responds with **404** before streaming (see [PLATFORM-REQUIREMENTS.md](PLATFORM-REQUIREMENTS.md)).

## Event envelope

Every line is JSON with:

```json
{
  "type": "<event_type>",
  "data": { }
}
```

`data` may be an empty object.

## Event types (in typical order)

| `type` | `data` fields | Purpose |
|--------|----------------|---------|
| `status` | `stage`, `label`, `detail`, `state` | Lifecycle / UX status (`active`, `completed`, `error`) |
| `conversation` | `conversationId`, `subject` | Persist this id for follow-up requests |
| `assistant_started` | (empty) | Assistant turn UI shell |
| `text_delta` | `text` | Incremental assistant prose |
| `thinking_delta` | `text` | Model thinking stream (when supported) |
| `widget_loading` | `loadingMessages`, optional `toolCallId` | Show loading card |
| `widget_ready` | `widget` (see below), `followUpChips` | Render iframe |
| `assistant_done` | `followUpChips` | End of successful turn; show chips |
| `error` | `title`, `detail`, optional `details` | Failure |
| `done` | (empty) | Application-level stream complete |

### `widget` object (`widget_ready`)

- `title` — snake_case id
- `loading_messages` — string[]
- `widget_code` — SVG or HTML fragment (validated server-side)
- `kind` — `"svg"` \| `"html"`

## Auth (optional)

When `CHAT_API_KEY` is set in the environment, clients must send:

`Authorization: Bearer <CHAT_API_KEY>`

## Rate limits

Limits are applied per **client id** (derived from `X-Forwarded-For` or the direct client IP) using the configured RPM / TPM / RPD and token budget settings.

## Relation to other docs

- [docs/frontend-widget-integration.md](frontend-widget-integration.md) — UI patterns; map these events in the client (this protocol uses `widget_loading` / `conversation`, not `widget_start` / `conversation_id`).
- [docs/pydantic-ai-visual-agent.md](pydantic-ai-visual-agent.md) — conceptual PydanticAI shapes; wire format is defined **here** for this repo.
