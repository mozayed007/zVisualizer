import { useEffect, useMemo, useRef, useState } from 'react'

import { buildWidgetThemeCss } from '../lib/designTokens'
import type { WidgetPayload } from '../types'

interface WidgetFrameProps {
  widget: WidgetPayload
  onPrompt: (text: string) => void
}

function formatWidgetTitle(title: string): string {
  return title.replace(/_/g, ' ')
}

function buildBridgeScript(title: string): string {
  return `<script>
  window.sendPrompt = function(text) {
    parent.postMessage({ type: 'prompt', text: text, widgetTitle: ${JSON.stringify(title)} }, '*');
  };
  window.openLink = function(url) {
    parent.postMessage({ type: 'open_link', url: url, widgetTitle: ${JSON.stringify(title)} }, '*');
  };
  let resizeObserver = null;
  const notifyHeight = function() {
    var b = document.body ? document.body.scrollHeight : 0;
    var e = document.documentElement ? document.documentElement.scrollHeight : 0;
    var h = Math.max(b, e);
    parent.postMessage({ type: 'iframe_resize', h: h, widgetTitle: ${JSON.stringify(title)} }, '*');
  };
  const startResizeObserver = function() {
    const target = document.body || document.documentElement;
    if (!target || resizeObserver) {
      notifyHeight();
      return;
    }
    notifyHeight();
    if (typeof ResizeObserver !== 'function') {
      return;
    }
    resizeObserver = new ResizeObserver(function() {
      window.requestAnimationFrame(notifyHeight);
    });
    resizeObserver.observe(target);
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startResizeObserver, { once: true });
  } else {
    startResizeObserver();
  }
  window.addEventListener('load', startResizeObserver, { once: true });
  window.addEventListener('error', function(event) {
    parent.postMessage({ type: 'widget_error', error: String(event.message || event.error || 'Unknown widget error'), widgetTitle: ${JSON.stringify(title)} }, '*');
  });
  </scr` + `ipt>`
}

function syncIframeDesignTokens(iframe: HTMLIFrameElement | null) {
  const doc = iframe?.contentDocument
  if (!doc) {
    return
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
  const [height, setHeight] = useState(180)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)

  const displayTitle = formatWidgetTitle(widget.title)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onSchemeChange = () => syncIframeDesignTokens(iframeRef.current)
    mq.addEventListener('change', onSchemeChange)
    return () => mq.removeEventListener('change', onSchemeChange)
  }, [])

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
      const iframeWindow = iframeRef.current?.contentWindow
      if (event.source !== iframeWindow || event.data?.widgetTitle !== widget.title) {
        return
      }

      if (event.data?.type === 'iframe_resize' && typeof event.data.h === 'number') {
        const h = event.data.h + 8
        if (h > 40) {
          setHeight(Math.max(96, h))
        }
      }

      if (event.data?.type === 'prompt' && typeof event.data.text === 'string') {
        onPrompt(event.data.text)
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

  return (
    <>
      {runtimeError ? (
        <div className="widget-runtime-error" role="status" aria-live="polite">
          This visual hit a runtime issue: {runtimeError}
        </div>
      ) : null}
      <iframe
        ref={iframeRef}
        className="widget-frame"
        data-widget={widget.title}
        title={displayTitle}
        aria-label={`Interactive visual: ${displayTitle}`}
        sandbox="allow-scripts allow-popups-to-escape-sandbox"
        srcDoc={srcDoc}
        style={{ height, transition: 'height 0.15s ease', borderRadius: 10 }}
        onLoad={() => {
          syncIframeDesignTokens(iframeRef.current)
          setRuntimeError(null)
        }}
        tabIndex={0}
      />
    </>
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
