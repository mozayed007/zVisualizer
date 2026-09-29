---
name: text-fitting-and-alignment
part-of: svg-template-agent
---

# Text Fitting and Alignment — Measurement, Line Splitting, and Placement

## Purpose

Incorrect text placement is the most common cause of broken SVG templates. SVG text does not auto-wrap. It does not resize to fit. It does not flow. The agent must compute every text placement decision before inserting content — not after.

**Measure before place. Wrap before insert. Validate after insert.**

---

## Character width model

Without live rendering, the agent estimates text dimensions using a per-font character width model. These are approximate values calibrated for common sans-serif fonts at standard weight. They are used for pre-insertion fit calculations.

### Width estimation table (px per character, at 1px font-size, multiply by actual font-size)

| Font weight | Latin lowercase | Latin uppercase | Digit | Space | CJK |
|------------|----------------|----------------|-------|-------|-----|
| 400 (regular) | 0.52 | 0.65 | 0.60 | 0.28 | 1.00 |
| 500 (medium) | 0.54 | 0.67 | 0.62 | 0.28 | 1.00 |
| 600 (semibold) | 0.56 | 0.70 | 0.64 | 0.30 | 1.00 |
| 700 (bold) | 0.58 | 0.72 | 0.66 | 0.30 | 1.00 |

### Practical formula
```
estimated_char_width(font_size, weight) =
  font_size × weight_factor

estimated_string_width(text, font_size, weight) =
  Σ estimated_char_width(char, font_size, weight) for each char in text

Simpler approximation for mixed-case Latin:
  width ≈ char_count × font_size × 0.56   (weight 400–500)
  width ≈ char_count × font_size × 0.60   (weight 600–700)
```

### Safety margin
Always add 8% to estimated width for kerning and rounding uncertainty:
```
safe_width = estimated_string_width × 1.08
```

---

## Slot capacity model

For each identified slot, the agent computes the capacity before mapping content to it.

```
SlotCapacity {
  max_width:       slot_container.width - (2 × SLOT_INTERNAL_PADDING)
  max_height:      slot_container.height - (2 × SLOT_INTERNAL_PADDING)
  font_size:       extracted from slot's existing text node
  font_weight:     extracted from slot's existing text node
  line_height:     extracted OR inferred as font_size × 1.35
  max_lines:       floor(max_height / line_height)
  max_chars_per_line: floor(max_width / (font_size × per_char_factor))
  total_capacity_chars: max_chars_per_line × max_lines
}
```

### SLOT_INTERNAL_PADDING
If the template's padding is not explicitly specified (via `x` offset within a group), infer it from the difference between the slot container rect's `x` and the text node's `x`:
```
padding = text_node.x - slot_container.x
```
This measured padding is the authoritative value for this slot's capacity calculation.

---

## Fit decision flow

Before inserting any content into a slot:

```
1. Compute slot capacity (max_chars_per_line, max_lines, total_capacity_chars)
2. Estimate content width as a single line
3. If single-line width ≤ max_width: insert as single line, done
4. If single-line width > max_width AND max_lines > 1:
   → compute line breaks (see wrapping algorithm)
   → if wrapped content fits in max_lines: insert with tspans, done
5. If wrapped content exceeds max_lines:
   → attempt font reduction (≤15%, minimum role font size)
   → recompute with reduced font
   → if fits: insert with reduced font, done, flag FONT_REDUCED
6. If still does not fit:
   → request shorter copy OR switch to denser template variant
   → do NOT insert content that will overflow
```

---

## Line wrapping algorithm

SVG text does not auto-wrap. The agent must compute explicit line breaks and produce `<tspan>` elements.

### Input
- `text`: the full string to insert
- `max_chars_per_line`: from slot capacity model
- `x`: the text element's x attribute value (must be applied to each tspan)
- `dy`: line height offset between tspans (= line_height, in px or em)

### Algorithm
```
words = text.split(' ')
current_line = []
lines = []

for each word in words:
  test_line = current_line + [word]
  if estimated_width(test_line.join(' ')) ≤ max_width:
    current_line = test_line
  else:
    if current_line is empty:
      # single word too long — must hyphenate or flag
      lines.append(word[:max_safe_chars] + '-')
      current_line = [word[max_safe_chars:]]  # remainder
    else:
      lines.append(current_line.join(' '))
      current_line = [word]

if current_line:
  lines.append(current_line.join(' '))
```

### Output: tspan structure
```xml
<text id="[original-id]" x="[original-x]" y="[first-line-y]"
      font-size="[original-font-size]" font-weight="[original-font-weight]"
      font-family="[original-font-family]" fill="[original-fill]"
      text-anchor="[original-anchor]" dominant-baseline="central">
  <tspan x="[original-x]" dy="0">[line 1 content]</tspan>
  <tspan x="[original-x]" dy="[line_height]px">[line 2 content]</tspan>
  <tspan x="[original-x]" dy="[line_height]px">[line 3 content]</tspan>
</text>
```

**Critical rules:**
- The `x` attribute must be repeated on every `<tspan>` — without it, each line starts where the previous ended
- The first `<tspan>` has `dy="0"` — it does not shift from the `<text>` element's y
- `dy` on subsequent lines is in px (match the unit used in the source template)
- The `dominant-baseline` on the parent `<text>` applies to the first line; subsequent lines are relative

---

## Alignment modes

### text-anchor="start"
Text flows to the right from the x coordinate.
```
safe_right_edge = text.x + safe_width
must satisfy: safe_right_edge ≤ slot_container.x + slot_container.width - SLOT_INTERNAL_PADDING
```

### text-anchor="middle"
Text extends equally left and right from the x coordinate.
```
safe_left_edge  = text.x - safe_width/2
safe_right_edge = text.x + safe_width/2
must satisfy: safe_left_edge ≥ slot_container.x + SLOT_INTERNAL_PADDING
              safe_right_edge ≤ slot_container.x + slot_container.width - SLOT_INTERNAL_PADDING
```

### text-anchor="end"
Text flows to the left from the x coordinate.
```
safe_left_edge = text.x - safe_width
must satisfy: safe_left_edge ≥ slot_container.x + SLOT_INTERNAL_PADDING
```

**Never change `text-anchor` to fix an overflow.** The anchor is a design decision. Fix the content length.

---

## Vertical positioning rules

### Single-line centering
For a single-line text in a slot container:
```
correct_y = slot_container.y + slot_container.height / 2
```
With `dominant-baseline="central"`, this visually centers the text. If the source text node is already at this position, do not adjust it.

### Multi-line centering (equal-spaced distribution)
For `n` lines in a slot container:
```
total_text_block_height = (n × font_size) + ((n-1) × line_spacing)
top_of_block = slot_container.y + (slot_container.height - total_text_block_height) / 2
first_line_y = top_of_block + (font_size / 2)   # center of first line's cap height
```

### Two-line slot (title + subtitle)
The source template will have pre-positioned y values for title and subtitle. Preserve these y values exactly. Do not recalculate them unless the title wraps to a second line (in which case, shift the subtitle down by one line_height).

---

## Optical centering vs numeric centering

Numerically centered text can feel visually off-center because of uppercase cap height vs descenders and the heaviness of certain characters. In production templates, designers often apply a -2 to -4px vertical offset to "feel" centered.

**Rule:** Do not correct for optical centering. The source template's text nodes are already optically positioned by the designer. Preserve their y values. Only adjust y if adding tspan lines for wrapping.

---

## Content generation guidelines

When the agent generates content (not just places user-provided content), it must respect these rules:

### Length constraints
```
Slot role = "title":    max 5–7 words, max 40 characters
Slot role = "heading":  max 7–10 words, max 60 characters
Slot role = "body":     max 20–25 words per line × max_lines
Slot role = "label":    max 3–4 words, max 25 characters
Slot role = "caption":  max 10–12 words, max 80 characters
Slot role = "number":   numeric only, max 6 characters including units
```

### Sentence case rule
Generated text uses sentence case: capitalize only the first word and proper nouns. Never title-case. Never all-caps (unless the template's existing text is all-caps, in which case match it).

### Parallel structure rule
In templates with multiple sibling slots (list, key-ideas, pyramid levels), all generated labels must have parallel grammatical structure. All noun phrases, or all verb phrases, or all complete sentences — never mixed.

### Specificity over generality
Generated slot content must be specific to the user's subject. Never generate placeholder-sounding content ("Key benefit 1", "Important point here"). Generate real candidate content that the user can keep or edit.
