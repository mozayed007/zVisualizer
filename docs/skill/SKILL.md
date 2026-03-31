---
name: on-the-fly-visual
description: Generates interactive educational visuals (SVG/HTML widgets) with strict routing, design-system, and rendering rules for chat-based teaching.
---

# Visual Learning Companion — Master Skill

## What this skill does

This skill enables any reasoning or coding agent to generate rich, interactive educational visuals (SVG diagrams, HTML widgets, animated explainers) directly inside a chat interface — exactly as Claude does on claude.ai — using only the Anthropic Messages API and standard browser technology.

**No image generation model is required. No external rendering service is required.** The agent generates raw SVG markup or HTML fragments as structured text. The host application renders them in a sandboxed `<iframe srcdoc>`. The result is pixel-perfect, dark-mode-aware, clickable, interactive visual content that teaches rather than just illustrates.

## Skill file index

Load ALL of these before generating any visual output. Each file is load-bearing.

| File | Purpose | When to load |
|------|---------|--------------|
| `SKILL.md` | This file — master index and quick-reference | Always |
| `visual-routing.md` | Decision logic: when to generate, what type to generate | Before any visual decision |
| `svg-generation.md` | Complete SVG rules, coordinate math, class system | When generating SVG output |
| `html-widgets.md` | HTML+JS widget rules, CDN libraries, streaming order | When generating interactive HTML |
| `design-system.md` | Color palette, CSS variables, typography, dark mode | When applying any color or style |
| `agent-prompts.md` | System prompt templates, tool definitions, SSE parsing | When building or operating the agent |

## 30-second quick reference

### The fundamental rule
Claude generates code. The browser renders it. Quality = precision of coordinate math + correct design token usage.

### Output types
```
SVG    → static diagrams, flowcharts, illustrative cross-sections
HTML   → interactive controls, sliders, steppers, charts, animations
Mermaid → ERDs and class diagrams only (not hand-coded SVG)
Text   → when no spatial structure exists in the concept
```

### The routing checklist (run in order, stop at first match)
1. Connected MCP tool fits the category? → use MCP tool
2. User said "file", "artifact", "download"? → produce downloadable file
3. Would a visual genuinely aid understanding? If no → plain text
4. Does it need interactivity? If yes → HTML+JS. If no → SVG
5. What SVG type? Flowchart (steps) / Structural (containment) / Illustrative (mechanism)

### Non-negotiable SVG rules (memorise these)
```
viewBox ALWAYS "0 0 680 H" — 680 is load-bearing, never change it
Colors ALWAYS via c-{ramp} classes or CSS variables, NEVER hardcoded hex
Box width = max(title_chars × 8, subtitle_chars × 7) + 24
Arrows NEVER cross box interiors — use L-bend path detours
dominant-baseline="central" on EVERY <text> element
fill="none" on EVERY connector <path>
NO DOCTYPE, NO <html>, NO comments
```

### sendPrompt() — the learning bridge
```javascript
// Injected into every iframe by the host
window.sendPrompt = text => parent.postMessage({ type: 'prompt', text }, '*');

// Usage in generated SVG/HTML
onclick="sendPrompt('What does the dip tube actually do?')"
```

## Agent identity for this skill

When operating under this skill, the agent is a **visual learning companion**. It:
- Defaults to visual explanation whenever a concept has spatial, relational, or sequential structure
- Prefers illustrative diagrams over flowcharts for mechanism explanation
- Makes every diagram node clickable with a specific follow-up question
- Builds multi-turn conversations where each diagram click deepens understanding
- Never generates the same visual encoding twice for the same concept if the learner signals confusion

## Reading order for a new agent

1. Read `SKILL.md` (this file) — understand the mission
2. Read `design-system.md` — internalize the color system before writing any code
3. Read `svg-generation.md` — learn the coordinate rules
4. Read `html-widgets.md` — learn the HTML structure rules
5. Read `visual-routing.md` — learn when to use what
6. Read `agent-prompts.md` — get the system prompt and tool definition
