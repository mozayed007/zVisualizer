---
name: svg-instance-editing
part-of: svg-template-agent
---

# SVG Instance Editing — Cloning, Mutation Rules, and Export

## Purpose

This document defines the exact protocol for creating a working copy of a source SVG template and safely inserting content into it. The source template is never touched. Every mutation happens on the isolated working copy only.

---

## The clone contract

```text
SOURCE TEMPLATE     →  READ-ONLY. Never opened for write. Never returned as output.
WORKING COPY        →  Deep clone. All mutations happen here. Created fresh per request.
EXPORTED INSTANCE   →  The final state of the working copy after FILL + VALIDATE + REPAIR.
```

### Deep clone requirements

A correct deep clone satisfies ALL of:

- All element `id` attributes are preserved exactly (do not rename, do not suffix)
- All group `<g>` tag `id` attributes are preserved exactly (do not rename, do not suffix, do not regenerate)
- All `xlink:href` and `href` references resolve correctly within the clone
- All `<defs>` entries are copied intact with their original `id` values
- All `transform`, `clip-path`, `mask`, `filter` attribute values are copied without modification
- The `viewBox` and `width`/`height` attributes on the root `<svg>` are copied without modification
- Parent-child nesting is preserved exactly
- Sibling order is preserved exactly
- No element is omitted, collapsed, or merged during cloning

**Cloning is byte-identical except for content within designated editable slots.**

### SVG identity preservation

The working copy must preserve the source SVG's identity, not just its appearance.

Identity includes:

- group structure
- layer order
- element ids
- group ids
- defs references
- parent-child relationships
- transform chains

If an edit would require regrouping, reparenting, flattening, or rebuilding the SVG subtree, treat that edit as unsafe and escalate instead of proceeding.

---

## Mutation taxonomy

Every possible mutation to the working copy falls into one of four categories:

| Category | Description | Permitted | Examples |
| -------- | ------------- | ----------- | --------- |
| **SAFE** | Content insertion into identified editable slots | Always | Replace `<text>` content, replace icon `href` |
| **CONDITIONAL** | Structural adjustment within pre-defined tolerances | Only when validated | Adjust `y` of a `<text>` by ≤2em to accommodate wrap; scale font by ≤15% |
| **RESTRICTED** | Changes to non-slot structural elements | Never without explicit flag | Background color, connector paths, container rects |
| **FORBIDDEN** | Changes to `<defs>`, transforms, viewBox, `id` attributes | Never | clipPath geometry, group transforms, viewBox dimensions |

---

## Safe mutation rules — text replacement

### Rule 1: Replace content, not nodes

Do not create new `<text>` elements to replace existing ones. Replace the `textContent` of the existing `<text>` node only. Preserves all style attributes, positioning, and class associations.

```xml
<!-- SOURCE (inside working copy before fill) -->
<text id="slot-1-title" class="title" x="60" y="100"
      text-anchor="start" dominant-baseline="central"
      font-size="28" fill="#1A1A1A">
  Title placeholder
</text>

<!-- AFTER FILL (correct) -->
<text id="slot-1-title" class="title" x="60" y="100"
      text-anchor="start" dominant-baseline="central"
      font-size="28" fill="#1A1A1A">
  Your actual title here
</text>

<!-- AFTER FILL (WRONG — new node, loses all attributes) -->
<text>Your actual title here</text>
```

### Rule 2: Multi-line text uses `<tspan>` within the existing `<text>`

When content requires multiple lines, do not add a second `<text>` element. Add `<tspan>` children inside the original `<text>` node.

```xml
<!-- CORRECT: multi-line via tspan -->
<text id="slot-2-body" x="60" y="200" font-size="16" fill="#444">
  <tspan x="60" dy="0">First line of body content that</tspan>
  <tspan x="60" dy="1.4em">wraps to the second line.</tspan>
</text>

<!-- WRONG: two separate text elements -->
<text x="60" y="200">First line</text>
<text x="60" y="224">Second line</text>
```

### Rule 3: Preserve all non-content attributes

When replacing text content, copy all original attributes verbatim onto the final element. Never drop:

- `id`
- `class`
- `x`, `y`
- `text-anchor`
- `dominant-baseline`
- `font-size`, `font-weight`, `font-family`
- `fill`
- `letter-spacing`, `word-spacing` (if present)
- `transform` (if present on the text element itself)

### Rule 3b: Preserve organization around the edited node

When editing a text or icon slot, do not:

- move the node into another group
- wrap it in a new group
- unwrap it from its existing group
- reorder it relative to siblings
- rename the containing group

Alignment often depends on inherited transforms, clipping, and paint order. Preserving the original organization is part of preserving alignment.

### Rule 4: Never change `text-anchor` to force positioning

If the original text is `text-anchor="middle"` and the new content looks off-center, the problem is a content length mismatch — not an anchor error. The correct fix is content adjustment, not anchor change. Changing `text-anchor` breaks the template's intentional alignment.

### Rule 5: Empty slots

When a slot exists in the template but the user's content has no value for it, populate it with a zero-width space (`&#x200B;`) or suppress its visibility with `display="none"` on the parent group. Never leave placeholder text visible in the export. Never delete the node.

---

## Safe mutation rules — icon replacement

### Rule 6: Icon replacement inside `<symbol>`

If the template uses `<symbol>` + `<use>` for icons, replace the path data inside the symbol only. Never change the `<use>` element's position, `width`, or `height`.

```xml
<!-- In <defs> — replace path d attribute only -->
<symbol id="icon-slot-1" viewBox="0 0 24 24">
  <path d="M12 2L2 7l10 5 10-5-10-5z..."/>  ← replace this d value only
</symbol>

<!-- <use> element — DO NOT TOUCH -->
<use href="#icon-slot-1" x="40" y="60" width="32" height="32"/>
```

### Rule 7: Direct icon `<path>` replacement

If the icon is a bare `<path>` (not in a symbol), replace only the `d` attribute. Preserve `fill`, `stroke`, `transform`, `class`, and `id`.

---

## Conditional mutations — when font size adjustment is permitted

Font size may be reduced from the template's original size only under ALL of these conditions:

1. The text content overflows the slot after correct wrapping
2. The text cannot be further shortened
3. No compact variant of the template is available
4. The reduction is ≤15% of the original font size
5. ALL text nodes in the same semantic level are reduced by the same percentage (never selectively reduce one label and leave siblings at original size)

**Minimum font sizes by role (never go below):**

```text
Title/heading:  16px
Body:           13px
Caption/label:  11px
```

---

## Forbidden mutations — enforced as hard blockers

The following mutations must never be applied to the working copy:

```text
FORBIDDEN: Changing any viewBox attribute
FORBIDDEN: Changing any id attribute on any element
FORBIDDEN: Changing any id attribute on any `<g>` element
FORBIDDEN: Modifying geometry of <clipPath>, <mask>, or <filter> children
FORBIDDEN: Adding or removing a transform attribute on a group
FORBIDDEN: Changing fill, stroke, or opacity of any structural or decorative element
FORBIDDEN: Removing any element from <defs>
FORBIDDEN: Adding new top-level <g> elements outside the original structure
FORBIDDEN: Reparenting an existing node into a different group
FORBIDDEN: Flattening, regrouping, or reordering existing groups
FORBIDDEN: Changing width/height attributes on <use> elements referencing symbols
FORBIDDEN: Merging two separate template SVGs (concatenation breaks defs id namespacing)
```

---

## Export rules

### Pre-export checklist

Before writing the final exported SVG, the agent must confirm:

- [ ] No source template file was opened for write at any point
- [ ] viewBox is identical to source
- [ ] All `<defs>` entries are present and their `id` values are unchanged
- [ ] All original group `<g>` ids are present and unchanged
- [ ] Parent-child organization matches the source template
- [ ] Sibling order matches the source template
- [ ] No `<text>` placeholder content remains visible (all slots either filled or hidden)
- [ ] No text overflows its slot bounding box (validated by violation-detection)
- [ ] No structural element has been modified
- [ ] All `id` attributes are present on all elements (none dropped during serialization)
- [ ] SVG is valid XML (well-formed, all tags closed, all attributes quoted)

### SVG serialization rules

```text
Use double quotes for all attribute values
Self-close empty elements: <path .../> not <path ...></path>
Preserve whitespace inside <text> elements exactly (extra spaces are visible)
Do not pretty-print into the defs block — whitespace can affect rendering
Do not add XML comments — they add size and expose internal naming to clients
```

### Output envelope

The agent's final output should be the SVG string only — no wrapping HTML, no markdown fences, no preamble characters. The consumer application receives clean SVG markup for direct injection.

---

## Working copy lifecycle

```text
1. REQUEST RECEIVED
   ↓
2. SOURCE TEMPLATE LOCATED (read-only access)
   ↓
3. DEEP CLONE CREATED (working copy, in-memory or temp storage)
   ↓
4. STRUCTURAL MAP APPLIED (from svg-template-analysis)
   ↓
5. CONTENT MAPPED TO SLOTS (from user payload)
   ↓
6. TEXT FITTING COMPUTED (from text-fitting-and-alignment)
   ↓
7. MUTATIONS APPLIED TO WORKING COPY (safe mutations only)
   ↓
8. VIOLATION DETECTION RUN (from violation-detection)
   ↓
9. REPAIRS APPLIED IF NEEDED (conditional mutations only)
   ↓
10. VALIDATION RE-RUN (must pass before export)
    ↓
11. EXPORTED INSTANCE RETURNED
    ↓
12. WORKING COPY DISCARDED (not stored long-term without explicit request)
```

No step can be skipped. Validation (step 10) must pass before export (step 11). If validation cannot pass after repairs, the agent escalates to template switching or content reduction — it never exports a violating result.
