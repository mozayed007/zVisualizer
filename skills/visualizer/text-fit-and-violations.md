# Text Fit and Geometric Violations — Visualizer Agent

## Purpose

Visualizer-agent SVGs are authored from scratch, not cloned from a template, so every `<rect>` and `<text>` placement is the agent's responsibility. The most common production defect is copy that overflows its box — either a single line that extends past `rect.right`, a multi-line block that extends below `rect.bottom`, or a callout rectangle that covers a sibling node. The widget validator enforces a geometric contract to catch these before the widget is rendered.

**Measure before you place. Wrap before you insert. Validate after you insert.**

---

## Character width model

Every `<text>` uses one of the host-injected classes. The validator and the agent share these metrics:

| Class | Font size | Weight factor | Notes |
|-------|-----------|---------------|-------|
| `th`  | 14 px     | 0.58          | title / node label (weight 500) |
| `t`   | 14 px     | 0.52          | body label (weight 400) |
| `ts`  | 12 px     | 0.50          | subtitle / annotation (weight 400) |

### Width formula

```
safe_text_width(chars, class) =
  chars × font_size[class] × weight_factor[class] × 1.08   # +8% kerning margin
```

### Required rect width

```
required_rect_width(class, longest_line_chars) =
  ceil( longest_line_chars × font_size × weight_factor × 1.08 + 24 )
                                                              ^ slot padding
```

### Required rect height

```
line_height = font_size × 1.35
required_rect_height(class, line_count) =
  line_count × line_height + 16       # ~8px vertical padding per side
```

If the copy cannot fit, shorten it first, then wrap with `<tspan>`, then switch to a smaller class — never let text overflow.

---

## Per-class word and character budgets

| Class | Max words | Max chars/line | Max lines |
|-------|-----------|----------------|-----------|
| `th`  | 7         | 40             | 2         |
| `t`   | 10        | 60             | 3         |
| `ts`  | 12        | 80             | 3         |

Exceeding any of these caps raises `V-VIZ-TEXT-WORDCOUNT`.

---

## Bounding-box estimation

For text elements the validator estimates the bbox using the width formula above plus:

- `text-anchor="start"`  → `left = x`
- `text-anchor="middle"` → `left = x - width / 2`
- `text-anchor="end"`    → `left = x - width`
- `dominant-baseline="central"` → `top = y - font_size/2`; other values treat `y` as the baseline.

For `<rect>` elements the bbox is `(x, y, width, height)` with any ancestor `translate(tx, ty)` applied. Non-translate transforms (rotate, scale, skew, matrix) are not decoded — avoid using them on node rects or their labels.

The "container" of a text element is the smallest-area `<rect>` whose bbox contains the text's `(x, y)` anchor point.

---

## Violation catalog — visualizer geometry

### V-VIZ-TEXT-OVERFLOW-H

Text bbox exits its container rect horizontally.

```
trigger:  text.right > rect.right - 4px   OR   text.x < rect.x + 4px
severity: HIGH
repair:   shorten copy → wrap with <tspan> → widen the rect
```

### V-VIZ-TEXT-OVERFLOW-V

Text bbox exits its container rect vertically.

```
trigger:  text.bottom > rect.bottom - 4px   OR   text.y < rect.y + 4px
severity: HIGH
repair:   reduce lines → use a taller rect → move annotation to clear space
```

### V-VIZ-SIBLING-OVERLAP

Two node rectangles (groups carrying `class="node"` or a `c-{ramp}` class) intersect.

```
trigger:  rect_A bbox overlaps rect_B bbox by more than 2px on both axes
severity: HIGH
repair:   move the callout into clear space → shrink the larger rect
```

### V-VIZ-VIEWBOX-ESCAPE

Any rect or text bbox extends outside the root `viewBox`.

```
trigger:  bbox.x < viewbox.x - 4   OR   bbox.y < viewbox.y - 4
          OR   bbox.right > viewbox.right + 4
          OR   bbox.bottom > viewbox.bottom + 4
severity: HIGH
repair:   shorten copy → move element inside safe area → never change the viewBox width 680
```

### V-VIZ-TEXT-WORDCOUNT

Text class exceeds its word / character / line budget.

```
trigger:  words > class_max_words
          OR longest_line > class_max_chars
          OR line_count > class_max_lines
severity: HIGH
repair:   shorten copy → split into a second element → downgrade class only if semantic role still fits
```

### V-VIZ-BOX-WIDTH-FORMULA

Node rect width is smaller than the docs-mandated budget for its label.

```
trigger:  rect.width + 4 < longest_line_chars × font_size × weight_factor × 1.08 + 24
severity: HIGH  (rect is a node; i.e. wrapped in a node / c-{ramp} group)
repair:   widen rect → shorten label
```

---

## Repair loop

When `build_widget_payload` detects a HIGH-severity geometry violation on a visualizer SVG, the failure is attached to the `ValidationAppError` with `kind="visualizer_raw_svg"`. The host runtime then invokes `SvgVisionRepairService.repair_raw_visualizer_svg` exactly once:

1. The failing SVG, a rendered preview, and the full violation list are sent to Gemini with the visualizer contract rules above.
2. The model returns a corrected SVG.
3. The corrected SVG is re-validated via `build_widget_payload`. If any violation remains, the original error is surfaced to the model as a `ModelRetry`.

The repair loop never runs more than once per call — the model must fix every reported violation in a single pass, or the agent is asked to regenerate.

---

## Checklist before emitting an SVG widget

- [ ] `viewBox="0 0 680 H"` — H recomputed from content.
- [ ] Every `<text>` has a class (`t`, `ts`, or `th`) and `dominant-baseline="central"`.
- [ ] For every `<text>` inside a rect, `estimated_width × 1.08 + 24 ≤ rect.width` and the wrapped height fits.
- [ ] Word / char / line counts respect the per-class caps.
- [ ] Callouts and annotations live in clear space or inside their own non-overlapping rect.
- [ ] No two node rectangles overlap by more than 2px.
- [ ] Rightmost rect / text `right ≤ 640`; bottommost `bottom ≤ H - 20`.
