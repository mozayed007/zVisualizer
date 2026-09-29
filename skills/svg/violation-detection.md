---
name: violation-detection
part-of: svg-template-agent
---

# Violation Detection — Dynamic Validation and Repair

## Purpose

Violation detection is the quality gate between filling and export. It is not a static checklist — it is a geometric and semantic inspection of the actual resulting SVG, performed every time after any mutation.

**The fundamental principle:** Do not trust that content "looks right." Inspect the geometry. Measure the text. Trace the bounding boxes. A violation that is not detected before export is a production defect that reaches the client.

---

## Inspection model

Every inspection operates on the working copy after filling. The agent computes or estimates geometric properties and compares them against the structural map from the analysis stage.

### Bounding box model

For every element in the working copy, the agent maintains or estimates a bounding box:

```text
BoundingBox {
  x: number        ← leftmost pixel (absolute, transforms resolved)
  y: number        ← topmost pixel
  width: number    ← bounding width
  height: number   ← bounding height
  right: number    ← x + width
  bottom: number   ← y + height
}
```

Text bounding boxes are estimated using the character width model defined in `text-fitting-and-alignment.md`. When rendering is not available, use the estimation model. When rendering is available, use measured values.

---

## Violation catalog — geometric

### V-GEO-01: Text overflow

**Definition:** A text node's estimated bounding box bottom exceeds the slot container's bottom edge.

```text
trigger:  text_bbox.bottom > slot_container.bottom
severity: CRITICAL
repair:   → shorten text → wrap at narrower column → reduce font (if within limits) → switch template
```

### V-GEO-02: Text horizontal overflow

**Definition:** A text node's estimated bounding box right exceeds the slot container's right edge.

```text
trigger:  text_bbox.right > slot_container.right   (for text-anchor="start")
          text_bbox.left < slot_container.left      (for text-anchor="end")
          either edge violation                      (for text-anchor="middle")
severity: CRITICAL
repair:   → shorten text → wrap → reduce font → switch template
```

### V-GEO-03: Clip path violation

**Definition:** A text or icon node's bounding box extends beyond the bounds of the `<clipPath>` applied to its ancestor group.

```text
trigger:  element_bbox intersects outside clipPath bounds
severity: CRITICAL — content will be invisibly cut
repair:   → shorten content → reduce font → move anchor within clip region
```

### V-GEO-04: Sibling overlap

**Definition:** Two adjacent slot bounding boxes intersect.

```text
trigger:  slot_A.right > slot_B.x   (horizontal adjacency)
          slot_A.bottom > slot_B.y  (vertical adjacency)
severity: HIGH
repair:   → reduce content in the larger slot → reduce font → switch to more spacious variant
```

### V-GEO-05: Baseline mismatch

**Definition:** Text elements that should be visually baseline-aligned (e.g., a row of peer labels) have different resolved y values after filling.

```text
trigger:  abs(label_A.resolved_y - label_B.resolved_y) > 2px   (among peer elements)
severity: MEDIUM — visible misalignment
repair:   → revert y values to source template values → do not reposition text elements
```

### V-GEO-06: Anchor drift

**Definition:** The visual center of a text string has drifted from the geometric center of its slot due to anchor + content interaction.

```text
trigger:  text-anchor="middle" AND
          abs( (slot.x + slot.width/2) - (text_bbox.x + text_bbox.width/2) ) > 4px
severity: MEDIUM
repair:   → reduce content length → the anchor itself must not be changed
```

### V-GEO-07: viewBox escape

**Definition:** Any element in the working copy has a bounding box that extends outside the root viewBox.

```text
trigger:  element_bbox.right > viewBox.width  OR  element_bbox.bottom > viewBox.height
          OR  element_bbox.x < 0  OR  element_bbox.y < 0
severity: CRITICAL — content is clipped at SVG boundary
repair:   → shorten content → reduce font → never change viewBox
```

---

## Violation catalog — brand

### V-BRAND-01: Palette intrusion

**Definition:** A fill or stroke value on an inserted element is not present in the inferred/declared brand palette.

```text
trigger:  element.fill NOT IN brand_palette.colors
severity: HIGH
repair:   → map to nearest brand token → or remove custom fill and inherit from parent
```

### V-BRAND-02: Font family mismatch

**Definition:** An inserted text node uses a `font-family` not in the brand token set.

```text
trigger:  text.font_family NOT IN brand_typography.font_families
severity: HIGH
repair:   → replace with FONT_FAMILY_PRIMARY or FONT_FAMILY_BODY as appropriate
```

### V-BRAND-03: Weight inconsistency

**Definition:** An inserted text node uses a `font-weight` that does not match its semantic level's defined weight.

```text
trigger:  slot_role = "body" AND text.font_weight != FONT_WEIGHT_REGULAR
          slot_role = "title" AND text.font_weight != FONT_WEIGHT_BOLD
severity: MEDIUM
repair:   → reset font-weight to brand token value
```

### V-BRAND-04: Radius inconsistency

**Definition:** A rect in the working copy has an `rx` value different from the brand token for its layer.

```text
trigger:  new_rect.rx != brand_shapes.CORNER_RADIUS_MD  (for standard slot containers)
severity: MEDIUM — only relevant if agent added a rect; should never happen
repair:   → correct rx value → if agent added a rect, that was a forbidden mutation; revert
```

### V-BRAND-05: Icon style mismatch

**Definition:** An inserted icon uses a different visual style (filled vs outline vs duo-tone) than the library's established icon style.

```text
trigger:  inserted_icon_style != brand_context.icon_style
severity: HIGH
repair:   → select the correct style variant of the icon
```

---

## Violation catalog — structural

### V-STRUCT-01: Transform mutation

**Definition:** A group's `transform` attribute value differs between source and working copy.

```text
trigger:  working_copy_group.transform != source_template_group.transform
severity: CRITICAL — layout of all children corrupted
repair:   → revert transform to source value immediately
```

### V-STRUCT-02: defs corruption

**Definition:** Any element in `<defs>` has been modified (geometry, color, or presence).

```text
trigger:  deep-compare working_copy.defs != source_template.defs  (except icon symbol content)
severity: CRITICAL
repair:   → revert entire defs block to source state
```

### V-STRUCT-03: Structural element mutation

**Definition:** An element classified as `structural` in the structural map has had its geometry, fill, stroke, or position changed.

```text
trigger:  structural_element attribute differs from source
severity: HIGH
repair:   → revert specific element attributes to source values
```

### V-STRUCT-04: id missing or changed

**Definition:** An element that had an `id` in the source template does not have that id in the working copy (dropped by serializer, or modified during editing).

```text
trigger:  element present in working copy but id attribute missing or different
severity: HIGH — breaks clipPath references, CSS selectors, JS targeting
repair:   → restore id attribute to source value
```

### V-STRUCT-05: Group identity mutation

**Definition:** A `<g>` element from the source template has a different `id`, different parent, or different role in the working copy.

```text
trigger:  any source `<g>` with id is missing, renamed, reparented, or replaced
severity: CRITICAL — breaks the SVG's organizational identity
repair:   → restore the original group node and re-apply content edits in place only
```

### V-STRUCT-06: Hierarchy or sibling-order drift

**Definition:** The working copy preserves the visible shapes but changes DOM organization in a way that can alter paint order, inherited styles, clipping behavior, or downstream targeting.

```text
trigger:  child order differs from source within a protected group
          OR parent-child relationship differs from source
severity: HIGH
repair:   → revert the affected subtree to source organization
```

---

## Violation catalog — content

### V-CONTENT-01: Placeholder text remaining

**Definition:** Any slot still contains placeholder text content after the fill stage.

```text
trigger:  text_content matches placeholder_pattern  (see svg-template-analysis.md)
severity: CRITICAL — placeholder visible in export
repair:   → populate the slot with actual content → or suppress with display="none"
```

### V-CONTENT-02: Symmetric layout imbalance

**Definition:** A template with a symmetric layout (e.g., two-column, mirrored comparison) has been populated with content of significantly different lengths on each side, creating visible visual imbalance.

```text
trigger:  left_slot.estimated_text_height > right_slot.estimated_text_height * 1.4
severity: MEDIUM
repair:   → redistribute content → shorten longer side → switch to an asymmetric variant
```

### V-CONTENT-03: Density overload

**Definition:** A slot has been populated with more content than the template was designed to hold, even if it technically does not overflow geometrically (e.g., font reduced to 11px to fit 200 characters into a heading slot).

```text
trigger:  font_size < minimum_role_font  OR  line_count > slot_capacity_lines * 1.5
severity: HIGH
repair:   → reduce content → switch to higher-density variant → split across multiple instances
```

---

## Severity escalation logic

```text
if any CRITICAL violation is present after repair attempts:
  → do NOT export
  → escalate to template switch or content reduction request

if any HIGH violation is present after repair attempts:
  → do NOT export
  → escalate (same as CRITICAL)

if any MEDIUM violation is present after repair attempts:
  → export with warning flag
  → log violation details for human review

if all violations resolved:
  → export with clean status
```

---

## Repair strategies catalog

| Violation | Repair tier 1 | Repair tier 2 | Repair tier 3 | Escalation |
| ----------- | ------------- | ----------- | ----------- | ----------- |
| Text overflow (vertical) | Wrap text | Reduce font ≤15% | — | Switch template or request shorter copy |
| Text overflow (horizontal) | Shorten text | Wrap earlier | Reduce font ≤15% | Switch template |
| Clip violation | Move anchor into clip bounds | Reduce content | — | Switch template |
| Sibling overlap | Reduce content in larger slot | — | — | Switch to spacious variant |
| Baseline mismatch | Revert y to source value | — | — | Reset all text positions to source |
| Anchor drift | Shorten text to reduce drift | — | — | If anchor cannot be preserved, refuse |
| Palette intrusion | Map to nearest token | Remove custom fill | — | Flag for human review |
| Font mismatch | Apply correct font-family | — | — | Always resolvable |
| Transform mutation | Revert to source | — | — | Always resolvable |
| defs corruption | Revert entire defs block | — | — | Always resolvable |
| Group identity mutation | Restore original group node | Re-apply safe content edits only | — | If repeated, block export |
| Hierarchy/order drift | Restore original subtree ordering | Re-apply safe content edits only | — | If repeated, block export |
| Placeholder remaining | Fill with content | Suppress with display=none | — | Never export unfilled |
| Symmetric imbalance | Redistribute content | Switch to asymmetric variant | — | Request content revision |

---

## Re-validation after repair

Every repair triggers a re-run of the full violation detection suite. Repairs can introduce secondary violations (e.g., shortening text in one slot may make a symmetric layout imbalanced). The validation loop continues until:

- All CRITICAL and HIGH violations are resolved, OR
- Maximum repair iterations (3) are reached — at which point the agent escalates and does not export

The repair loop never runs more than 3 times before escalating. Infinite repair loops indicate a content/template mismatch that requires human routing.
