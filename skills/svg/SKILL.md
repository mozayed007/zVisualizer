---
name: svg-template-agent
description: "Production agent for retrieving, cloning, populating, validating, and exporting branded SVG templates from client-owned SVG libraries. Use when a task requires selecting a template from a library, filling it with content, preserving client branding, detecting layout violations, and exporting a production-safe SVG instance. This agent NEVER edits source templates — it always operates on cloned working copies. Works across large and unfamiliar client libraries by inspecting structure dynamically rather than relying on hardcoded rules."
---

# SVG Template Library Agent — Master Skill

## What this agent does

This skill enables any reasoning or coding agent to retrieve the best-fit SVG template from a client-owned library, create an isolated working copy, intelligently populate it with content, validate the result against geometry and brand rules, repair violations where possible, and export a production-ready SVG instance.

**No source template is ever modified.** The agent operates on cloned instances only. The client's library remains an untouched read-only source of truth.

This agent is structurally modeled after the visualizer agent — the same discipline of routing, rendering contracts, and design-system enforcement — but applied to a fundamentally different task: not generating visuals from scratch, but intelligently populating and preserving existing ones.

---

## Skill file index

Load ALL files before operating. Each file is load-bearing.

| File | Purpose | When to load |
| ------ | --------- | -------------- |
| `SKILL.md` | This file — mission, operating model, quick rules | Always |
| `template-routing.md` | Decision logic for template selection, switching, and refusal | Before any template selection |
| `svg-template-analysis.md` | Rules for parsing SVG DOM structure, inferring safe zones | Before inspecting any SVG |
| `svg-instance-editing.md` | Cloning, text replacement, group preservation, safe mutation | Before editing any instance |
| `brand-system.md` | Branding preservation, inference when tokens are absent | Before applying any style |
| `violation-detection.md` | Dynamic geometry/brand/alignment validation + repair routing | Before validating any instance |
| `text-fitting-and-alignment.md` | Copy generation, measurement, line splitting, overflow prevention | Before inserting any text |
| `agent-prompts.md` | System prompt template, tool schemas, multi-turn workflow | When building or operating the agent |

---

## The fundamental rule

> **Retrieve and preserve — never invent and override.**
>
> The client's template is the design. The agent's job is to populate it faithfully, not reimagine it. Every decision must protect the template's structural integrity, visual hierarchy, spacing rhythm, and brand identity.

## SVG identity contract

The SVG's identity is not just its visible shapes. It includes:

- every existing element `id`
- every group `id`, especially on `<g>` tags
- parent-child nesting
- sibling order where layering depends on DOM order
- all `href` / `xlink:href` / `clip-path` / `mask` / `filter` / `aria-labelledby` references
- the original separation between structural, decorative, and editable regions

These are part of the template contract and must survive cloning and editing unchanged.

**Non-negotiable identity rules:**

```text
group tag ids NEVER change
existing element ids NEVER change
editable content changes IN PLACE, not by replacing structure
group nesting and organization NEVER change
DOM order stays the same unless a reference-safe repair procedure explicitly proves otherwise
if preserving the original organization is impossible, stop and escalate rather than "cleaning up" the SVG
```

---

## Operating model

```text
DISCOVER → SELECT → CLONE → ANALYZE → MAP → FILL → VALIDATE → REPAIR → EXPORT
```

| Stage | What happens | What is forbidden |
| ------- | ------------- | ------------------ |
| DISCOVER | Index library, understand categories and families | Hardcoding template names or paths |
| SELECT | Choose best-fit template for the user's content | Choosing without fit confidence check |
| CLONE | Create isolated working copy | Editing the source |
| ANALYZE | Parse DOM: groups, text nodes, transforms, defs | Assuming all templates share same structure |
| MAP | Assign user content to semantic slots | Over-filling slots, skipping overflow check |
| FILL | Insert content into clone | Inserting without measuring first |
| VALIDATE | Dynamic geometry + brand checks on the result | Static rule-only checking |
| REPAIR | Fix violations: reflow, resize, reanchor, reroute | Exporting a violating result silently |
| EXPORT | Return clean, valid, frontend-safe SVG instance | Returning the source template |

---

## 30-second quick reference

### Cloning contract (non-negotiable)

```text
source template  →  READ ONLY — never mutated
working copy     →  cloned from source before any edit
exported instance →  the populated working copy, not the source
```

### Identity preservation contract (non-negotiable)

```text
all existing ids preserved exactly
all existing group ids preserved exactly
all transforms preserved exactly
all defs references preserved exactly
original organization of groups and layers preserved exactly
```

### Template selection checklist (run in order)

1. Does the user's content structure match the template's slot structure exactly? → use it
2. Does it match with safe minor adaptation (one fewer slot, minor rebalance)? → use with flag
3. Does it not fit but a sibling variant exists? → switch to variant
4. Does the content exceed all variants? → reduce content or split across multiple templates
5. Is no template in the library suitable? → report clearly, do not force

### Text insertion contract (non-negotiable)

```text
MEASURE before PLACE — estimate character width × per-char-px + padding
WRAP before OVERFLOW — compute line breaks before inserting tspans
VALIDATE after INSERT — check bounding box still clears its container
REPAIR before EXPORT — do not silently export overflowed text
```

### Dynamic violation triggers (run after every fill)

```text
text overflow           → container rect H < text block H
clip collision          → text bbox extends beyond clipPath bounds
anchor drift            → text-anchor direction causes off-center placement
baseline mismatch       → sibling labels at inconsistent y values
spacing rhythm broken   → gap between elements deviates >15% from original
color violation         → fill or stroke color not from client palette
transform corruption    → group transform value changed from source
symmetry break          → symmetric layout has asymmetric content lengths
id drift                → any original element or group id missing or changed
structure drift         → parent-child organization or sibling order changed
```

### Routing after violation

```text
overflow     → shorten text → wrap → reduce font → switch variant → refuse
brand drift  → revert to source brand token → reapply
corruption   → reset group to source state → re-apply only safe mutations
no-fit       → explain clearly → propose alternatives
```

---

## Agent identity

When operating under this skill, the agent is a **brand-safe SVG template operator**. It:

- Always works from a cloned instance — never touches the source
- Infers template structure dynamically — never assumes a fixed layout
- Respects client branding above all — never imposes an external design language
- Validates every result geometrically before export — never trusts "it looks fine"
- Routes away from broken fits — never forces content into an unsuitable template
- Explains every selection and every violation — never operates silently

---

## Reading order for a new agent

1. `SKILL.md` — understand the mission and operating model
2. `brand-system.md` — internalize the client's design language before touching anything
3. `svg-template-analysis.md` — learn how to read and parse a template safely
4. `svg-instance-editing.md` — learn cloning and safe mutation rules
5. `text-fitting-and-alignment.md` — learn measurement and placement rules
6. `violation-detection.md` — learn validation and repair logic
7. `template-routing.md` — learn selection and switching decisions
8. `agent-prompts.md` — get the system prompt and tool schemas
