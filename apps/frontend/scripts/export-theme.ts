/**
 * export-theme - generates the backend/MCP copy of the widget theme contract.
 *
 * Source of truth: src/lib/designTokens.ts (guarded by __tests__/designTokens.test.ts).
 * Outputs (committed, consumed by the Python MCP render pipeline):
 *   apps/backend/app/mcp/render/assets/widget-theme.css   - exact buildWidgetThemeCss() text
 *   apps/backend/app/mcp/render/assets/widget-theme.json  - structured tokens + ramps
 *
 * Run: bun run export:theme  (from apps/frontend)
 * Freshness is enforced by scripts/check.ps1 / check.sh, which regenerate and
 * fail on `git diff --exit-code` for these two files.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildWidgetThemeCss, colorRamps } from '../src/lib/designTokens'

const here = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(here, '../../backend/app/mcp/render/assets')

const css = buildWidgetThemeCss()

function extractBlock(cssText: string, selector: string): string {
  const index = cssText.indexOf(selector)
  if (index === -1) {
    throw new Error(`export-theme: selector not found in theme CSS: ${selector}`)
  }
  const open = cssText.indexOf('{', index)
  const close = cssText.indexOf('}', open)
  if (open === -1 || close === -1) {
    throw new Error(`export-theme: malformed block for selector: ${selector}`)
  }
  return cssText.slice(open + 1, close)
}

function parseCustomProps(blockText: string): Record<string, string> {
  const props: Record<string, string> = {}
  for (const part of blockText.split(';')) {
    const separator = part.indexOf(':')
    if (separator === -1) {
      continue
    }
    const name = part.slice(0, separator).trim()
    const value = part.slice(separator + 1).trim()
    if (!name.startsWith('--') || !value) {
      continue
    }
    props[name] = value
  }
  return props
}

const light = parseCustomProps(extractBlock(css, ':root {'))
const dark = parseCustomProps(extractBlock(css, ':root.dark {'))

const requiredTokens = [
  '--color-background-primary',
  '--color-background-secondary',
  '--color-background-tertiary',
  '--color-text-primary',
  '--color-text-secondary',
  '--color-text-tertiary',
  '--color-border-tertiary',
  '--color-border-secondary',
  '--font-sans',
  '--font-mono',
  '--border-radius-md',
  '--p',
  '--s',
  '--t',
  '--bg2',
  '--b',
]
for (const token of requiredTokens) {
  if (!(token in light)) {
    throw new Error(`export-theme: required token missing from :root: ${token}`)
  }
}
const rampSteps = ['50', '100', '200', '400', '600', '800', '900'] as const
for (const [rampName, ramp] of Object.entries(colorRamps)) {
  for (const step of rampSteps) {
    if (!(step in ramp)) {
      throw new Error(`export-theme: ramp ${rampName} missing step ${step}`)
    }
  }
}

const payload = {
  version: 1,
  source: 'apps/frontend/src/lib/designTokens.ts',
  tokens: { light, dark },
  ramps: colorRamps,
}

mkdirSync(outDir, { recursive: true })
writeFileSync(resolve(outDir, 'widget-theme.css'), css.endsWith('\n') ? css : `${css}\n`, 'utf8')
writeFileSync(resolve(outDir, 'widget-theme.json'), `${JSON.stringify(payload, null, 2)}\n`, 'utf8')

console.log(
  `export-theme: wrote widget-theme.css (${css.length} chars) and widget-theme.json ` +
    `(${Object.keys(light).length} light tokens) to ${outDir}`,
)
