/**
 * Widget iframe bridge script.
 *
 * Produces the <script> block that runs inside every visualizer-agent widget
 * iframe. It exposes the globals + postMessage types that generated
 * `widget_code` relies on. Contract: docs/frontend-widget-integration.md §4.
 *
 * DO NOT rename any of:
 *   - window.sendPrompt(text)
 *   - window.openLink(url)
 *   - postMessage types: 'prompt' | 'iframe_resize' | 'open_link' | 'widget_error'
 *
 * A bun test (`__tests__/widgetBridge.test.ts`) guards this contract.
 */
export function buildBridgeScript(title: string): string {
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
