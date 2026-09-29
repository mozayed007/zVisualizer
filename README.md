# Visualizer Agent

A visual learning companion powered by **PydanticAI** and **Google Gemini**. Ask naturally, learn visually, and stay in the same chat flow. The agent composes each conversational turn into a reasoning panel, a main answer card, and a final visuals section — instead of mirroring raw tool-call order.

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              VISUALIZER AGENT                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  FRONTEND (React + Vite)          │  BACKEND (FastAPI + PydanticAI)         │
│                                   │                                         │
│  ┌─────────────────────────────┐  │  ┌─────────────────────────────────────┐│
│  │ WidgetFrame Component       │  │  │ Chat Service                        ││
│  │ • Sandboxed iframe renderer │  │  │ • PydanticAI Agent orchestration    ││
│  │ • PostMessage bridge        │◄─┼──┼─│ • SSE streaming to frontend       ││
│  │ • Auto-resize handling      │  │  │ • Widget payload validation         ││
│  │ • Design token injection    │  │  │ • Visual recovery on failures       ││
│  └─────────────────────────────┘  │  └─────────────────────────────────────┘│
│              ▲                    │              ▲                          │
│              │ widget_code        │              │ show_widget tool call    │
│              │ (SVG/HTML)         │              │                          │
│  ┌───────────┴────────────────┐   │  ┌───────────┴───────────────────────┐  │
│  │ App.tsx                    │   │  │ Agent (Gemini via PydanticAI)     │  │
│  │ • Chat message management  │   │  │ • System prompt with skill docs   │  │
│  │ • SSE event handling       │◄──┼──┤ • Structured output: WidgetPayload│  │
│  │ • Visual panel rendering   │   │  │ • Tool: show_widget               │  │
│  └────────────────────────────┘   │  └───────────────────────────────────┘  │
│                                   │                                         │
│  Design Tokens (designTokens.ts)  │  Widget Validator (widget_validator.py) │
│  • CSS variables (--color-*)      │  • Security & structure validation      │
│  • Color ramps (c-purple, etc.)   │  • SVG: viewBox, defs, text classes     │
│  • Typography (--font-sans)       │  • HTML: CDN allowlist, no localStorage │
│  • Dark mode support              │  • Enforces platform contract           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Dual agents

The backend loads two YAML-defined agents from `config/`:

| Agent ID | Config | Purpose |
|----------|--------|---------|
| `visualizer` (default) | `agent.visual.yaml` | Educational SVG/HTML widgets via `show_widget(title, loading_messages, widget_code)` |
| `svg` | `agent.svg.yaml` | Branded template population; `show_widget` also requires `template_id` (library relative path, e.g. `versus/compare.svg`) |

Select an agent per chat request via `agent_id`. The SVG agent validates every `widget_code` clone against the source template before render. Template files live under `data/SVGs_Organized/`.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+ (with npm, yarn, pnpm, or bun)
- Google AI Studio API key

### Environment Setup

1. **Copy the example environment file:**

   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` and add your API keys:**

   ```bash
   GOOGLE_API_KEY=your_google_ai_studio_key_here
   GEMINI_API_KEY=your_google_ai_studio_key_here  # Same as above
   ```

### Backend Setup

```bash
cd apps/backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend will be available at `http://localhost:8000`.

### Frontend Setup

```bash
cd apps/frontend

# Install dependencies (choose your package manager)
npm install
# or: yarn install
# or: pnpm install
# or: bun install

# Start development server
npm run dev
# or: yarn dev
# or: pnpm dev
# or: bun dev
```

The frontend will be available at `http://localhost:5173`.

## How the Visualizer Works

### 1. Widget Frontend Component

The `WidgetFrame` component (`apps/frontend/src/components/WidgetFrame.tsx`) is the heart of visual rendering:

#### Key Responsibilities

| Feature | Implementation |
|---------|---------------|
| **Sandboxed Rendering** | Each widget renders in an isolated `<iframe>` with `sandbox="allow-scripts allow-popups-to-escape-sandbox"` |
| **Auto-Resizing** | Uses `ResizeObserver` via postMessage to dynamically adjust iframe height based on content |
| **Design Token Injection** | Injects CSS variables, typography, and color ramps automatically into the iframe |
| **Bidirectional Communication** | `postMessage` bridge for: `prompt` (click-to-ask), `open_link` (secure navigation), `widget_error` (error handling) |
| **CSP Enforcement** | Content Security Policy restricts script sources to approved CDNs only |
| **SVG Export (v0.1)** | Download rendered SVGs with computed styles inlined for portability — preserves colors, markers, and CSS variable resolution |

#### Dependencies

```typescript
// Core widget rendering dependencies
import { useEffect, useMemo, useRef, useState } from 'react'
import { buildWidgetThemeCss } from '../lib/designTokens'
import type { WidgetPayload } from '../types'
```

The widget receives a `WidgetPayload` object:

```typescript
interface WidgetPayload {
  title: string              // snake_case identifier (e.g., "dense_vs_moe_architecture")
  loading_messages: string[] // 1-4 learner-facing loading messages
  widget_code: string       // Raw SVG or HTML fragment
  kind: 'svg' | 'html'      // Visual type discriminator
}
```

### 2. Backend Widget Support

The backend provides comprehensive widget lifecycle management through several layers:

#### A. Chat Service (`apps/backend/app/services/chat_service.py`)

The `ChatService` orchestrates the entire conversation flow:

```python
class ChatService:
    def __init__(self, ...):
        self.config = get_agent_config(self.settings)
        self._compiled_system_prompt = get_compiled_system_prompt(self.settings)
        self._widget_payload_cache = OrderedDict()  # LRU cache for widgets
```

**Key Features:**

- **PydanticAI Integration**: Uses `Agent[AgentDependencies, str]` for conversational responses
- **SSE Streaming**: Real-time event streaming via `text/event-stream`
- **Widget Caching**: LRU cache for validated widget payloads (max 100 items)
- **Visual Recovery**: Fallback visual generation when the primary agent fails to produce a widget
- **Rate Limiting**: Built-in Gemini API rate limiter with token estimation
- **Web Search & Web Fetch**: Agent can search the web and fetch content to augment responses with current information

#### B. Widget Validator (`apps/backend/app/agent/widget_validator.py`)

Strict validation ensures security and platform compliance:

**SVG Widget Rules:**

- Must start with `<svg>` directly (no wrapper `<style>` block)
- Requires `width='100%'` and `viewBox='0 0 680 H'`
- Must include `<defs>` with arrow marker `id='arrow'`
- Text elements need `dominant-baseline='central'` and class `t`/`ts`/`th`
- Connector paths with `marker-end='url(#arrow)'` must have `fill='none'` or `class='arr'`

**HTML Widget Rules:**

- Structure: `<style>` → visible content → CDN `<script>` → inline logic
- No `localStorage`, `sessionStorage`, `IndexedDB`, or `position:fixed`
- Allowed CDN hosts: `cdnjs.cloudflare.com`, `esm.sh`, `cdn.jsdelivr.net`, `unpkg.com`
- No `<link>` tags or document-level markup (`<!doctype`, `<html`, `<head`, `<body`)
- No HTML comments or CSS block comments

**Design Token Validation:**

- Only approved CSS variables: `--color-*`, `--font-*`, `--border-radius-*`, `--p`, `--s`, `--t`, `--bg2`, `--b`
- Only approved color ramp classes: `c-purple`, `c-teal`, `c-amber`, `c-coral`, `c-blue`, `c-green`, `c-pink`, `c-gray`, `c-red`

### 3. Agent Visual Creation Flow

The agent creates visuals through a sophisticated multi-step process:

```text
User Request
     │
     ▼
┌─────────────────────────┐
│ ChatService.stream_chat │
│  - Rate limit check     │
│  - Conversation load    │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ Primary Agent           │────►│ Visual Recovery Agent   │
│ (Gemini via PydanticAI) │     │ (On widget failure)     │
│                         │     │                         │
│ • System prompt with    │     │ • Dedicated visual      │
│   skill docs            │     │   generation prompt     │
│ • show_widget tool      │     │ • Structured output:    │
│ • Streaming response    │     │   VisualWidgetDraft     │
└──────────┬──────────────┘     └─────────────────────────┘
           │
           ▼
┌─────────────────────────┐
│ Widget Validator        │
│  - Security checks      │
│  - Structure validation │
│  - Design token verify  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ SSE Event Stream        │
│  - assistant_started    │
│  - thinking_delta       │
│  - text_delta           │
│  - widget_loading       │
│  - widget_ready         │
│  - assistant_done       │
└─────────────────────────┘
```

#### Agent Configuration (`config/agent.visual.yaml`)

The agent behavior is configured through YAML:

```yaml
agent:
  name: visual-learning-companion
  provider: google-gla
  model: gemini-3.1-flash-lite-preview
  subject_area: computer science, mathematics, data, and systems thinking
  learner_profile: motivated learners who benefit from visual intuition
  tone: warm, direct, encouraging, and Socratic

  tool:
    name: show_widget
    max_loading_messages: 4
    max_widget_code_chars: 75000

  prompt_contract:
    visual_requests_require_tool_call: true
    enforce_platform_requirements: true
    # ... extensive rules for visual generation

  source_docs:
    - path: skills/visualizer/SKILL.md
    - path: skills/visualizer/design-system.md
    - path: skills/visualizer/svg-generation.md
    - path: skills/visualizer/html-widgets.md
    - path: skills/visualizer/visual-routing.md
    - path: skills/visualizer/agent-prompts.md
    - path: skills/visualizer/text-fit-and-violations.md
    - path: skills/visualizer/imagination-patches-v2.md
    - path: docs/PLATFORM-REQUIREMENTS.md
```

#### Skill-Based Prompt System

The agent loads skill documentation as runtime context:

1. **SKILL.md** - Master skill contract and high-level behaviors
2. **design-system.md** - Color ramps, typography, spacing tokens
3. **svg-generation.md** - SVG structure, viewBox, arrow defs, text classes
4. **html-widgets.md** - HTML widget patterns, CDN usage, interactivity rules
5. **visual-routing.md** - When to use SVG vs HTML, routing decision logic
6. **agent-prompts.md** - System prompt construction rules
7. **text-fit-and-violations.md** - Text-fit constraints and violation detection
8. **imagination-patches-v2.md** - Cognitive-shape protocols for metaphor construction
9. **PLATFORM-REQUIREMENTS.md** - Platform enforcement requirements

#### Visual Routing Logic

The agent decides visual format based on content type:

| Content Type | Format | Example |
|-------------|--------|---------|
| Reference maps, architecture, containment | SVG | System architecture diagram |
| Comparisons (static) | SVG | Side-by-side concept comparison |
| Mechanisms without parameters | SVG | Illustrated process flow |
| Parameter-driven systems | HTML | Learning rate slider affecting gradient descent |
| Staged/stepped processes | HTML | Step-through algorithm visualization |
| Interactive controls needed | HTML | Adjustable frequency sine wave |

### 4. Design Token System

The frontend provides a comprehensive design token system (`apps/frontend/src/lib/designTokens.ts`):

#### CSS Variables (Auto-Injected)

```css
:root {
  /* Backgrounds */
  --color-background-primary: #ffffff;      /* Cards, main surfaces */
  --color-background-secondary: #f4f2eb;      /* Subtle containers */
  --color-background-tertiary: #eceae3;       /* Input backgrounds */
  --color-background-info: #e6f1fb;
  --color-background-success: #eaf3de;
  --color-background-warning: #faeeda;
  --color-background-danger: #faece7;

  /* Text */
  --color-text-primary: #1a1918;              /* Headings, primary text */
  --color-text-secondary: #5a5855;            /* Body text */
  --color-text-tertiary: #9b9890;             /* Muted text */
  --color-text-info: #185fa5;
  --color-text-success: #27500a;
  --color-text-warning: #633806;
  --color-text-danger: #712b13;

  /* Typography */
  --font-sans: 'Plus Jakarta Sans', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-serif: Georgia, serif;

  /* Spacing/Shorthand for SVG */
  --p: var(--color-text-primary);              /* Primary text color */
  --s: var(--color-text-secondary);          /* Secondary text */
  --t: var(--color-text-tertiary);            /* Tertiary/muted */
  --bg2: var(--color-background-secondary);   /* Secondary background */
  --b: var(--color-border-tertiary);          /* Border color */
}
```

#### Color Ramp Classes

Widgets can use semantic color classes:

```html
<!-- In SVG -->
<g class="c-purple">
  <rect class="box" x="10" y="10" width="100" height="60" />
  <text class="th" x="60" y="40">Title</text>
  <text class="ts" x="60" y="55">Subtitle</text>
</g>

<!-- In HTML -->
<div class="c-teal box">Content</div>
```

Available ramps: `c-purple`, `c-teal`, `c-amber`, `c-coral`, `c-blue`, `c-green`, `c-pink`, `c-gray`, `c-red`

Each ramp provides automatic light/dark mode adaptation via CSS custom properties.

### 5. Widget-to-Chat Communication

Widgets can communicate back to the chat interface:

```javascript
// Inside a widget's inline script
window.sendPrompt("Explain the backpropagation step");
window.openLink("https://example.com/resource");
```

These calls are caught by the `WidgetFrame` component and converted to:

- **sendPrompt**: Opens a new user message in the chat with the provided text
- **openLink**: Secure link opening (HTTPS only, with user confirmation)

## Project Structure

```text
visualizer-agent/
├── apps/
│   ├── backend/              # FastAPI + PydanticAI backend
│   │   ├── app/
│   │   │   ├── agent/        # Agent config, prompts, validators
│   │   │   ├── core/         # Settings, errors, logging
│   │   │   ├── models/       # Pydantic models (chat, widget)
│   │   │   ├── repositories/ # Conversation persistence (SQLite)
│   │   │   ├── services/     # Chat service, model catalog, rate limiting
│   │   │   └── main.py       # FastAPI entry point
│   │   ├── tests/            # Pytest test suite
│   │   ├── Dockerfile
│   │   └── pyproject.toml    # Python dependencies (source of truth)
│   │
│   └── frontend/             # React + Vite frontend
│       ├── src/
│       │   ├── components/   # Chat UI + WidgetFrame
│       │   ├── hooks/        # useTheme, useLearnerProfile
│       │   ├── lib/          # chatApi, designTokens, widgetBridge
│       │   ├── App.tsx       # Main chat interface
│       │   └── index.css     # Global styles
│       ├── Dockerfile
│       ├── index.html
│       ├── package.json
│       └── vite.config.ts
│
├── config/                   # Agent behavior configuration (visualizer + SVG)
├── data/                     # Local runtime data: SQLite store + SVG template library (gitignored)
├── docker/                   # Nginx config for the frontend container
├── docs/                     # Human-facing documentation
│   ├── current/              # Runtime reference docs
│   ├── PLATFORM-REQUIREMENTS.md
│   └── SSE-STREAM-PROTOCOL.md
├── skills/                   # Agent skill docs loaded at runtime
│   ├── svg/
│   └── visualizer/
├── scripts/                  # start / stop / check dev scripts
│
├── .dockerignore
├── .env.example              # Environment template
├── docker-compose.yml        # Production-style container stack
├── LICENSE
└── README.md                 # This file
```

## API Endpoints

### Chat Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/chat` | `POST` | Start a chat stream (SSE) |
| `/api/v1/models` | `GET` | List available Gemini models |
| `/api/v1/runtime` | `GET` | Get runtime status and configuration |

### Health Check

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | `GET` | Service health status |

## Development

### Backend Development

```bash
cd apps/backend

# Run tests
pytest

# Run with coverage
pytest --cov=app

# Type checking
mypy app

# Linting
ruff check .
ruff format .
```

### Frontend Development

```bash
cd apps/frontend

# Type checking
npm run typecheck

# Linting
npm run lint

# Build for production
npm run build
```

## Deployment

### Environment Variables for Production

```bash
# Required
GOOGLE_API_KEY=your_production_api_key
GEMINI_API_KEY=your_production_api_key

# Optional tuning
GOOGLE_MODEL_NAME=gemini-3.1-flash-lite-preview
GOOGLE_FALLBACK_MODEL_NAME=gemini-3.1-pro-preview
GOOGLE_MAX_OUTPUT_TOKENS=12288
GOOGLE_THINKING_LEVEL=medium
FRONTEND_ORIGIN=https://your-domain.com
VITE_API_BASE_URL=https://your-api-domain.com

# Optional security
CHAT_API_KEY=your-secret-api-key
VITE_CHAT_API_KEY=your-secret-api-key

# Optional database (defaults to data/conversations.db)
DATABASE_PATH=/path/to/conversations.db
```

### Docker Compose

The repository includes a production-style `docker-compose.yml` that builds:

- `backend`: FastAPI + PydanticAI app on internal port `8000`
- `frontend`: static Vite build served by Nginx on port `80`
- `conversations-data`: named volume for the SQLite conversation store

#### 1. Prepare environment

```bash
cp .env.example .env
```

Set at least:

```bash
GOOGLE_API_KEY=your_production_api_key
GEMINI_API_KEY=your_production_api_key
FRONTEND_ORIGIN=http://localhost
```

Recommended for Compose:

```bash
# Let the frontend use same-origin /api via the bundled Nginx reverse proxy
PUBLIC_VITE_API_BASE_URL=

# Optional published HTTP port
FRONTEND_PORT=80

# Optional shared API key between browser and backend
# CHAT_API_KEY=your-long-random-secret
# PUBLIC_VITE_CHAT_API_KEY=your-long-random-secret
```

#### 2. Build and start

```bash
docker compose up --build -d
```

The app will be available at `http://localhost` by default, or at `http://localhost:<FRONTEND_PORT>` if you change the published port.

#### 3. Stop the stack

```bash
docker compose down
```

To also remove the persisted SQLite volume:

```bash
docker compose down -v
```

#### Notes

- The frontend container proxies `/api/*` requests, including SSE and WebSocket traffic, to the backend container.
- SQLite data is persisted in the `conversations-data` named volume mounted at `/app/data`.
- If you deploy behind a real domain, set `FRONTEND_ORIGIN` to that public origin before starting the stack.

## License

MIT License — feel free to use, modify, and distribute.

## Acknowledgments

- **PydanticAI** for the robust agent framework
- **Google Gemini** for the underlying language model capabilities
- **Claude** for visual design inspiration and pedagogical patterns
