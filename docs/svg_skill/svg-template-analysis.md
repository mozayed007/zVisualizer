---
name: svg-template-analysis
part-of: svg-template-agent
---

# SVG Template Analysis — Parsing and Safe Zone Inference

## Purpose

Before any content can be inserted, the agent must fully understand the template's internal structure. This means parsing the SVG DOM, classifying every element, and producing a structural map that drives every subsequent editing decision.

**This analysis always runs on the source template — read-only.** The structural map is then applied to the working clone. Analysis findings are never assumed to persist across templates; every new template is analyzed fresh.

---

## The structural map

The output of analysis is a `TemplateStructuralMap` — a typed representation of every element in the SVG and its role. The map drives all downstream decisions.

```text
TemplateStructuralMap {
  viewBox: { x, y, width, height }
  slots: SlotRegion[]
  structural_groups: StructuralGroup[]
  defs: DefElement[]
  unsafe_regions: UnsafeRegion[]
  brand_tokens: BrandToken[]
  transforms: TransformRecord[]
  text_nodes: TextNode[]
  icon_nodes: IconNode[]
  identity_map: IdentityRecord[]
}
```

`identity_map` records the original organizational signature of the SVG so later validation can prove that editing preserved it.

---

## DOM traversal order

Traverse the SVG in this order to build the structural map:

1. **Parse `<defs>`** — catalog all `<clipPath>`, `<mask>`, `<marker>`, `<linearGradient>`, `<radialGradient>`, `<pattern>`, `<symbol>`, `<filter>`. These are structural elements. They must never be modified unless the brand system explicitly permits a gradient or color swap.

2. **Identify root-level `<g>` elements** — each root group typically represents one major structural zone (background, content area, decoration). Record `id`, `class`, and `transform` attributes.

   Also record:
   - parent id
   - sibling index
   - child ids in order
   - whether the group participates in clipping, masking, or symbol use

3. **Walk each `<g>` recursively** — at each level, classify the element as one of:
   - `slot`: an editable region containing a text node or icon placeholder
   - `structural`: a shape that defines layout (background rect, divider line, connector arrow)
   - `decorative`: a non-content visual (pattern, gradient fill, illustration element)
   - `def_consumer`: an element whose visual depends on a `<defs>` entry (via `clip-path`, `mask`, `fill=url(...)`)

4. **Catalog all `<text>` and `<tspan>` elements** — for each, record: parent group `id`, x/y position, `text-anchor`, `dominant-baseline`, `font-size`, `font-weight`, `fill`, max character width (estimated from `textLength` or inferred), and current content.

5. **Catalog all `<image>`, `<use>`, and icon-shaped `<path>` elements** — these are potential icon slots.

6. **Record all `transform` attribute values** — never infer that a group at x=200 is centered by naive x reading if the parent group has `transform="translate(50,0)"`. Resolve all transforms to absolute coordinates.

7. **Record identity signatures** — for every element with an `id`, especially every `<g>`:
   - tag name
   - id
   - parent id
   - ordered child id list
   - sibling index
   - reference attributes (`href`, `xlink:href`, `clip-path`, `mask`, `filter`)

   This identity signature is later compared against the working copy to ensure the SVG's organization was preserved.

---

## Element classification rules

### Slot detection

A group or element is a **slot** (editable) if it satisfies ALL of:

- Contains at least one `<text>` or `<tspan>` element
- The text content is a placeholder pattern (see below)
- It is not referenced as a structural anchor by a connector or layout guide

**Placeholder patterns to detect:**

```text
Exact strings:  "Title", "Subtitle", "Label", "Description", "Step N", "Item N",
                "Header", "Body", "Caption", "Category", "Stage N", "Point N",
                "Name", "Value", "Number", "Text here", "Enter text",
                "Placeholder", "[text]", "...", "•"

Regex patterns:
  /^Title\s*\d*$/i
  /^Step\s+\d+$/i
  /^Item\s+\d+$/i
  /^\[.*\]$/
  /^(Your|Enter|Add)\s/i
  /^\d+\.\s*(title|label|text)?$/i
```

**Icon placeholder patterns:**

```text
<rect> or <circle> with class="icon-placeholder" or id containing "icon"
<path> with d="M..." and fill="none" and class/id suggesting placeholder
<use> with href referencing a placeholder symbol
<image> with href pointing to a default/generic icon asset
```

### Structural element detection

An element is **structural** (do not edit) if:

- It is a background shape (rect spanning >80% of viewBox width or height)
- It is a connector line or arrow between slots
- It is a border or frame element
- Its `id` or `class` contains: `bg`, `background`, `frame`, `border`, `connector`, `arrow`, `guide`, `grid`, `axis`, `divider`, `separator`
- It is referenced by `clip-path` or `mask` on another element
- Removing it would cause other elements to lose their visual boundary

### Decorative element detection

An element is **decorative** if:

- It has no text content and is not referenced by any slot
- Its `opacity` is ≤ 0.3 (likely a watermark or texture)
- It uses a `<pattern>` or `<filter>` fill
- It is positioned entirely outside any slot's bounding box
- Its `id` or `class` contains: `deco`, `decoration`, `ornament`, `texture`, `bg-art`

---

## Transform resolution

**Never read coordinates without resolving the full transform chain.** A `<text>` at `x=50 y=20` inside a `<g transform="translate(100, 80)">` is actually at absolute position `x=150 y=100`.

### Transform types to handle

```text
translate(tx, ty)          → add tx to x, ty to y
scale(sx [, sy])           → multiply x by sx, y by sy
rotate(angle [cx, cy])     → trigonometric rotation around pivot
matrix(a b c d e f)        → full affine transform
skewX(angle) / skewY(angle) → shear transforms (rare in templates, flag as unsafe if present)
```

### Resolution algorithm

For any element E at depth D:

1. Start with element's own `x`, `y` (or `cx`, `cy` for circles)
2. Walk up the ancestor chain, collecting each group's `transform`
3. Apply transforms in order from outermost to innermost
4. The resolved coordinate is the absolute page position

**Store both**: original local coordinate AND resolved absolute coordinate in the structural map. Editing uses local coordinates; validation uses absolute coordinates.

---

## Safe zone inference

After analysis, the agent must classify every region of the viewBox as:

| Zone type | Definition | Agent behavior |
| ----------- | ----------- | ----------- |
| **editable_slot** | Identified slot region | May fill with content |
| **editable_icon** | Icon placeholder region | May replace with approved icon |
| **brand_structural** | Structural element using brand tokens | Must not modify geometry or color |
| **unsafe_def** | Element consuming a clipPath or mask | Must not modify at all |
| **decorative** | Purely visual, non-semantic | Must not modify |
| **unknown** | Cannot be classified confidently | Must not modify; flag for human review |

**Rule:** If an element's classification is ambiguous, default to `unknown` and treat as non-editable. Never attempt to edit an element classified as `unknown`.

---

## viewBox contract

The template's `viewBox="x y W H"` defines the coordinate system for the entire document. These four values are the coordinate contract.

**Non-negotiable rules:**

- Never change the viewBox values in the working copy
- Never scale or resize the viewBox to fit content
- Never add `width` or `height` attributes that conflict with the viewBox aspect ratio
- If content cannot fit within the viewBox at the original font sizes, the answer is content reduction or template switching — not viewBox expansion

---

## defs catalog

Every entry in `<defs>` must be cataloged before editing begins.

| Def type | Risk level | Edit rule |
| ----------- | ----------- | ----------- |
| `<clipPath>` | CRITICAL | Never modify geometry; never change `id` |
| `<mask>` | CRITICAL | Never modify; any change breaks masked elements |
| `<linearGradient>` | HIGH | Color stops may be swapped if brand permits; geometry must not change |
| `<radialGradient>` | HIGH | Same as linearGradient |
| `<filter>` | HIGH | Never modify |
| `<marker>` | MEDIUM | Do not change geometry; color may be swapped if brand permits |
| `<symbol>` | MEDIUM | May substitute icon content only inside `<symbol>` blocks designated as icon slots |
| `<pattern>` | LOW | Decorative only; do not modify |

---

## Group nesting analysis

Deep nesting is common in professional SVG templates. The agent must understand the nesting purpose before touching anything inside.

### Nesting patterns to recognize

**Slot group pattern:**

```xml
<g id="slot-1" class="content-slot">
  <rect id="slot-1-bg" .../>          ← background of the slot, structural
  <text id="slot-1-title" ...>Title</text>  ← editable
  <text id="slot-1-body" ...>Description</text>  ← editable
</g>
```

**Icon + label compound slot:**

```xml
<g id="feature-3">
  <g id="feature-3-icon">             ← icon group, may be editable
    <circle .../>
    <use href="#icon-placeholder"/>
  </g>
  <g id="feature-3-text">            ← text group, editable
    <text class="label">Label</text>
    <text class="body">Body text</text>
  </g>
</g>
```

**Transform-offset layout group:**

```xml
<g transform="translate(240, 0)">    ← positional offset, structural
  <g id="col-2-slot">                ← actual slot inside offset group
    <rect .../>
    <text>...</text>
  </g>
</g>
```

**Rule:** Never apply a `transform` to a slot group when editing. If text needs repositioning, adjust the text's own `x`/`y` attributes inside its existing group — never by adding a transform to the group itself.

### Group identity rules

Every group with an `id` is part of the SVG's identity contract. During analysis, treat these properties as protected:

- group tag name
- group `id`
- parent group
- child ordering
- participation in clipping or masking chains

If a future edit would require changing any of these, that is a structural mutation, not a text edit.

---

## Analysis output format

The agent must produce and log a structural map summary before proceeding to the CLONE stage. Minimum required output:

```text
TEMPLATE ANALYSIS SUMMARY
─────────────────────────
viewBox: 0 0 1200 675
Total slots: 4
  slot-1 (title):   editable text, x=60 y=80, W=520, H=60, anchor=start
  slot-2 (body-1):  editable text, x=60 y=160, W=520, H=120, anchor=start, 2-line
  slot-3 (body-2):  editable text, x=640 y=160, W=520, H=120, anchor=start, 2-line
  slot-4 (caption): editable text, x=60 y=600, W=1080, H=40, anchor=middle
Icon slots: 2 (slot-icon-1, slot-icon-2)
Structural groups: 6 (background, frame, divider, connector-1, connector-2, logo-zone)
Defs catalog: 1 clipPath, 1 linearGradient, 2 markers
Unsafe regions: logo-zone (locked), bg-art (decorative)
Brand tokens detected: fill=#2B5CEF (primary), fill=#F5F5F5 (surface), stroke=#CCCCCC
Transform chain: root group has no transform; slot-3 parent has translate(640,0)
Identity checks: group ids stable, child order recorded, defs references recorded
```
