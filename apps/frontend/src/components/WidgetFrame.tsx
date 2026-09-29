/**
 * WidgetFrame — iframe host for visualizer-agent generated `widget_code`.
 *
 * This file implements a contract with the visualizer agent. Changing any of the
 * following surfaces without a coordinated update to the agent prompts and the
 * docs below will silently break generated widgets:
 *
 *   Sandbox attrs:   `allow-scripts allow-popups-to-escape-sandbox`
 *                    (deliberately NO `allow-same-origin` — parent origin stays isolated)
 *   CSP `csp` attr:  script-src from cdnjs / esm.sh / cdn.jsdelivr.net / unpkg.com,
 *                    style-src inline + fonts.googleapis.com, font-src fonts.gstatic.com
 *   Srcdoc order:    design-tokens <style> → bridge <script> → widget_code
 *   Bridge globals:  window.sendPrompt(text), window.openLink(url)
 *   Parent messages: { type: 'prompt' | 'iframe_resize' | 'open_link' | 'widget_error',
 *                      widgetTitle, ... }
 *   Iframe layout:   width 100%, display block, min-height 80 (flash guard per docs)
 *
 * Canonical references:
 *   - docs/frontend-widget-integration.md  §4 (WidgetFrame / srcdoc assembly)
 *                                          §5 (injected CSS contract)
 *   - docs/visualizer_skill/design-system.md
 *   - docs/backend-widget-endpoint.md      (SSE event + tool schema)
 *
 * If you need to change any contract surface, update the agent prompts in
 * apps/backend/app/agent/prompt.py and the four docs above in the same PR.
 */
import { AlertTriangle, Download } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { useTheme } from '@/hooks/useTheme'
import { buildWidgetThemeCss } from '@/lib/designTokens'
import { cn } from '@/lib/utils'
import { buildBridgeScript } from '@/lib/widgetBridge'
import type { WidgetPayload } from '@/types'

interface WidgetFrameProps {
  widget: WidgetPayload
  onPrompt: (text: string) => void
}

function isSvgMarkup(code: string): boolean {
  return code.trimStart().toLowerCase().startsWith('<svg')
}

const SVG_COMPUTED_STYLE_PROPERTIES = [
  'fill',
  'fill-opacity',
  'stroke',
  'stroke-width',
  'stroke-opacity',
  'stroke-linecap',
  'stroke-linejoin',
  'stroke-miterlimit',
  'stroke-dasharray',
  'stroke-dashoffset',
  'opacity',
  'font-family',
  'font-size',
  'font-style',
  'font-weight',
  'letter-spacing',
  'word-spacing',
  'text-anchor',
  'dominant-baseline',
  'vector-effect',
  'paint-order',
  'shape-rendering',
  'text-rendering',
  'visibility',
  'display',
] as const

const SVG_PRESENTATION_ATTRIBUTES: ReadonlyArray<readonly [string, string]> = [
  ['fill', 'fill'],
  ['fill-opacity', 'fill-opacity'],
  ['stroke', 'stroke'],
  ['stroke-width', 'stroke-width'],
  ['stroke-opacity', 'stroke-opacity'],
  ['stroke-linecap', 'stroke-linecap'],
  ['stroke-linejoin', 'stroke-linejoin'],
  ['stroke-miterlimit', 'stroke-miterlimit'],
  ['stroke-dasharray', 'stroke-dasharray'],
  ['stroke-dashoffset', 'stroke-dashoffset'],
  ['opacity', 'opacity'],
  ['font-family', 'font-family'],
  ['font-size', 'font-size'],
  ['font-style', 'font-style'],
  ['font-weight', 'font-weight'],
  ['letter-spacing', 'letter-spacing'],
  ['word-spacing', 'word-spacing'],
  ['text-anchor', 'text-anchor'],
  ['dominant-baseline', 'dominant-baseline'],
  ['vector-effect', 'vector-effect'],
  ['paint-order', 'paint-order'],
  ['shape-rendering', 'shape-rendering'],
  ['text-rendering', 'text-rendering'],
]

function withSvgNamespace(svgText: string): string {
  if (/\sxmlns\s*=\s*['"]http:\/\/www\.w3\.org\/2000\/svg['"]/i.test(svgText)) {
    return svgText
  }
  return svgText.replace(/<svg\b/i, '<svg xmlns="http://www.w3.org/2000/svg"')
}

function resolveCssVarReferences(value: string, computedStyle: CSSStyleDeclaration): string {
  let resolved = value

  for (let i = 0; i < 8 && /var\(/.test(resolved); i += 1) {
    resolved = resolved.replace(/var\(\s*(--[a-z0-9_-]+)\s*(?:,\s*([^)]+))?\)/gi, (_, varName, fallback) => {
      const customValue = computedStyle.getPropertyValue(varName).trim()
      if (customValue) {
        return customValue
      }
      return typeof fallback === 'string' ? fallback.trim() : ''
    })
  }

  return resolved.trim()
}

function inlineComputedStylesForPortableSvg(
  originalSvg: SVGSVGElement,
  clonedSvg: SVGSVGElement,
  win: Window,
): void {
  const originalElements = [originalSvg, ...Array.from(originalSvg.querySelectorAll<SVGElement>('*'))]
  const clonedElements = [clonedSvg, ...Array.from(clonedSvg.querySelectorAll<SVGElement>('*'))]
  const size = Math.min(originalElements.length, clonedElements.length)

  for (let i = 0; i < size; i += 1) {
    const sourceNode = originalElements[i]
    const targetNode = clonedElements[i]
    const computedStyle = win.getComputedStyle(sourceNode)

    const computedDeclarations: string[] = []
    for (const property of SVG_COMPUTED_STYLE_PROPERTIES) {
      const value = computedStyle.getPropertyValue(property).trim()
      if (!value) {
        continue
      }
      const resolvedValue = resolveCssVarReferences(value, computedStyle)
      if (!resolvedValue) {
        continue
      }
      computedDeclarations.push(`${property}:${resolvedValue}`)
    }

    if (computedDeclarations.length > 0) {
      const existingStyle = targetNode.getAttribute('style')?.trim() ?? ''
      const stylePrefix = existingStyle ? `${existingStyle}${existingStyle.endsWith(';') ? '' : ';'}` : ''
      targetNode.setAttribute('style', `${stylePrefix}${computedDeclarations.join(';')};`)
    }

    for (const [cssProperty, attributeName] of SVG_PRESENTATION_ATTRIBUTES) {
      const value = computedStyle.getPropertyValue(cssProperty).trim()
      if (!value) {
        continue
      }
      const resolvedValue = resolveCssVarReferences(value, computedStyle)
      if (!resolvedValue) {
        continue
      }
      targetNode.setAttribute(attributeName, resolvedValue)
    }
  }
}

function extractMarkerIdFromUrl(markerReference: string): string | null {
  const match = markerReference.trim().match(/^url\(\s*['"]?#([^)\s'"]+)['"]?\s*\)$/i)
  return match?.[1] ?? null
}

function getElementPaintColor(element: SVGElement, attributeName: 'fill' | 'stroke'): string | null {
  const attributeValue = element.getAttribute(attributeName)?.trim() ?? ''
  if (
    attributeValue &&
    !/^context-(?:stroke|fill)$/i.test(attributeValue) &&
    !/\bvar\(/i.test(attributeValue)
  ) {
    return attributeValue
  }

  const inlineStyleValue = element.style.getPropertyValue(attributeName).trim()
  if (
    inlineStyleValue &&
    !/^context-(?:stroke|fill)$/i.test(inlineStyleValue) &&
    !/\bvar\(/i.test(inlineStyleValue)
  ) {
    return inlineStyleValue
  }

  return null
}

function resolveMarkerContextPaint(clonedSvg: SVGSVGElement): void {
  const markerColors = new Map<string, { stroke: string | null; fill: string | null }>()
  const referencingElements = clonedSvg.querySelectorAll<SVGElement>('[marker-start],[marker-mid],[marker-end]')

  for (const element of referencingElements) {
    const strokeColor = getElementPaintColor(element, 'stroke')
    const fillColor = getElementPaintColor(element, 'fill')
    const markerReferences = [
      element.getAttribute('marker-start'),
      element.getAttribute('marker-mid'),
      element.getAttribute('marker-end'),
    ]

    for (const markerReference of markerReferences) {
      if (!markerReference) {
        continue
      }
      const markerId = extractMarkerIdFromUrl(markerReference)
      if (!markerId || markerColors.has(markerId)) {
        continue
      }
      markerColors.set(markerId, { stroke: strokeColor, fill: fillColor })
    }
  }

  if (markerColors.size === 0) {
    return
  }

  const markers = clonedSvg.querySelectorAll<SVGMarkerElement>('marker[id]')
  for (const marker of markers) {
    const markerId = marker.getAttribute('id')
    if (!markerId) {
      continue
    }
    const markerColor = markerColors.get(markerId)
    if (!markerColor) {
      continue
    }

    const markerNodes = [marker, ...Array.from(marker.querySelectorAll<SVGElement>('*'))]
    for (const node of markerNodes) {
      const fillValue = node.getAttribute('fill')
      if (fillValue && /context-fill|context-stroke/i.test(fillValue)) {
        const resolvedFill = fillValue
          .replace(/context-stroke/gi, markerColor.stroke ?? 'none')
          .replace(/context-fill/gi, markerColor.fill ?? 'none')
        node.setAttribute('fill', resolvedFill)
      }

      const strokeValue = node.getAttribute('stroke')
      if (strokeValue && /context-fill|context-stroke/i.test(strokeValue)) {
        const resolvedStroke = strokeValue
          .replace(/context-stroke/gi, markerColor.stroke ?? 'none')
          .replace(/context-fill/gi, markerColor.fill ?? 'none')
        node.setAttribute('stroke', resolvedStroke)
      }

      const styleValue = node.getAttribute('style')
      if (styleValue && /context-fill|context-stroke/i.test(styleValue)) {
        const resolvedStyle = styleValue
          .replace(/context-stroke/gi, markerColor.stroke ?? 'none')
          .replace(/context-fill/gi, markerColor.fill ?? 'none')
        node.setAttribute('style', resolvedStyle)
      }
    }
  }
}

function serializePortableRenderedSvg(renderedSvg: SVGSVGElement): string {
  const ownerWindow = renderedSvg.ownerDocument.defaultView
  if (!ownerWindow) {
    return new XMLSerializer().serializeToString(renderedSvg)
  }

  const portableClone = renderedSvg.cloneNode(true) as SVGSVGElement
  inlineComputedStylesForPortableSvg(renderedSvg, portableClone, ownerWindow)
  resolveMarkerContextPaint(portableClone)

  if (!portableClone.getAttribute('xmlns')) {
    portableClone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  }
  if (!portableClone.getAttribute('xmlns:xlink')) {
    portableClone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')
  }

  return new XMLSerializer().serializeToString(portableClone)
}

function buildFallbackResolvedStyleBlock(doc: Document | null): string {
  const rootStyle = doc ? doc.defaultView?.getComputedStyle(doc.documentElement) : null
  const readToken = (tokenName: string, fallback: string) => {
    const value = rootStyle?.getPropertyValue(tokenName).trim()
    return value || fallback
  }

  return [
    ':root{',
    `--color-background-primary:${readToken('--color-background-primary', '#ffffff')};`,
    `--color-background-secondary:${readToken('--color-background-secondary', '#f4f2eb')};`,
    `--color-text-primary:${readToken('--color-text-primary', '#1a1918')};`,
    `--color-text-secondary:${readToken('--color-text-secondary', '#5a5855')};`,
    `--color-border-secondary:${readToken('--color-border-secondary', 'rgba(0, 0, 0, 0.14)')};`,
    `--font-sans:${readToken('--font-sans', "'Plus Jakarta Sans', system-ui, sans-serif")};`,
    `--p:${readToken('--p', readToken('--color-text-primary', '#1a1918'))};`,
    `--s:${readToken('--s', readToken('--color-text-secondary', '#5a5855'))};`,
    `--t:${readToken('--t', readToken('--color-text-secondary', '#5a5855'))};`,
    `--bg2:${readToken('--bg2', readToken('--color-background-secondary', '#f4f2eb'))};`,
    `--b:${readToken('--b', readToken('--color-border-secondary', 'rgba(0, 0, 0, 0.14)'))};`,
    '}',
    '.box{fill:var(--color-background-secondary);stroke:var(--color-border-secondary);stroke-width:0.5;rx:12}',
    '.th,.t,.ts{dominant-baseline:central;font-family:var(--font-sans)}',
    '.th{font-size:14px;font-weight:500;fill:var(--color-text-primary)}',
    '.t{font-size:14px;font-weight:400;fill:var(--color-text-primary)}',
    '.ts{font-size:12px;font-weight:400;fill:var(--color-text-secondary)}',
    '.arr{fill:none;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round;stroke:var(--color-border-secondary)}',
  ].join('')
}

function injectFallbackResolvedStyleBlock(svgText: string, doc: Document | null): string {
  const styleBlock = buildFallbackResolvedStyleBlock(doc)
  const styleTag = `<style>${styleBlock}</style>`
  if (/<svg\b[^>]*>/i.test(svgText)) {
    return svgText.replace(/<svg\b([^>]*)>/i, `<svg$1>${styleTag}`)
  }
  return svgText
}

function toSafeSvgFilename(title: string): string {
  const normalized = title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return `${normalized || 'visual'}.svg`
}

function formatWidgetTitle(title: string): string {
  return title.replace(/_/g, ' ')
}

function syncIframeDesignTokens(iframe: HTMLIFrameElement | null, theme?: 'light' | 'dark') {
  const doc = iframe?.contentDocument
  if (!doc) {
    return
  }

  if (theme) {
    doc.documentElement.classList.toggle('dark', theme === 'dark')
    doc.documentElement.classList.toggle('light', theme === 'light')
  }

  let tokenStyle = doc.querySelector<HTMLStyleElement>('#design-tokens')
  if (!tokenStyle) {
    tokenStyle = doc.createElement('style')
    tokenStyle.id = 'design-tokens'
    ;(doc.head ?? doc.documentElement).appendChild(tokenStyle)
  }
  tokenStyle.textContent = buildWidgetThemeCss()
}

function WidgetFrameInner({ widget, onPrompt }: WidgetFrameProps) {
  const { theme } = useTheme()
  const [height, setHeight] = useState(180)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [isDownloadingSvg, setIsDownloadingSvg] = useState(false)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)

  const displayTitle = formatWidgetTitle(widget.title)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onSchemeChange = () => syncIframeDesignTokens(iframeRef.current, theme)
    mq.addEventListener('change', onSchemeChange)
    return () => mq.removeEventListener('change', onSchemeChange)
  }, [theme])

  useEffect(() => {
    syncIframeDesignTokens(iframeRef.current, theme)
  }, [theme])

  const srcDoc = useMemo(() => {
    return [
      '<!doctype html><html><head><meta charset="utf-8" />',
      '<meta name="viewport" content="width=device-width, initial-scale=1" />',
      '<style>html,body{margin:0;padding:0;background:transparent;overflow-x:hidden;}body{min-height:96px;}</style>',
      `<style id="design-tokens">${buildWidgetThemeCss()}</style>`,
      buildBridgeScript(widget.title),
      `</head><body>${widget.widget_code}</body></html>`,
    ].join('')
  }, [widget])

  useEffect(() => {
    iframeRef.current?.setAttribute(
      'csp',
      "script-src 'unsafe-inline' https://cdnjs.cloudflare.com https://esm.sh https://cdn.jsdelivr.net https://unpkg.com; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com data:; img-src * data: blob:; media-src * data: blob:; connect-src *; worker-src blob: data:;",
    )
  }, [])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const eventWidgetTitle =
        typeof event.data?.widgetTitle === 'string' ? event.data.widgetTitle : null
      
      // Strict check: if the message doesn't have the matching title, ignore it.
      // This is safe because our bridge script injects the title.
      if (eventWidgetTitle !== widget.title) {
        return
      }

      if (event.data?.type === 'iframe_resize' && typeof event.data.h === 'number') {
        const h = event.data.h + 8
        if (h > 40) {
          setHeight(Math.max(96, h))
        }
      }

      if (event.data?.type === 'prompt') {
        const promptText =
          typeof event.data.text === 'string'
            ? event.data.text
            : typeof event.data.value === 'string'
              ? event.data.value
              : null
        if (promptText) {
          onPrompt(promptText)
        }
      }

      if (event.data?.type === 'open_link' && typeof event.data.url === 'string') {
        let safeUrl: URL
        try {
          safeUrl = new URL(event.data.url, window.location.href)
        } catch {
          setRuntimeError('Invalid URL emitted by widget.')
          return
        }
        if (safeUrl.protocol !== 'https:') {
          return
        }
        const shouldOpen = window.confirm(`Open this link in a new tab?\n\n${safeUrl.toString()}`)
        if (shouldOpen) {
          window.open(safeUrl.toString(), '_blank', 'noopener,noreferrer')
        }
      }

      if (event.data?.type === 'widget_error') {
        const message =
          typeof event.data?.error === 'string' ? event.data.error.trim() : 'Unknown widget runtime error.'
        if (/^script error\.?$/i.test(message)) {
          return
        }
        setRuntimeError(message || 'Unknown widget runtime error.')
      }
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [onPrompt, widget.title])

  const canDownloadSvg = widget.kind === 'svg'

  const handleDownloadSvg = () => {
    setIsDownloadingSvg(true)
    try {
      const iframeDoc = iframeRef.current?.contentDocument ?? null
      const renderedSvg = iframeRef.current?.contentDocument?.querySelector<SVGSVGElement>('svg')
      const serializedRenderedSvg = renderedSvg
        ? serializePortableRenderedSvg(renderedSvg)
        : null
      const fallbackSvg = isSvgMarkup(widget.widget_code)
        ? injectFallbackResolvedStyleBlock(widget.widget_code.trim(), iframeDoc)
        : null
      const svgContent = serializedRenderedSvg ?? fallbackSvg

      if (!svgContent) {
        setRuntimeError('Unable to export SVG from this visual.')
        return
      }

      const namespacedSvg = withSvgNamespace(svgContent)
      const downloadableSvg = namespacedSvg.startsWith('<?xml')
        ? namespacedSvg
        : `<?xml version="1.0" encoding="UTF-8"?>\n${namespacedSvg}`
      const blob = new Blob([downloadableSvg], {
        type: 'image/svg+xml;charset=utf-8',
      })

      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = toSafeSvgFilename(widget.title)
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch {
      setRuntimeError('Unable to export SVG from this visual.')
    } finally {
      setIsDownloadingSvg(false)
    }
  }

  return (
    <div className={cn('flex flex-col')}>
      <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-muted/30 px-3 py-2">
        <div className="min-w-0 truncate text-xs font-medium text-muted-foreground">
          {displayTitle}
        </div>
        {canDownloadSvg ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={handleDownloadSvg}
            disabled={isDownloadingSvg}
            aria-label={`Download ${displayTitle} as SVG`}
          >
            <Download className="size-3.5" />
            {isDownloadingSvg ? 'Preparing…' : 'Download SVG'}
          </Button>
        ) : null}
      </div>
      {runtimeError ? (
        <div
          className="flex items-start gap-2 border-b border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-foreground"
          role="status"
          aria-live="polite"
        >
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
          <span>This visual hit a runtime issue: {runtimeError}</span>
        </div>
      ) : null}
      <iframe
        ref={iframeRef}
        className="block w-full border-0 bg-transparent min-h-[80px]"
        data-widget={widget.title}
        title={displayTitle}
        aria-label={`Interactive visual: ${displayTitle}`}
        sandbox="allow-scripts allow-popups-to-escape-sandbox"
        srcDoc={srcDoc}
        style={{ height, transition: 'height 0.15s ease' }}
        onLoad={() => {
          syncIframeDesignTokens(iframeRef.current, theme)
          setRuntimeError(null)
        }}
        tabIndex={0}
      />
    </div>
  )
}

export function WidgetFrame({ widget, onPrompt }: WidgetFrameProps) {
  return (
    <WidgetFrameInner
      key={`${widget.title}:${widget.widget_code.length}`}
      widget={widget}
      onPrompt={onPrompt}
    />
  )
}
