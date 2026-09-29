# Design System — Colors, Typography, and Theming

## Philosophy

The design system has two goals:
1. **Consistency** — every visual looks like it belongs to the same product
2. **Automatic dark mode** — no manual dark-mode variants needed for diagram code

Both goals are achieved through CSS custom properties injected by the host into every iframe. Widget code never hardcodes colors — it uses class names and variables that the host resolves at paint time.

---

## The 9-ramp color palette

Each ramp has 7 stops: 50 (lightest), 100, 200, 400, 600, 800, 900 (darkest).

### Purple
| Stop | Hex | Usage |
|------|-----|-------|
| 50   | #EEEDFE | Light mode fill (c-purple background) |
| 100  | #CECBF6 | Light fills, dark mode text |
| 200  | #AFA9EC | Borders, dark mode subtitle text |
| 400  | #7F77DD | Mid tones, interactive elements |
| 600  | #534AB7 | Light mode stroke, dark fills |
| 800  | #3C3489 | Light mode title text, dark mode fill |
| 900  | #26215C | Darkest text, dark backgrounds |

### Teal
| Stop | Hex |
|------|-----|
| 50   | #E1F5EE |
| 100  | #9FE1CB |
| 200  | #5DCAA5 |
| 400  | #1D9E75 |
| 600  | #0F6E56 |
| 800  | #085041 |
| 900  | #04342C |

### Amber
| Stop | Hex |
|------|-----|
| 50   | #FAEEDA |
| 100  | #FAC775 |
| 200  | #EF9F27 |
| 400  | #BA7517 |
| 600  | #854F0B |
| 800  | #633806 |
| 900  | #412402 |

### Coral
| Stop | Hex |
|------|-----|
| 50   | #FAECE7 |
| 100  | #F5C4B3 |
| 200  | #F0997B |
| 400  | #D85A30 |
| 600  | #993C1D |
| 800  | #712B13 |
| 900  | #4A1B0C |

### Blue
| Stop | Hex |
|------|-----|
| 50   | #E6F1FB |
| 100  | #B5D4F4 |
| 200  | #85B7EB |
| 400  | #378ADD |
| 600  | #185FA5 |
| 800  | #0C447C |
| 900  | #042C53 |

### Green
| Stop | Hex |
|------|-----|
| 50   | #EAF3DE |
| 100  | #C0DD97 |
| 200  | #97C459 |
| 400  | #639922 |
| 600  | #3B6D11 |
| 800  | #27500A |
| 900  | #173404 |

### Pink
| Stop | Hex |
|------|-----|
| 50   | #FBEAF0 |
| 100  | #F4C0D1 |
| 200  | #ED93B1 |
| 400  | #D4537E |
| 600  | #993556 |
| 800  | #72243E |
| 900  | #4B1528 |

### Gray
| Stop | Hex |
|------|-----|
| 50   | #F1EFE8 |
| 100  | #D3D1C7 |
| 200  | #B4B2A9 |
| 400  | #888780 |
| 600  | #5F5E5A |
| 800  | #444441 |
| 900  | #2C2C2A |

### Red
| Stop | Hex |
|------|-----|
| 50   | #FCEBEB |
| 100  | #F7C1C1 |
| 200  | #F09595 |
| 400  | #E24B4A |
| 600  | #A32D2D |
| 800  | #791F1F |
| 900  | #501313 |

---

## Light/dark mode stops

When the `c-{ramp}` class is applied to an SVG group, the host stylesheet resolves these stops automatically:

| Context | Fill | Stroke | Title text | Subtitle text |
|---------|------|--------|-----------|--------------|
| Light mode | 50 stop | 600 stop | 800 stop | 600 stop |
| Dark mode | 800 stop | 200 stop | 100 stop | 200 stop |

**Example for c-blue:**
```
Light: fill=#E6F1FB, stroke=#185FA5, title text=#0C447C, subtitle text=#185FA5
Dark:  fill=#0C447C, stroke=#85B7EB, title text=#B5D4F4, subtitle text=#85B7EB
```

This is why you never hardcode hex values in diagram code — the same class produces the correct color in both modes.

---

## CSS variables reference — complete list

### Page background
```css
--color-background-primary    /* #ffffff / #141417 */
--color-background-secondary  /* #f4f2eb / #1a1a1f */
--color-background-tertiary   /* #eceae3 / #0d0d0f */
```

### Semantic backgrounds (for status indicators)
```css
--color-background-info       /* blue-50 / rgba(blue,0.15) */
--color-background-success    /* green-50 / rgba(green,0.15) */
--color-background-warning    /* amber-50 / rgba(amber,0.15) */
--color-background-danger     /* coral-50 / rgba(coral,0.15) */
```

### Text
```css
--color-text-primary          /* #1a1918 / #e8e6df */
--color-text-secondary        /* #5a5855 / #9b9890 */
--color-text-tertiary         /* #9b9890 / #5e5c58 */
--color-text-info             /* #185fa5 / #378add */
--color-text-success          /* #27500a / #639922 */
--color-text-warning          /* #633806 / #ef9f27 */
--color-text-danger           /* #712b13 / #d85a30 */
```

### Borders
```css
--color-border-tertiary       /* rgba(0,0,0,0.09) / rgba(255,255,255,0.08) */
--color-border-secondary      /* rgba(0,0,0,0.14) / rgba(255,255,255,0.14) */
--color-border-primary        /* rgba(0,0,0,0.4)  / rgba(255,255,255,0.4)  */
--color-border-info           /* blue-600 / blue-400 */
--color-border-success        /* green-600 / green-400 */
--color-border-warning        /* amber-600 / amber-400 */
--color-border-danger         /* coral-600 / coral-400 */
```

### Typography
```css
--font-sans                   /* 'Anthropic Sans', system-ui, sans-serif */
--font-mono                   /* 'JetBrains Mono', 'Fira Code', monospace */
--font-serif                  /* Georgia, serif */
```

### Layout
```css
--border-radius-sm            /* 4px */
--border-radius-md            /* 8px */
--border-radius-lg            /* 12px */
--border-radius-xl            /* 16px */
```

### SVG shorthand aliases (injected for SVG use)
```css
--p    /* = var(--color-text-primary) */
--s    /* = var(--color-text-secondary) */
--t    /* = var(--color-text-tertiary) */
--bg2  /* = var(--color-background-secondary) */
--b    /* = var(--color-border-tertiary) */
```

---

## Typography rules

### Font sizes — two sizes only in diagrams

```
14px + weight 500  →  class="th"   (node titles, region names)
14px + weight 400  →  class="t"    (body labels, general text)
12px + weight 400  →  class="ts"   (subtitles, annotations, callouts)
```

No other font sizes in SVG diagrams. In HTML widgets: h1=22px, h2=18px, h3=16px, body=16px, caption=13px.

### Font weight — two weights only
```
400  →  regular (body, descriptions)
500  →  medium (headings, labels, emphasis)
```

Never use 600, 700, or 800 weight in widget HTML. They appear too heavy against the host UI.

### Sentence case everywhere
```
CORRECT: "Transformer layer"
WRONG:   "Transformer Layer"  (Title Case)
WRONG:   "TRANSFORMER LAYER"  (ALL CAPS)
```

This applies to SVG labels, HTML headings, button text, and diagram annotations.

---

## Spacing and layout tokens

### Border widths
```
Default stroke:   0.5px (diagram borders, edges)
Emphasis stroke:  1px   (selected nodes, active elements)
Featured border:  2px   (featured cards — ONLY exception to 0.5px rule)
```

### Border radius
```
Slight corners:   rx="4"   (SVG) / border-radius: 4px (HTML)
Standard corners: rx="8"   (SVG) / border-radius: var(--border-radius-md) (HTML)
Card corners:     rx="12"  (SVG) / border-radius: var(--border-radius-lg) (HTML)
Pill shape:       rx ≥ half the element height
```

**No rounded corners on single-sided borders.** `border-left: 2px solid X` must have `border-radius: 0`.

### Spacing rhythm
```
Component-internal gaps: 8px, 12px, 16px, 24px (px values)
Vertical rhythm between sections: 1rem, 1.5rem, 2rem (rem values)
SVG minimum box padding: 24px each side
SVG minimum between nodes: 60px
SVG minimum inside structural containers: 20px
```

---

## Physical-color exception

Molecular structures, anatomical diagrams, and material cross-sections use conventional colors that must NOT invert in dark mode:

```
Chemistry atom colors (Jmol convention):
  Hydrogen:  #FFFFFF (white)
  Carbon:    #404040 (dark gray)
  Nitrogen:  #3050F8 (blue)
  Oxygen:    #FF0D0D (red)
  Sulfur:    #FFFF30 (yellow)
  Phosphorus: #FF8000 (orange)

Physics / material colors:
  Copper wire:  #B87333
  Silicon:      #A0A0A0
  Water:        #4169E1 (transparent fill)
  Sky:          #87CEEB
  Earth/soil:   #8B4513
```

**Rule:** When generating physical-color diagrams, hardcode these hex values and do NOT apply `c-{ramp}` classes to these shapes. Add `@media (prefers-color-scheme: dark)` overrides if any element specifically needs a dark-mode variant.

---

## Color assignment decision tree

```
Assign color to a node:
├── Is this a START or END node? → c-gray (neutral)
├── Does this represent an ERROR or DANGER state? → c-red or c-coral
├── Does this represent SUCCESS or COMPLETION? → c-green
├── Does this represent a WARNING or CAUTION? → c-amber
├── Does this represent INFORMATION? → c-blue
├── Is this in a PHYSICAL diagram?
│   ├── Hot/active/high-energy? → c-amber or c-coral
│   ├── Cold/passive/low-energy? → c-blue or c-teal
│   └── Structural/inert? → c-gray
└── Category-based grouping (most common):
    ├── First category → c-purple (preferred for general use)
    ├── Second category → c-teal
    └── Third category → c-coral or c-amber
```

**Never:** Cycle through colors sequentially (node 1 = purple, node 2 = teal, node 3 = amber, node 4 = blue...). This makes color encode sequence rather than meaning.

---

## Color Variety Guidance

The visual learning companion has 9 distinct color ramps available. Using the same ramps repeatedly creates visual fatigue and reduces distinctiveness between concepts.

### Variety Rules

1. **Rotate ramps across consecutive visuals**: If the previous visual used c-purple and c-teal, the next unrelated visual should use different ramps (e.g., c-coral, c-blue, c-green).

2. **Avoid the default triangle**: Resist the urge to always start with purple-teal-amber. This is the most common "safe" choice but creates monotony.

3. **Use color to encode session progression**: 
   - Early concepts: c-purple, c-teal (familiar, calm)
   - Mid-session concepts: c-coral, c-blue, c-green (energy, variety)
   - Important distinctions: c-amber, c-red (attention-grabbing)
   - Neutral/structural: c-gray, c-pink

4. **Related concepts get related colors**: If visualizing attention mechanisms and then transformer architecture, keeping the same color family (purples/blues) helps connect the concepts. Unrelated concepts (attention mechanisms → sorting algorithms) should switch ramps entirely.

### Example Session Progression

```
Turn 1: "Explain attention" → c-purple, c-teal (familiar base)
Turn 2: "Show transformer architecture" → c-purple, c-blue, c-teal (building on attention)
Turn 3: "Compare sorting algorithms" → c-coral, c-green, c-amber (fresh distinction)
Turn 4: "How does backprop work?" → c-blue, c-pink (new concept, new colors)
Turn 5: "Compare optimizers" → c-amber, c-red, c-gray (attention-grabbing comparison)
```

### Color Ramp Quick Reference

| Ramp | Character | Best Used For |
|------|-------------|---------------|
| c-purple | Calm, familiar, default | General starting point |
| c-teal | Technical, cool, precise | Algorithms, processes |
| c-amber | Warm, active, caution | Energy, warnings, activity |
| c-coral | Vibrant, urgent | Attention mechanisms, important distinctions |
| c-blue | Trustworthy, informational | Data flow, information processing |
| c-green | Positive, growth | Success states, convergence, growth |
| c-pink | Distinctive, alternate | Secondary categories, alternatives |
| c-gray | Neutral, structural | Infrastructure, containers, defaults |
| c-red | Critical, danger | Errors, breaking conditions, critical paths |

---

## The injected stylesheet — full implementation

This is what the host must inject into every iframe as a `<style>` block prepended to the srcdoc. Agents building the host application must implement this exactly.

```css
/* ── ROOT VARIABLES ─────────────────────────────────────── */
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
  /* SVG shorthand */
  --p: #1a1918;
  --s: #5a5855;
  --t: #9b9890;
  --bg2: #f4f2eb;
  --b: rgba(0,0,0,0.09);
}

/* ── DARK MODE OVERRIDES ─────────────────────────────────── */
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
    --p: #e8e6df;
    --s: #9b9890;
    --t: #5e5c58;
    --bg2: #1a1a1f;
    --b: rgba(255,255,255,0.08);
  }
}

/* ── SVG COLOR CLASSES ───────────────────────────────────── */
.c-purple > rect, .c-purple > circle, .c-purple > ellipse
  { fill: #EEEDFE; stroke: #534AB7; }
.c-purple > text.t, .c-purple > text.th { fill: #3C3489; }
.c-purple > text.ts { fill: #534AB7; }

.c-teal > rect, .c-teal > circle, .c-teal > ellipse
  { fill: #E1F5EE; stroke: #0F6E56; }
.c-teal > text.t, .c-teal > text.th { fill: #085041; }
.c-teal > text.ts { fill: #0F6E56; }

.c-blue > rect, .c-blue > circle, .c-blue > ellipse
  { fill: #E6F1FB; stroke: #185FA5; }
.c-blue > text.t, .c-blue > text.th { fill: #0C447C; }
.c-blue > text.ts { fill: #185FA5; }

.c-amber > rect, .c-amber > circle, .c-amber > ellipse
  { fill: #FAEEDA; stroke: #854F0B; }
.c-amber > text.t, .c-amber > text.th { fill: #633806; }
.c-amber > text.ts { fill: #854F0B; }

.c-green > rect, .c-green > circle, .c-green > ellipse
  { fill: #EAF3DE; stroke: #3B6D11; }
.c-green > text.t, .c-green > text.th { fill: #27500A; }
.c-green > text.ts { fill: #3B6D11; }

.c-coral > rect, .c-coral > circle, .c-coral > ellipse
  { fill: #FAECE7; stroke: #993C1D; }
.c-coral > text.t, .c-coral > text.th { fill: #712B13; }
.c-coral > text.ts { fill: #993C1D; }

.c-pink > rect, .c-pink > circle, .c-pink > ellipse
  { fill: #FBEAF0; stroke: #993556; }
.c-pink > text.t, .c-pink > text.th { fill: #72243E; }
.c-pink > text.ts { fill: #993556; }

.c-gray > rect, .c-gray > circle, .c-gray > ellipse
  { fill: #F1EFE8; stroke: #5F5E5A; }
.c-gray > text.t, .c-gray > text.th { fill: #444441; }
.c-gray > text.ts { fill: #5F5E5A; }

.c-red > rect, .c-red > circle, .c-red > ellipse
  { fill: #FCEBEB; stroke: #A32D2D; }
.c-red > text.t, .c-red > text.th { fill: #791F1F; }
.c-red > text.ts { fill: #A32D2D; }

/* Dark mode variants for all ramps */
@media (prefers-color-scheme: dark) {
  .c-purple > rect, .c-purple > circle, .c-purple > ellipse
    { fill: #3C3489; stroke: #534AB7; }
  .c-purple > text.t, .c-purple > text.th { fill: #CECBF6; }
  .c-purple > text.ts { fill: #AFA9EC; }

  .c-teal > rect, .c-teal > circle, .c-teal > ellipse
    { fill: #085041; stroke: #0F6E56; }
  .c-teal > text.t, .c-teal > text.th { fill: #9FE1CB; }
  .c-teal > text.ts { fill: #5DCAA5; }

  .c-blue > rect, .c-blue > circle, .c-blue > ellipse
    { fill: #0C447C; stroke: #185FA5; }
  .c-blue > text.t, .c-blue > text.th { fill: #B5D4F4; }
  .c-blue > text.ts { fill: #85B7EB; }

  .c-amber > rect, .c-amber > circle, .c-amber > ellipse
    { fill: #633806; stroke: #854F0B; }
  .c-amber > text.t, .c-amber > text.th { fill: #FAC775; }
  .c-amber > text.ts { fill: #EF9F27; }

  .c-green > rect, .c-green > circle, .c-green > ellipse
    { fill: #27500A; stroke: #3B6D11; }
  .c-green > text.t, .c-green > text.th { fill: #C0DD97; }
  .c-green > text.ts { fill: #97C459; }

  .c-coral > rect, .c-coral > circle, .c-coral > ellipse
    { fill: #712B13; stroke: #993C1D; }
  .c-coral > text.t, .c-coral > text.th { fill: #F5C4B3; }
  .c-coral > text.ts { fill: #F0997B; }

  .c-pink > rect, .c-pink > circle, .c-pink > ellipse
    { fill: #72243E; stroke: #993556; }
  .c-pink > text.t, .c-pink > text.th { fill: #F4C0D1; }
  .c-pink > text.ts { fill: #ED93B1; }

  .c-gray > rect, .c-gray > circle, .c-gray > ellipse
    { fill: #444441; stroke: #5F5E5A; }
  .c-gray > text.t, .c-gray > text.th { fill: #D3D1C7; }
  .c-gray > text.ts { fill: #B4B2A9; }

  .c-red > rect, .c-red > circle, .c-red > ellipse
    { fill: #791F1F; stroke: #A32D2D; }
  .c-red > text.t, .c-red > text.th { fill: #F7C1C1; }
  .c-red > text.ts { fill: #F09595; }
}

/* ── SVG UTILITY CLASSES ─────────────────────────────────── */
text.t  { font-size: 14px; font-weight: 400; fill: var(--color-text-primary);
           font-family: var(--font-sans); }
text.th { font-size: 14px; font-weight: 500; fill: var(--color-text-primary);
           font-family: var(--font-sans); }
text.ts { font-size: 12px; font-weight: 400; fill: var(--color-text-secondary);
           font-family: var(--font-sans); }
.node   { cursor: pointer; }
.node:hover { opacity: 0.82; }
.arr    { stroke: var(--color-border-secondary); stroke-width: 1.5; fill: none; }
.box    { fill: var(--color-background-secondary);
          stroke: var(--color-border-secondary); }
.leader { stroke: var(--color-border-tertiary); stroke-width: 0.5;
          fill: none; stroke-dasharray: 3 3; }

/* ── RESET ───────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: transparent;
  font-family: var(--font-sans);
  color: var(--color-text-primary);
  font-size: 15px;
  line-height: 1.7;
}

/* ── HTML ELEMENT PRE-STYLES ─────────────────────────────── */
input[type="range"] {
  width: 100%;
  accent-color: var(--color-text-info);
  cursor: pointer;
}
input[type="text"], input[type="number"] {
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--border-radius-md);
  background: var(--color-background-secondary);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  font-size: 14px;
}
input[type="text"]:focus, input[type="number"]:focus {
  outline: none;
  border-color: var(--color-border-info);
}
button {
  background: transparent;
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--border-radius-md);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  padding: 7px 16px;
  cursor: pointer;
  transition: background 0.15s, transform 0.1s;
}
button:hover  { background: var(--color-background-secondary); }
button:active { transform: scale(0.98); }
select {
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--border-radius-md);
  background: var(--color-background-secondary);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  font-size: 14px;
  cursor: pointer;
}
```
