"""Standalone HTML document assembly for widgets rendered outside the web app.

Mirrors the WidgetFrame srcdoc order (`apps/frontend/src/components/WidgetFrame.tsx`):
`<html class="{theme}">` -> design-tokens `<style>` -> bridge `<script>` -> widget_code.

The standalone bridge keeps the `window.sendPrompt` / `window.openLink` globals
that generated HTML widgets rely on, without a host chat to postMessage to.
"""

from __future__ import annotations

from html import escape as _html_escape

from app.mcp.render.theme import ThemeMode, widget_theme_css

STANDALONE_BRIDGE_SCRIPT = """<script>
(function () {
  window.sendPrompt = function (text) {
    try {
      window.dispatchEvent(
        new CustomEvent('visualizer:prompt', { detail: { text: String(text) } })
      );
    } catch (error) {}
    if (window.console && console.log) {
      console.log('visualizer sendPrompt:', text);
    }
  };
  window.openLink = function (url) {
    try {
      window.open(String(url), '_blank', 'noopener');
    } catch (error) {}
  };
})();
</script>"""

# The web app supplies the surface behind transparent widget bodies; standalone
# documents must paint it themselves or dark-mode artifacts render on white.
SURFACE_STYLE = "<style>html, body { background: var(--color-background-primary); }</style>"
PNG_SURFACE_RULES = "html,body{margin:0;padding:0;background:var(--color-background-primary);}"


def build_standalone_document(*, content: str, title: str, theme: ThemeMode) -> str:
    """Assemble a complete document around widget content (raw SVG or HTML fragment)."""
    safe_title = _html_escape(title, quote=True)
    return (
        "<!doctype html>\n"
        f'<html class="{theme}" lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{safe_title}</title>\n"
        f'<style id="design-tokens">{widget_theme_css()}</style>\n'
        f"{SURFACE_STYLE}\n"
        f"{STANDALONE_BRIDGE_SCRIPT}\n"
        "</head>\n"
        "<body>\n"
        f"{content}\n"
        "</body>\n"
        "</html>\n"
    )


def build_png_document(*, content: str, title: str, theme: ThemeMode) -> str:
    """Document used for screenshots: same assembly, no margins around the widget."""
    document = build_standalone_document(content=content, title=title, theme=theme)
    return document.replace(
        "</head>",
        f"<style>{PNG_SURFACE_RULES}</style>\n</head>",
        1,
    )
