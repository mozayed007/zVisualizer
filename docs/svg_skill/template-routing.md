---
name: template-routing
part-of: svg-template-agent
---

# Template Routing — Decision Logic

## Purpose

This document defines every branching decision the agent must make when selecting, switching, composing, or refusing SVG templates. Like the visualizer's visual-routing, routing here is the most consequential decision in the pipeline — a wrong template choice cannot be fully corrected by downstream filling.

**Critical rule:** Route on *content structure and semantic intent*, not on file name or category label alone. A "timeline" template might be the best fit for a 4-step sequential process. A "list" template might fail for 3 items if the content is comparative. Category names are starting hints, not final answers.

---

## The routing tree

```
User request arrives
        │
        ▼
┌──────────────────────────────────────┐
│ Is the library indexed?              │
│ (has DISCOVER stage been run?)       │
└──────────────────────────────────────┘
        │ NO  → run DISCOVER before routing
        │ YES ▼
┌──────────────────────────────────────┐
│ Classify content structure:          │
│ • item count                         │
│ • relationship type                  │
│ • hierarchy depth                    │
│ • directionality (linear/cyclic/radial)│
│ • comparison axis (yes/no)           │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ Does an exact-match template exist?  │
│ (slot count, layout type, direction) │
└──────────────────────────────────────┘
        │ YES → use exact match, confidence = HIGH
        │ NO  ▼
┌──────────────────────────────────────┐
│ Does a near-match exist with safe    │
│ adaptation? (one slot delta,         │
│ same layout family)                  │
└──────────────────────────────────────┘
        │ YES → use with adaptation flag, confidence = MEDIUM
        │ NO  ▼
┌──────────────────────────────────────┐
│ Does a sibling variant exist?        │
│ (same category, different density)   │
└──────────────────────────────────────┘
        │ YES → switch to variant, explain delta
        │ NO  ▼
┌──────────────────────────────────────┐
│ Can content be reduced or split      │
│ across multiple template instances?  │
└──────────────────────────────────────┘
        │ YES → propose reduction or multi-frame
        │ NO  ▼
┌──────────────────────────────────────┐
│ Report no-fit clearly.               │
│ List closest alternatives.           │
│ Do NOT force a broken template.      │
└──────────────────────────────────────┘
```

---

## Content classification

Before any template can be selected, the agent must classify the user's content along these axes:

### Structural type
| Type | Signal words | Examples |
|------|-------------|---------|
| **sequence** | steps, stages, flow, process, then, next | onboarding flow, deployment pipeline |
| **cycle** | loop, repeat, recurring, phase | development lifecycle, feedback loop |
| **hierarchy** | levels, tiers, above/below, parent/child | org chart, priority pyramid |
| **comparison** | versus, vs, pros/cons, differences | feature comparison, A vs B |
| **relationship** | connects, leads to, depends on | concept map, dependency web |
| **list** | items, points, elements, things | key ideas, takeaways |
| **journey** | path, milestones, timeline, over time | customer journey, project roadmap |
| **distribution** | segments, categories, portions | market share, category breakdown |
| **table** | rows, columns, matrix | data table, grid comparison |
| **mindmap** | branches, subtopics, clusters | brainstorm, topic tree |

### Quantitative properties
```
item_count     → how many top-level slots are needed
depth_levels   → max nesting depth
text_density   → estimated total characters per slot
label_count    → number of distinct label regions
has_icons      → boolean: does content reference visual icons
has_numbers    → boolean: does content include numeric values
```

### Fit formula (compute before selection)
```
fit_score = (
  slot_match_bonus         +  # exact slot count = +40
  layout_type_bonus        +  # correct structural type = +30
  density_penalty          +  # excess text per slot = -10 per overflow slot
  depth_mismatch_penalty   +  # each extra nesting level = -15
  icon_presence_bonus         # template supports icons when needed = +10
)

confidence = HIGH   if fit_score >= 70
confidence = MEDIUM if fit_score >= 45
confidence = LOW    if fit_score < 45
```

---

## Template family map

Each category in a library typically contains a family of variants. The agent must understand the family, not just individual files.

### Common family patterns
```
[category]-3   →  3-slot variant
[category]-4   →  4-slot variant
[category]-5   →  5-slot variant
[category]-dark / [category]-light  →  theme variant
[category]-icon  →  icon-supporting variant
[category]-numbered  →  variant with numeric labels
[category]-compact  →  reduced-density variant
```

**Rule:** When the user's item count does not exactly match a variant, prefer the closest count that requires hiding a slot over the closest count that requires overfilling a slot. An empty slot is always safer than an overflowed one.

---

## Selection decision table

| Content structure | Item count | Recommended category | Notes |
|------------------|-----------|---------------------|-------|
| Linear sequential | 3–6 | sequence | Use numbered variant if order is explicit |
| Cyclic process | 3–5 | cycle | Never use list — cycle connectors are structural |
| Layered hierarchy | 3–5 | pyramid | Top-heavy content → inverted pyramid variant |
| Two-sided comparison | 2 subjects | versus / pros-and-cons | Pros-cons for single subject; versus for two |
| Multiple comparisons | 3+ subjects | table | If >4 attributes, table is the only safe fit |
| Journey with dates | 3–8 milestones | timeline / journey | Use journey for emotional arc, timeline for dates |
| Branching concepts | 3–8 branches | mindmap | Only if relationships are truly radial |
| Key takeaways | 3–6 items | key-ideas / list | Key-ideas if items need icons; list if text-only |
| Partial overlaps | 2–3 sets | venn | Only for set membership — not for comparison |
| Relationship network | 3–7 nodes | relationship | Use only if connections are the subject |

---

## Routing modes

### Mode 1: Exact match
Template slot count equals content item count. Layout type matches structural type. No adaptation needed.
→ Proceed directly to CLONE stage. Log: `route=exact, confidence=HIGH`

### Mode 2: Near match with safe adaptation
Slot delta is ±1 and within the same layout family. Example: user has 4 items, only a 5-slot variant exists. One slot can be visually suppressed or left empty with a structural separator.
→ Proceed with adaptation flag. Log: `route=near_match, adaptation=slot_suppression, confidence=MEDIUM`

### Mode 3: Variant switch
Item count or density falls into a different variant of the same category. Example: user has dense text, compact variant is unavailable, standard variant would overflow.
→ Switch to sibling with explanation. Log: `route=variant_switch, reason=[...]`

### Mode 4: Category switch
The initial category is wrong for the content's true structure. Example: user asks for a "list" but the content is comparative — switch to versus or pros-and-cons.
→ Switch to correct category. Explain why to the user. Log: `route=category_switch, from=[...], to=[...]`

### Mode 5: Multi-template composition
Content is too dense or too large for a single template. Best handled as multiple instances.
→ Propose splitting. Present each sub-instance separately. Never merge two template SVGs by concatenation.

### Mode 6: Content reduction request
No template in the library can safely contain the content as given. The agent must ask the user to reduce, simplify, or summarize.
→ Pause pipeline. Report the specific density issue. Propose concrete reductions (e.g., "this slot has 140 characters, the template supports 60 — please shorten to one sentence").

### Mode 7: Refusal
The request asks for an edit that would structurally violate the template or the source library. Examples: adding a new category not in the library, changing the underlying geometry of a template, merging incompatible template types.
→ Refuse clearly. Explain what is safe. Offer alternatives.

---

## When to switch templates mid-pipeline

The agent may discover during ANALYZE or FILL that the selected template is a worse fit than initially assessed. Switch triggers:

| Trigger | Action |
|---------|--------|
| Text overflows in >2 slots after wrap attempts | Switch to compact variant or request shorter copy |
| A structural group cannot be identified as editable | Switch to a variant where the equivalent group is clearly labeled |
| Brand tokens in the template are incompatible with client's library | Report mismatch, do not attempt to reconcile silently |
| Icon slots exist but the user's content has no icons | Use the no-icon variant of the same category |
| The template uses a fixed-width layout and content is highly asymmetric | Switch to a balanced-weight variant |

---

## Anti-patterns

### 1. Routing by file name alone
```
BAD:  user says "process" → pick file named "process.svg"
GOOD: user says "process" → classify content → sequence with 4 steps → find best-fit sequence variant
```

### 2. Forcing a template that cannot contain the content
```
BAD:  3-slot template, user has 5 items → squeeze 5 items into 3 slots
GOOD: find 5-slot variant → if none, ask user to reduce to 3 or propose two separate instances
```

### 3. Ignoring density in the fit check
```
BAD:  item count matches, assume it fits
GOOD: item count matches AND estimated text width per slot < slot capacity
```

### 4. Switching templates without explanation
```
BAD:  silently use a different template than the one the user named
GOOD: explain why the named template is a weaker fit, confirm before switching
```

### 5. Using category-switch as a last resort instead of first check
```
BAD:  attempt to fill a versus template with 5-item list content, fail, then switch
GOOD: classify content first, detect mismatch before cloning, propose correct category upfront
```
