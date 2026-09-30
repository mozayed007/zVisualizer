"""Tests for the Python port of the frontend SVG export contract."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.mcp.render.svg_export import build_exportable_svg

SVG = (
    '<svg width="100%" viewBox="0 0 680 200">'
    '<defs><marker id="arrow"></marker></defs>'
    '<rect class="box" x="10" y="10" width="100" height="60"/>'
    "</svg>"
)


def test_exportable_svg_inlines_theme_stylesheet() -> None:
    exported = build_exportable_svg(SVG, "light")
    assert exported is not None
    assert '<svg xmlns="http://www.w3.org/2000/svg" class="light" width="100%" viewBox="0 0 680 200">' in exported
    # Style element sits directly after the opening tag and XML-escapes the
    # Google Fonts import query (`&amp;family=`), because standalone SVG is XML.
    assert "<style>\n  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans" in exported
    assert "&amp;family=JetBrains+Mono" in exported


def test_exportable_svg_keeps_existing_root_classes() -> None:
    with_class = SVG.replace("<svg ", '<svg class="widget " ')
    exported = build_exportable_svg(with_class, "dark")
    assert exported is not None
    assert 'class="widget dark"' in exported


def test_exportable_svg_does_not_duplicate_pinned_theme_class() -> None:
    with_class = SVG.replace("<svg ", '<svg class="widget light" ')
    exported = build_exportable_svg(with_class, "light")
    assert exported is not None
    assert 'class="widget light"' in exported
    assert "light light" not in exported


def test_exportable_svg_is_well_formed_xml_document() -> None:
    exported = build_exportable_svg(SVG, "light")
    assert exported is not None
    assert exported.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(exported)
    assert root.tag.endswith("svg")


def test_exportable_svg_returns_none_for_html_fragments() -> None:
    assert build_exportable_svg("<style>.x{}</style><div></div>", "light") is None
