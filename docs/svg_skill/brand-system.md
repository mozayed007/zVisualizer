---
name: brand-system
part-of: svg-template-agent
---

# Brand System — Preservation and Inference

## Purpose

The client's SVG templates are brand artifacts. Their color palette, typography choices, stroke widths, corner radii, icon style, and spacing logic are intentional design decisions. The agent's job is to preserve that design language exactly — not dilute it, not accidentally override it, and not inject an alien aesthetic into it.

When explicit brand tokens are absent, the agent must infer the local design language from the template library itself. Every library expresses a coherent visual identity that can be reconstructed through systematic observation.

---

## Brand token types

A brand system has these token categories. The agent must catalog every token present in the source templates before touching any working copy.

### Color tokens
```
PRIMARY          → dominant brand color (most frequent fill or stroke)
SECONDARY        → supporting accent color
NEUTRAL_DARK     → dark text, dark backgrounds
NEUTRAL_MID      → borders, dividers, secondary fills
NEUTRAL_LIGHT    → surface backgrounds, light fills
SEMANTIC_SUCCESS → green-family, used for positive states
SEMANTIC_WARNING → amber/orange-family, used for caution states
SEMANTIC_ERROR   → red-family, used for negative states
SEMANTIC_INFO    → blue-family, used for informational states
```

### Typography tokens
```
FONT_FAMILY_PRIMARY    → heading font stack
FONT_FAMILY_BODY       → body text font stack
FONT_SIZE_TITLE        → largest text size in use
FONT_SIZE_HEADING      → section heading size
FONT_SIZE_BODY         → standard body size
FONT_SIZE_CAPTION      → smallest used size
FONT_WEIGHT_BOLD       → heading weight (typically 600–700)
FONT_WEIGHT_REGULAR    → body weight (typically 400)
LETTER_SPACING_LABEL   → tracking applied to labels and captions
LINE_HEIGHT_BODY       → leading for body text blocks
```

### Shape tokens
```
CORNER_RADIUS_SM    → small radius (tags, badges)
CORNER_RADIUS_MD    → standard radius (cards, slots)
CORNER_RADIUS_LG    → large radius (containers, panels)
STROKE_WIDTH_FINE   → fine border (typically 0.5–1px)
STROKE_WIDTH_MEDIUM → standard border (typically 1.5–2px)
STROKE_WIDTH_BOLD   → emphasis border (typically 3–4px)
```

### Spacing tokens
```
SLOT_INTERNAL_PADDING   → gap between slot border and text content
SLOT_HORIZONTAL_GAP     → horizontal gap between adjacent slots
SLOT_VERTICAL_GAP       → vertical gap between stacked slots
ICON_LABEL_GAP          → gap between icon and its associated label
SECTION_MARGIN          → space between major sections
```

---

## Brand token detection — from SVG source

When explicit token documentation is unavailable, the agent extracts the design language by systematically sampling the source SVG files. This produces an **inferred brand token set** that is specific to the client's library.

### Color extraction algorithm
1. Collect all unique `fill` and `stroke` attribute values across all SVG files in the library
2. Exclude: `none`, `transparent`, `inherit`, `currentColor`, white (#fff, #ffffff), black (#000, #000000)
3. Group by perceptual similarity (hue distance < 15°, lightness distance < 10%)
4. The most frequently occurring color cluster = PRIMARY
5. The second most frequent = SECONDARY
6. The darkest color cluster in frequent use = NEUTRAL_DARK
7. Colors in the 40–80% lightness range with low saturation = NEUTRAL_MID / NEUTRAL_LIGHT
8. Log the inferred palette for human confirmation before production use

### Typography extraction algorithm
1. Collect all `font-family`, `font-size`, `font-weight`, `letter-spacing` values across all text nodes
2. The most common `font-family` = FONT_FAMILY_PRIMARY
3. Sort `font-size` values: largest cluster = FONT_SIZE_TITLE, modal value = FONT_SIZE_BODY
4. Most common `font-weight` ≥ 600 = FONT_WEIGHT_BOLD

### Shape extraction algorithm
1. Collect all `rx` (corner radius) values from `<rect>` elements
2. Most common rx value = CORNER_RADIUS_MD
3. Collect all `stroke-width` values from non-structural path/line elements
4. Modal value = STROKE_WIDTH_MEDIUM

---

## Brand application rules

### Rule 1: Never introduce colors not in the inferred palette
When inserting content, only apply colors from the extracted token set. If you need to apply emphasis to inserted text, use the token closest to the intent — never invent a new hex value.

### Rule 2: Typography must match the template's text nodes
Font family, weight, size, and letter-spacing for inserted content must match the existing text nodes in the same slot family. If slot-title uses `font-family="Inter" font-size="24" font-weight="600"`, all inserted titles use exactly that.

### Rule 3: Corner radii must be consistent within a layer
If the template uses `rx="8"` on all card rects, never write `rx="4"` or `rx="12"` on a rect in the working copy. Inconsistent radii are an immediately visible brand violation.

### Rule 4: Stroke widths must be consistent within a role
All borders of the same semantic role (slot borders, connectors, dividers) must use the same stroke-width as the source. Never modify stroke-width to "clean up" the look.

### Rule 5: Do not mix font weights within a text hierarchy level
If all body text in the template is `font-weight="400"`, never insert `font-weight="500"` into a body slot to add emphasis. Use the SEMANTIC color tokens for emphasis instead.

---

## Brand violation types

The agent must detect these violations dynamically after filling:

| Violation | Signal | Cause |
|-----------|--------|-------|
| **Palette intrusion** | A fill or stroke color not in the inferred palette | Inserted icon or text carrying hardcoded external hex |
| **Font family mismatch** | Text in a slot using a different `font-family` than siblings | Content copied from an external source with inline style |
| **Weight inconsistency** | A label at `font-weight="600"` among siblings at `400` | Content generation applied bold to "important" words |
| **Radius inconsistency** | A container rect at `rx="4"` in a library using `rx="8"` throughout | Template switching chose a template from a different client |
| **Stroke width drift** | A connector at `stroke-width="2"` when library uses `1` | Manual edit overrode the template value |
| **Icon style mismatch** | A filled icon in a template that uses outline-only icons | Wrong icon variant selected |
| **Spacing deviation** | Slot padding deviates >20% from inferred SLOT_INTERNAL_PADDING | Text repositioned by adjusting x/y rather than managing content length |

---

## Multi-client library support

The agent must support multiple client libraries, each with its own brand system. This requires explicit brand context switching.

### Brand context structure
```
BrandContext {
  client_id: string
  library_path: string
  palette: ColorToken[]
  typography: TypographyToken[]
  shapes: ShapeToken[]
  spacing: SpacingToken[]
  icon_style: "filled" | "outline" | "duo-tone" | "flat"
  inferred: boolean  ← true if tokens were extracted, false if provided explicitly
  confidence: "HIGH" | "MEDIUM" | "LOW"
}
```

### Context isolation rule
Brand contexts must never bleed between clients. If the agent operates on ClientA's library in one request and ClientB's in the next, all token values must be re-loaded from the respective library. There is no default or shared global palette.

### Conflict detection
If a template's internal styles contradict the declared brand context (e.g., the file uses a color not in the declared palette), the agent must flag this before proceeding rather than silently accepting the file's internal styles. The template may be from the wrong client, or the brand context may be outdated.

---

## When brand inference is uncertain

If the brand extraction algorithm produces low confidence (< 3 template files sampled, highly variable colors across files, no consistent font family), the agent must:

1. Report what was found and its confidence level
2. Ask for explicit brand tokens before proceeding
3. Never guess and proceed — a wrong palette produces output that visually repudiates the client's brand

**Low confidence signals:**
- Fewer than 3 files sampled in the library
- More than 8 distinct color values with no clear frequency winner
- Different font families used in different files (suggests the library spans multiple brands or eras)
- Corner radii varying between 0, 4, 8, and 12 with no dominant value
