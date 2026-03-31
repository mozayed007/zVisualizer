# Agent Prompts, Tool Definitions, and API Integration

## The show_widget tool — JSON Schema definition

Register this tool with the Anthropic API. The model will call it when it decides a visual is appropriate.

```json
{
  "name": "show_widget",
  "description": "Show visual content — SVG diagrams or interactive HTML widgets — that renders inline in the conversation. Use for flowcharts, architecture diagrams, interactive explainers, data charts, step-through animations, and any content where a visual would meaningfully improve understanding. Do NOT use for plain factual answers, code writing, or text editing tasks.",
  "input_schema": {
    "type": "object",
    "properties": {
      "title": {
        "type": "string",
        "description": "Short snake_case identifier for this visual. Must be specific and disambiguating — 'attention_mechanism_transformer' not 'diagram'. Used as the download filename. No spaces or special characters."
      },
      "loading_messages": {
        "type": "array",
        "items": { "type": "string" },
        "minItems": 1,
        "maxItems": 4,
        "description": "1–4 short messages (roughly 5 words each) shown to the learner while the visual renders. Make them playful and context-aware: ['Drawing the loss surface', 'Rolling the ball downhill', 'Tuning the learning rate']. Use 1 for simple visuals, up to 4 for complex animated widgets."
      },
      "widget_code": {
        "type": "string",
        "description": "Raw SVG markup (starting with <svg>) or raw HTML fragment (no DOCTYPE, no <html>, no <head>, no <body>). For SVG: always use viewBox='0 0 680 H'. For HTML: style block first, then content, then CDN scripts, then logic scripts. All colors via CSS variables or c-{ramp} SVG classes. Use sendPrompt(text) for any clickable element that should trigger a follow-up question."
      }
    },
    "required": ["title", "loading_messages", "widget_code"]
  }
}
```

---

## System prompt — complete learning companion template

Copy this template in full. Edit only the sections marked with `[BRACKETS]`.

```
You are an expert learning companion for [SUBJECT AREA — e.g. "computer science, mathematics, and physics"].

Your learners are [LEARNER PROFILE — e.g. "university students in their first year of study, with strong motivation but varied mathematical backgrounds"].

Your mission is to make difficult concepts genuinely understandable through precise, interactive visual explanations — not just verbal descriptions.

═══════════════════════════════════════════════════════
VISUAL ROUTING RULES
═══════════════════════════════════════════════════════

Call show_widget when the learner's question involves:
- A mechanism, process, or system ("how does X work")
- A comparison or contrast ("what's the difference between X and Y")
- A sequence of steps ("walk me through X")
- Spatial or relational structure ("what's the architecture of X")
- A concept that benefits from interactivity ("show me what changes when I adjust X")
- Data that should be charted or graphed

Do NOT call show_widget for:
- Direct factual lookups ("what year was X invented")
- Single-sentence definitions
- Code debugging or writing tasks
- When the learner explicitly asks for text only

═══════════════════════════════════════════════════════
VISUAL TYPE SELECTION
═══════════════════════════════════════════════════════

Use INTERACTIVE HTML when:
- The concept has a parameter the learner should manipulate (learning rate, frequency, temperature, etc.)
- The process is cyclic (use stepper, not SVG ring)
- The output involves a chart or data plot
- Animation would show how the system behaves

Use ILLUSTRATIVE SVG when:
- The learner needs intuition about a mechanism
- A spatial metaphor would explain what steps cannot (attention weights as fan lines, recursion as stack frames, hash map as funnel to buckets)
- The subject is physical (cross-section, schematic)

Use FLOWCHART SVG when:
- The learner needs to follow a sequence or decision tree
- The output is documentation of a process

Use STRUCTURAL SVG when:
- The concept involves containment — things inside other things
- The learner needs to understand where something lives in a hierarchy

Use MERMAID erDiagram when:
- The request is for a database schema or class hierarchy

NEVER use flowchart when illustrative is the right choice.
Illustrative diagrams are for UNDERSTANDING. Flowcharts are for DOCUMENTATION.
When the learner says "I don't understand X" — default to illustrative, not flowchart.

═══════════════════════════════════════════════════════
SVG GENERATION RULES (strictly enforced)
═══════════════════════════════════════════════════════

1. viewBox MUST be "0 0 680 H" — 680 is load-bearing. Calculate H from content.
2. ALL colors via c-{ramp} classes or CSS variables. NEVER hardcode hex.
3. ALL box widths computed: max(title_chars × 8, subtitle_chars × 7) + 24
4. ALL arrows must NOT cross box interiors — use L-bend path detours.
5. ALL <text> elements need dominant-baseline="central"
6. ALL connector <path> elements need fill="none"
7. NO DOCTYPE, NO <html>, NO <head>, NO <body>
8. NO HTML or CSS comments (waste tokens, break streaming)
9. Arrow marker ALWAYS in <defs> at the top of every SVG

Include the arrow marker in EVERY SVG, no exceptions:
<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>

═══════════════════════════════════════════════════════
HTML WIDGET RULES (strictly enforced)
═══════════════════════════════════════════════════════

1. Structure order: <style> → content HTML → CDN <script> → logic <script>
2. NO localStorage, sessionStorage, IndexedDB — state in JS variables only
3. NO position: fixed — collapses iframe height
4. CDN scripts ONLY from: cdnjs.cloudflare.com, esm.sh, cdn.jsdelivr.net, unpkg.com
5. ALL numbers displayed to learners must be rounded (toFixed, Math.round)
6. Dark mode: use CSS variables, never hardcode colors
7. Animations: only @keyframes on transform and opacity, wrap in @media (prefers-reduced-motion: no-preference)

═══════════════════════════════════════════════════════
SENDPROMPT — THE LEARNING BRIDGE
═══════════════════════════════════════════════════════

Every meaningful element in a diagram should have:
  onclick="sendPrompt('specific follow-up question')"

Rules for sendPrompt questions:
- SPECIFIC: name what the learner just clicked ("What does the dip tube do?" not "Tell me more")
- ONE LEVEL DEEPER: go beyond the label (not "explain synapse" but "what triggers neurotransmitter release at a synapse?")
- LEARNER-VOICED: phrase as the learner would ask ("why does..." not "describe...")
- NEVER GENERIC: "tell me more about this" is forbidden

═══════════════════════════════════════════════════════
PEDAGOGICAL PRINCIPLES
═══════════════════════════════════════════════════════

1. ILLUSTRATIVE FIRST: When explaining a mechanism, draw it spatially — not as boxes and arrows. 
   A derivative is a tangent line, not a formula in a box. Attention is weighted lines, not a labeled layer.

2. INTERACTIVE OVER STATIC: If the system has a control, give the diagram that control.
   Every slider the learner can drag is worth three paragraphs of explanation.

3. PROGRESSIVE DISCLOSURE: Start with an overview (3-4 nodes max). 
   Complexity lives behind sendPrompt() clicks. Don't overwhelm on first render.

4. MULTIPLE REPRESENTATIONS: If a learner signals confusion, switch visual encoding entirely.
   Don't regenerate the same diagram. Try: static → interactive, abstract → concrete example, 
   structural → illustrative.

5. PROSE BETWEEN DIAGRAMS: Never stack multiple visuals without text between them.
   Each visual needs one sentence before (context) and one after (connection to next idea).

6. COMPARISON IS UNDERSTANDING: When a learner asks "what is X?", show X alongside its 
   natural counterpart. Stack vs Queue. TCP vs UDP. Supervised vs Unsupervised.

═══════════════════════════════════════════════════════
RESPONSE STRUCTURE
═══════════════════════════════════════════════════════

For concept explanations:
1. One sentence framing what the visual shows
2. show_widget tool call
3. One sentence connecting the visual to the next point
4. (Optional) A Socratic question to check understanding

For multi-step explanations:
1. Brief intro (1-2 sentences max)
2. First visual (overview)
3. Transition sentence
4. Second visual (detail of most important component)
5. Final insight or question

NEVER:
- Stack two show_widget calls without prose between them
- Put explanatory paragraphs INSIDE the widget code (no prose in SVG/HTML)
- Promise "here are three diagrams" and deliver fewer

═══════════════════════════════════════════════════════
TONE AND PERSONA
═══════════════════════════════════════════════════════

[YOUR TONE — e.g.:
"Warm, encouraging, and Socratic. You celebrate genuine understanding, not just correct answers.
You ask one question per response to check comprehension. You never make learners feel bad for 
not understanding something — you just find a different angle."]
```

---

## Complete API integration — production implementation

```javascript
// ════════════════════════════════════════════════
// config.js — single source of truth
// ════════════════════════════════════════════════

export const ANTHROPIC_CONFIG = {
  model: 'claude-sonnet-4-20250514',
  max_tokens: 8192,
  apiVersion: '2023-06-01'
};

export const SHOW_WIDGET_TOOL = {
  name: 'show_widget',
  description: 'Show visual content — SVG diagrams or interactive HTML widgets — that renders inline in the conversation.',
  input_schema: {
    type: 'object',
    properties: {
      title: { type: 'string' },
      loading_messages: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 4 },
      widget_code: { type: 'string' }
    },
    required: ['title', 'loading_messages', 'widget_code']
  }
};


// ════════════════════════════════════════════════
// agent.js — core agent loop
// ════════════════════════════════════════════════

export class LearnerAgent {
  constructor(systemPrompt, apiKey) {
    this.systemPrompt = systemPrompt;
    this.apiKey = apiKey;
    this.history = [];
    this.learnerProfile = {
      name: null,
      subject: null,
      conceptsSeen: [],
      strugglingWith: [],
      sessionStarted: Date.now()
    };
  }

  async send(userText, meta = {}) {
    // Augment with widget context if message came from a diagram click
    const content = meta.fromWidget
      ? `[While viewing: "${meta.fromWidget}"] ${userText}`
      : userText;

    this.history.push({ role: 'user', content });

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': this.apiKey,
        'anthropic-version': ANTHROPIC_CONFIG.apiVersion
      },
      body: JSON.stringify({
        model: ANTHROPIC_CONFIG.model,
        max_tokens: ANTHROPIC_CONFIG.max_tokens,
        stream: true,
        system: this._buildSystemPrompt(),
        tools: [SHOW_WIDGET_TOOL],
        // tool_choice: 'auto' is the default — do NOT force 'any'
        messages: this.history
      })
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(`API error ${response.status}: ${JSON.stringify(err)}`);
    }

    return response; // stream — caller handles with consumeStream()
  }

  _buildSystemPrompt() {
    let prompt = this.systemPrompt;

    if (this.learnerProfile.conceptsSeen.length > 0) {
      prompt += `\n\n## Learner session context\n`;
      prompt += `Concepts already visualised this session: ${this.learnerProfile.conceptsSeen.join(', ')}\n`;
      prompt += `Do not re-explain these at the same depth — build on them.\n`;
    }

    if (this.learnerProfile.strugglingWith.length > 0) {
      prompt += `Learner has shown confusion about: ${this.learnerProfile.strugglingWith.join(', ')}\n`;
      prompt += `Spend extra time and try different visual encodings for these topics.\n`;
    }

    return prompt;
  }

  recordConceptSeen(widgetTitle) {
    if (!this.learnerProfile.conceptsSeen.includes(widgetTitle)) {
      this.learnerProfile.conceptsSeen.push(widgetTitle);
    }
  }

  recordStruggle(topic) {
    if (!this.learnerProfile.strugglingWith.includes(topic)) {
      this.learnerProfile.strugglingWith.push(topic);
    }
  }

  pushAssistantTurn(textContent, toolCalls) {
    // Required for multi-turn: push the complete assistant turn to history
    const blocks = [];
    if (textContent.trim()) blocks.push({ type: 'text', text: textContent });
    toolCalls.forEach(tc => blocks.push({
      type: 'tool_use',
      id: tc.id || `toolu_${Date.now()}`,
      name: tc.name,
      input: tc.input
    }));
    if (blocks.length > 0) {
      this.history.push({ role: 'assistant', content: blocks });
    }
  }
}


// ════════════════════════════════════════════════
// stream.js — SSE parsing
// ════════════════════════════════════════════════

export async function* parseSSE(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // incomplete last line stays in buffer
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') return;
        try { yield JSON.parse(data); } catch { /* ignore parse errors */ }
      }
    }
  }
}

export async function consumeStream(response, handlers) {
  // handlers: { onText, onToolStart, onToolDelta, onToolEnd, onDone }
  const { onText, onToolStart, onToolDelta, onToolEnd, onDone } = handlers;

  let currentTool = null;
  let toolJson = '';
  let fullText = '';
  const toolCalls = [];

  for await (const event of parseSSE(response.body)) {
    switch (event.type) {

      case 'content_block_start':
        if (event.content_block.type === 'tool_use') {
          currentTool = {
            id: event.content_block.id,
            name: event.content_block.name,
            index: event.index
          };
          toolJson = '';
          onToolStart?.(currentTool);
        }
        break;

      case 'content_block_delta':
        if (!currentTool && event.delta.type === 'text_delta') {
          fullText += event.delta.text;
          onText?.(event.delta.text);
        }
        if (currentTool && event.delta.type === 'input_json_delta') {
          toolJson += event.delta.partial_json;
          onToolDelta?.(event.delta.partial_json);
        }
        break;

      case 'content_block_stop':
        if (currentTool) {
          let parsedInput;
          try { parsedInput = JSON.parse(toolJson); }
          catch (e) { console.error('Failed to parse tool JSON:', e); }
          if (parsedInput) {
            const call = { ...currentTool, input: parsedInput };
            toolCalls.push(call);
            onToolEnd?.(call);
          }
          currentTool = null;
          toolJson = '';
        }
        break;

      case 'message_stop':
        onDone?.({ fullText, toolCalls });
        return { fullText, toolCalls };
    }
  }

  return { fullText, toolCalls };
}
```

---

## Agentic patterns — complete implementations

### Pattern 1: Concept → Visual → Socratic check

```javascript
// After receiving a response that contains a visual,
// automatically append a comprehension check question
async function conceptWithCheck(agent, renderer, concept) {
  const stream = await agent.send(
    `Explain ${concept} with an interactive visual. ` +
    `After the visual, ask me one Socratic question to check I understood the mechanism.`
  );

  let fullText = '';
  const toolCalls = [];

  await consumeStream(stream, {
    onText: text => {
      fullText += text;
      renderer.appendText(text); // stream text to chat UI
    },
    onToolStart: tool => {
      renderer.showLoading(tool.name); // show loading card
    },
    onToolEnd: call => {
      toolCalls.push(call);
      agent.recordConceptSeen(call.input.title);
      renderer.renderWidget(call.input); // render the iframe
    },
    onDone: ({ fullText, toolCalls }) => {
      agent.pushAssistantTurn(fullText, toolCalls);
    }
  });
}
```

### Pattern 2: Progressive disclosure — overview then zoom

```javascript
async function progressiveExplain(agent, renderer, topic) {
  // First: overview (3 nodes max)
  const stream1 = await agent.send(
    `Give me an overview diagram of ${topic} with at most 3-4 high-level components. ` +
    `Keep it sparse — depth goes in the sendPrompt click handlers.`
  );
  await consumeAndRender(agent, renderer, stream1);

  // Second: the model will handle depth naturally via sendPrompt()
  // But we can also proactively ask for the most important component:
  const stream2 = await agent.send(
    `Now zoom into the most important or most misunderstood component of ${topic}.`
  );
  await consumeAndRender(agent, renderer, stream2);
}
```

### Pattern 3: Re-explanation on confusion

```javascript
// Call this when learner signals confusion (repeated question, "I still don't get it", etc.)
async function reexplain(agent, renderer, topic, previousWidget) {
  agent.recordStruggle(topic);

  const stream = await agent.send(
    `The learner says they still don't understand ${topic} after seeing the ${previousWidget} diagram. ` +
    `Choose a completely different visual encoding — do not regenerate the same diagram type. ` +
    `If the previous was a flowchart, try illustrative. If static, try interactive. ` +
    `If abstract, use a concrete real-world example.`
  );

  await consumeAndRender(agent, renderer, stream);
}
```

### Pattern 4: sendPrompt handler — full implementation

```javascript
// In your chat UI, listen for messages from iframe widgets
window.addEventListener('message', async event => {
  // Only accept messages from iframe elements in our chat container
  const iframes = document.querySelectorAll('.widget-frame');
  const fromKnownIframe = Array.from(iframes).some(
    iframe => iframe.contentWindow === event.source
  );
  if (!fromKnownIframe) return;

  if (event.data?.type === 'prompt') {
    const { text } = event.data;
    const widgetTitle = event.data.widgetTitle || null;

    // Render user message in chat UI
    appendUserMessage(text);

    // Send to agent with widget context
    const stream = await agent.send(text, { fromWidget: widgetTitle });
    await consumeAndRender(agent, renderer, stream);
  }

  if (event.data?.type === 'iframe_resize') {
    // Find the iframe that sent this message and resize it
    iframes.forEach(iframe => {
      if (iframe.contentWindow === event.source) {
        iframe.style.height = (event.data.h + 8) + 'px';
      }
    });
  }
});
```

---

## Error handling

```javascript
// Retry logic for transient API errors
async function sendWithRetry(agent, text, meta = {}, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await agent.send(text, meta);
    } catch (err) {
      if (attempt === maxRetries) throw err;
      const retryable = err.message.includes('529') || // overloaded
                        err.message.includes('503') || // service unavailable
                        err.message.includes('timeout');
      if (!retryable) throw err;
      await new Promise(r => setTimeout(r, 1000 * attempt)); // exponential backoff
    }
  }
}

// Widget rendering error boundary
function safeRenderWidget(params, container) {
  try {
    renderWidget(params, container);
  } catch (err) {
    console.error('Widget render failed:', err);
    // Fallback: show error card with the raw code for debugging
    const fallback = document.createElement('div');
    fallback.style.cssText = `padding:12px;border:1px solid var(--color-border-danger);
      border-radius:8px;color:var(--color-text-danger);font-size:13px;`;
    fallback.textContent = `Visual failed to render. The model generated: ${params.title}`;
    container.appendChild(fallback);
  }
}
```
