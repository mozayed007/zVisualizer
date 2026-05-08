import { describe, expect, it } from 'bun:test'

import { buildWidgetThemeCss } from '../designTokens'

/**
 * These tests guard the host side of the visualizer-agent widget contract.
 * Generated `widget_code` references these exact identifiers — if any of them
 * disappear from `buildWidgetThemeCss()`, widgets will silently render wrong.
 *
 * Canonical sources of truth:
 *   - docs/visualizer_skill/design-system.md
 *   - docs/frontend-widget-integration.md §5
 */

const css = buildWidgetThemeCss()

const RAMPS = ['purple', 'teal', 'amber', 'coral', 'blue', 'green', 'pink', 'gray', 'red'] as const

const REQUIRED_CSS_VARS = [
  '--color-background-primary',
  '--color-background-secondary',
  '--color-background-tertiary',
  '--color-background-info',
  '--color-background-success',
  '--color-background-warning',
  '--color-background-danger',
  '--color-text-primary',
  '--color-text-secondary',
  '--color-text-tertiary',
  '--color-text-info',
  '--color-text-success',
  '--color-text-warning',
  '--color-text-danger',
  '--color-border-tertiary',
  '--color-border-secondary',
  '--color-border-primary',
  '--color-border-info',
  '--color-border-success',
  '--color-border-warning',
  '--color-border-danger',
  '--font-sans',
  '--font-mono',
  '--font-serif',
  '--border-radius-sm',
  '--border-radius-md',
  '--border-radius-lg',
  '--border-radius-xl',
  '--p',
  '--s',
  '--t',
  '--bg2',
  '--b',
] as const

describe('buildWidgetThemeCss — CSS custom properties', () => {
  for (const varName of REQUIRED_CSS_VARS) {
    it(`declares ${varName}`, () => {
      expect(css).toContain(varName)
    })
  }

  it('declares dark-mode overrides via prefers-color-scheme', () => {
    expect(css).toMatch(/@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)/)
  })
})

describe('buildWidgetThemeCss — color ramps', () => {
  for (const ramp of RAMPS) {
    it(`declares direct-child ramp for c-${ramp}`, () => {
      // e.g. .c-purple>rect,.c-purple>circle,.c-purple>ellipse
      const pattern = new RegExp(`\\.c-${ramp}\\s*>\\s*rect`)
      expect(css).toMatch(pattern)
    })

    it(`declares class-form ramp (.c-${ramp} .box)`, () => {
      const pattern = new RegExp(`\\.c-${ramp}\\s+\\.box`)
      expect(css).toMatch(pattern)
    })

    it(`declares title text fill for c-${ramp}`, () => {
      // either `.c-purple .th` (class form) or `.c-purple>text.th` (child form)
      const pattern = new RegExp(`\\.c-${ramp}[\\s>][^{]*\\.?th`)
      expect(css).toMatch(pattern)
    })

    it(`declares subtitle text fill for c-${ramp}`, () => {
      const pattern = new RegExp(`\\.c-${ramp}[\\s>][^{]*\\.?ts`)
      expect(css).toMatch(pattern)
    })
  }

  it('emits dark-mode overrides for every ramp', () => {
    // The docs promise: each c-{ramp} ramp appears both outside and inside a
    // `@media(prefers-color-scheme:dark)` block. We can't easily scope by AST
    // in a string test, but we can check occurrence count is >= 2 per ramp.
    for (const ramp of RAMPS) {
      const occurrences = css.match(new RegExp(`\\.c-${ramp}`, 'g')) ?? []
      expect(occurrences.length).toBeGreaterThanOrEqual(2)
    }
  })
})

describe('buildWidgetThemeCss — SVG utility classes', () => {
  const selectors = [
    /\.box\b/,
    /text\.t\b/,
    /text\.th\b/,
    /text\.ts\b/,
    /\.arr\b/,
    /\.node\b/,
    /\.leader\b/,
  ]
  for (const pattern of selectors) {
    it(`declares ${pattern.source}`, () => {
      expect(css).toMatch(pattern)
    })
  }

  it('SVG text baselines use dominant-baseline: central', () => {
    expect(css).toMatch(/dominant-baseline\s*:\s*central/)
  })
})

describe('buildWidgetThemeCss — form element pre-styles', () => {
  it("pre-styles input[type='range']", () => {
    expect(css).toMatch(/input\[type='range'\]/)
  })
  it("pre-styles input[type='text']", () => {
    expect(css).toMatch(/input\[type='text'\]/)
  })
  it("pre-styles input[type='number']", () => {
    expect(css).toMatch(/input\[type='number'\]/)
  })
  it("pre-styles input[type='checkbox']", () => {
    expect(css).toMatch(/input\[type='checkbox'\]/)
  })
  it('pre-styles button', () => {
    expect(css).toMatch(/button\s*\{[^}]*font-family/)
  })
  it('pre-styles select', () => {
    expect(css).toMatch(/select\s*,?\s*\{|select\s*\{/)
  })
})

describe('buildWidgetThemeCss — base + reset + motion', () => {
  it('imports Plus Jakarta Sans + JetBrains Mono from Google Fonts', () => {
    expect(css).toContain('https://fonts.googleapis.com/css2')
    expect(css).toContain('Plus+Jakarta+Sans')
    expect(css).toContain('JetBrains+Mono')
  })
  it('resets box-sizing', () => {
    expect(css).toMatch(/box-sizing\s*:\s*border-box/)
  })
  it('body uses transparent background + font-sans', () => {
    expect(css).toMatch(/background\s*:\s*transparent/)
    expect(css).toMatch(/font-family\s*:\s*var\(\s*--font-sans\s*\)/)
  })
  it('svg scales to 100% width', () => {
    expect(css).toMatch(/svg[^{]*\{[^}]*width\s*:\s*100%/)
  })
  it('honours prefers-reduced-motion', () => {
    expect(css).toMatch(/@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)/)
  })
})
