/**
 * WidgetFrame — iframe host for visualizer-agent generated `widget_code`.
 *
 * This file implements a contract with the visualizer agent. Changing any of the
 * following surfaces without a coordinated update to the agent prompts and the
 * docs below will silently break generated widgets:
 *
 *   Sandbox attrs:   `allow-scripts allow-popups-to-escape-sandbox`
 *                    (deliberately NO `allow-same-origin` — parent origin stays
 *                    isolated, and the frame therefore has an opaque origin:
 *                    the host must never touch `iframe.contentDocument` and must
 *                    coordinate with the frame over postMessage instead).
 *   CSP `csp` attr:  script-src from cdnjs / esm.sh / cdn.jsdelivr.net / unpkg.com,
 *                    style-src inline + fonts.googleapis.com, font-src fonts.gstatic.com
 *   Srcdoc order:    <html class="{theme}"> → design-tokens <style> → bridge <script> → widget_code
 *   Bridge globals:  window.sendPrompt(text), window.openLink(url)
 *   Parent messages: { type: 'prompt' | 'iframe_resize' | 'open_link' | 'widget_error',
 *                      widgetTitle, ... }
 *   Host messages:   { type: 'host_theme', theme: 'light' | 'dark' }
 *   Iframe layout:   width 100%, display block, min-height 80 (flash guard per docs)
 *
 * Canonical references:
 *   - docs/frontend-widget-integration.md  §4 (WidgetFrame / srcdoc assembly)
 *                                          §5 (injected CSS contract)
 *   - skills/visualizer/design-system.md
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
import { buildExportableSvg } from '@/lib/svgExport'
import { cn } from '@/lib/utils'
import { buildBridgeScript } from '@/lib/widgetBridge'
import type { WidgetPayload } from '@/types'

interface WidgetFrameProps {
  widget: WidgetPayload
  onPrompt: (text: string) => void
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

function postThemeToIframe(iframe: HTMLIFrameElement | null, theme: 'light' | 'dark') {
  // The sandboxed frame has an opaque origin, so this is a cross-origin
  // postMessage: '*' is required because a specific targetOrigin can never
  // match the frame's "null" origin.
  iframe?.contentWindow?.postMessage({ type: 'host_theme', theme }, '*')
}

function WidgetFrameInner({ widget, onPrompt }: WidgetFrameProps) {
  const { theme } = useTheme()
  // The srcdoc bakes the theme that applied when the frame was created; later
  // theme changes are delivered to the live frame via postThemeToIframe.
  const initialThemeRef = useRef(theme)
  const [height, setHeight] = useState(180)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [isDownloadingSvg, setIsDownloadingSvg] = useState(false)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)

  const displayTitle = formatWidgetTitle(widget.title)

  useEffect(() => {
    postThemeToIframe(iframeRef.current, theme)
  }, [theme])

  const srcDoc = useMemo(() => {
    return [
      `<!doctype html><html class="${initialThemeRef.current}"><head><meta charset="utf-8" />`,
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
      const iframeWindow = iframeRef.current?.contentWindow
      if (!iframeWindow || event.source !== iframeWindow) {
        return
      }

      const eventWidgetTitle =
        typeof event.data?.widgetTitle === 'string' ? event.data.widgetTitle : null
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
      const svgContent = buildExportableSvg(widget.widget_code, theme)
      if (!svgContent) {
        setRuntimeError('Unable to export SVG from this visual.')
        return
      }

      const blob = new Blob([svgContent], {
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
          postThemeToIframe(iframeRef.current, theme)
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
