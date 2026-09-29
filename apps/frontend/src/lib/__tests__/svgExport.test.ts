import { describe, expect, it } from 'bun:test'

import { buildExportableSvg } from '../svgExport'

/**
 * Export contract guard: sandboxed iframes cannot be read from the host, so the
 * exported SVG is built from the authored widget code plus the full theme
 * stylesheet with the active theme pinned via a class on the SVG root.
 */

const SVG = '<svg viewBox="0 0 100 100"><rect class="box"/></svg>'

describe('buildExportableSvg', () => {
  it('returns null for non-SVG widget code', () => {
    expect(buildExportableSvg('<div>hello</div>', 'dark')).toBeNull()
  })

  it('pins the requested theme class on the SVG root', () => {
    expect(buildExportableSvg(SVG, 'dark')).toMatch(/<svg\b[^>]*class="dark"/)
    expect(buildExportableSvg(SVG, 'light')).toMatch(/<svg\b[^>]*class="light"/)
  })

  it('merges the theme class with an existing class attribute', () => {
    const output = buildExportableSvg('<svg class="my-art" viewBox="0 0 1 1"></svg>', 'dark')
    expect(output).toContain('class="my-art dark"')
  })

  it('does not duplicate the theme class when already present', () => {
    const output = buildExportableSvg('<svg class="dark" viewBox="0 0 1 1"></svg>', 'dark')
    expect(output).toContain('class="dark"')
    expect(output).not.toContain('class="dark dark"')
  })

  it('inlines the full theme stylesheet including ramp rules', () => {
    const output = buildExportableSvg(SVG, 'dark') ?? ''
    expect(output).toContain('<style>')
    expect(output).toContain('.c-purple')
    expect(output).toContain(':root.dark')
  })

  it('escapes the stylesheet so the file parses as XML', () => {
    const output = buildExportableSvg(SVG, 'dark') ?? ''
    // The Google Fonts import contains raw `&` in the CSS; standalone SVG files
    // are XML, so it must be entity-escaped.
    expect(output).toContain('&amp;family=JetBrains')
    expect(output).not.toContain('&family=JetBrains')
  })

  it('adds the SVG namespace when missing and keeps an existing one', () => {
    const withoutNamespace = buildExportableSvg(SVG, 'dark') ?? ''
    expect(withoutNamespace).toContain('xmlns="http://www.w3.org/2000/svg"')

    const withNamespace =
      buildExportableSvg('<svg xmlns="http://www.w3.org/2000/svg"></svg>', 'dark') ?? ''
    const namespaceMatches = withNamespace.match(/xmlns="http:\/\/www\.w3\.org\/2000\/svg"/g) ?? []
    expect(namespaceMatches.length).toBe(1)
  })

  it('prefixes an XML declaration exactly once', () => {
    const output = buildExportableSvg(SVG, 'dark') ?? ''
    expect(output.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true)
    expect((output.match(/<\?xml/g) ?? []).length).toBe(1)
  })
})
