# SVG Generation — Complete Rules

## The SVG coordinate contract

Every SVG Claude generates must satisfy this contract:

```
viewBox="0 0 680 H"   — width ALWAYS 680, H = content height + 40
width="100%"          — fills the container
background: none      — parent provides the card background
```

**Why 680 is load-bearing:** With `width="100%"`, the browser scales the entire coordinate space proportionally. A `viewBox="0 0 480 H"` in a 680px container scales everything by 680/480 = 1.42×. This means a box you computed as 160px wide now renders as 227px, and your "14px" font renders as 20px. The host CSS and all font calibration math assume 1:1 coordinate-to-pixel mapping. Changing the viewBox width breaks everything. Keep it at 680.

---

## Required boilerplate — every SVG

```svg
<svg width="100%" viewBox="0 0 680 H">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
            stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>
  <!-- content here -->
</svg>
```

The arrow marker uses `stroke="context-stroke"` — this makes the arrowhead inherit the color of whatever line it sits on. A purple line gets a purple arrowhead. A gray line gets a gray arrowhead. Never a color mismatch.

`<defs>` may additionally contain:
- One `<clipPath>` per illustrative diagram (for tank fill clipping)
- One `<linearGradient>` per illustrative diagram (for continuous property gradients only)
- **Nothing else** — no filters, no patterns, no extra markers

---

## The viewBox height calculation

**Never guess the height. Always compute it.**

Algorithm:
1. List all elements and their bottom edges: `max(y + height)` for rects, `max(y)` for text baselines
2. Add 20px buffer: `H = max_bottom_y + 20`
3. Add 40px if content starts at y=0 and needs top padding

Example:
```
Elements:
  rect at y=30, height=44  → bottom = 74
  rect at y=110, height=56 → bottom = 166
  text at y=200            → bottom ≈ 214 (baseline + 4px descent)

H = 214 + 20 = 234
viewBox = "0 0 680 234"
```

---

## Safe area

```
Horizontal: x=40 to x=640  (40px margin each side)
Vertical:   y=30 to y=(H-20)
```

Content outside the safe area will be clipped. Text with `text-anchor="end"` at x=40 is dangerous — the text extends LEFT from x, and a long label will start at x<0.

**Rule for `text-anchor="end"`:** Only safe if `label_chars × 8 < anchor_x`. For a 15-char label, the anchor must be at x≥120. When in doubt, use `text-anchor="start"` and align the column differently.

---

## Color system — the c-{ramp} classes

The host injects a stylesheet into every iframe that defines these classes. An agent generating SVG must use these classes and never hardcode colors.

### How c-{ramp} works

Apply `class="c-blue"` to a `<g>` element. The injected CSS uses direct-child selectors:
```css
.c-blue > rect, .c-blue > circle, .c-blue > ellipse {
  fill: #E6F1FB;    /* light mode: blue-50 */
  stroke: #185FA5;  /* light mode: blue-600 */
}
.c-blue > text.th { fill: #0C447C; }  /* light mode: blue-800 */
.c-blue > text.ts { fill: #185FA5; }  /* light mode: blue-600 */
/* dark mode equivalents are in @media (prefers-color-scheme: dark) */
```

**Critical nesting rule:** The `>` selector means DIRECT children only. If you wrap shapes in an extra `<g>`, they become grandchildren and lose the fill — rendering as SVG default black.

```svg
<!-- CORRECT: c-blue on the innermost group holding the shapes -->
<g class="node c-blue" onclick="sendPrompt('...')">
  <rect x="60" y="30" width="160" height="44" rx="8" stroke-width="0.5"/>
  <text class="th" x="140" y="52" text-anchor="middle" dominant-baseline="central">Label</text>
</g>

<!-- WRONG: extra wrapper group breaks the selector -->
<g class="node" onclick="sendPrompt('...')">
  <g class="c-blue">          <!-- c-blue here -->
    <g>                       <!-- extra wrapper — shapes are now grandchildren -->
      <rect .../>             <!-- loses fill, renders black -->
    </g>
  </g>
</g>
```

### Available ramps

| Class | Light fill | Light stroke | Dark fill | Dark stroke |
|-------|-----------|-------------|----------|------------|
| `c-purple` | #EEEDFE | #534AB7 | #3C3489 | #534AB7 |
| `c-teal` | #E1F5EE | #0F6E56 | #085041 | #0F6E56 |
| `c-blue` | #E6F1FB | #185FA5 | #0C447C | #185FA5 |
| `c-amber` | #FAEEDA | #854F0B | #633806 | #854F0B |
| `c-green` | #EAF3DE | #3B6D11 | #27500A | #3B6D11 |
| `c-coral` | #FAECE7 | #993C1D | #712B13 | #993C1D |
| `c-pink` | #FBEAF0 | #993556 | #72243E | #993556 |
| `c-gray` | #F1EFE8 | #5F5E5A | #444441 | #5F5E5A |
| `c-red` | #FCEBEB | #A32D2D | #791F1F | #A32D2D |

### Color assignment rules

1. **Encode meaning, not sequence.** Don't cycle colors (step 1 = blue, step 2 = amber, step 3 = teal). Group nodes by CATEGORY — all nodes of the same type share one color.

2. **2–3 ramps maximum per diagram.** More colors = more visual noise. `c-gray + c-purple + c-teal` is cleaner than 6 ramps.

3. **Reserve semantic colors.** `c-blue` = informational, `c-green` = success, `c-amber` = warning, `c-red` = error. Don't use these for arbitrary categorization.

4. **Map physical properties in illustrative diagrams:** warm (amber/coral/red) = heat/energy/pressure, cool (blue/teal) = cold/calm, green = organic/growth, gray = inert structure.

5. **Prefer purple, teal, coral, pink** for general diagram categories without semantic meaning.

---

## Typography system

### Text classes (always include one of these on every `<text>`)

```svg
class="th"  → 14px / font-weight 500 / primary color (titles, node labels)
class="t"   → 14px / font-weight 400 / primary color (body labels)
class="ts"  → 12px / font-weight 400 / secondary color (subtitles, annotations)
```

**An unclassed `<text>` inherits SVG defaults** — wrong font, wrong size, wrong color. Every `<text>` must have a class.

### Vertical centering — always required

```svg
<!-- CORRECT: text centered vertically in its slot -->
<text class="th" x="140" y="52" text-anchor="middle" dominant-baseline="central">
  Label
</text>

<!-- WRONG: y is the baseline, not the center — text appears too high -->
<text class="th" x="140" y="52" text-anchor="middle">
  Label
</text>
```

**Formula:** For a rect at `(rx, ry, rw, rh)`, center a single line of text at:
```
x = rx + rw/2    (horizontal center)
y = ry + rh/2    (vertical center)
```

For two-line boxes (title + subtitle):
```
title y    = ry + rh/3       (upper third)
subtitle y = ry + (2 × rh/3) (lower third)
```

### Font width calibration

At 14px Anthropic Sans, characters are approximately:
```
Regular Latin:      ~7.5px per character
Bold/500 Latin:     ~8px per character
Subtitle/ts Latin:  ~7px per character
CJK characters:     ~14px per character (full-width)
Subscript numbers:  ~6px per character
```

**Pre-computation example:**
```
Label: "Authentication Service" (22 chars, font-weight 500)
Width ≈ 22 × 8 = 176px
Box width = 176 + 24 (padding) = 200px minimum

Subtitle: "Validates incoming tokens" (25 chars)
Width ≈ 25 × 7 = 175px
Box width = max(200, 175 + 24) = 200px → use 200px
```

### Text does not auto-wrap

Every line break requires an explicit `<tspan>`:
```svg
<text class="ts" x="140" y="60" text-anchor="middle" dominant-baseline="central">
  <tspan x="140" dy="0">First line of text</tspan>
  <tspan x="140" dy="1.4em">Second line of text</tspan>
</text>
```

If a subtitle needs wrapping, it's too long — shorten it to ≤5 words.

---

## Node patterns

### Single-line node (44px tall)
```svg
<g class="node c-purple" onclick="sendPrompt('Tell me more about Input')">
  <rect x="60" y="30" width="180" height="44" rx="8" stroke-width="0.5"/>
  <text class="th" x="150" y="52" text-anchor="middle" dominant-baseline="central">
    Input tokens
  </text>
</g>
```

### Two-line node (56px tall)
```svg
<g class="node c-teal" onclick="sendPrompt('How do transformer layers process tokens?')">
  <rect x="60" y="30" width="200" height="56" rx="8" stroke-width="0.5"/>
  <text class="th" x="160" y="47" text-anchor="middle" dominant-baseline="central">
    Transformer layer
  </text>
  <text class="ts" x="160" y="67" text-anchor="middle" dominant-baseline="central">
    attention + FFN
  </text>
</g>
```

### Start/end node (neutral gray)
```svg
<g class="node" onclick="sendPrompt('What triggers this process?')">
  <rect class="box" x="60" y="30" width="120" height="44" rx="22" stroke-width="0.5"/>
  <text class="t" x="120" y="52" text-anchor="middle" dominant-baseline="central">
    Start
  </text>
</g>
```

### Container node (structural diagram outer)
```svg
<g class="c-green">
  <rect x="40" y="30" width="600" height="240" rx="20" stroke-width="0.5"/>
  <text class="th" x="60" y="60" dominant-baseline="central">
    System boundary
  </text>
</g>
```

---

## Connector patterns

### Simple arrow
```svg
<line x1="240" y1="52" x2="318" y2="52" class="arr" marker-end="url(#arrow)"/>
```

### L-bend (when direct path would cross a box)
```svg
<!-- Vertical then horizontal routing -->
<path d="M 140 74 L 140 110 L 380 110 L 380 86"
      fill="none" class="arr" marker-end="url(#arrow)"/>
```

### Labeled connector
```svg
<!-- Put label in clear space above/below the line, never on its midpoint -->
<line x1="240" y1="52" x2="318" y2="52" class="arr" marker-end="url(#arrow)"/>
<text class="ts" x="279" y="44" text-anchor="middle" dominant-baseline="central">
  transforms
</text>
```

### Leader line (illustrative diagrams)
```svg
<line x1="386" y1="34" x2="468" y2="70" class="leader"/>
<circle cx="386" cy="34" r="2" fill="var(--t)"/>
<text class="ts" x="474" y="74" dominant-baseline="central">Hot water outlet</text>
```

---

## Pre-built utility classes

The host stylesheet also defines:

```
class="node"   → cursor: pointer, hover opacity 0.85
class="arr"    → stroke 1.5px, color from --border-secondary, fill none
class="box"    → fill from --background-secondary, stroke from --border-secondary
class="leader" → stroke 0.5px, dashed 3 3, --border-tertiary color
```

---

## Complete flowchart example — annotated

```svg
<svg width="100%" viewBox="0 0 680 380">

  <!-- Required: arrow marker in defs -->
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
            stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>

  <!-- Node 1: Start (neutral gray, no onclick needed for start/end) -->
  <g class="node c-gray">
    <rect x="270" y="30" width="140" height="44" rx="22" stroke-width="0.5"/>
    <text class="th" x="340" y="52" text-anchor="middle" dominant-baseline="central">
      User submits form
    </text>
  </g>

  <!-- Arrow: Node 1 → Node 2 (vertical, straight, no collision) -->
  <line x1="340" y1="74" x2="340" y2="110" class="arr" marker-end="url(#arrow)"/>

  <!-- Node 2: Validation (two-line) -->
  <!-- Width: "Validate input" = 14 chars × 8 = 112 + 24 = 136; subtitle "check types + required" = 22 × 7 = 154 + 24 = 178 → use 200px -->
  <g class="node c-amber" onclick="sendPrompt('What exactly does input validation check?')">
    <rect x="240" y="110" width="200" height="56" rx="8" stroke-width="0.5"/>
    <text class="th" x="340" y="130" text-anchor="middle" dominant-baseline="central">
      Validate input
    </text>
    <text class="ts" x="340" y="150" text-anchor="middle" dominant-baseline="central">
      types, required fields
    </text>
  </g>

  <!-- Decision branches -->
  <!-- Arrow: Node 2 → Error (left branch) -->
  <path d="M 240 138 L 140 138 L 140 240" fill="none" class="arr" marker-end="url(#arrow)"/>
  <text class="ts" x="185" y="132" text-anchor="middle">invalid</text>

  <!-- Arrow: Node 2 → Process (down) -->
  <line x1="340" y1="166" x2="340" y2="202" class="arr" marker-end="url(#arrow)"/>
  <text class="ts" x="355" y="186" dominant-baseline="central">valid</text>

  <!-- Node 3a: Error (left) -->
  <g class="node c-red" onclick="sendPrompt('What error messages are shown to the user?')">
    <rect x="60" y="240" width="160" height="44" rx="8" stroke-width="0.5"/>
    <text class="th" x="140" y="262" text-anchor="middle" dominant-baseline="central">
      Show error
    </text>
  </g>

  <!-- Node 3b: Process (center) -->
  <g class="node c-teal" onclick="sendPrompt('What happens to the data during processing?')">
    <rect x="240" y="202" width="200" height="56" rx="8" stroke-width="0.5"/>
    <text class="th" x="340" y="222" text-anchor="middle" dominant-baseline="central">
      Process &amp; store
    </text>
    <text class="ts" x="340" y="242" text-anchor="middle" dominant-baseline="central">
      sanitize, save to DB
    </text>
  </g>

  <!-- Arrow: Process → Success -->
  <line x1="340" y1="258" x2="340" y2="294" class="arr" marker-end="url(#arrow)"/>

  <!-- Node 4: Success (neutral) -->
  <g class="node c-gray">
    <rect x="270" y="294" width="140" height="44" rx="22" stroke-width="0.5"/>
    <text class="th" x="340" y="316" text-anchor="middle" dominant-baseline="central">
      Success response
    </text>
  </g>

</svg>
```

---

## Complete illustrative diagram example — attention mechanism

```svg
<svg width="100%" viewBox="0 0 680 320">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
            stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>

  <!-- Transformer layers (structural backdrop) -->
  <g class="c-purple">
    <rect x="60" y="30" width="560" height="26" rx="6" stroke-width="0.5"/>
    <text class="ts" x="72" y="43" dominant-baseline="central">Layer 3 — output</text>
  </g>
  <g class="c-purple">
    <rect x="60" y="70" width="560" height="26" rx="6" stroke-width="0.5"/>
    <text class="ts" x="72" y="83" dominant-baseline="central">Layer 2</text>
  </g>
  <g class="c-purple">
    <rect x="60" y="110" width="560" height="26" rx="6" stroke-width="0.5"/>
    <text class="ts" x="72" y="123" dominant-baseline="central">Layer 1</text>
  </g>

  <!-- Attention weight lines — stroke-width encodes weight magnitude -->
  <!-- From query token "sat" (x=340) to each key token -->
  <line x1="340" y1="220" x2="116" y2="136" stroke="#EF9F27" stroke-width="0.8" opacity="0.25" stroke-linecap="round"/>
  <line x1="340" y1="220" x2="228" y2="136" stroke="#EF9F27" stroke-width="1.5" opacity="0.40" stroke-linecap="round"/>
  <line x1="340" y1="220" x2="340" y2="136" stroke="#EF9F27" stroke-width="5"   opacity="1.00" stroke-linecap="round"/>
  <line x1="340" y1="220" x2="452" y2="136" stroke="#EF9F27" stroke-width="2.5" opacity="0.70" stroke-linecap="round"/>
  <line x1="340" y1="220" x2="564" y2="136" stroke="#EF9F27" stroke-width="0.8" opacity="0.20" stroke-linecap="round"/>

  <!-- Token row — query token highlighted in amber, others in gray -->
  <g class="node c-gray" onclick="sendPrompt('What is the query token in attention?')">
    <rect x="80" y="204" width="72" height="36" rx="6" stroke-width="0.5"/>
    <text class="ts" x="116" y="222" text-anchor="middle" dominant-baseline="central">the</text>
  </g>
  <g class="node c-gray" onclick="sendPrompt('How does the word cat attend to other words?')">
    <rect x="192" y="204" width="72" height="36" rx="6" stroke-width="0.5"/>
    <text class="ts" x="228" y="222" text-anchor="middle" dominant-baseline="central">cat</text>
  </g>
  <!-- Query token (amber = active/attending) -->
  <g class="node c-amber" onclick="sendPrompt('Why is sat the query token in this example?')">
    <rect x="304" y="200" width="72" height="44" rx="6" stroke-width="1.5"/>
    <text class="th" x="340" y="222" text-anchor="middle" dominant-baseline="central">sat</text>
    <text class="ts" x="340" y="236" text-anchor="middle" dominant-baseline="central">query</text>
  </g>
  <g class="node c-gray" onclick="sendPrompt('What does on attend to?')">
    <rect x="416" y="204" width="72" height="36" rx="6" stroke-width="0.5"/>
    <text class="ts" x="452" y="222" text-anchor="middle" dominant-baseline="central">on</text>
  </g>
  <g class="node c-gray" onclick="sendPrompt('Why does the second the get low attention weight?')">
    <rect x="528" y="204" width="72" height="36" rx="6" stroke-width="0.5"/>
    <text class="ts" x="564" y="222" text-anchor="middle" dominant-baseline="central">the</text>
  </g>

  <!-- Caption — placed in clear space below, no strokes crossing it -->
  <text class="ts" x="340" y="274" text-anchor="middle" dominant-baseline="central">
    line thickness = how strongly "sat" attends to each other token
  </text>
  <text class="ts" x="340" y="292" text-anchor="middle" dominant-baseline="central">
    click any token to make it the query and see its attention pattern
  </text>
</svg>
```

---

## Checklist before finalizing any SVG

Run this checklist before submitting:

- [ ] `viewBox="0 0 680 H"` — is H computed correctly (max bottom edge + 20)?
- [ ] All `<text>` elements have a class (`t`, `ts`, or `th`)?
- [ ] All `<text>` elements have `dominant-baseline="central"`?
- [ ] All `<text>` elements have `text-anchor="middle"` or `"start"` or `"end"` as appropriate?
- [ ] All colored nodes use `c-{ramp}` classes — no hardcoded hex colors?
- [ ] All connector `<path>` elements have `fill="none"`?
- [ ] No arrow crosses through a box interior (check each one geometrically)?
- [ ] All box widths were computed from label character counts?
- [ ] Rightmost element's (x + width) ≤ 640?
- [ ] All `<text>` with `text-anchor="end"` — does `label_chars × 8 < anchor_x`?
- [ ] No DOCTYPE, no `<html>`, no `<head>`, no `<body>`?
- [ ] No HTML comments (`<!-- -->`)?
- [ ] All clickable nodes wrapped in `<g class="node ..." onclick="sendPrompt('...')">`?
- [ ] sendPrompt questions are specific to the node — not generic "tell me more"?
