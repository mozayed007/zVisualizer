/**
 * svgExport - builds a standalone, downloadable SVG document from a widget's
 * authored `widget_code`.
 *
 * Sandboxed widget iframes (no `allow-same-origin`) have an opaque origin, so
 * the host cannot read `iframe.contentDocument`. The export therefore starts
 * from the authored code plus the full theme stylesheet, and pins the current
 * theme with a class on the SVG root - `:root` matches the SVG root element in
 * a standalone SVG document, so `:root.dark` / `:root.light` resolve correctly
 * in both browsers and image contexts.
 *
 * A bun test (`__tests__/svgExport.test.ts`) guards the output contract.
 */
import { buildWidgetThemeCss } from './designTokens'

function withSvgNamespace(svgText: string): string {
  if (/\sxmlns\s*=\s*['"]http:\/\/www\.w3\.org\/2000\/svg['"]/i.test(svgText)) {
    return svgText
  }
  return svgText.replace(/<svg\b/i, '<svg xmlns="http://www.w3.org/2000/svg"')
}

function withThemeClass(svgText: string, theme: 'light' | 'dark'): string {
  const classPattern = /(<svg\b[^>]*\sclass\s*=\s*)(['"])(.*?)\2/i
  const match = svgText.match(classPattern)
  if (!match) {
    return svgText.replace(/<svg\b/i, `<svg class="${theme}"`)
  }
  const classes = match[3].split(/\s+/).filter(Boolean)
  if (!classes.includes(theme)) {
    classes.push(theme)
  }
  return svgText.replace(classPattern, `$1$2${classes.join(' ')}$2`)
}

function xmlEscapeText(value: string): string {
  // Standalone SVG files are parsed as XML, where `<style>` content is plain
  // character data: raw `&` / `<` would be a parse error.
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;')
}

export function buildExportableSvg(widgetCode: string, theme: 'light' | 'dark'): string | null {
  const svgText = widgetCode.trim()
  if (!/^<svg\b/i.test(svgText)) {
    return null
  }

  const styleTag = `<style>${xmlEscapeText(buildWidgetThemeCss())}</style>`
  let output = svgText.replace(/<svg\b([^>]*)>/i, `<svg$1>${styleTag}`)
  output = withThemeClass(output, theme)
  output = withSvgNamespace(output)

  if (!output.startsWith('<?xml')) {
    output = `<?xml version="1.0" encoding="UTF-8"?>\n${output}`
  }
  return output
}
