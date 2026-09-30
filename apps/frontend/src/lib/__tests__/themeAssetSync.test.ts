/**
 * Drift gate for the generated backend/MCP theme assets.
 *
 * `bun run export:theme` writes apps/backend/app/mcp/render/assets/* from
 * designTokens.ts; these tests fail when either side changes without the other.
 */
import { describe, expect, it } from 'bun:test'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildWidgetThemeCss, colorRamps } from '../designTokens'

const here = dirname(fileURLToPath(import.meta.url))
const assetsDir = resolve(here, '../../../../backend/app/mcp/render/assets')

describe('generated MCP theme assets', () => {
  it('widget-theme.css matches buildWidgetThemeCss()', () => {
    const css = buildWidgetThemeCss()
    const expected = css.endsWith('\n') ? css : `${css}\n`
    const generated = readFileSync(resolve(assetsDir, 'widget-theme.css'), 'utf8')
    expect(generated).toBe(expected)
  })

  it('widget-theme.json carries the full ramp table', () => {
    const payload = JSON.parse(readFileSync(resolve(assetsDir, 'widget-theme.json'), 'utf8')) as {
      version: number
      tokens: { light: Record<string, string>; dark: Record<string, string> }
      ramps: Record<string, Record<string, string>>
    }
    expect(payload.version).toBe(1)
    expect(payload.ramps).toEqual(colorRamps)
    expect(payload.tokens.light['--color-text-primary']).toBe('#1a1918')
    expect(payload.tokens.dark['--color-text-primary']).toBe('#e8e6df')
    expect(payload.tokens.light['--p']).toBe('var(--color-text-primary)')
  })
})
