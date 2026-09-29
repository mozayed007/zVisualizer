# Platform Requirements — Frontend & Backend

## Purpose

This document specifies everything a development team must build to host the visual learning companion agent. It is separate from the skill documents because it describes the **host application infrastructure**, not the agent's behavior.

**Rule:** The agent generates code. This platform renders it. These two layers are strictly separated. The agent has no knowledge of the host application's internals — only the design token contracts specified in `design-system.md`.

---

# FRONTEND REQUIREMENTS

## 1. Chat UI — core structure

### 1.1 Message rendering

The chat UI must handle three content types in a single response:

```
Type 1: Plain text (streamed)
  → Render as Markdown or plain HTML
  → Stream token-by-token into the DOM as they arrive

Type 2: Visual widget (from tool call)
  → Show loading card while widget_code accumulates
  → Render widget in sandboxed iframe on tool call completion
  → Auto-size iframe to content height

Type 3: Mixed (text + widget in same response)
  → Interleave text and widgets in document order
  → Never hold back text while waiting for a widget
```

### 1.2 Streaming text rendering

```javascript
// Pattern: append text spans as tokens arrive, preserve existing DOM
function appendStreamingText(text, container) {
  // Option A: Simple append (works for plain text)
  container.insertAdjacentText('beforeend', text);

  // Option B: Markdown streaming (requires incremental markdown parser)
  // Use: https://github.com/nicholasgasior/streaming-markdown
  // Or: Buffer until sentence boundary, then parse+append
}
```

**Requirements:**
- Text must appear immediately as tokens arrive — do not buffer the full response
- Line breaks and paragraphs must render correctly mid-stream
- Code blocks must be syntax-highlighted after streaming completes (not during)

### 1.3 Loading card

While `widget_code` accumulates (during the tool call), show a loading card:

```html
<div class="widget-loading-card">
  <div class="loading-spinner"></div>
  <div class="loading-message" id="loading-msg">Building the visualization…</div>
</div>
```

Requirements:
- Cycle through `loading_messages` array every 1.8 seconds
- Replace with the rendered iframe when complete
- Loading card must have the same width and approximate height as a typical widget

```javascript
function showLoadingCard(loadingMessages, container) {
  const card = document.createElement('div');
  card.className = 'widget-loading-card';
  // ... render card

  let idx = 0;
  const interval = setInterval(() => {
    idx = (idx + 1) % loadingMessages.length;
    card.querySelector('.loading-message').textContent = loadingMessages[idx];
  }, 1800);

  // Return cleanup function
  return { card, stop: () => clearInterval(interval) };
}
```

---

## 2. Widget iframe — sandboxed renderer

### 2.1 Iframe creation

```javascript
function createWidgetIframe(widgetParams) {
  const { title, widget_code } = widgetParams;

  const iframe = document.createElement('iframe');
  iframe.sandbox = 'allow-scripts allow-popups-to-escape-sandbox';
  // DO NOT add allow-same-origin — that would give widget access to parent cookies/storage

  iframe.style.cssText = `
    width: 100%;
    border: none;
    display: block;
    border-radius: 10px;
    min-height: 80px;
  `;
  iframe.title = title; // accessibility

  return iframe;
}
```

### 2.2 Content injection order

The srcdoc must be assembled in this exact order:

```javascript
function buildSrcdoc(widgetCode, cssVariables) {
  const bridge = `<script>
    window.sendPrompt = function(text) {
      parent.postMessage({ type: 'prompt', text: text, widgetTitle: '${widgetTitle}' }, '*');
    };
    window.openLink = function(url) {
      parent.postMessage({ type: 'open_link', url: url }, '*');
    };
    // Auto-size: notify parent of height after load and on resize
    function notifyHeight() {
      parent.postMessage({
        type: 'iframe_resize',
        h: document.documentElement.scrollHeight
      }, '*');
    }
    window.addEventListener('load', notifyHeight);
    new ResizeObserver(notifyHeight).observe(document.body);
  <\/script>`;

  return [
    `<style>${cssVariables}</style>`,  // 1. Design tokens
    bridge,                             // 2. Communication bridge
    widgetCode                          // 3. Agent-generated code
  ].join('');
}
```

**Critical:** The CSS variables stylesheet and the bridge script MUST be prepended before widget code. The widget code references both.

### 2.3 Auto-sizing

```javascript
// In the parent page
const iframeMap = new WeakMap(); // iframe element → widget ID

window.addEventListener('message', event => {
  if (event.data?.type === 'iframe_resize') {
    // Find the iframe that sent this message
    const iframe = findIframeByWindow(event.source);
    if (iframe) {
      const newHeight = event.data.h + 8; // 8px buffer for borders
      if (Math.abs(parseInt(iframe.style.height) - newHeight) > 2) {
        iframe.style.height = newHeight + 'px';
      }
    }
  }
});

function findIframeByWindow(contentWindow) {
  return Array.from(document.querySelectorAll('iframe'))
    .find(iframe => iframe.contentWindow === contentWindow);
}
```

### 2.4 Content Security Policy for iframes

The parent page should serve this CSP header (or meta tag) to restrict iframe script sources:

```
Content-Security-Policy:
  default-src 'self';
  script-src 'unsafe-inline' https://cdnjs.cloudflare.com https://esm.sh https://cdn.jsdelivr.net https://unpkg.com;
  style-src 'unsafe-inline';
  img-src * data:;
  connect-src *;
  frame-src 'self'
```

For iframe-specific restrictions, use the `csp` attribute on the iframe element:
```javascript
iframe.setAttribute('csp', "script-src 'unsafe-inline' https://cdnjs.cloudflare.com https://esm.sh https://cdn.jsdelivr.net https://unpkg.com");
```

---

## 3. Design token injection

### 3.1 Static CSS with theme classes

The design token stylesheet is static: light tokens live on `:root`, dark overrides on `:root.dark`, with an OS-scheme fallback under `@media (prefers-color-scheme: dark)`. Bake the initial theme class into the iframe root (`<html class="dark">`) and update existing frames over `postMessage`.

```javascript
// Update all iframes when the color scheme changes.
// Widget iframes are sandboxed without allow-same-origin, so they have an
// opaque origin: iframe.contentDocument is null for the host, and theme
// changes must travel over postMessage. The bridge script applies
// `host_theme` by toggling the dark/light classes inside the frame.
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
  const theme = e.matches ? 'dark' : 'light';
  document.querySelectorAll('.widget-frame').forEach(iframe => {
    iframe.contentWindow?.postMessage({ type: 'host_theme', theme }, '*');
  });
});
```

### 3.2 Font loading in iframes

Iframes do not inherit fonts from the parent. The design token CSS must include the font import:

```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap');

/* OR: embed the font-face declarations directly if self-hosting fonts */
@font-face {
  font-family: 'Anthropic Sans';
  src: url('/fonts/anthropic-sans.woff2') format('woff2');
  font-weight: 400;
  font-display: swap;
}
```

---

## 4. PostMessage bridge — all message types

```javascript
window.addEventListener('message', event => {
  // Security: verify message comes from one of our iframes
  const knownIframes = document.querySelectorAll('iframe[data-widget]');
  const isFromKnownIframe = Array.from(knownIframes)
    .some(iframe => iframe.contentWindow === event.source);

  if (!isFromKnownIframe) return;

  switch (event.data?.type) {

    case 'prompt':
      // Learner clicked a sendPrompt() node
      handleLearnerPrompt({
        text: event.data.text,
        fromWidget: event.data.widgetTitle
      });
      break;

    case 'iframe_resize':
      // Widget is reporting its intrinsic height
      resizeIframe(event.source, event.data.h);
      break;

    case 'open_link':
      // Widget called openLink() — open in new tab after confirmation
      showLinkConfirmation(event.data.url);
      break;

    case 'widget_error':
      // Widget reported a JS error
      console.error('Widget error:', event.data.error, event.data.widgetTitle);
      showWidgetErrorState(event.source);
      break;

    case 'widget_interaction':
      // Optional: track learner interactions for analytics
      trackInteraction({
        widgetTitle: event.data.widgetTitle,
        element: event.data.element,
        value: event.data.value,
        timestamp: Date.now()
      });
      break;
  }
});
```

---

## 5. Quick-action chips

After every agent response, render contextual follow-up chips:

```javascript
function renderFollowUpChips(responseContext, chatContainer) {
  // Determine chip set based on response content
  const chips = [];

  if (responseContext.hadWidget) {
    chips.push('Make it interactive');
    chips.push('Show a real-world example');
    chips.push('What breaks if this goes wrong?');
    chips.push('Ask me a question about this');
  } else {
    chips.push('Show me this visually');
    chips.push('Walk me through step by step');
    chips.push('Compare this to something I know');
  }

  const row = document.createElement('div');
  row.className = 'chip-row';
  chips.forEach(text => {
    const chip = document.createElement('button');
    chip.className = 'chip';
    chip.textContent = text;
    chip.onclick = () => {
      row.remove(); // remove chips after selection
      handleLearnerPrompt({ text });
    };
    row.appendChild(chip);
  });

  chatContainer.appendChild(row);
}
```

---

## 6. Accessibility requirements

```
- All iframes must have a title attribute (set from widget title)
- Loading cards must have role="status" and aria-live="polite"
- Widget iframes should have tabindex="0" to be keyboard-focusable
- Color contrast: all text must meet WCAG AA (4.5:1 for body text, 3:1 for large text)
- prefers-reduced-motion must suppress all CSS animations in injected CSS
- Focus must not be trapped inside iframes after they render
```

---

# BACKEND REQUIREMENTS

## 7. API proxy server

**Never expose the Anthropic API key to the browser.** All API calls must be proxied through your backend.

### 7.1 Proxy endpoint specification

```
POST /api/chat
Content-Type: application/json

Request body:
{
  "messages": [...],          // Full conversation history (array of role/content pairs)
  "subject": "string",        // Optional: subject area for system prompt selection
  "learnerProfile": {...}     // Optional: accumulated learner profile data
}

Response:
Content-Type: text/event-stream  // SSE — streams Anthropic API response
X-Widget-Detected: true/false    // Optional header for frontend optimization
```

### 7.2 Proxy implementation (Node.js / Express)

```javascript
import Anthropic from '@anthropic-ai/sdk';
import express from 'express';

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const router = express.Router();

router.post('/chat', async (req, res) => {
  const { messages, subject, learnerProfile } = req.body;

  // Validate input
  if (!Array.isArray(messages) || messages.length === 0) {
    return res.status(400).json({ error: 'messages array required' });
  }

  // Rate limiting check (see §8)
  const userId = req.user?.id || req.ip;
  if (await isRateLimited(userId)) {
    return res.status(429).json({ error: 'Rate limit exceeded', retryAfter: 60 });
  }

  // Build system prompt from learner profile
  const systemPrompt = buildSystemPrompt(subject, learnerProfile);

  // Set up SSE
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no' // prevent nginx buffering
  });

  try {
    const stream = await client.messages.stream({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 8192,
      system: systemPrompt,
      tools: [SHOW_WIDGET_TOOL],
      messages: sanitizeMessages(messages)
    });

    // Pipe the stream to the SSE response
    for await (const event of stream) {
      res.write(`data: ${JSON.stringify(event)}\n\n`);
    }

    res.write('data: [DONE]\n\n');
    res.end();

  } catch (err) {
    console.error('Anthropic API error:', err);
    // Send error event in SSE format so frontend can handle it
    res.write(`data: ${JSON.stringify({ type: 'error', error: err.message })}\n\n`);
    res.end();
  }
});

function sanitizeMessages(messages) {
  // Strip any client-injected system-role messages
  // Validate message structure
  return messages.filter(m =>
    ['user', 'assistant'].includes(m.role) &&
    (typeof m.content === 'string' || Array.isArray(m.content))
  ).map(m => ({
    role: m.role,
    content: typeof m.content === 'string'
      ? m.content.slice(0, 50000) // cap individual message length
      : m.content
  }));
}
```

### 7.3 Python / FastAPI alternative

```python
import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json

client = anthropic.Anthropic()
app = FastAPI()

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])

    async def event_stream():
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=build_system_prompt(body.get("subject"), body.get("learnerProfile")),
            tools=[SHOW_WIDGET_TOOL],
            messages=messages
        ) as stream:
            for event in stream:
                data = json.dumps(event.model_dump() if hasattr(event, 'model_dump') else event)
                yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## 8. Rate limiting

```javascript
// Per-user rate limiting (Redis-backed recommended for multi-instance)
const RATE_LIMITS = {
  anonymous: { requests: 10, window: 3600 },   // 10/hour for unauthenticated
  free_tier:  { requests: 50, window: 3600 },   // 50/hour for free accounts
  paid_tier:  { requests: 500, window: 3600 },  // 500/hour for paid accounts
  admin:      { requests: Infinity, window: 0 }
};

// Also implement per-request token estimation to prevent abuse
const MAX_HISTORY_TOKENS = 100000; // Truncate history if conversation gets too long

function truncateHistory(messages, maxTokens) {
  // Keep the most recent messages that fit within the token budget
  // Always preserve the first message (user's initial question)
  // Rough estimate: 4 chars per token
  let totalChars = 0;
  const kept = [];

  for (let i = messages.length - 1; i >= 0; i--) {
    const content = typeof messages[i].content === 'string'
      ? messages[i].content
      : JSON.stringify(messages[i].content);
    totalChars += content.length;
    if (totalChars > maxTokens * 4) break;
    kept.unshift(messages[i]);
  }

  return kept.length > 0 ? kept : [messages[messages.length - 1]];
}
```

---

## 9. Conversation persistence

```javascript
// Conversation schema
{
  id: 'conv_abc123',
  userId: 'user_xyz',
  subject: 'machine_learning',
  createdAt: '2025-01-15T10:00:00Z',
  updatedAt: '2025-01-15T11:30:00Z',
  messages: [
    {
      role: 'user',
      content: 'Explain attention in transformers',
      timestamp: '2025-01-15T10:00:00Z'
    },
    {
      role: 'assistant',
      content: [
        { type: 'text', text: 'Let me show you...' },
        {
          type: 'tool_use',
          id: 'toolu_123',
          name: 'show_widget',
          input: {
            title: 'attention_mechanism',
            loading_messages: ['Drawing the attention fan...'],
            widget_code: '<svg...>...</svg>'  // store the full generated code
          }
        }
      ],
      timestamp: '2025-01-15T10:00:05Z'
    }
  ],
  learnerProfile: {
    conceptsSeen: ['attention_mechanism', 'transformer_architecture'],
    strugglingWith: [],
    interactionCount: 12
  }
}
```

**Storage recommendations:**
- PostgreSQL (JSONB column for messages) — best for structured queries on learner data
- MongoDB — easiest for schema-flexible message storage
- Redis — cache recent conversation turns for fast retrieval (TTL: 24 hours)

---

## 10. Widget code storage and replay

Store every generated `widget_code` string. This enables:
- Replay: re-render a widget from conversation history without re-calling the API
- Analytics: analyze what types of visuals were generated most
- Caching: return cached widget for identical concept+level combinations

```javascript
// Widget deduplication cache
async function getCachedWidget(concept, level, subject) {
  const cacheKey = `widget:${subject}:${concept}:${level}`;
  const cached = await redis.get(cacheKey);
  if (cached) return JSON.parse(cached);
  return null;
}

async function cacheWidget(concept, level, subject, widgetParams) {
  const cacheKey = `widget:${subject}:${concept}:${level}`;
  await redis.setex(cacheKey, 86400 * 7, JSON.stringify(widgetParams)); // 7-day TTL
}
```

---

## 11. Analytics — what to track

```javascript
// Track these events for product improvement
const EVENTS = {
  // Widget events
  WIDGET_RENDERED: 'widget.rendered',          // { widgetTitle, subject, durationMs }
  WIDGET_CLICKED: 'widget.node_clicked',        // { widgetTitle, promptText, subject }
  WIDGET_RENDER_FAILED: 'widget.render_failed', // { widgetTitle, errorMsg }

  // Learning events
  CONCEPT_SEEN: 'learning.concept_seen',        // { concept, subject, visualType }
  FOLLOW_UP_ASKED: 'learning.follow_up',        // { fromWidget, question, subject }
  CONFUSION_SIGNAL: 'learning.confusion',       // { concept, subject } (repeated question)

  // Session events
  SESSION_STARTED: 'session.started',
  SESSION_ENDED: 'session.ended',               // { duration, conceptCount, clickCount }
  CHIP_CLICKED: 'session.chip_clicked',         // { chipText }
};

// Most valuable metric: "visual interaction rate"
// = (widget node clicks) / (widgets rendered)
// High rate → visuals are engaging. Low rate → visuals might be confusing or not interactive enough.
```

---

## 12. Security checklist

```
Iframe sandbox:
  ✓ sandbox="allow-scripts allow-popups-to-escape-sandbox"
  ✗ NEVER add allow-same-origin (would expose parent cookies/storage)
  ✗ NEVER add allow-top-navigation (would allow widget to navigate parent)

PostMessage:
  ✓ Verify event.source is a known iframe before processing
  ✓ Never eval() content from postMessage
  ✓ Validate event.data shape before acting on it

API key:
  ✓ Always proxied through backend — never in browser bundle
  ✓ Rotated regularly
  ✓ Different keys for dev/staging/production

Content:
  ✓ Sanitize user inputs before including in messages
  ✓ Cap message length at 50,000 characters
  ✓ Validate messages array length (max 200 turns)
  ✓ Strip any <script> tags from user-provided content before sending to API

Widget code:
  ✓ Store widget code server-side — never trust client-provided widget code
  ✗ NEVER execute widget code received from a client request
  ✓ Widget code is only generated by the API, never modified by the client
```

---

## 13. Infrastructure — recommended stack

```
Frontend:
  Framework:      Next.js 14+ (App Router) or plain HTML+JS
  Styling:        CSS Modules or Tailwind (for host UI — not widgets)
  Streaming:      Native fetch + ReadableStream (no library needed)
  State:          React useState / Zustand (conversation history)
  Fonts:          Google Fonts (Plus Jakarta Sans + JetBrains Mono) or self-hosted

Backend:
  Runtime:        Node.js 20+ or Python 3.11+
  Framework:      Express / Fastify (Node) or FastAPI (Python)
  Database:       PostgreSQL 15+ with JSONB
  Cache:          Redis 7+
  Auth:           Supabase Auth / Auth0 / Clerk (JWT-based)
  Hosting:        Vercel / Railway / Render / AWS (any with SSE support)

Key hosting requirement:
  The backend MUST support long-lived HTTP connections for SSE streaming.
  Serverless functions with hard timeout limits (< 30s) are not suitable.
  Use: Railway, Render, Fly.io, AWS ECS, Google Cloud Run (min-instances=1)
  Avoid: Vercel Serverless Functions (60s max), Netlify Functions (10s max)

CDN / Edge:
  Disable response buffering for /api/chat route — SSE requires immediate flush
  nginx: proxy_buffering off; proxy_read_timeout 300s;
  CloudFront: disable compression on streaming endpoints
```

---

## 14. Environment variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...          # Never commit, always from environment

# Database
DATABASE_URL=postgresql://...
REDIS_URL=redis://...

# Auth
JWT_SECRET=...
AUTH_PROVIDER_SECRET=...

# Optional: analytics
POSTHOG_API_KEY=...
MIXPANEL_TOKEN=...

# Optional: monitoring
SENTRY_DSN=...

# Feature flags
ENABLE_WIDGET_CACHE=true              # Cache generated widgets by concept
ENABLE_LEARNER_PROFILES=true          # Track per-learner concept history
MAX_CONVERSATION_TURNS=200            # Cap conversation length
WIDGET_RENDER_TIMEOUT_MS=30000        # Timeout for widget load
```
