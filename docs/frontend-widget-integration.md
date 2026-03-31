---
name: frontend-widget-integration
description: Step-by-step implementation guide for adding the visual widget rendering system to an existing frontend. Assumes an existing React, Vue, Svelte, or plain-JS chat UI is already in place. Covers the WidgetRenderer component in full, the complete injected CSS stylesheet with all 9 color ramps and dark-mode variants, iframe sandbox setup, srcdoc assembly, auto-sizing via ResizeObserver, the postMessage bridge, loading card lifecycle, streaming text interleaving, quick-action chips, and all CSS classes needed to match claude.ai visual quality. Use this document when building the frontend widget layer.
---

# Frontend Widget Integration — Implementation Guide

## Assumptions

- You have an existing chat UI that renders user and assistant messages
- You already handle the SSE stream from your backend and have `text` tokens flowing into the DOM
- You need to add the widget rendering layer on top of what exists
- Framework-agnostic patterns are shown first; React hooks follow

---

## 1. What to build — component map

```
ChatMessage
  ├── TextContent          (existing — streaming prose)
  ├── WidgetSlot           (NEW — where widgets appear between text blocks)
  │   ├── WidgetLoadingCard (shown while widget_code accumulates)
  │   └── WidgetFrame      (iframe that replaces loading card on completion)
  └── ChipRow              (NEW — follow-up quick-action buttons)
```

The key insight: **text and widgets interleave**. One assistant response can have prose, then a widget, then more prose. Your stream consumer must maintain a cursor that tracks whether the current position in the response is inside a tool call block or in a text block.

---

## 2. Stream consumer — detecting tool calls

Your existing text streaming probably handles `content_block_delta` events with `text_delta` type. You need to extend it to also handle `tool_use` blocks.

```typescript
// types.ts
interface StreamCursor {
  type: 'text' | 'tool_use' | 'idle';
  toolName?: string;
  toolJson: string;      // accumulates partial_json deltas
  textBuffer: string;    // accumulates text for the current text block
}

// streamConsumer.ts
export async function consumeStream(
  response: Response,
  handlers: {
    onTextDelta: (text: string) => void;
    onToolStart: (toolName: string, loadingMessages: string[]) => void;
    onToolComplete: (toolName: string, params: WidgetParams) => void;
    onStreamEnd: () => void;
  }
) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const cursor: StreamCursor = { type: 'idle', toolJson: '', textBuffer: '' };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';  // keep incomplete last line

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6);
      if (raw === '[DONE]') { handlers.onStreamEnd(); return; }

      let event: AnthropicSSEEvent;
      try { event = JSON.parse(raw); }
      catch { continue; }

      switch (event.type) {

        case 'content_block_start':
          if (event.content_block.type === 'tool_use') {
            cursor.type = 'tool_use';
            cursor.toolName = event.content_block.name;
            cursor.toolJson = '';
            // We'll call onToolStart once we have loading_messages from partial_json
          }
          if (event.content_block.type === 'text') {
            cursor.type = 'text';
          }
          break;

        case 'content_block_delta':
          if (cursor.type === 'text' && event.delta.type === 'text_delta') {
            handlers.onTextDelta(event.delta.text);
          }
          if (cursor.type === 'tool_use' && event.delta.type === 'input_json_delta') {
            cursor.toolJson += event.delta.partial_json ?? '';

            // Try to extract loading_messages early for the loading card
            // They appear near the start of the JSON, so we can often parse them
            // before widget_code arrives
            if (!cursor.loadingStarted) {
              tryExtractLoadingMessages(cursor.toolJson, (msgs) => {
                cursor.loadingStarted = true;
                handlers.onToolStart(cursor.toolName!, msgs);
              });
            }
          }
          break;

        case 'content_block_stop':
          if (cursor.type === 'tool_use' && cursor.toolJson) {
            try {
              const params: WidgetParams = JSON.parse(cursor.toolJson);
              // If loading card wasn't started yet (no loading_messages parsed early),
              // start it now and immediately complete it
              if (!cursor.loadingStarted) {
                handlers.onToolStart(cursor.toolName!, params.loading_messages ?? ['Building…']);
              }
              handlers.onToolComplete(cursor.toolName!, params);
            } catch (e) {
              console.error('Failed to parse tool JSON', e);
            }
          }
          cursor.type = 'idle';
          cursor.toolJson = '';
          cursor.loadingStarted = false;
          break;
      }
    }
  }

  handlers.onStreamEnd();
}

// Extract loading_messages from partial JSON before it's complete
// Works because loading_messages appears early in the JSON structure
function tryExtractLoadingMessages(
  partialJson: string,
  onFound: (msgs: string[]) => void
) {
  // Match the loading_messages array even if the JSON isn't complete
  const match = partialJson.match(/"loading_messages"\s*:\s*(\[[^\]]+\])/);
  if (match) {
    try {
      const msgs = JSON.parse(match[1]);
      if (Array.isArray(msgs) && msgs.length > 0) onFound(msgs);
    } catch {}
  }
}
```

---

## 3. WidgetLoadingCard — full implementation

```typescript
// WidgetLoadingCard.ts
export interface LoadingCardHandle {
  replace: (iframe: HTMLIFrameElement) => void;
  destroy: () => void;
}

export function createWidgetLoadingCard(
  loadingMessages: string[],
  container: HTMLElement
): LoadingCardHandle {
  const card = document.createElement('div');
  card.className = 'widget-loading-card';
  card.setAttribute('role', 'status');
  card.setAttribute('aria-live', 'polite');
  card.setAttribute('aria-label', 'Visual loading');

  card.innerHTML = `
    <div class="widget-loading-inner">
      <div class="widget-loading-dots">
        <span></span><span></span><span></span>
      </div>
      <div class="widget-loading-message">${escapeHtml(loadingMessages[0] ?? 'Building…')}</div>
    </div>
  `;
  container.appendChild(card);

  let msgIdx = 0;
  const interval = setInterval(() => {
    if (loadingMessages.length > 1) {
      msgIdx = (msgIdx + 1) % loadingMessages.length;
      const el = card.querySelector('.widget-loading-message');
      if (el) el.textContent = loadingMessages[msgIdx];
    }
  }, 1800);

  return {
    replace(iframe: HTMLIFrameElement) {
      clearInterval(interval);
      card.replaceWith(iframe);
    },
    destroy() {
      clearInterval(interval);
      card.remove();
    }
  };
}
```

### Loading card CSS

```css
.widget-loading-card {
  width: 100%;
  min-height: 120px;
  border: 1px solid var(--color-border-tertiary, rgba(255,255,255,0.08));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 12px 0;
  background: var(--color-background-secondary, #1a1a1f);
}

.widget-loading-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.widget-loading-dots {
  display: flex;
  gap: 5px;
}

.widget-loading-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-text-tertiary, #5e5c58);
  animation: wlc-pulse 1.2s ease-in-out infinite;
}
.widget-loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.widget-loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes wlc-pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50%       { opacity: 1;   transform: scale(1);   }
}

@media (prefers-reduced-motion: reduce) {
  .widget-loading-dots span { animation: none; opacity: 0.6; }
}

.widget-loading-message {
  font-size: 13px;
  color: var(--color-text-tertiary, #5e5c58);
  font-family: var(--font-mono, monospace);
}
```

---

## 4. WidgetFrame — iframe creation and srcdoc assembly

```typescript
// WidgetFrame.ts

export interface WidgetParams {
  title: string;
  loading_messages: string[];
  widget_code: string;
}

export interface WidgetFrameOptions {
  params: WidgetParams;
  onSendPrompt: (text: string, fromWidget: string) => void;
  onResize?: (height: number) => void;
}

let frameCounter = 0;

export function createWidgetFrame(options: WidgetFrameOptions): HTMLIFrameElement {
  const { params, onSendPrompt, onResize } = options;
  const frameId = `widget-frame-${++frameCounter}`;

  const iframe = document.createElement('iframe');
  iframe.id = frameId;
  iframe.dataset.widget = params.title;
  iframe.sandbox.add('allow-scripts');
  iframe.sandbox.add('allow-popups-to-escape-sandbox');
  // CRITICAL: do NOT add 'allow-same-origin' — keeps widget isolated from parent storage
  iframe.title = params.title.replace(/_/g, ' ');  // accessibility
  iframe.setAttribute('aria-label', `Interactive visual: ${params.title.replace(/_/g, ' ')}`);

  iframe.style.cssText = `
    width: 100%;
    border: none;
    display: block;
    border-radius: 10px;
    min-height: 80px;
    transition: height 0.15s ease;
  `;

  // Assemble srcdoc — order matters
  iframe.srcdoc = assembleSrcdoc(params, frameId);

  // Listen for messages from this frame
  const messageHandler = (event: MessageEvent) => {
    // Security: only accept messages from this specific iframe
    if (event.source !== iframe.contentWindow) return;

    switch (event.data?.type) {
      case 'prompt':
        onSendPrompt(event.data.text, params.title);
        break;

      case 'iframe_resize':
        const h = (event.data.h ?? 0) + 8;  // 8px buffer
        if (h > 40) {  // ignore spurious 0-height reports
          iframe.style.height = h + 'px';
          onResize?.(h);
        }
        break;

      case 'open_link':
        // Route through a confirmation dialog in the parent
        if (event.data.url?.startsWith('https://')) {
          window.open(event.data.url, '_blank', 'noopener,noreferrer');
        }
        break;
    }
  };

  window.addEventListener('message', messageHandler);

  // Cleanup when iframe is removed from DOM
  const observer = new MutationObserver(() => {
    if (!document.contains(iframe)) {
      window.removeEventListener('message', messageHandler);
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

  return iframe;
}


function assembleSrcdoc(params: WidgetParams, frameId: string): string {
  const designTokens = getInjectedCSS();   // see §5

  const bridge = `<script>
    var __widgetId = ${JSON.stringify(params.title)};
    var __frameId  = ${JSON.stringify(frameId)};

    window.sendPrompt = function(text) {
      parent.postMessage({ type: 'prompt', text: text, widgetTitle: __widgetId }, '*');
    };

    window.openLink = function(url) {
      parent.postMessage({ type: 'open_link', url: url }, '*');
    };

    // Report height immediately on load and whenever content changes
    function _reportHeight() {
      var h = Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight
      );
      parent.postMessage({ type: 'iframe_resize', h: h, frameId: __frameId }, '*');
    }

    window.addEventListener('load', _reportHeight);

    if (window.ResizeObserver) {
      new ResizeObserver(_reportHeight).observe(document.body);
    } else {
      // Fallback for older browsers
      setInterval(_reportHeight, 300);
    }

    // Catch and report JS errors inside widgets
    window.addEventListener('error', function(e) {
      parent.postMessage({
        type: 'widget_error',
        error: e.message,
        widgetTitle: __widgetId
      }, '*');
    });
  <\/script>`;

  return [
    `<style>${designTokens}</style>`,
    bridge,
    params.widget_code
  ].join('\n');
}
```

---

## 5. The injected CSS — complete implementation

This stylesheet is prepended to every iframe's srcdoc. It defines all design tokens, color ramp classes, SVG utility classes, and pre-styles bare HTML elements. Copy this exactly — every character matters for dark mode.

```typescript
// designTokens.ts

export function getInjectedCSS(): string {
  return `
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── DESIGN TOKENS ──────────────────────────────────── */
:root {
  --color-text-primary: #1a1918;
  --color-text-secondary: #5a5855;
  --color-text-tertiary: #9b9890;
  --color-text-info: #185fa5;
  --color-text-success: #27500a;
  --color-text-warning: #633806;
  --color-text-danger: #712b13;
  --color-background-primary: #ffffff;
  --color-background-secondary: #f4f2eb;
  --color-background-tertiary: #eceae3;
  --color-background-info: #e6f1fb;
  --color-background-success: #eaf3de;
  --color-background-warning: #faeeda;
  --color-background-danger: #faece7;
  --color-border-tertiary: rgba(0,0,0,0.09);
  --color-border-secondary: rgba(0,0,0,0.14);
  --color-border-primary: rgba(0,0,0,0.4);
  --color-border-info: #185fa5;
  --color-border-success: #3b6d11;
  --color-border-warning: #854f0b;
  --color-border-danger: #993c1d;
  --font-sans: 'Plus Jakarta Sans', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-serif: Georgia, serif;
  --border-radius-sm: 4px;
  --border-radius-md: 8px;
  --border-radius-lg: 12px;
  --border-radius-xl: 16px;
  /* SVG shorthand aliases */
  --p: #1a1918; --s: #5a5855; --t: #9b9890;
  --bg2: #f4f2eb; --b: rgba(0,0,0,0.09);
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-text-primary: #e8e6df;
    --color-text-secondary: #9b9890;
    --color-text-tertiary: #5e5c58;
    --color-text-info: #378add;
    --color-text-success: #639922;
    --color-text-warning: #ef9f27;
    --color-text-danger: #d85a30;
    --color-background-primary: #141417;
    --color-background-secondary: #1a1a1f;
    --color-background-tertiary: #0d0d0f;
    --color-background-info: rgba(55,138,221,0.15);
    --color-background-success: rgba(99,153,34,0.15);
    --color-background-warning: rgba(239,159,39,0.15);
    --color-background-danger: rgba(216,90,48,0.15);
    --color-border-tertiary: rgba(255,255,255,0.08);
    --color-border-secondary: rgba(255,255,255,0.14);
    --color-border-primary: rgba(255,255,255,0.4);
    --p: #e8e6df; --s: #9b9890; --t: #5e5c58;
    --bg2: #1a1a1f; --b: rgba(255,255,255,0.08);
  }
}

/* ── SVG COLOR CLASSES — ALL 9 RAMPS ─────────────────── */
/* Light mode */
.c-purple>rect,.c-purple>circle,.c-purple>ellipse{fill:#EEEDFE;stroke:#534AB7}
.c-purple>text.t,.c-purple>text.th{fill:#3C3489}
.c-purple>text.ts{fill:#534AB7}
.c-teal>rect,.c-teal>circle,.c-teal>ellipse{fill:#E1F5EE;stroke:#0F6E56}
.c-teal>text.t,.c-teal>text.th{fill:#085041}
.c-teal>text.ts{fill:#0F6E56}
.c-blue>rect,.c-blue>circle,.c-blue>ellipse{fill:#E6F1FB;stroke:#185FA5}
.c-blue>text.t,.c-blue>text.th{fill:#0C447C}
.c-blue>text.ts{fill:#185FA5}
.c-amber>rect,.c-amber>circle,.c-amber>ellipse{fill:#FAEEDA;stroke:#854F0B}
.c-amber>text.t,.c-amber>text.th{fill:#633806}
.c-amber>text.ts{fill:#854F0B}
.c-green>rect,.c-green>circle,.c-green>ellipse{fill:#EAF3DE;stroke:#3B6D11}
.c-green>text.t,.c-green>text.th{fill:#27500A}
.c-green>text.ts{fill:#3B6D11}
.c-coral>rect,.c-coral>circle,.c-coral>ellipse{fill:#FAECE7;stroke:#993C1D}
.c-coral>text.t,.c-coral>text.th{fill:#712B13}
.c-coral>text.ts{fill:#993C1D}
.c-pink>rect,.c-pink>circle,.c-pink>ellipse{fill:#FBEAF0;stroke:#993556}
.c-pink>text.t,.c-pink>text.th{fill:#72243E}
.c-pink>text.ts{fill:#993556}
.c-gray>rect,.c-gray>circle,.c-gray>ellipse{fill:#F1EFE8;stroke:#5F5E5A}
.c-gray>text.t,.c-gray>text.th{fill:#444441}
.c-gray>text.ts{fill:#5F5E5A}
.c-red>rect,.c-red>circle,.c-red>ellipse{fill:#FCEBEB;stroke:#A32D2D}
.c-red>text.t,.c-red>text.th{fill:#791F1F}
.c-red>text.ts{fill:#A32D2D}

/* Dark mode overrides */
@media(prefers-color-scheme:dark){
.c-purple>rect,.c-purple>circle,.c-purple>ellipse{fill:#3C3489;stroke:#534AB7}
.c-purple>text.t,.c-purple>text.th{fill:#CECBF6}
.c-purple>text.ts{fill:#AFA9EC}
.c-teal>rect,.c-teal>circle,.c-teal>ellipse{fill:#085041;stroke:#0F6E56}
.c-teal>text.t,.c-teal>text.th{fill:#9FE1CB}
.c-teal>text.ts{fill:#5DCAA5}
.c-blue>rect,.c-blue>circle,.c-blue>ellipse{fill:#0C447C;stroke:#185FA5}
.c-blue>text.t,.c-blue>text.th{fill:#B5D4F4}
.c-blue>text.ts{fill:#85B7EB}
.c-amber>rect,.c-amber>circle,.c-amber>ellipse{fill:#633806;stroke:#854F0B}
.c-amber>text.t,.c-amber>text.th{fill:#FAC775}
.c-amber>text.ts{fill:#EF9F27}
.c-green>rect,.c-green>circle,.c-green>ellipse{fill:#27500A;stroke:#3B6D11}
.c-green>text.t,.c-green>text.th{fill:#C0DD97}
.c-green>text.ts{fill:#97C459}
.c-coral>rect,.c-coral>circle,.c-coral>ellipse{fill:#712B13;stroke:#993C1D}
.c-coral>text.t,.c-coral>text.th{fill:#F5C4B3}
.c-coral>text.ts{fill:#F0997B}
.c-pink>rect,.c-pink>circle,.c-pink>ellipse{fill:#72243E;stroke:#993556}
.c-pink>text.t,.c-pink>text.th{fill:#F4C0D1}
.c-pink>text.ts{fill:#ED93B1}
.c-gray>rect,.c-gray>circle,.c-gray>ellipse{fill:#444441;stroke:#5F5E5A}
.c-gray>text.t,.c-gray>text.th{fill:#D3D1C7}
.c-gray>text.ts{fill:#B4B2A9}
.c-red>rect,.c-red>circle,.c-red>ellipse{fill:#791F1F;stroke:#A32D2D}
.c-red>text.t,.c-red>text.th{fill:#F7C1C1}
.c-red>text.ts{fill:#F09595}
}

/* ── SVG UTILITY CLASSES ────────────────────────────── */
text.t{font-size:14px;font-weight:400;fill:var(--color-text-primary);font-family:var(--font-sans)}
text.th{font-size:14px;font-weight:500;fill:var(--color-text-primary);font-family:var(--font-sans)}
text.ts{font-size:12px;font-weight:400;fill:var(--color-text-secondary);font-family:var(--font-sans)}
.node{cursor:pointer}
.node:hover{opacity:0.82}
.arr{stroke:var(--color-border-secondary);stroke-width:1.5;fill:none}
.box{fill:var(--color-background-secondary);stroke:var(--color-border-secondary)}
.leader{stroke:var(--color-border-tertiary);stroke-width:0.5;fill:none;stroke-dasharray:3 3}

/* ── RESET AND BASE ─────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{
  background:transparent;
  font-family:var(--font-sans);
  color:var(--color-text-primary);
  font-size:15px;
  line-height:1.7;
}

/* ── PRE-STYLED HTML ELEMENTS ───────────────────────── */
input[type=range]{width:100%;accent-color:var(--color-text-info);cursor:pointer}
input[type=text],input[type=number]{
  height:36px;padding:0 10px;
  border:1px solid var(--color-border-secondary);
  border-radius:var(--border-radius-md);
  background:var(--color-background-secondary);
  color:var(--color-text-primary);
  font-family:var(--font-sans);font-size:14px
}
input[type=text]:focus,input[type=number]:focus{
  outline:none;border-color:var(--color-border-info)
}
button{
  background:transparent;
  border:1px solid var(--color-border-secondary);
  border-radius:var(--border-radius-md);
  color:var(--color-text-primary);
  font-family:var(--font-sans);
  font-size:13px;font-weight:500;
  padding:7px 16px;cursor:pointer;
  transition:background 0.15s,transform 0.1s
}
button:hover{background:var(--color-background-secondary)}
button:active{transform:scale(0.98)}
select{
  height:36px;padding:0 10px;
  border:1px solid var(--color-border-secondary);
  border-radius:var(--border-radius-md);
  background:var(--color-background-secondary);
  color:var(--color-text-primary);
  font-family:var(--font-sans);font-size:14px;cursor:pointer
}

/* ── prefers-reduced-motion ─────────────────────────── */
@media(prefers-reduced-motion:reduce){
  *{animation-duration:0.01ms!important;transition-duration:0.01ms!important}
}
`;
}
```

---

## 6. React integration — hooks and components

```tsx
// useWidgetStream.ts — hook that manages stream state for one assistant turn

import { useState, useRef, useCallback } from 'react';

interface MessageBlock {
  id: string;
  type: 'text' | 'widget';
  content: string;         // for text blocks
  widgetParams?: WidgetParams;   // for widget blocks
  loading?: boolean;       // widget still accumulating
}

export function useWidgetStream() {
  const [blocks, setBlocks] = useState<MessageBlock[]>([]);
  const currentTextBlockId = useRef<string | null>(null);
  const counter = useRef(0);

  const newId = () => `block-${++counter.current}`;

  const handlers = {
    onTextDelta: useCallback((text: string) => {
      setBlocks(prev => {
        const last = prev[prev.length - 1];
        // Append to existing text block if last block is text
        if (last?.type === 'text') {
          return [
            ...prev.slice(0, -1),
            { ...last, content: last.content + text }
          ];
        }
        // Start new text block
        const id = newId();
        currentTextBlockId.current = id;
        return [...prev, { id, type: 'text', content: text }];
      });
    }, []),

    onToolStart: useCallback((toolName: string, loadingMessages: string[]) => {
      const id = newId();
      setBlocks(prev => [
        ...prev,
        {
          id,
          type: 'widget',
          content: '',
          widgetParams: {
            title: toolName + '_loading',
            loading_messages: loadingMessages,
            widget_code: ''
          },
          loading: true
        }
      ]);
    }, []),

    onToolComplete: useCallback((_toolName: string, params: WidgetParams) => {
      setBlocks(prev => {
        // Find the most recent loading widget block and replace it
        const idx = [...prev].reverse().findIndex(b => b.type === 'widget' && b.loading);
        if (idx === -1) return prev;
        const realIdx = prev.length - 1 - idx;
        const updated = [...prev];
        updated[realIdx] = {
          ...updated[realIdx],
          widgetParams: params,
          loading: false
        };
        return updated;
      });
    }, []),

    onStreamEnd: useCallback(() => {
      currentTextBlockId.current = null;
    }, [])
  };

  return { blocks, handlers };
}

// ChatMessage.tsx — renders a single assistant turn with mixed content
export function AssistantMessage({
  blocks,
  onSendPrompt
}: {
  blocks: MessageBlock[];
  onSendPrompt: (text: string, fromWidget: string) => void;
}) {
  return (
    <div className="assistant-message">
      {blocks.map(block => (
        block.type === 'text' ? (
          <TextBlock key={block.id} content={block.content} />
        ) : (
          <WidgetBlock
            key={block.id}
            params={block.widgetParams!}
            loading={block.loading ?? false}
            onSendPrompt={onSendPrompt}
          />
        )
      ))}
    </div>
  );
}

// WidgetBlock.tsx — handles loading → rendered transition
function WidgetBlock({
  params,
  loading,
  onSendPrompt
}: {
  params: WidgetParams;
  loading: boolean;
  onSendPrompt: (text: string, fromWidget: string) => void;
}) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [height, setHeight] = useState(120);

  useEffect(() => {
    if (loading || !params.widget_code) return;

    const iframe = createWidgetFrame({
      params,
      onSendPrompt,
      onResize: setHeight
    });
    iframeRef.current = iframe;

    return () => {
      window.removeEventListener('message', iframe._messageHandler);
    };
  }, [loading, params.widget_code]);

  if (loading) {
    return (
      <LoadingCard
        messages={params.loading_messages}
      />
    );
  }

  return (
    <div className="widget-container" style={{ height }}>
      <iframe
        ref={el => {
          if (el && iframeRef.current) {
            el.sandbox.add('allow-scripts');
            el.sandbox.add('allow-popups-to-escape-sandbox');
            el.srcdoc = assembleSrcdoc(params, `frame-${Date.now()}`);
          }
        }}
        title={params.title}
        style={{ width: '100%', height: '100%', border: 'none', borderRadius: '10px' }}
      />
    </div>
  );
}
```

---

## 7. Quick-action chips

```tsx
// ChipRow.tsx
const CHIPS_AFTER_WIDGET = [
  'Make it interactive',
  'Show a real-world example',
  'What breaks if this goes wrong?',
  'Ask me a question about this',
  'Zoom into the most complex part',
];

const CHIPS_AFTER_TEXT = [
  'Show me this visually',
  'Walk me through step by step',
  'Compare to something I know',
  'Give me an interactive version',
];

export function ChipRow({
  hadWidget,
  onChipClick
}: {
  hadWidget: boolean;
  onChipClick: (text: string) => void;
}) {
  const chips = hadWidget ? CHIPS_AFTER_WIDGET : CHIPS_AFTER_TEXT;
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  return (
    <div className="chip-row">
      {chips.map(text => (
        <button
          key={text}
          className="chip"
          onClick={() => {
            setDismissed(true);
            onChipClick(text);
          }}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
```

```css
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.chip {
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-family: var(--font-sans, system-ui);
  border: 1px solid var(--color-border-secondary, rgba(0,0,0,0.14));
  background: transparent;
  color: var(--color-text-secondary, #5a5855);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
  white-space: nowrap;
}
.chip:hover {
  border-color: var(--color-text-info, #185fa5);
  color: var(--color-text-info, #185fa5);
  background: var(--color-background-info, #e6f1fb);
}
```

---

## 8. Color-scheme synchronisation

When the user switches OS dark/light mode, existing iframes must update:

```typescript
// colorSchemeSync.ts
export function setupColorSchemeSync() {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const freshCSS = getInjectedCSS();  // re-generate with new scheme

    document.querySelectorAll<HTMLIFrameElement>('iframe[data-widget]').forEach(iframe => {
      try {
        const doc = iframe.contentDocument;
        if (!doc) return;

        let tokenStyle = doc.querySelector<HTMLStyleElement>('#design-tokens');
        if (!tokenStyle) {
          tokenStyle = doc.createElement('style');
          tokenStyle.id = 'design-tokens';
          doc.head?.appendChild(tokenStyle);
        }
        tokenStyle.textContent = freshCSS;
      } catch {
        // Cross-origin frames will throw — that's expected for external iframes
      }
    });
  });
}
```

---

## 9. Accessibility checklist

```
Iframes:
  ✓ title attribute set from widget title (spaces, not underscores)
  ✓ aria-label on the iframe: "Interactive visual: {title}"
  ✓ tabindex="0" so keyboard users can navigate into the widget
  ✓ After rendering, move focus to the iframe if the user submitted the prompt

Loading cards:
  ✓ role="status" on the loading card container
  ✓ aria-live="polite" so screen readers announce "Visual loading"
  ✓ Loading dots are decorative — mark them aria-hidden="true"

Chips:
  ✓ Each chip is a <button>, not a <div>
  ✓ ChipRow has aria-label="Follow-up suggestions"

Color:
  ✓ Never rely on color alone to convey meaning in diagrams
  ✓ All text within widgets meets WCAG AA (4.5:1 contrast minimum)
  ✓ prefers-reduced-motion suppresses all CSS animations in injected CSS

Keyboard:
  ✓ Tab into iframe → arrow keys navigate between clickable SVG nodes
  ✓ Enter/Space fires onclick on focused SVG nodes (add tabindex="0" to nodes in generated SVG)
```
