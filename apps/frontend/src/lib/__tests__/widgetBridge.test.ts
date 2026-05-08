import { describe, expect, it } from 'bun:test'

import { buildBridgeScript } from '../widgetBridge'

/**
 * Bridge-script contract guard. Generated `widget_code` assumes these globals
 * and postMessage types exist on the iframe window — rename any of them and
 * every existing widget breaks silently.
 *
 * Canonical reference: docs/frontend-widget-integration.md §4.
 */

const script = buildBridgeScript('demo_widget_title')

describe('buildBridgeScript — required globals', () => {
  it('defines window.sendPrompt', () => {
    expect(script).toMatch(/window\.sendPrompt\s*=\s*function/)
  })
  it('defines window.openLink', () => {
    expect(script).toMatch(/window\.openLink\s*=\s*function/)
  })
})

describe('buildBridgeScript — postMessage types', () => {
  it("emits type: 'prompt' on sendPrompt", () => {
    expect(script).toMatch(/type:\s*'prompt'/)
  })
  it("emits type: 'open_link' on openLink", () => {
    expect(script).toMatch(/type:\s*'open_link'/)
  })
  it("emits type: 'iframe_resize' on resize", () => {
    expect(script).toMatch(/type:\s*'iframe_resize'/)
  })
  it("emits type: 'widget_error' on window error", () => {
    expect(script).toMatch(/type:\s*'widget_error'/)
  })
  it('every outgoing postMessage carries the widgetTitle back to the host', () => {
    const matches = script.match(/widgetTitle:\s*"demo_widget_title"/g) ?? []
    // Four message types × one widgetTitle each
    expect(matches.length).toBeGreaterThanOrEqual(4)
  })
})

describe('buildBridgeScript — resize wiring', () => {
  it('uses ResizeObserver when available', () => {
    expect(script).toMatch(/ResizeObserver/)
  })
  it('reports height on DOMContentLoaded + load', () => {
    expect(script).toMatch(/DOMContentLoaded/)
    expect(script).toMatch(/addEventListener\(\s*'load'/)
  })
  it('computes height from body + documentElement', () => {
    expect(script).toMatch(/document\.body/)
    expect(script).toMatch(/document\.documentElement/)
    expect(script).toMatch(/Math\.max/)
  })
})

describe('buildBridgeScript — output shape', () => {
  it('is wrapped in a <script> tag', () => {
    expect(script.startsWith('<script>')).toBe(true)
    expect(script.endsWith('</script>')).toBe(true)
  })
})
