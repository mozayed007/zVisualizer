"""Class/var() flattening for SVG rasterizers.

External rasterizers (librsvg, ImageMagick's SVG delegate, Inkscape CLI) have
weak or absent CSS custom property support, so a themed widget SVG can rasterize
with wrong colors. This module rewrites the *closed* widget class contract
(ramp classes, .box / .t / .ts / .th / .arr / .leader, var() references) into
literal presentation attributes for a chosen theme mode.

It intentionally covers only the documented contract; anything outside it is
left untouched. Callers should treat `FlattenResult.unresolved` as "do not trust
the flattened output" and fall back to a browser renderer.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from app.mcp.render.theme import ThemeMode, WidgetTheme, widget_theme

SVG_NAMESPACE = "http://www.w3.org/2000/svg"

_RAMP_CLASS_PATTERN = re.compile(r"^c-([a-z]+)$")
_TEXT_CLASSES = {"t", "ts", "th"}
_SHAPE_TAGS = {"rect", "circle", "ellipse"}

# Values from the theme stylesheet utilities (designTokens.ts) that the
# contract relies on. Colors are resolved through the theme token tables.
_UTILITY_RULES: dict[str, dict[str, str]] = {
    "box": {
        "fill": "var(--color-background-secondary)",
        "stroke": "var(--color-border-secondary)",
        "stroke-width": "0.5",
        "rx": "12",
    },
    "t": {
        "fill": "var(--color-text-primary)",
        "font-size": "14px",
        "font-weight": "400",
    },
    "th": {
        "fill": "var(--color-text-primary)",
        "font-size": "14px",
        "font-weight": "500",
    },
    "ts": {
        "fill": "var(--color-text-secondary)",
        "font-size": "12px",
        "font-weight": "400",
    },
    "arr": {
        "stroke": "var(--color-border-secondary)",
        "stroke-width": "1.5",
        "fill": "none",
    },
    "leader": {
        "stroke": "var(--color-border-tertiary)",
        "stroke-width": "0.5",
        "stroke-dasharray": "3 3",
        "fill": "none",
    },
}

_PRESENTATION_KEYS = (
    "fill",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "font-size",
    "font-weight",
    "font-family",
    "rx",
)


@dataclass(frozen=True, slots=True)
class FlattenResult:
    svg: str
    warnings: list[str] = field(default_factory=list)
    unresolved: bool = False


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_style_attribute(value: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for part in value.split(";"):
        if ":" not in part:
            continue
        name, _, raw = part.partition(":")
        name = name.strip().lower()
        if name:
            declarations[name] = raw.strip()
    return declarations


def _resolve_theme_value(
    theme: WidgetTheme,
    mode: ThemeMode,
    value: str | None,
) -> tuple[str | None, bool]:
    """Resolve var() references; returns (value, unresolved_flag)."""
    if value is None or "var(" not in value:
        return value, False
    resolved = theme.resolve(value, mode)
    if resolved is not None and theme.has_unresolved_var(resolved):
        return resolved, True
    return resolved, False


def _match_ramp(classes: list[str]) -> str | None:
    for name in classes:
        match = _RAMP_CLASS_PATTERN.match(name)
        if match and match.group(1) in widget_theme().ramp_names():
            return match.group(1)
    return None


def _rule_values_for_element(
    *,
    theme: WidgetTheme,
    mode: ThemeMode,
    local_tag: str,
    classes: list[str],
    own_ramp: str | None,
    ancestor_ramp: str | None,
) -> tuple[dict[str, str], list[str]]:
    """Compute class/ramp rule values for one element."""
    warnings: list[str] = []
    values: dict[str, str] = {}
    ramp = own_ramp or ancestor_ramp

    for utility in classes:
        rule = _UTILITY_RULES.get(utility)
        if rule is None:
            continue
        for key, raw in rule.items():
            resolved, unresolved = _resolve_theme_value(theme, mode, raw)
            if resolved is not None:
                values[key] = resolved
            if unresolved:
                warnings.append(f"Unresolved token in utility rule '{utility}' ({key}): {raw}")

    if ramp is not None:
        colors = theme.ramp(ramp, mode, variant="class")
        if "box" in classes:
            values["fill"] = colors.fill
            values["stroke"] = colors.stroke
        if _TEXT_CLASSES.intersection(classes):
            values["fill"] = colors.subtitle if "ts" in classes else colors.title
        if "arr" in classes:
            values["stroke"] = colors.stroke
        if local_tag in _SHAPE_TAGS and "box" not in classes and "arr" not in classes:
            # Direct-child ramp rule (`.c-X>rect`): stroke keeps ramp[600] in
            # both modes, unlike the class-based `.c-X .box` variant.
            direct = theme.ramp(ramp, mode, variant="direct")
            values["fill"] = direct.fill
            values["stroke"] = direct.stroke

    return values, warnings


def flatten_svg(svg_markup: str, mode: ThemeMode, theme: WidgetTheme | None = None) -> FlattenResult | None:
    """Flatten a widget SVG for rasterization.

    Returns None when the markup cannot be parsed as XML (caller should skip the
    rasterizer fallback rather than render unthemed output).
    """
    active_theme = theme or widget_theme()
    warnings: list[str] = []
    unresolved = False

    try:
        root = ET.fromstring(svg_markup.strip())
    except ET.ParseError:
        return None

    root_local = _local_name(root.tag)
    if root_local != "svg":
        return None

    def walk(
        element: ET.Element,
        *,
        inherited_ramp: str | None,
    ) -> None:
        nonlocal unresolved

        classes = [name for name in (element.get("class") or "").split() if name]
        own_ramp = _match_ramp(classes)
        local_tag = _local_name(element.tag)

        rule_values, rule_warnings = _rule_values_for_element(
            theme=active_theme,
            mode=mode,
            local_tag=local_tag,
            classes=classes,
            own_ramp=own_ramp,
            ancestor_ramp=inherited_ramp,
        )
        warnings.extend(rule_warnings)

        style_declarations = _parse_style_attribute(element.get("style") or "")
        for key in list(style_declarations):
            resolved, style_unresolved = _resolve_theme_value(active_theme, mode, style_declarations[key])
            if resolved is not None:
                style_declarations[key] = resolved
            if style_unresolved:
                unresolved = True
                warnings.append(f"Unresolved token in style attribute ({key})")

        attr_values: dict[str, str] = {}
        for key in _PRESENTATION_KEYS:
            raw = element.get(key)
            if raw is None:
                continue
            resolved, attr_unresolved = _resolve_theme_value(active_theme, mode, raw)
            if resolved is not None:
                attr_values[key] = resolved
            if attr_unresolved:
                unresolved = True
                warnings.append(f"Unresolved token in {key} attribute: {raw}")

        # CSS specificity order: class rules beat presentation attributes, inline
        # style beats both.
        final_values: dict[str, str] = {}
        for key in _PRESENTATION_KEYS:
            if key in attr_values:
                final_values[key] = attr_values[key]
            if key in rule_values:
                final_values[key] = rule_values[key]
            if key in style_declarations:
                final_values[key] = style_declarations[key]

        if local_tag == "text" and "font-family" not in final_values:
            font_family, font_unresolved = _resolve_theme_value(active_theme, mode, "var(--font-sans)")
            if font_family is not None:
                final_values["font-family"] = font_family
            if font_unresolved:
                unresolved = True
                warnings.append("Unresolved token in font-family fallback")

        for key, value in final_values.items():
            element.set(key, value)

        if style_declarations:
            rebuilt = "; ".join(f"{key}: {value}" for key, value in style_declarations.items() if value)
            if rebuilt:
                element.set("style", rebuilt)

        effective_ramp = own_ramp or inherited_ramp
        for child in element:
            walk(child, inherited_ramp=effective_ramp)

    walk(root, inherited_ramp=None)

    # Serialize without clobbering the SVG namespace prefix.
    if _local_name(root.tag) == root.tag and ":" not in root.tag:
        ET.register_namespace("", SVG_NAMESPACE)
    serialized = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    if "xmlns" not in serialized.split(">", 1)[0]:
        serialized = re.sub(r"^<svg\b", f'<svg xmlns="{SVG_NAMESPACE}"', serialized, count=1, flags=re.IGNORECASE)

    if unresolved:
        warnings.append("Some var() tokens could not be resolved for rasterization.")

    return FlattenResult(svg=serialized, warnings=warnings, unresolved=unresolved)


def with_explicit_pixel_size(
    svg_markup: str,
    *,
    width_px: int,
    height_px: int,
    scale: float,
) -> str:
    """Set width/height attributes so rasterizers render at the requested size."""

    def _attrs(match: re.Match[str]) -> str:
        attrs = match.group(1)
        attrs = re.sub(r"\s(width|height)\s*=\s*['\"][^'\"]*['\"]", "", attrs, flags=re.IGNORECASE)
        target_w = max(1, round(width_px * scale))
        target_h = max(1, round(height_px * scale))
        return f'<svg{attrs} width="{target_w}" height="{target_h}">'

    return re.sub(r"<svg\b([^>]*)>", _attrs, svg_markup, count=1, flags=re.IGNORECASE)


def is_svg_root(widget_code: str) -> bool:
    return re.match(r"^\s*<svg\b", widget_code, flags=re.IGNORECASE) is not None


__all__: list[str] = [
    "FlattenResult",
    "SVG_NAMESPACE",
    "flatten_svg",
    "is_svg_root",
    "with_explicit_pixel_size",
]
