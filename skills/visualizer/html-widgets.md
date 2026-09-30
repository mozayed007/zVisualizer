# HTML Widget Generation — Complete Rules

## When to generate HTML instead of SVG

Generate an HTML widget (not SVG) when:
- The concept has a **control** the user should manipulate (slider, toggle, step button)
- The visual needs **animation** that responds to time or user input
- The output uses an **external library** (Chart.js, D3, Three.js)
- The process is **cyclic** (event loop, Krebs cycle → stepper, not ring)
- The user needs to see **live calculations** update as inputs change
- The concept benefits from **multiple panels** (step-through explainer)

**Decision rule:** If the real-world system has a dial, lever, or switch, give the diagram that control.

---

## Non-negotiable structural rules

```
NO DOCTYPE declaration
NO <html> tag
NO <head> tag
NO <body> tag
NO HTML comments (<!-- -->)
NO CSS comments (/* */)
NO localStorage, sessionStorage, IndexedDB (all blocked by sandbox)
NO position: fixed (collapses iframe height)
NO external resources except from the CDN allowlist
```

The output is a **fragment** that gets injected as `iframe srcdoc`. It renders inside a parent document. Adding document-level tags creates broken HTML.

---

## Required streaming order

```
1. <style> block       — CSS variables, layout rules, component styles
2. Content HTML        — all visible elements (divs, inputs, buttons, SVG)
3. CDN <script> tags   — external libraries (load after content is visible)
4. Logic <script>      — uses the CDN globals loaded above
```

This order ensures the user sees content immediately while libraries download. If the logic script comes before the CDN script, the global will be undefined and the widget breaks silently.

---

## CSS variable system

All colors, fonts, and spacing must use CSS variables — never hardcoded values. The host injects these variables into every iframe.

### Text colors
```css
var(--color-text-primary)      /* main text — auto light/dark */
var(--color-text-secondary)    /* muted descriptions */
var(--color-text-tertiary)     /* hints, placeholders */
var(--color-text-info)         /* blue informational text */
var(--color-text-success)      /* green success text */
var(--color-text-warning)      /* amber warning text */
var(--color-text-danger)       /* red/coral error text */
```

### Background colors
```css
var(--color-background-primary)    /* white / near-black */
var(--color-background-secondary)  /* card surface */
var(--color-background-tertiary)   /* page background */
var(--color-background-info)       /* light blue tint */
var(--color-background-success)    /* light green tint */
var(--color-background-warning)    /* light amber tint */
var(--color-background-danger)     /* light red/coral tint */
```

### Border colors
```css
var(--color-border-tertiary)   /* 0.15α — default borders */
var(--color-border-secondary)  /* 0.3α — hover/active borders */
var(--color-border-primary)    /* 0.4α — emphasized borders */
var(--color-border-info)       /* blue borders */
var(--color-border-success)    /* green borders */
```

### Typography
```css
var(--font-sans)    /* Anthropic Sans (or fallback system sans-serif) */
var(--font-mono)    /* JetBrains Mono (or fallback monospace) */
var(--font-serif)   /* for rare editorial/blockquote moments */
```

### Layout
```css
var(--border-radius-sm)   /* 4px */
var(--border-radius-md)   /* 8px — default for most components */
var(--border-radius-lg)   /* 12px — cards, panels */
var(--border-radius-xl)   /* 16px — large containers */
```

### Dark mode rule
**Never use hardcoded colors in HTML widgets.** The one exception is physical-color illustrations (atom diagrams, molecular structures, cross-sections with material colors) where colors should NOT invert in dark mode. In those cases, hardcode the hex and add `@media (prefers-color-scheme: dark)` overrides explicitly.

---

## Pre-styled HTML elements

The host stylesheet pre-styles bare HTML elements. Use them as-is, add `style="..."` only to override.

### Inputs
```html
<!-- Range slider — pre-styled with 4px track, 18px thumb, accent-color from --color-text-info -->
<input type="range" min="0" max="100" value="50" id="mySlider" oninput="update(this.value)">

<!-- Text input — pre-styled with 36px height, border, border-radius-md -->
<input type="text" placeholder="Enter value..." id="myInput">

<!-- Checkbox — pre-styled -->
<input type="checkbox" id="myCheck" onchange="toggle(this.checked)">
```

### Buttons
```html
<!-- Standard button — transparent bg, border, hover bg-secondary, active scale(0.98) -->
<button onclick="doSomething()">Run</button>

<!-- sendPrompt button — append ↗ to signal it opens chat -->
<button onclick="sendPrompt('What happens if the step size is too high?')">
  Ask about step size ↗
</button>
```

### Number display — ALWAYS round
```javascript
// JS float math leaks: 0.1 + 0.2 = 0.30000000000000004
// Every number shown to a user must be rounded

element.textContent = value.toFixed(2);           // 2 decimals
element.textContent = Math.round(value);           // integer
element.textContent = value.toLocaleString();      // currency/large numbers
element.textContent = (value * 100).toFixed(1) + '%'; // percentage
```

---

## State management

No browser storage is available in the sandbox. All widget state lives in JavaScript variables.

```javascript
// CORRECT: state in JS variables
let step = 0;
let currentData = [1, 2, 3, 4, 5];
let isPlaying = false;

// WRONG: localStorage is blocked by sandbox — throws silently
localStorage.setItem('step', 0);  // fails
sessionStorage.setItem('data', JSON.stringify([]));  // fails
```

For widgets that should persist state across page navigations, the host application must handle state serialization and inject it into the widget via the srcdoc generation.

---

## The sendPrompt bridge

```javascript
// Injected by the host into every iframe — do not redefine it
window.sendPrompt = text => parent.postMessage({ type: 'prompt', text }, '*');

// USAGE in onclick attributes:
onclick="sendPrompt('Why does the step size affect convergence speed?')"

// USAGE in JS code:
document.querySelector('#explore-btn').addEventListener('click', () => {
  sendPrompt(`What happens to the loss when the step size is ${currentStepSize.toFixed(3)}?`);
});
```

**sendPrompt question quality rules:**
- Be specific to what the user just interacted with
- Include the current value if it's informative ("what happens at step size 0.1")
- Phrase as the user would ask it, not as a machine label
- One question only — not "tell me more" or "explain everything"

---

## Complete stepper widget pattern

The stepper is the standard pattern for sequential or cyclic processes. One panel per stage. Stage content stays hidden until that stage is active — but all content is in the DOM (not `display:none` during streaming).

```html
<style>
  .stepper { font-family: var(--font-sans); padding: 1rem 0; }
  .progress { display: flex; gap: 6px; margin-bottom: 20px; }
  .dot { width: 8px; height: 8px; border-radius: 50%;
         background: var(--color-border-secondary); transition: background 0.2s; }
  .dot.active { background: var(--color-text-info); }
  .panel { display: none; }
  .panel.active { display: block; }
  .panel-title { font-size: 15px; font-weight: 500; color: var(--color-text-primary);
                 margin-bottom: 8px; }
  .panel-body  { font-size: 13px; color: var(--color-text-secondary); line-height: 1.65;
                 margin-bottom: 16px; }
  .nav { display: flex; gap: 8px; align-items: center; }
  .step-counter { font-size: 12px; color: var(--color-text-tertiary);
                  font-family: var(--font-mono); }
</style>

<div class="stepper">
  <div class="progress" id="progress"></div>

  <div class="panel active" id="panel-0">
    <div class="panel-title">Stage 1: Detection</div>
    <div class="panel-body">
      A pathogen enters the body. Innate immune cells (macrophages, dendritic cells)
      detect foreign antigens using pattern recognition receptors (PRRs) that identify
      pathogen-associated molecular patterns (PAMPs).
    </div>
    <!-- Optional: inline SVG illustration for this stage -->
    <svg width="100%" viewBox="0 0 680 120">
      <!-- stage-specific illustration here -->
    </svg>
  </div>

  <div class="panel" id="panel-1">
    <div class="panel-title">Stage 2: Antigen presentation</div>
    <div class="panel-body">
      Dendritic cells engulf the pathogen and migrate to lymph nodes.
      They display pathogen fragments (antigens) on MHC class II molecules,
      presenting them to T helper cells.
    </div>
  </div>

  <div class="panel" id="panel-2">
    <div class="panel-title">Stage 3: T cell activation</div>
    <div class="panel-body">
      T helper cells recognize the antigen-MHC complex and activate.
      They proliferate and release cytokines that amplify the immune response,
      activating B cells and cytotoxic T cells.
    </div>
  </div>

  <!-- Add more panels as needed -->

  <div class="nav">
    <button onclick="prevStep()">← Back</button>
    <span class="step-counter" id="counter">1 / 3</span>
    <button onclick="nextStep()">Next →</button>
    <button onclick="sendPrompt('Tell me more about T cell activation')">
      Dig deeper ↗
    </button>
  </div>
</div>

<script>
const TOTAL = 3; // update to match number of panels
let current = 0;

// Build progress dots
const progress = document.getElementById('progress');
for (let i = 0; i < TOTAL; i++) {
  const d = document.createElement('div');
  d.className = 'dot' + (i === 0 ? ' active' : '');
  d.onclick = () => goTo(i);
  d.style.cursor = 'pointer';
  progress.appendChild(d);
}

function goTo(n) {
  document.getElementById('panel-' + current).classList.remove('active');
  document.querySelectorAll('.dot')[current].classList.remove('active');
  current = (n + TOTAL) % TOTAL;
  document.getElementById('panel-' + current).classList.add('active');
  document.querySelectorAll('.dot')[current].classList.add('active');
  document.getElementById('counter').textContent = (current + 1) + ' / ' + TOTAL;
}

function nextStep() { goTo(current + 1); }
function prevStep() { goTo(current - 1); }
</script>
```

---

## Chart.js pattern — correct initialization

```html
<style>
  .chart-container { position: relative; height: 280px; margin: 1rem 0; }
</style>

<div class="chart-container">
  <canvas id="myChart"></canvas>
</div>

<div style="display:flex;align-items:center;gap:12px;margin-top:12px;font-size:13px;color:var(--color-text-secondary)">
  <label>Step size</label>
  <input type="range" min="1" max="100" value="10" id="stepSlider"
         oninput="updateStepSize(this.value)" style="flex:1">
  <span id="stepDisplay" style="min-width:40px;font-family:var(--font-mono)">0.10</span>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script>
// Detect dark mode for chart colors
const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const textColor = dark ? '#9b9890' : '#5a5855';
const gridColor = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';

// Compute initial data
function computeLoss(stepSize, steps = 30) {
  const data = [];
  let loss = 10;
  for (let i = 0; i < steps; i++) {
    // Simplified: high step size oscillates, low step size converges slowly
    const noise = (Math.random() - 0.5) * stepSize * 0.4;
    loss = Math.max(0.01, loss * (1 - stepSize * 0.08) + noise);
    data.push(+loss.toFixed(3));
  }
  return data;
}

const ctx = document.getElementById('myChart').getContext('2d');
const chart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: Array.from({length: 30}, (_, i) => i + 1),
    datasets: [{
      label: 'Training loss',
      data: computeLoss(0.10),
      borderColor: '#7f77dd',
      backgroundColor: 'rgba(127,119,221,0.1)',
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0.3
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: {
      legend: { labels: { color: textColor, font: { size: 12 } } }
    },
    scales: {
      x: { ticks: { color: textColor }, grid: { color: gridColor } },
      y: { ticks: { color: textColor }, grid: { color: gridColor }, min: 0 }
    }
  }
});

function updateStepSize(rawValue) {
  const stepSize = rawValue / 100;
  document.getElementById('stepDisplay').textContent = stepSize.toFixed(2);
  chart.data.datasets[0].data = computeLoss(stepSize);
  chart.update();
}
</script>
```

---

## D3 pattern — force-directed graph for concept maps

```html
<div id="graph" style="width:100%;height:320px;"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const nodes = [
  { id: 'Neuron', group: 0 },
  { id: 'Synapse', group: 0 },
  { id: 'Axon', group: 0 },
  { id: 'Dendrite', group: 0 },
  { id: 'Action potential', group: 1 },
  { id: 'Neurotransmitter', group: 1 }
];
const links = [
  { source: 'Neuron', target: 'Axon' },
  { source: 'Neuron', target: 'Dendrite' },
  { source: 'Axon', target: 'Synapse' },
  { source: 'Synapse', target: 'Neurotransmitter' },
  { source: 'Action potential', target: 'Axon' }
];

const colors = ['#7f77dd', '#1d9e75'];
const W = document.getElementById('graph').clientWidth;
const H = 320;

const svg = d3.select('#graph').append('svg')
  .attr('width', W).attr('height', H);

const sim = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(links).id(d => d.id).distance(80))
  .force('charge', d3.forceManyBody().strength(-200))
  .force('center', d3.forceCenter(W / 2, H / 2));

const link = svg.append('g').selectAll('line').data(links).join('line')
  .attr('stroke', dark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)')
  .attr('stroke-width', 1.5);

const node = svg.append('g').selectAll('circle').data(nodes).join('circle')
  .attr('r', 20).attr('fill', d => colors[d.group])
  .attr('stroke', dark ? '#0d0d0f' : '#fff').attr('stroke-width', 2)
  .style('cursor', 'pointer')
  .on('click', (event, d) => sendPrompt(`Explain ${d.id} in detail`))
  .call(d3.drag()
    .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
    .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
    .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

const label = svg.append('g').selectAll('text').data(nodes).join('text')
  .text(d => d.id).attr('font-size', 11).attr('text-anchor', 'middle')
  .attr('dy', '0.35em').attr('fill', dark ? '#e8e6df' : '#1a1918')
  .style('pointer-events', 'none');

sim.on('tick', () => {
  link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  node.attr('cx', d => d.x).attr('cy', d => d.y);
  label.attr('x', d => d.x).attr('y', d => d.y);
});
</script>
```

---

## Animation rules

Animations are allowed in HTML widgets but must follow these constraints:

```css
/* ALLOWED: animating transform and opacity only */
@keyframes fadeIn   { from { opacity: 0 } to { opacity: 1 } }
@keyframes slideUp  { from { transform: translateY(20px); opacity: 0 }
                      to   { transform: translateY(0);    opacity: 1 } }
@keyframes pulse    { 0%, 100% { opacity: 0.4 } 50% { opacity: 0.8 } }
@keyframes flow     { to { stroke-dashoffset: -20 } }  /* for moving dashes */

/* REQUIRED: respect prefers-reduced-motion */
@media (prefers-reduced-motion: no-preference) {
  .animated { animation: fadeIn 0.3s ease; }
}

/* Convection current example */
.conv-line {
  stroke-dasharray: 5 5;
  animation: flow 1.6s linear infinite;
}
```

**Limits:**
- Loops under 2 seconds
- Only `transform` and `opacity` in keyframes (GPU composited — no layout thrashing)
- No physics engines or heavy JS animation libraries
- Animations must show the system's behavior (heat rising, electrons moving) — not decoration

---

## CDN import patterns

### UMD global (preferred — loads synchronously before logic script)
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script>
  const chart = new Chart(ctx, config); // Chart is a global
</script>
```

### ES Module (for Mermaid — must use type="module")
```html
<script type="module">
  import mermaid from 'https://esm.sh/mermaid@11/dist/mermaid.esm.min.mjs';
  await mermaid.initialize({ startOnLoad: false, theme: 'base' });
  const { svg } = await mermaid.render('id', diagramDefinition);
  document.getElementById('container').innerHTML = svg;
</script>
```

### Three.js — use r128 specifically
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
  // THREE is a global
  // Note: THREE.CapsuleGeometry was added in r142 — NOT available in r128
  // Use: SphereGeometry, CylinderGeometry, BoxGeometry, PlaneGeometry
  const geometry = new THREE.SphereGeometry(1, 32, 32);
</script>
```

---

## Common failure modes

### Failure: iframe collapses to 0px height
**Cause:** `position: fixed` on any element  
**Fix:** All layout must be in normal document flow. Use `min-height` on wrappers instead.

### Failure: chart or diagram is invisible
**Cause:** Canvas/SVG has no defined height  
**Fix:** Always wrap canvas in a div with explicit height: `<div style="height:300px"><canvas></canvas></div>`

### Failure: CDN library undefined when logic runs
**Cause:** Logic script placed before the CDN `<script>` tag  
**Fix:** Enforce the streaming order: style → content → CDN script → logic script

### Failure: dark mode text invisible
**Cause:** `color: #333` hardcoded instead of CSS variable  
**Fix:** Every text color must use `var(--color-text-primary)` or `var(--color-text-secondary)`

### Failure: floating point displayed incorrectly
**Cause:** `element.textContent = value` where value is a JS float  
**Fix:** Always `.toFixed(n)` or `Math.round()` before displaying any computed number

### Failure: sendPrompt is undefined
**Cause:** Widget ran before the host injected the bridge, or srcdoc was set before bridge injection  
**Fix:** The host must prepend the bridge script before the widget code in srcdoc
