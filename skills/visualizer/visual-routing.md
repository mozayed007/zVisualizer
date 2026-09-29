# Visual Routing — Decision Logic

## Purpose

This document defines the complete decision tree an agent must run before generating any visual output. Every branch is explained with rationale, examples, and anti-patterns.

**Critical rule:** The routing decision is made on *intent*, not *subject matter*. The same topic can produce different visuals depending on what the learner needs to understand.

---

## The routing tree

```
User message arrives
        │
        ▼
┌─────────────────────────────────┐
│ Is a connected MCP tool a fit?  │
│ (Figma, Amplitude, Hex, etc.)   │
└─────────────────────────────────┘
        │ YES → call MCP tool (category match wins over aesthetic)
        │ NO  ▼
┌─────────────────────────────────┐
│ Did user say "file", "artifact",│
│ "download", "save as"?          │
└─────────────────────────────────┘
        │ YES → produce downloadable file (not inline visual)
        │ NO  ▼
┌─────────────────────────────────┐
│ Would a visual genuinely help   │
│ understanding here?             │
└─────────────────────────────────┘
        │ NO  → plain text response
        │ YES ▼
┌─────────────────────────────────┐
│ Does it need interactivity?     │
│ (controls, sliders, animation,  │
│  step-through, live calculation)│
└─────────────────────────────────┘
        │ YES → HTML + JS widget
        │ NO  ▼
┌─────────────────────────────────┐
│ Is it a database schema / ERD?  │
└─────────────────────────────────┘
        │ YES → Mermaid.js erDiagram (not hand-coded SVG)
        │ NO  ▼
┌─────────────────────────────────┐
│ What does the learner need?     │
│ Steps/decisions → FLOWCHART     │
│ Containment/architecture → STRUCTURAL
│ Mechanism/intuition → ILLUSTRATIVE
└─────────────────────────────────┘
```

---

## Branch 1: Plain text (no visual)

Generate plain text when:
- The question is a direct factual lookup ("What year was TCP invented?")
- The answer is a single definition that can be stated in one sentence
- The learner explicitly says "just explain in words"
- The task is code debugging, code writing, or text editing
- The concept has no spatial, relational, or sequential structure

**Test:** Remove the visual from the response. Does the learner lose any understanding? If no — don't generate it.

---

## Branch 2: HTML + JS widget

Use HTML when the concept has a **control** — something the learner should be able to manipulate to see how the output changes.

### When to choose HTML

| Signal in the request | Type of control to add |
|----------------------|----------------------|
| "how does X change when Y changes" | Slider for Y |
| "what happens if I increase/decrease X" | Range input for X |
| "walk me through step by step" | Next/prev stepper buttons |
| "show me the process over time" | Play/pause animation control |
| "I want to explore X" | Multiple sliders or inputs |
| "plot / chart / graph" | Chart.js or D3 visualization |
| cyclic processes (event loop, Krebs cycle) | HTML stepper (not SVG ring) |

### Decision rule: does the real system have a control?
- Water heater has a thermostat → add temperature slider
- LLM has a temperature parameter → add temperature slider
- Gradient descent has a learning rate → add learning rate slider
- Sort algorithm has array contents → add "shuffle" and "step" buttons
- Wave has frequency and amplitude → add two range sliders

### HTML structure order (strictly enforced)
```
1. <style> block — CSS variables, layout, component styles
2. Content HTML — visible immediately while scripts load
3. <script src="CDN"> — external library (if needed)
4. <script> — logic using the CDN global
```

This order ensures the learner sees content while scripts are still downloading.

### Available CDN libraries
All must load from: `cdnjs.cloudflare.com`, `esm.sh`, `cdn.jsdelivr.net`, `unpkg.com`
Any other domain is blocked by CSP silently.

```
Chart.js 4.x     — line, bar, scatter, radar, doughnut charts
D3.js 7.x        — custom data visualizations, force-directed graphs
Three.js r128    — 3D scenes (use r128 specifically)
Mermaid.js 11    — flowcharts, ERDs, class diagrams (import from esm.sh)
Plotly.js        — scientific charts, 3D surface plots
Tone.js          — audio synthesis for music/acoustics lessons
MathJS           — symbolic math, unit conversion, expression parsing
Lodash           — array/object utilities
Papaparse        — CSV parsing for data lessons
SheetJS          — Excel file parsing
TensorFlow.js    — in-browser ML model inference
```

---

## Branch 3: SVG — Flowchart

### When to use
- The concept is a **sequence of steps** the learner needs to follow
- The concept involves **decisions** with branching paths
- The learner asked: "what are the steps", "walk me through the process", "what happens when"
- The output is **documentation** of a process (not explanation of a mechanism)

### Flowchart composition rules
```
Direction: single direction only — all top-down OR all left-right
Max nodes: 5 per diagram (beyond this, split into multiple diagrams)
Box heights: uniform — all single-line = 44px, all two-line = 56px
Spacing: 60px minimum between boxes
Padding: 24px inside each box
Arrow gap: 10px between arrowhead and box edge
```

### Box sizing formula (compute before drawing — never guess)
```
title_width    = title_chars × 8
subtitle_width = subtitle_chars × 7
box_width      = max(title_width, subtitle_width) + 24
box_height     = 44  (single line)
box_height     = 56  (two lines, with 22px between text baselines)
```

### Collision check (run before every arrow)
Before writing any `<line>` or `<path>`, trace its start and end coordinates against every existing rect. If the line would pass through any rect's interior (not just touch its boundary), route around it with an L-bend:
```svg
<!-- Direct path crosses a box — use L-bend instead -->
<path d="M x1 y1 L x1 ymid L x2 ymid L x2 y2" fill="none" class="arr" marker-end="url(#arrow)"/>
```

### Cycles and loops
**Never draw a cyclic process as a ring of SVG boxes.** Ring layouts require trigonometric placement that always produces overlapping elements. Instead:
- Use an HTML stepper where the last "next" wraps to stage 1
- Use a linear SVG with a curved return arrow at the end
- Use a `↻` glyph + text label near the cycle point

---

## Branch 4: SVG — Structural diagram

### When to use
- The concept involves **containment** — things inside other things
- The learner needs to understand **where** something lives in a hierarchy
- Examples: CPU caches (L1 inside core, L2 shared), VPC/subnet/EC2, cell organelles, file system (blocks in inodes in partitions)
- The learner asked: "what's the architecture of", "where does X live", "how is X organized"

### Structural diagram rules
```
Outer container: large rounded rect, rx=20-24, lightest fill (50 stop), 0.5px stroke
Inner regions:   medium rects, rx=8-12, different color ramp from parent
Padding:         20px minimum inside every container
Nesting:         max 3 levels deep (deeper = unreadable at 680px)
External arrows: inputs/outputs from outside the container, short labels only
```

### Color hierarchy in structural diagrams
Nested regions MUST use different ramps. Same ramp on parent and child produces identical fills that flatten the visual hierarchy.
```
Good: outer = c-green (system), inner-left = c-teal (subsystem A), inner-right = c-amber (subsystem B)
Bad:  outer = c-blue,           inner = c-blue  ← identical fills, no hierarchy
```

### When to use Mermaid for structural
Use Mermaid `erDiagram` or `classDiagram` when:
- The diagram is a database schema with typed fields
- The diagram is a class hierarchy with methods and properties
- Connector routing would require 10+ manually-placed arrows

Hand-coded SVG cannot reliably handle crow's-foot connectors or auto-layout. Mermaid handles both.

---

## Branch 5: SVG — Illustrative diagram

### When to use
This is the most powerful and most commonly underused type. Choose it when:
- The learner needs **intuition** about a mechanism, not a map of its components
- The concept is abstract but can be given a spatial metaphor
- The learner said: "I don't get X", "explain how X actually works", "give me an intuition for X"
- A picture of the *process* would explain what a list of steps cannot

### Physical subjects → draw them
Physical things get simplified cross-sections or schematics:
```
Water heater → tall rect (tank) + burner at bottom + pipes at top + convection currents
Heart        → two chambers + valves as curved paths + flow arrows
Neuron       → cell body (circle) + dendrites (branching lines) + axon (long line) + myelin sheaths
```

### Abstract subjects → spatial metaphors
Invent a shape for things that don't have one. The metaphor must reveal the mechanism:
```
Hash map     → key falling through a funnel into one of N labeled buckets
Call stack   → literal stack of labeled rectangles, growing downward, shrinking on return
TCP stream   → two endpoints with numbered envelope icons in flight between them
Attention    → one amber token with fan of lines to every other token, stroke-width = weight
Transformer  → horizontal slabs stacked vertically, tokens as vertical bars, attention as threads
Gradient descent → 3D contour surface (rendered as 2D ellipses), ball with trail, arrow = negative gradient
Embeddings   → scatter of labeled dots, similar words clustered together
Recursion    → frames inside frames, each slightly inset, same function name in each
```

### What changes from flowchart rules
```
Shapes:   freeform — <path>, <ellipse>, <circle>, <polygon> allowed
Layout:   follows the subject's geometry, not a grid
Color:    encodes INTENSITY not category (warm = active/hot, cool = passive/cold)
Overlap:  shapes may overlap for depth — pipes entering tanks, attention through layers
Text:     NEVER let a stroke cross text — place labels in quiet margins with leader lines
```

### The one-gradient rule
Illustrative diagrams may use ONE `<linearGradient>` between exactly two stops from the same ramp — only when showing a continuous physical property (temperature gradient in a tank, pressure drop along a pipe). No radial gradients, no multi-stop fades, no gradient-as-decoration.

### Fidelity ceiling
These are schematics, not illustrations. Every shape must read at a glance:
```
Good: tank = rounded rect, flame = three triangles, bubble = small circle
Bad:  tank = 40-segment Bézier portrait, flame = detailed illustration
```
If a `<path>` needs more than ~6 segments, simplify it. Recognizable silhouette > accurate contour.

---

## Subject-specific routing table

| Learner says | Visual type | Key visual element |
|---|---|---|
| "explain gradient descent" | HTML interactive | Loss surface, ball, learning rate slider |
| "transformer architecture" | SVG structural | Labeled layer boxes: embedding, attention, FFN |
| "how does attention work" | SVG illustrative | Token row, amber query token, weighted fan lines |
| "what are the steps of backprop" | SVG flowchart | Forward → Loss → Backward → Update |
| "show me bubble sort" | HTML stepper | Colored array bars, comparison highlight, swap animation |
| "explain recursion" | SVG illustrative | Stack of frames, growing and shrinking |
| "how does a hash map work" | SVG illustrative | Key → funnel → bucket row |
| "what's inside a TCP packet" | SVG structural | Containment diagram of header fields |
| "show me BFS vs DFS" | HTML interactive | Tree with traversal order highlighted, step button |
| "draw the database schema" | Mermaid erDiagram | Auto-layout with crow's-foot connectors |
| "explain the Krebs cycle" | HTML stepper | One panel per stage, wraps back to stage 1 |
| "derivative of sin(x)" | HTML interactive | Animated tangent line on sine curve, x-slider |
| "how does DNA replication work" | HTML stepper | 4 stages, SVG inline in each panel |
| "explain convolution in CNNs" | HTML interactive | Kernel sliding over input, output computing live |
| "what is entropy" | SVG illustrative | Scattered particles (disorder) vs ordered grid |

---

## Parameterized Comparisons

When the learner asks to compare two concepts, the choice between HTML and SVG depends on one question: *Would exploration through parameter variation deepen understanding?*

If both concepts being compared have real parameters the learner could adjust (learning rates, thresholds, step counts, temperatures, input values), an HTML widget with controls teaches more than a static side-by-side SVG.

### Decision Rule

| Has tunable parameters? | Comparison type | Visual Type |
|-------------------------|-----------------|-------------|
| **Yes, parameters affect behavior** | Optimizers, activation functions, schedulers, temperature-based systems, iterative algorithms | **HTML widget** — controls let the learner see how each responds to the same parameter change |
| **No, behavior is fixed** | Data structures, architectural patterns, static taxonomies, procedural sequences | **SVG** — show structural or behavioral differences directly |
| **Step-through teaches better** | Algorithms where sequence matters more than static structure | **HTML stepper** — let the learner step through both side-by-side |

### Anti-pattern: Static comparison when variation would teach

```
BAD:  "Compare X and Y" (both have tunable parameters) → static side-by-side SVG with fixed values
GOOD: "Compare X and Y" (both have tunable parameters) → HTML widget with parameter slider, showing both responding live

BAD:  "Compare Stack and Queue" → HTML widget trying to vary a "push speed" parameter (meaningless)
GOOD: "Compare Stack and Queue" → SVG showing LIFO vs FIFO behavior directly
```

When comparing any two concepts, ask: *Would letting the learner adjust a meaningful parameter teach more than showing fixed values?* If yes → HTML widget. If no → SVG.

---

## Anti-patterns to avoid

### 1. Forcing a flowchart when illustrative is needed
```
BAD:  "How does attention work?" → boxes labelled "Multi-head attention" → "Add & Norm"
GOOD: "How does attention work?" → fan of weighted lines between tokens
```
The flowchart documents the architecture. The illustrative diagram explains the mechanism.

### 2. Overloading a single diagram
```
BAD:  6+ nodes in one SVG → cramped, arrows crossing, text overflowing
GOOD: Overview diagram (3 nodes) → prose transition → detail diagram per component
```

### 3. Generating the same visual for a confused learner
```
BAD:  Learner says "I still don't get it" → regenerate same SVG flowchart
GOOD: Switch to interactive HTML, or illustrative SVG, or concrete example
```

### 4. Missing the interactivity opportunity
```
BAD:  Static SVG of gradient descent (ball on surface, fixed position)
GOOD: HTML with learning rate slider, step button, trail of past positions
```

### 5. Orphaned diagrams
Every diagram must be preceded by a prose sentence contextualizing it and followed by at least one sentence connecting it to the next idea. Never stack multiple tool calls without prose between them.
