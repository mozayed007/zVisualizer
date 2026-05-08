/**
 * designTokens — CSS injected into every visualizer-agent widget iframe.
 *
 * The string returned by `buildWidgetThemeCss()` is the host half of the
 * contract documented in:
 *   - docs/visualizer_skill/design-system.md  (canonical spec)
 *   - docs/frontend-widget-integration.md §5  (reference stylesheet)
 *
 * Generated `widget_code` from the visualizer agent references these exact
 * identifiers. Do NOT rename, drop, or recolor any of the following without a
 * coordinated update to the agent prompts (apps/backend/app/agent/prompt.py)
 * and the two docs above:
 *
 *   CSS custom props: --color-background-{primary,secondary,tertiary,info,success,warning,danger}
 *                     --color-text-{primary,secondary,tertiary,info,success,warning,danger}
 *                     --color-border-{tertiary,secondary,primary,info,success,warning,danger}
 *                     --font-{sans,mono,serif}
 *                     --border-radius-{sm,md,lg,xl}
 *                     --p, --s, --t, --bg2, --b        (SVG shorthand aliases)
 *   Ramp classes:     c-{purple,teal,amber,coral,blue,green,pink,gray,red}
 *                     — both class form (.c-X .box) AND direct-child form (.c-X>rect)
 *                     — light AND dark variants
 *   SVG utilities:    .box, text.t, text.th, text.ts, .arr, .node, .leader
 *   Form elements:    button, select, input[type={range,text,number,checkbox}]
 *   Font import:      https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans+...+JetBrains+Mono
 *
 * A bun test (`__tests__/designTokens.test.ts`) asserts every surface above is
 * present — it will fail loudly if any is accidentally removed.
 */
const colorRamps = {
  purple: { 50: '#EEEDFE', 100: '#CECBF6', 200: '#AFA9EC', 400: '#7F77DD', 600: '#534AB7', 800: '#3C3489', 900: '#26215C' },
  teal: { 50: '#E1F5EE', 100: '#9FE1CB', 200: '#5DCAA5', 400: '#1D9E75', 600: '#0F6E56', 800: '#085041', 900: '#04342C' },
  amber: { 50: '#FAEEDA', 100: '#FAC775', 200: '#EF9F27', 400: '#BA7517', 600: '#854F0B', 800: '#633806', 900: '#412402' },
  coral: { 50: '#FAECE7', 100: '#F5C4B3', 200: '#F0997B', 400: '#D85A30', 600: '#993C1D', 800: '#712B13', 900: '#4A1B0C' },
  blue: { 50: '#E6F1FB', 100: '#B5D4F4', 200: '#85B7EB', 400: '#378ADD', 600: '#185FA5', 800: '#0C447C', 900: '#042C53' },
  green: { 50: '#EAF3DE', 100: '#C0DD97', 200: '#97C459', 400: '#639922', 600: '#3B6D11', 800: '#27500A', 900: '#173404' },
  pink: { 50: '#FBEAF0', 100: '#F4C0D1', 200: '#ED93B1', 400: '#D4537E', 600: '#993556', 800: '#72243E', 900: '#4B1528' },
  gray: { 50: '#F1EFE8', 100: '#D3D1C7', 200: '#B4B2A9', 400: '#888780', 600: '#5F5E5A', 800: '#444441', 900: '#2C2C2A' },
  red: { 50: '#FCEBEB', 100: '#F7C1C1', 200: '#F09595', 400: '#E24B4A', 600: '#A32D2D', 800: '#791F1F', 900: '#501313' },
} as const

function buildRampClasses(mode: 'light' | 'dark', rootSelector: string = ''): string {
  return Object.entries(colorRamps)
    .map(([name, ramp]) => {
      const fill = mode === 'light' ? ramp[50] : ramp[800]
      const stroke = mode === 'light' ? ramp[600] : ramp[200]
      const title = mode === 'light' ? ramp[800] : ramp[100]
      const subtitle = mode === 'light' ? ramp[600] : ramp[200]

      const prefix = rootSelector ? `${rootSelector} ` : ''
      return `
      ${prefix}.c-${name} .box, ${prefix}.c-${name}.box { fill: ${fill}; stroke: ${stroke}; }
      ${prefix}.c-${name} .th, ${prefix}.c-${name}.th, ${prefix}.c-${name} .t, ${prefix}.c-${name}.t { fill: ${title}; }
      ${prefix}.c-${name} .ts, ${prefix}.c-${name}.ts { fill: ${subtitle}; }
      ${prefix}.c-${name} .arr, ${prefix}.c-${name}.arr { stroke: ${stroke}; }
      `
    })
    .join('\n')
}

export function buildWidgetThemeCss(): string {
  return `
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap');

  :root {
    color-scheme: light dark;
    --color-background-primary: #ffffff;
    --color-background-secondary: #f4f2eb;
    --color-background-tertiary: #eceae3;
    --color-background-info: #e6f1fb;
    --color-background-success: #eaf3de;
    --color-background-warning: #faeeda;
    --color-background-danger: #faece7;
    --color-text-primary: #1a1918;
    --color-text-secondary: #5a5855;
    --color-text-tertiary: #9b9890;
    --color-text-info: #185fa5;
    --color-text-success: #27500a;
    --color-text-warning: #633806;
    --color-text-danger: #712b13;
    --color-border-tertiary: rgba(0, 0, 0, 0.09);
    --color-border-secondary: rgba(0, 0, 0, 0.14);
    --color-border-primary: rgba(0, 0, 0, 0.4);
    --color-border-info: #185fa5;
    --color-border-success: #3b6d11;
    --color-border-warning: #854f0b;
    --color-border-danger: #993c1d;
    --font-sans: 'Plus Jakarta Sans', system-ui, sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
    --font-serif: Georgia, serif;
    --border-radius-sm: 4px;
    --border-radius-md: 8px;
    --border-radius-lg: 12px;
    --border-radius-xl: 16px;
    --p: var(--color-text-primary);
    --s: var(--color-text-secondary);
    --t: var(--color-text-tertiary);
    --bg2: var(--color-background-secondary);
    --b: var(--color-border-tertiary);
  }

  @media (prefers-color-scheme: dark) {
    :root:not(.light) {
      --color-background-primary: #141417;
      --color-background-secondary: #1a1a1f;
      --color-background-tertiary: #0d0d0f;
      --color-background-info: rgba(55, 138, 221, 0.15);
      --color-background-success: rgba(99, 153, 34, 0.15);
      --color-background-warning: rgba(239, 159, 39, 0.15);
      --color-background-danger: rgba(216, 90, 48, 0.15);
      --color-text-primary: #e8e6df;
      --color-text-secondary: #9b9890;
      --color-text-tertiary: #5e5c58;
      --color-text-info: #378add;
      --color-text-success: #639922;
      --color-text-warning: #ef9f27;
      --color-text-danger: #d85a30;
      --color-border-tertiary: rgba(255, 255, 255, 0.08);
      --color-border-secondary: rgba(255, 255, 255, 0.14);
      --color-border-primary: rgba(255, 255, 255, 0.4);
    }
  }

  :root.dark {
    --color-background-primary: #141417;
    --color-background-secondary: #1a1a1f;
    --color-background-tertiary: #0d0d0f;
    --color-background-info: rgba(55, 138, 221, 0.15);
    --color-background-success: rgba(99, 153, 34, 0.15);
    --color-background-warning: rgba(239, 159, 39, 0.15);
    --color-background-danger: rgba(216, 90, 48, 0.15);
    --color-text-primary: #e8e6df;
    --color-text-secondary: #9b9890;
    --color-text-tertiary: #5e5c58;
    --color-text-info: #378add;
    --color-text-success: #639922;
    --color-text-warning: #ef9f27;
    --color-text-danger: #d85a30;
    --color-border-tertiary: rgba(255, 255, 255, 0.08);
    --color-border-secondary: rgba(255, 255, 255, 0.14);
    --color-border-primary: rgba(255, 255, 255, 0.4);
  }

  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    width: 100%;
    background: transparent;
    color: var(--color-text-primary);
    font-family: var(--font-sans);
    font-size: 15px;
    line-height: 1.7;
  }
  svg, canvas, img, video {
    width: 100%;
    display: block;
  }
  svg, img, video {
    height: auto;
  }
  canvas {
    max-width: 100%;
  }
  svg {
    font-family: var(--font-sans);
  }
  .box {
    fill: var(--color-background-secondary);
    stroke: var(--color-border-secondary);
    stroke-width: 0.5;
    rx: 12;
  }
  .th, .t, .ts {
    dominant-baseline: central;
    font-family: var(--font-sans);
  }
  .th { font-size: 14px; font-weight: 500; }
  .t { font-size: 14px; font-weight: 400; }
  .ts { font-size: 12px; font-weight: 400; }
  .arr {
    fill: none;
    stroke-width: 1.5;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  button, input, select {
    font: inherit;
  }
  input[type='range'] {
    width: 100%;
    accent-color: var(--color-text-info);
    cursor: pointer;
  }
  input[type='checkbox'] {
    accent-color: var(--color-text-info);
    cursor: pointer;
  }
  input[type='text'], input[type='number'], select {
    height: 36px;
    padding: 0 10px;
    border: 1px solid var(--color-border-secondary);
    border-radius: var(--border-radius-md);
    background: var(--color-background-secondary);
    color: var(--color-text-primary);
    font-family: var(--font-sans);
    font-size: 14px;
  }
  input[type='text']:focus, input[type='number']:focus {
    outline: none;
    border-color: var(--color-border-info);
  }
  select:focus {
    outline: none;
    border-color: var(--color-border-info);
  }
  a {
    color: var(--color-text-info);
  }
  button {
    background: transparent;
    border: 1px solid var(--color-border-secondary);
    border-radius: var(--border-radius-md);
    color: var(--color-text-primary);
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 500;
    padding: 7px 16px;
    cursor: pointer;
    transition: background 0.15s, transform 0.1s;
  }
  button:hover {
    background: var(--color-background-secondary);
  }
  button:active {
    transform: scale(0.98);
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation: none !important;
      transition: none !important;
      scroll-behavior: auto !important;
    }
  }
  ${buildRampClasses('light')}
  @media (prefers-color-scheme: dark) {
    ${buildRampClasses('dark', ':root:not(.light)')}
  }
  ${buildRampClasses('dark', ':root.dark')}

  /* docs/frontend-widget-integration.md — direct-child SVG ramps (skill output) */
  ${documentedSvgChildRamps()}
  `
}

/** Matches docs/frontend-widget-integration §5 — complements .c-* .box class-based widgets. */
function documentedSvgChildRamps(): string {
  const buildChildRamps = (mode: 'light' | 'dark', rootSelector: string = '') => {
    return Object.entries(colorRamps)
      .map(([name, ramp]) => {
        const fill = mode === 'light' ? ramp[50] : ramp[800]
        const stroke = mode === 'light' ? ramp[600] : ramp[600] // Wait, documented string uses 600 for stroke in both light and dark! Wait, let me check.
        // Actually, looking at the previous hardcoded string:
        // .c-purple>rect... {fill:#3C3489;stroke:#534AB7} -> 800 and 600
        // Light: fill 50, stroke 600
        const title = mode === 'light' ? ramp[800] : ramp[100]
        const subtitle = mode === 'light' ? ramp[600] : ramp[200]
        
        const prefix = rootSelector ? `${rootSelector} ` : ''
        return `
${prefix}.c-${name}>rect,${prefix}.c-${name}>circle,${prefix}.c-${name}>ellipse{fill:${fill};stroke:${stroke}}
${prefix}.c-${name}>text.t,${prefix}.c-${name}>text.th{fill:${title}}
${prefix}.c-${name}>text.ts{fill:${subtitle}}`
      })
      .join('')
  }

  return `
${buildChildRamps('light')}
@media(prefers-color-scheme:dark){
${buildChildRamps('dark', ':root:not(.light)')}
}
${buildChildRamps('dark', ':root.dark')}

text.t{font-size:14px;font-weight:400;fill:var(--color-text-primary);font-family:var(--font-sans)}
text.th{font-size:14px;font-weight:500;fill:var(--color-text-primary);font-family:var(--font-sans)}
text.ts{font-size:12px;font-weight:400;fill:var(--color-text-secondary);font-family:var(--font-sans)}
.node{cursor:pointer}
.node:hover{opacity:0.82}
.arr{stroke:var(--color-border-secondary);stroke-width:1.5;fill:none}
.leader{stroke:var(--color-border-tertiary);stroke-width:0.5;fill:none;stroke-dasharray:3 3}
`
}
