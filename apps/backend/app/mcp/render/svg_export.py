"""Python port of the frontend SVG export contract.

Mirrors `apps/frontend/src/lib/svgExport.ts` (`buildExportableSvg`): starts from
the authored `widget_code`, inlines `buildWidgetThemeCss()`, pins the theme with
a class on the SVG root, and guarantees an XML namespace + declaration so the
file is valid standalone SVG.
"""

from __future__ import annotations

import re

from app.mcp.render.theme import ThemeMode, widget_theme_css

_SVG_OPEN_PATTERN = re.compile(r"<svg\b", re.IGNORECASE)
_SVG_TAG_PATTERN = re.compile(r"<svg\b([^>]*)>", re.IGNORECASE)
_CLASS_ATTR_PATTERN = re.compile(r"(<svg\b[^>]*\sclass\s*=\s*)(['\"])(.*?)\2", re.IGNORECASE)
_XMLNS_PATTERN = re.compile(r"\sxmlns\s*=\s*['\"]http://www\.w3\.org/2000/svg['\"]", re.IGNORECASE)


def _xml_escape_text(value: str) -> str:
    # Standalone SVG files are parsed as XML, where <style> content is plain
    # character data: raw & / < would be a parse error.
    return value.replace("&", "&amp;").replace("<", "&lt;")


def _with_svg_namespace(svg_text: str) -> str:
    if _XMLNS_PATTERN.search(svg_text):
        return svg_text
    return _SVG_OPEN_PATTERN.sub('<svg xmlns="http://www.w3.org/2000/svg"', svg_text, count=1)


def _with_theme_class(svg_text: str, theme: ThemeMode) -> str:
    match = _CLASS_ATTR_PATTERN.search(svg_text)
    if match is None:
        return _SVG_OPEN_PATTERN.sub(f'<svg class="{theme}"', svg_text, count=1)
    classes = [name for name in match.group(3).split() if name]
    if theme not in classes:
        classes.append(theme)
    replacement = f"{match.group(1)}{match.group(2)}{' '.join(classes)}{match.group(2)}"
    return svg_text[: match.start()] + replacement + svg_text[match.end() :]


def build_exportable_svg(widget_code: str, theme: ThemeMode) -> str | None:
    """Return a standalone themed SVG document, or None when the code is not raw SVG."""
    svg_text = widget_code.strip()
    if not _SVG_OPEN_PATTERN.match(svg_text):
        return None

    style_tag = f"<style>{_xml_escape_text(widget_theme_css())}</style>"
    output = _SVG_TAG_PATTERN.sub(lambda match: f"<svg{match.group(1)}>{style_tag}", svg_text, count=1)
    output = _with_theme_class(output, theme)
    output = _with_svg_namespace(output)

    if not output.startswith("<?xml"):
        output = f'<?xml version="1.0" encoding="UTF-8"?>\n{output}'
    return output
