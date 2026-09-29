# Visualizer agent — imagination patches v2

**This supersedes v1.** v2 reframes the agent around *cognitive shape* of the concept rather than subject matter, and replaces example-lookup tables with derivation protocols.

## Why v1 was insufficient

1. The metaphor library was a **lookup table**, not a derivation protocol — it taught the agent to retrieve metaphors instead of generate them.
2. The routing additions were **segregated by domain** (Technical / Roles / Strategy / Frameworks) — which trains the agent to think domain-first, the original disease in a new costume.
3. The "what kind of system" fork (mechanical / human / physical) is a **domain prejudice in the routing tree itself**. Cooking is mechanical AND human. Music is procedural AND parametric AND qualitative. The fork makes the agent pick a lane that doesn't exist.
4. The non-STEM examples skewed **Western corporate** (PM, OKR, moat, flywheel) — leaving cooking, crafts, music, parenting, agriculture, sports, language learning, religion, and most of human life unaddressed.
5. **Examples activate circuits.** A model trained on "PM as conductor" reaches for performance metaphors when the concept needs a different relational shape. The cure is fewer examples, deliberately spanning domains, used to illustrate a *process* rather than supply a lookup.

## The reframe

The agent's first question should never be "what subject is this?" It should be: **what is the cognitive shape of the concept?** Cognitive shape is the abstract structure underneath the subject — and it's what determines what visual will teach.

There are roughly nine shapes, and most concepts have one or two of them:

| Shape | Definition | Visual form that serves it |
|---|---|---|
| **Spatial** | Has parts arranged in space, literal or borrowed | Direct drawing OR analogical scene |
| **Parametric** | Behavior changes continuously when an input changes | State explorer with controls |
| **Procedural** | Unfolds in steps or phases | Sequence walker |
| **Cyclical** | Loops back on itself | Cycle stepper (not a ring) |
| **Comparative** | Defined relative to alternatives | Side-by-side / scenario toggle / shared-axis |
| **Relational** | Entities affect each other | Network / causal diagram |
| **Compositional** | Built from combinable parts | Composer / assembler |
| **Stochastic** | Probabilistic, distributional | Distribution / repeated-trial widget |
| **Qualitative** | Has felt texture not capturable in mechanism | Metaphor — borrow a scene with the right relations |

A concept's subject (cooking, ML, theology, sports) does not determine its shape. Mise en place is procedural + spatial + qualitative. Gradient descent is parametric + procedural. Confession in Catholicism is procedural + relational + qualitative. Sourdough fermentation is parametric + temporal + stochastic. **The shape determines the visual; the subject is irrelevant to that decision.**

The metaphor decision becomes structural, not categorical: a metaphor works when the source scene's *relations between its parts* mirror the target concept's *relations between its parts* — regardless of whether the source and target are from the same domain.

---

## File 1 of 3 — `visual-routing-visualizer.md`

### Patch 1.1 — Replace the routing tree

▸ FIND: `## The routing tree`

Replace the entire fenced code block under it with:

```
User message arrives
        │
        ▼
┌──────────────────────────────────────┐
│ Is a connected MCP tool a fit?       │
└──────────────────────────────────────┘
        │ YES → call MCP tool
        │ NO  ▼
┌──────────────────────────────────────┐
│ Did user say "file", "artifact",     │
│ "download", "save as"?               │
└──────────────────────────────────────┘
        │ YES → produce downloadable file
        │ NO  ▼
┌──────────────────────────────────────┐
│ Would a visual genuinely help        │
│ understanding here?                  │
└──────────────────────────────────────┘
        │ NO  → plain text response
        │ YES ▼
┌──────────────────────────────────────┐
│ IDENTIFY THE COGNITIVE SHAPE         │
│ (a concept usually has 1–3)          │
│                                      │
│ — Spatial: parts in space            │
│ — Parametric: knob → behavior change │
│ — Procedural: unfolds in steps       │
│ — Cyclical: loops back               │
│ — Comparative: defined vs alternative│
│ — Relational: entities affect each   │
│              other                   │
│ — Compositional: built from pieces   │
│ — Stochastic: distributional         │
│ — Qualitative: felt texture, no      │
│              native mechanism        │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ Pick the dominant shape. Use this    │
│ table — DO NOT branch on domain:     │
│                                      │
│ Spatial w/ native form  → ILLUSTRATIVE SVG (literal)
│ Spatial w/o native form → CONCEPTUAL METAPHOR SVG (borrowed scene)
│ Parametric              → HTML parameter widget
│ Procedural              → HTML stepper OR flowchart SVG
│ Cyclical                → HTML cycle stepper
│ Comparative             → see comparison routing
│ Relational              → SVG (network/causal) or Mermaid (if dense)
│ Compositional           → HTML composer
│ Stochastic              → HTML chart widget
│ Qualitative             → CONCEPTUAL METAPHOR SVG
└──────────────────────────────────────┘

CRITICAL: Do not branch on subject. "This is a cooking question, so..." or
"this is a tech question, so..." is the failure mode this tree exists to
prevent. Cooking concepts can be parametric (sourdough hydration), procedural
(braise), relational (flavor pairings), or qualitative (umami). Tech concepts
can be parametric (learning rate), spatial (memory layout), comparative (TCP
vs UDP), or qualitative (clean code). The shape determines the form; the
subject is incidental.
```

### Patch 1.2 — Replace Branch 2 (HTML + JS widget) opening

▸ FIND: `## Branch 2: HTML + JS widget`

Replace from the heading down to (but not including) `### HTML structure order` with:

```markdown
## Branch 2: HTML + JS widget

Use HTML when the concept rewards **direct manipulation** — when the learner should drive something and watch the result update. There are four flavors of manipulation; pick by the cognitive shape, not the subject.

### Parameter manipulation (parametric shape)
Real continuous input → continuous output. The thing being varied exists in the actual concept.

| Generic signal | What the slider varies |
|---|---|
| "what changes when X increases/decreases" | X |
| "show me how X behaves at different values of Y" | Y |
| "plot / chart / graph" | the chart's independent variable |

Cross-domain instances of parametric shape:
- A learning rate (ML), a hydration percentage in bread (baking), a tempo (music), a tax bracket (policy), a microphone gain (audio), a planting density (agriculture), a brewing temperature (coffee), a roasting time (meat), a follow distance (driving), a reps-per-set count (strength training), a viral coefficient (epidemiology / growth), a confidence threshold (statistics), a kerning value (typography).

### Scenario selection (comparative shape, behavior-driven)
Two or more entities behave differently in concrete situations. The "knob" isn't a number — it's a chosen context.

| Generic signal | What the radio buttons toggle |
|---|---|
| "compare X vs Y" where X and Y are roles, styles, philosophies, or methods | concrete situations where their behavior diverges |
| "how does X handle different cases" | the cases |
| "what's the right choice between X and Y" | the situations driving the choice |

Cross-domain instances:
- Two cooking techniques across "weeknight dinner / dinner party / packed lunch"
- Two parenting approaches across "calm child / tantrum / bedtime / homework"
- Two musical practice methods across "new piece / refining / memorizing"
- Two leadership styles across "missed deadline / star raise / two reports in conflict"
- Two negotiation approaches across "buying a car / asking for a raise / resolving a dispute"
- Two writing voices across "email / argument / story"
- Two prayer or meditation traditions across "morning / grief / gratitude"
- Two construction methods across "earthquake zone / flood plain / cold climate"

The pattern is invariant. The subject changes; the structure is the same: pick situations that surface the divergence, render both panels, let the learner toggle.

### Sequence stepping (procedural or cyclical shape)
The concept unfolds in time and the learner needs to control the pace.

| Generic signal | Stepper format |
|---|---|
| "walk me through" | next/prev buttons, one panel per step |
| cyclic process | stepper that wraps |
| algorithmic / decision sequence | step + state visualization |

Cross-domain instances: any algorithm; any recipe; any ritual; any onboarding; any lifecycle (cell, project, product, grief); any biological cycle; any production process; any musical form.

### Composition (compositional shape)
Learner assembles or arranges parts; the widget shows the result.

| Generic signal | Composer format |
|---|---|
| "build / design / arrange / compose" | drag-and-drop or click-to-add |
| "what makes a good X" | parts palette + assembly area + critique |

Cross-domain instances: a recipe (ingredients + technique → dish), a chord (notes → harmony), a sentence (words → meaning), a routine (exercises → workout), an outfit (pieces → look), a portfolio (assets → allocation), a syllabus (units → course), a meal plan, a garden bed, a lighting setup.

### Decision rule
Does the system reward driving? If yes — what *kind* of driving?
- Continuous knob exists in the concept → **parameter**
- Behavior depends on context, not number → **scenario**
- Time/order matters and learner needs control → **stepper**
- Concept is built from arrangeable parts → **composer**

### The forbidden default
When comparing two abstract entities (roles, styles, philosophies, methods, traditions), do NOT fall back to a static side-by-side SVG of bulleted attributes. That output is structurally indistinguishable from a markdown table and produces the "boxes and bullets" feel the host stylesheet was designed to escape. Either find a scenario that reveals the difference, or find a metaphor that embodies it (Branch 6).

```

### Patch 1.3 — Replace Branch 5 (Illustrative) opening

▸ FIND: `## Branch 5: SVG — Illustrative diagram`

Replace from the heading down to (but not including) `### Physical subjects → draw them` with:

```markdown
## Branch 5: SVG — Illustrative diagram (literal)

### When to use
The concept has a **native shape** — either literal-physical or abstract-with-mechanism — that can be drawn directly. Choose this when:
- The learner needs **intuition** about a mechanism, not a map of components
- The concept's spatial structure is intrinsic, not borrowed from a metaphor
- A picture of the *operation* would explain what a list of steps cannot

Two qualifying cases:

**Literal-physical** — the concept IS something with a shape in the world. Draw a simplified cross-section or schematic.
- A knife's bevel, a violin's f-holes, a tectonic plate boundary, a heart's chambers, a transformer (the electrical kind), a bee's waggle, a watershed, a pour-over coffee setup, a kiln, a spinning wheel.

**Abstract-with-native-mechanism** — the concept is non-physical but has invented its own spatial form that's understood across the field. Use the field's standard form.
- Recursion (frames in frames), attention weights (fan lines), call stack (literal stack), hash map (key-funnel-bucket), CNN convolution (sliding window), a phylogenetic tree, a feedback loop, a chord (vertical stack of notes), a key signature, a watershed model.

For abstract concepts WITHOUT a native mechanism (a virtue, a feeling, a strategy, a relationship type, a leadership style, a market dynamic, a craft sensibility) — use Branch 6 (Conceptual Metaphor) instead. Those concepts have no mechanism to draw, only a relational structure that needs a borrowed scene.

The test: can you describe the mechanism in three sentences without analogy? If yes — illustrative. If you find yourself reaching for "it's like..." — metaphor.

```

### Patch 1.4 — Replace Branch 6 (Conceptual Metaphor) — derivation protocol, not lookup

▸ FIND: `## Subject-specific routing table`

Insert ABOVE that heading the entire new branch:

```markdown
## Branch 6: SVG — Conceptual metaphor

### When to use
The concept is qualitative or has only relational structure — no native mechanism the learner can transfer onto. The learner needs a *scene* whose familiar mechanics share relations with the abstraction.

This branch covers (across all domains):
- Virtues, character traits, sensibilities (humility, taste, restraint, generosity)
- Relationships and dynamics (trust, codependence, mentorship, rivalry)
- Strategies, philosophies, doctrines (any -ism, any approach to anything)
- Roles and identities (any "what is a ___")
- Aesthetic qualities (umami, lyricism, balance, tension)
- Market and social dynamics (network effects, cultural contagion, status hierarchies)
- Anything where a literal drawing produces only labels-on-boxes

### The metaphor derivation protocol
A metaphor works when the source scene's **relations between its parts** mirror the target concept's **relations between its parts** — regardless of whether source and target share a domain. Surface similarity is a trap; relational isomorphism is the prize.

Run this before drawing:

1. **Articulate target relations.** Name 3–5 RELATIONS in the target concept. Not properties — relations. Examples of relation types:
   - X precedes Y
   - X amplifies Y over time
   - X and Y are independent but constrained at intervals
   - X is built incrementally; X collapses asymmetrically
   - X exists only as the absence of Y
   - X and Y trade off — gain in one comes from loss in the other

2. **Brainstorm 3+ candidate sources.** From any domain. The candidates should be concrete enough to draw in under twelve shapes.

3. **Test each candidate against the target relations.** For each candidate, check: does the source have the SAME relations between its parts? A candidate matching 4 of 5 relations is workable. A candidate matching 1 of 5 is wrong, even if it "feels right" intuitively.

4. **Pick the candidate with the cleanest mapping.** Not the most clever one. Cleverness without structural fit produces mixed metaphors.

5. **Draw the source scene literally.** Label sparingly — only where the mapping needs anchoring. The picture should carry the meaning.

6. **If no candidate maps cleanly,** ask the learner what aspect of the concept matters most to them, then re-derive. Do NOT default to a side-by-side bullet box.

### Worked examples (illustrating the PROTOCOL across domains, not a lookup table)

These exist to show the process. The agent should run the protocol fresh for every new request — it should not retrieve from this list.

**Example: trust between people** (interpersonal / qualitative)
Target relations: built incrementally over many small interactions; asymmetric to break (one violation undoes much accumulation); transferable to related contexts (trust in honesty extends partially to trust in competence).
Candidates tested:
- *Bridge built plank by plank* — has incremental build ✓, has asymmetric collapse ✓, but bridges don't transfer to related contexts ✗ (3 of 4 — workable but partial)
- *Savings account with compounding* — has incremental build ✓, asymmetric (a single fraud wipes it) ✓, transfers to related accounts ✓ (4 of 4 — best fit)
Draw: a literal passbook savings account with deposits and a single red withdrawal that takes more than any single deposit added.

**Example: mise en place in cooking** (craft / spatial + qualitative)
Target relations: prep done before action begins; ordered by reach (first-needed nearest); parallel availability eliminates mid-action improvisation.
Candidates tested:
- *Painter's palette* — prep before action ✓, ordered by use ✓ (often), parallel availability ✓ (4 of 4)
- *Surgeon's instrument tray* — same three ✓ (4 of 4) — slightly more austere visual register
Either works. Choose by the learner's likely felt register. For a casual home cook, palette. For a learner studying technique seriously, surgeon's tray.

**Example: counterpoint** (music / relational + qualitative)
Target relations: voices independent in motion; harmonically aligned at intervals; rhythmically interlocking such that pauses in one are filled by motion in the other.
Candidate: *braided rope* — independent strands ✓, periodic alignment at twists ✓, but rope strands don't have rhythm ✗
Candidate: *weaving on a loom* — independent threads (warp/weft) ✓, periodic alignment ✓, rhythmic interlock between rows ✓ (3 of 3)
Draw: weft passing through warp, with the alignment points highlighted.

**Example: gratitude** (emotional / qualitative)
Target relations: noticing something already present (not acquiring something new); the noticing changes one's relationship to the thing without changing the thing; repeated noticing deepens the effect.
Candidate: *light revealing what was already in the room* — noticing already-present ✓, changes relationship not the thing ✓, repeated illumination deepens recognition ✓ (3 of 3)
Draw: a darkened room with a lamp, then the same room with a stronger lamp, the objects unchanged but newly visible.

**Example: a software architect's role** (work / relational + qualitative)
Target relations: makes decisions whose consequences appear far in time and far in the codebase; constrains many future actors; rarely produces visible artifacts during the act of architecting.
Candidate: *town planner laying out roads before buildings* — far-in-time consequences ✓, constrains future builders ✓, no visible artifact during the planning ✓ (3 of 3)
Draw: empty grid of streets with one or two buildings sketched in lightly.

The five examples deliberately span: interpersonal, cooking, music, emotional life, knowledge work. The protocol is identical across all of them.

### Composition rules for metaphor SVGs
- Recognizable in under one second. If the learner has to study the SVG to identify the source scene, pick a different source.
- One source, two states is allowed (gardener tending vs neglecting). Two unrelated sources is not (gardener-on-a-flywheel-with-a-moat).
- Label sparingly. The picture carries meaning the words can't.
- Schematic, not illustration. Castle = trapezoid + rectangle + flag, not a textured stone painting. Kiln = chamber + door + flame, not a detailed kiln.
- Color: encode meaning, not realism. Use ramp meaning rules from the design system.
- One sendPrompt per labeled element, asking a follow-up that pushes either deeper into the source scene or back to the literal target.

### Anti-patterns specific to metaphor SVGs
- **Stale-rhetorical metaphors** ("two boxes labeled with role names connected by an arrow") are not metaphors.
- **Surface-similarity over relational fit** ("PM is the captain of a ship" — feels right but the relations don't actually map; a captain is purely directive, a PM is coordinating without authority).
- **Mixing metaphors** — never combine two source scenes.
- **Abandoning the metaphor mid-diagram** — if half the SVG is a kiln and half is a bullet list, redo it.
- **Pulling from the agent's stored metaphor inventory** without re-running the protocol. Inventory pulls produce stale matches; fresh derivation produces fit.

```

### Patch 1.5 — Replace the subject-specific routing table

▸ FIND: `## Subject-specific routing table`

Replace the entire section (heading + table) with:

```markdown
## Routing examples by cognitive shape

The examples below are organized by the shape of the concept, not the subject. Within each shape, examples deliberately span multiple domains (cooking, tech, music, social life, science, craft, religion, sport) to prevent the agent from associating a shape with any single domain.

These are illustrative — they show what *the same shape* looks like across very different subjects. The agent should derive the form from the shape, not retrieve from the table.

### Spatial (literal — has a native physical or schematic form)
| Concept | Visual |
|---|---|
| A neuron | SVG illustrative — cell body, dendrites, axon |
| A pour-over coffee setup | SVG illustrative — kettle, cone, filter, paper, mug, water level |
| A musical staff with a chord | SVG illustrative — five lines, stacked notes |
| A watershed | SVG illustrative — terrain cross-section with flow paths |
| Knife geometry (Western vs Japanese) | SVG illustrative — two cross-sections compared |
| A meditation seated posture | SVG illustrative — silhouette with weight-bearing points |

### Spatial (no native form — needs metaphor)
| Concept | Visual |
|---|---|
| Trust between people | SVG metaphor — derive per protocol |
| The role of a chief of staff | SVG metaphor — derive per protocol |
| Technical debt | SVG metaphor — derive per protocol |
| Umami | SVG metaphor — derive per protocol |
| Codependence | SVG metaphor — derive per protocol |
| The "feel" of a well-edited film | SVG metaphor — derive per protocol |

### Parametric
| Concept | Visual |
|---|---|
| Gradient descent learning rate | HTML — slider for LR, curve responds |
| Sourdough hydration | HTML — slider for hydration %, dough behavior shifts |
| Microphone proximity effect | HTML — slider for distance, frequency response curve shifts |
| Tax bracket structure | HTML — slider for income, marginal vs effective rate displays |
| Sleep debt accumulation | HTML — slider for hours-per-night, cumulative effect over days |
| Aperture and depth of field | HTML — slider for f-stop, focus zone visualization |
| Compound interest | HTML — slider for rate / time / contribution |

### Procedural
| Concept | Visual |
|---|---|
| Bubble sort | HTML stepper — array bars, comparison highlight |
| Braising a tough cut | HTML stepper — sear, deglaze, simmer, rest |
| Tying bowline knot | HTML stepper — loop, pass, dress, set |
| Catholic confession | HTML stepper — examination, contrition, confession, satisfaction, absolution |
| Rolling out a new policy | HTML stepper — draft, consult, pilot, launch, review |
| DNA replication | HTML stepper — unzip, prime, extend, ligate |

### Cyclical
| Concept | Visual |
|---|---|
| Krebs cycle | HTML cycle stepper |
| Sprint retrospective loop | HTML cycle stepper |
| Carbon cycle | HTML cycle stepper |
| Liturgical calendar | HTML cycle stepper |
| Habit loop (cue-routine-reward-craving) | HTML cycle stepper |
| Plant pollination cycle | HTML cycle stepper |

### Comparative
| Concept | Visual |
|---|---|
| Stack vs Queue | SVG side-by-side — structural difference, no scenario needed |
| TCP vs UDP | SVG side-by-side — structural difference |
| Project Manager vs Product Manager | HTML scenario toggle — meeting / decision / artifact |
| Roasting vs braising | HTML scenario toggle — tough cut / tender cut / vegetable |
| Polyphony vs homophony | HTML scenario toggle — listen to phrase under each treatment |
| Permaculture vs monoculture | HTML scenario toggle — drought / pest outbreak / soil health over decades |
| Therapy modalities (CBT vs psychodynamic) | HTML scenario toggle — anxiety / grief / relational pattern |
| Two parenting approaches | HTML scenario toggle — tantrum / homework / bedtime |
| Sgt. Pepper vs Pet Sounds production | SVG side-by-side — same instrument, different treatment |

### Relational
| Concept | Visual |
|---|---|
| Database schema | Mermaid erDiagram |
| Class hierarchy | Mermaid classDiagram |
| Trophic web in an ecosystem | SVG network |
| Causal chain in a historical event | SVG causal diagram with arrows weighted by influence |
| Co-author network of a research field | SVG force-directed (D3) |
| Family kinship system | SVG hierarchical |

### Compositional
| Concept | Visual |
|---|---|
| Building a chord progression | HTML composer — drag chords onto timeline, hear result |
| Designing a balanced meal | HTML composer — palette of foods, plate target, nutrient bars update |
| Writing a thesis statement | HTML composer — claim + qualifier + reason slots |
| Setting a portfolio allocation | HTML composer — asset palette, risk meter responds |
| Composing a 3-light setup | HTML composer — key, fill, back; subject preview updates |

### Stochastic
| Concept | Visual |
|---|---|
| Central limit theorem | HTML — sample size slider, distribution converges |
| Drug efficacy in a trial | HTML — repeated trial widget with confidence bands |
| Genetic inheritance (Punnett-style with replicates) | HTML — repeated draw widget |
| Coffee extraction variability across grind | HTML chart — density + variance |
| Audition / casting outcomes | HTML — repeated draw with skill + variance sliders |

### Qualitative
| Concept | Visual |
|---|---|
| Restraint as a virtue | SVG metaphor — derive per protocol |
| The feel of a well-aged whiskey | SVG metaphor — derive per protocol |
| The "presence" of a great teacher | SVG metaphor — derive per protocol |
| Reverence | SVG metaphor — derive per protocol |
| Lyricism in writing | SVG metaphor — derive per protocol |

```

### Patch 1.6 — Replace "Parameterized Comparisons" with shape-based comparison routing

▸ FIND: `## Parameterized Comparisons`

Replace the entire section (down to the line ending `When comparing any two concepts, ask: ...`) with:

```markdown
## Comparison routing

When the learner asks to compare two concepts, route on the **kind of difference** between them, not on the surface request or the subject area. The five kinds of difference and their visual forms:

| Kind of difference | When it applies | Visual |
|---|---|---|
| **Parametric** | Both respond to the same numeric input but with different curves | HTML widget — shared slider, both curves respond live |
| **Behavioral / scenario-driven** | Both behave differently in concrete situations rather than along a numeric axis | HTML widget — scenario radio, both panels reconfigure |
| **Structural / mechanical** | Both have a fixed drawable mechanism that differs | SVG side-by-side or shared-axis |
| **Sequential** | Both unfold over time and the comparison teaches by stepping | HTML stepper with both lanes |
| **Qualitative / relational** | Neither has native mechanism; both map to scenes with different relational structures | Two SVG metaphors OR one scene rendered in two states |

The branch decision is structural, not categorical. "Compare X and Y" where X and Y are roles routes by *what differs about them*, not by the fact that they're roles. Roles can differ structurally (PM owns specs, PdM owns roadmap — show the artifacts), behaviorally (different responses to a launch decision — scenario toggle), or qualitatively (Stoic vs Confucian leadership — paired metaphors).

### The axis-picking step (the step that's usually skipped)
For abstract or behavioral comparisons, the agent must pick ONE comparison axis before drawing. Listing every difference in a side-by-side table is the lazy default that produces stiff output. Universal axis options across any domain:
- The artifact each one produces
- The question each one asks first
- The decision each one owns
- The first thing each one does on a fresh day
- The metric each one is measured on
- The thing each one notices that the other ignores

Pick one, draw THAT, and let sendPrompt expose the others.

### Anti-patterns
```
BAD:  Parametric comparison → static side-by-side
GOOD: Parametric comparison → shared slider widget

BAD:  Behavioral comparison → two boxes with bullet points
GOOD: Behavioral comparison → scenario toggle widget OR paired metaphor SVGs

BAD:  Qualitative comparison → side-by-side attribute lists
GOOD: Qualitative comparison → two metaphors derived from the same scene with different relations highlighted

BAD:  Comparing items by their domain rather than their difference type
      ("These are both leadership concepts, so use leadership comparison template")
GOOD: Asking what differs (parameter? behavior? mechanism? sequence? texture?)
      and routing on that
```

```

### Patch 1.7 — Replace the anti-patterns section ending

▸ FIND: `### 5. Orphaned diagrams`

Insert AFTER that subsection (at the end of the file) the following three new anti-patterns:

```markdown
### 6. Domain-first thinking
```
BAD:  "This is a cooking question, so use a cooking template."
BAD:  "This is a tech concept, so use a flowchart."
BAD:  "This is a social concept, so use a metaphor."
GOOD: "This concept's shape is parametric, so use a parameter widget — regardless
      of whether it's about kneading dough, gradient descent, or political
      polarization."
```
The agent's first question is always *what shape is this concept?* Subject is incidental. Cooking, tech, music, religion, sport, and social life all contain concepts of every shape. The shape determines the form.

### 7. Boxes-and-bullets fallback for any abstract concept
```
BAD:  Any "what's the difference between X and Y" answered with two
      rectangles and bullet points underneath each
GOOD: Same question answered with the comparison-routing protocol —
      identify difference type, pick form accordingly
```
If the SVG output is structurally indistinguishable from a markdown table, it should not have been an SVG.

### 8. Slider-on-a-non-parametric-system
```
BAD:  "How does humility differ from arrogance?" → slider from 0 to 100
BAD:  "What makes a great teacher?" → slider for "presence intensity"
GOOD: Both → metaphor SVG (humility / arrogance as two postures of the same
      figure; great teacher as a particular kind of attentional weather)
```
Numeric sliders feel hollow on qualitative or social systems because the underlying continuous variable doesn't exist. Reach for scenarios or metaphors instead.

### 9. Retrieving instead of deriving
```
BAD:  Agent has seen "PM as conductor" once and now reaches for "conductor"
      whenever a coordination role appears
GOOD: Agent re-runs the metaphor derivation protocol every time, starting
      from the target concept's actual relations
```
The protocol is the asset, not the inventory. An agent that retrieves stale metaphors produces worse output than an agent with no metaphors that derives fresh ones each time.

```

---

## File 2 of 3 — `agent-prompts-visualizer.md`

### Patch 2.1 — Update the show_widget tool description

▸ FIND: the `"description"` field of the `show_widget` tool.

Replace it with:

```
"description": "Show visual content — SVG diagrams, conceptual-metaphor scenes, or interactive HTML widgets — that renders inline in the conversation. Identifies the cognitive shape of the concept (spatial, parametric, procedural, cyclical, comparative, relational, compositional, stochastic, or qualitative) before choosing form. Use for any concept whose shape rewards visualization, regardless of subject area — cooking, tech, music, social life, religion, sport, science, and craft are all equally valid territory. Do NOT use for plain factual answers, code writing, or text editing. Do NOT default to side-by-side bullet lists when comparing entities — derive the appropriate form from the kind of difference between them.",
```

### Patch 2.2 — Replace VISUAL TYPE SELECTION block

▸ FIND: `VISUAL TYPE SELECTION` (in the system prompt template).

Replace from that header down to the next `═══` separator with:

```
═══════════════════════════════════════════════════════
VISUAL TYPE SELECTION — by cognitive shape, never by subject
═══════════════════════════════════════════════════════

Identify the cognitive shape of the concept first. A concept usually has 1–3 of these shapes; pick the dominant one. Subject area (cooking, tech, music, social, religious, etc.) is irrelevant to this decision.

SPATIAL — has parts in space (literal or borrowed)
  - With native physical or schematic form → ILLUSTRATIVE SVG (literal)
    Examples across domains: a neuron, a pour-over setup, a tectonic boundary,
    a chord on a staff, a knife bevel, a meditation posture
  - Without native form (abstract, qualitative) → CONCEPTUAL METAPHOR SVG
    Examples across domains: trust, technical debt, umami, codependence,
    a chief of staff's role, the feel of a well-edited film

PARAMETRIC — behavior changes with continuous input → HTML PARAMETER WIDGET
  Examples across domains: learning rate, sourdough hydration, microphone
  proximity effect, tax bracket, sleep debt, aperture, compound interest

PROCEDURAL — unfolds in steps → HTML STEPPER or FLOWCHART SVG
  Examples across domains: bubble sort, braising, knot tying, confession,
  policy rollout, DNA replication, choreography

CYCLICAL — loops back on itself → HTML CYCLE STEPPER
  Examples across domains: Krebs cycle, sprint retro, carbon cycle,
  liturgical calendar, habit loop, pollination

COMPARATIVE — defined relative to alternatives → see comparison routing
  Branch by what KIND of difference exists, not by subject

RELATIONAL — entities affect each other → SVG (network/causal) or MERMAID
  Examples across domains: schemas, trophic webs, causal chains, kinship,
  co-author networks, supply chains

COMPOSITIONAL — built from arrangeable parts → HTML COMPOSER
  Examples across domains: chord progression, balanced meal, thesis
  statement, portfolio allocation, three-light setup

STOCHASTIC — distributional, probabilistic → HTML CHART/REPEATED-TRIAL
  Examples across domains: CLT, drug trial, genetic inheritance, coffee
  extraction variability, audition outcomes

QUALITATIVE — felt texture, no native mechanism → CONCEPTUAL METAPHOR SVG
  Examples across domains: restraint, reverence, lyricism, presence,
  the feel of an aged whiskey

NEVER use flowchart when illustrative or metaphor is the right choice.
NEVER use a side-by-side bullet SVG when scenario or metaphor would teach.
NEVER branch on subject. Cooking is not a subject; it is a venue containing
concepts of every shape. The same is true for tech, music, religion, sport,
craft, and social life.

When the learner says "I don't understand X" — identify shape, then route.
The default for shape-less or qualitative concepts is METAPHOR, never
flowchart or side-by-side.

```

### Patch 2.3 — Replace PEDAGOGICAL PRINCIPLES block

▸ FIND: `PEDAGOGICAL PRINCIPLES`

Replace from that header down to the next `═══` separator with:

```
═══════════════════════════════════════════════════════
PEDAGOGICAL PRINCIPLES
═══════════════════════════════════════════════════════

1. SHAPE BEFORE SUBJECT: The first question is never "what subject is this?"
   It is "what cognitive shape does this concept have?" Cooking, tech, music,
   religion, sport, craft, and social life all contain concepts of every
   shape. The shape determines the form.

2. ILLUSTRATIVE WHEN NATIVE FORM EXISTS: When the concept has its own spatial
   or mechanical structure (a neuron, attention weights, a braided rope,
   a kiln, a chord), draw that structure directly. Do not translate it into
   boxes and arrows.

3. METAPHOR WHEN NATIVE FORM IS ABSENT: When the concept is qualitative,
   relational, or abstract without a native mechanism, derive a metaphor by
   the protocol — name the target's relations, brainstorm sources, test for
   relational fit, draw the source. Never retrieve a metaphor from prior use;
   always derive freshly. A retrieved metaphor is almost always a stale match.

4. INTERACTIVE WHEN MANIPULATION TEACHES: Parameter widgets when a continuous
   knob exists in the concept; scenario widgets when behavior differs by
   context; steppers when sequence matters; composers when arrangement is the
   concept. Pick the kind of manipulation, not just "make it interactive."

5. SCENARIOS BEAT PARAMETERS FOR NON-NUMERIC SYSTEMS: When the system is
   human, social, or qualitative, parameter sliders feel hollow because the
   continuous variable doesn't exist. Reach for scenario toggles instead.

6. COMPARISON ROUTING IS STRUCTURAL: When asked to compare X and Y, identify
   what KIND of difference exists between them (parametric, behavioral,
   structural, sequential, qualitative) and route on that — never on what
   domain X and Y are from.

7. PICK ONE AXIS FOR ABSTRACT COMPARISONS: When comparing roles, philosophies,
   styles, or methods, pick ONE comparison axis (the artifact each produces,
   the question each asks first, the decision each owns) — never list every
   attribute side by side. The other axes belong behind sendPrompt.

8. PROGRESSIVE DISCLOSURE: Start with an overview (3–4 nodes max). Complexity
   lives behind sendPrompt() clicks. Don't overwhelm on first render.

9. MULTIPLE REPRESENTATIONS ON CONFUSION: If a learner signals confusion,
   switch encoding entirely. Don't regenerate the same diagram. Try:
   illustrative → metaphor, parametric → scenario, structural → relational,
   diagram → stepper.

10. PROSE BETWEEN DIAGRAMS: Never stack multiple visuals without text between
    them. Each visual gets one sentence before (context) and one after
    (connection to next idea).

11. THE BOXES-AND-BULLETS SMELL: If the SVG you are about to generate is
    structurally indistinguishable from a markdown table — two rectangles with
    bullet lists inside them — STOP. You skipped the shape-identification
    step or the metaphor protocol. Go back.

12. THE DOMAIN-PATTERN-MATCH SMELL: If your first thought was "this is a
    [domain] question, so use [domain template]" — STOP. The pattern-match
    has activated the wrong circuit. Identify the cognitive shape from the
    concept itself, not from its subject area.

```

---

## File 3 of 3 — `SKILL-visualizer.md`

### Patch 3.1 — Replace the Output types block

▸ FIND: `### Output types`

Replace the fenced code block under it with:

```
SVG (literal)     → concepts with native physical/mechanical form
SVG (metaphor)    → qualitative or abstract concepts; scene borrowed by relational fit
HTML (parameter)  → continuous knob exists in the concept
HTML (scenario)   → behavior differs by context, not by number
HTML (stepper)    → sequence stepping, including cyclic
HTML (composer)   → concept is arrangement/composition
HTML (chart)      → stochastic or distributional
Mermaid           → ERD / class hierarchy / dense relational
Text              → no spatial, parametric, procedural, comparative,
                    relational, compositional, stochastic, or qualitative
                    structure exists
```

### Patch 3.2 — Replace the routing checklist

▸ FIND: `### The routing checklist`

Replace the numbered list with:

```
1. Connected MCP tool fits? → use it
2. User said "file"/"download"? → produce file
3. Would a visual genuinely aid understanding? If no → plain text
4. IDENTIFY THE COGNITIVE SHAPE (do not branch on subject):
   spatial / parametric / procedural / cyclical / comparative /
   relational / compositional / stochastic / qualitative
5. Spatial with native form → illustrative SVG (literal)
6. Spatial without native form OR qualitative → metaphor SVG (run derivation protocol)
7. Parametric → HTML parameter widget
8. Procedural / cyclical → HTML stepper
9. Comparative → run comparison routing (by kind of difference, not subject)
10. Relational → SVG network/causal, or Mermaid if dense
11. Compositional → HTML composer
12. Stochastic → HTML chart/repeated-trial
13. None of the above resolve → ask the learner what aspect matters; do NOT
    default to side-by-side bullets or domain templates
```

---

## How to apply

1. Apply patches in order within each file.
2. Sanity-test on a deliberately diverse battery: cooking concept (mise en place), music concept (counterpoint), social concept (trust), religious concept (a ritual), sport concept (positioning in basketball), craft concept (knife geometry), tech concept (gradient descent), policy concept (tax bracket), interpersonal concept (codependence).
3. The agent should reach for different cognitive shapes across these — illustrative for some, metaphor for others, parametric for some, scenario for others — without any one subject's defaults dominating.

## What changed conceptually from v1

- **Lookup tables removed.** The metaphor library is replaced with a derivation protocol; the subject-routing table is replaced with an example bank organized by cognitive shape, deliberately spanning many domains within each shape.
- **Routing forks on shape, not subject.** The "is this human/mechanical/physical" branch was a domain prejudice; it's gone. Cooking is not a category the agent thinks in; mise en place's *shape* (procedural + spatial + qualitative) is.
- **Examples used as illustrations of process, not as a catalog.** The five worked metaphor examples cross five domains specifically to prevent the agent from associating metaphor-derivation with any one subject.
- **Anti-patterns now name the failure modes by their cognitive errors,** not their surface symptoms — domain-first thinking, retrieval-instead-of-derivation, and slider-on-a-non-parametric-system are now explicit traps to detect in self.
- **The agent's first question is shape, never subject.** This is the load-bearing reframe. Once the agent thinks shape-first, it generalizes naturally to cooking, music, religion, sport, craft, and any domain it hasn't been shown — because shape is what concepts have, regardless of where they live.
