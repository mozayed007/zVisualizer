"""Tests for the rasterizer-facing SVG flattener."""

from __future__ import annotations

from app.mcp.render.svg_flatten import flatten_svg, with_explicit_pixel_size

RAMP_FIXTURE = (
    '<svg width="100%" viewBox="0 0 680 200">'
    '<g class="c-purple">'
    '<rect class="box" x="40" y="60" width="220" height="90"/>'
    '<text class="th" x="150" y="95" dominant-baseline="central">Title</text>'
    '<text class="ts" x="150" y="120" dominant-baseline="central">Subtitle</text>'
    "</g>"
    '<g class="c-teal">'
    '<rect x="420" y="60" width="220" height="90"/>'
    "</g>"
    '<rect class="box" x="10" y="10" width="30" height="30"/>'
    '<text class="t" x="200" y="200" dominant-baseline="central" fill="var(--p)">Plain</text>'
    "</svg>"
)


def test_flatten_resolves_ramp_classes_for_light_mode() -> None:
    result = flatten_svg(RAMP_FIXTURE, "light")
    assert result is not None
    assert result.unresolved is False
    svg = result.svg
    assert "var(" not in svg
    # Class-based ramp box: fill ramp[50], stroke ramp[600].
    assert 'fill="#EEEDFE"' in svg
    assert 'stroke="#534AB7"' in svg
    # Direct-child rect inside a ramp group: fill ramp[50], stroke ramp[600].
    assert 'fill="#E1F5EE"' in svg
    assert 'stroke="#0F6E56"' in svg
    # Text classes inside the ramp group take ramp title/subtitle colors.
    assert 'fill="#3C3489"' in svg
    # Non-ramp box falls back to the theme utility colors.
    assert 'fill="#f4f2eb"' in svg
    # var(--p) attribute resolves to the light primary text color.
    assert 'fill="#1a1918"' in svg


def test_flatten_uses_dark_ramp_values() -> None:
    result = flatten_svg(RAMP_FIXTURE, "dark")
    assert result is not None
    svg = result.svg
    # Class-based ramp box: fill ramp[800], stroke ramp[200].
    assert 'fill="#3C3489"' in svg
    assert 'stroke="#AFA9EC"' in svg
    # Direct-child rect keeps ramp[600] stroke in both modes.
    assert 'stroke="#0F6E56"' in svg
    assert 'fill="#085041"' in svg


def test_style_attribute_wins_over_class_rules() -> None:
    fixture = (
        '<svg width="100%" viewBox="0 0 680 200">'
        '<g class="c-blue">'
        '<rect class="box" style="fill: var(--color-text-danger)" x="10" y="10" width="50" height="50"/>'
        "</g>"
        "</svg>"
    )
    result = flatten_svg(fixture, "light")
    assert result is not None
    assert 'fill="#712b13"' in result.svg


def test_unresolved_tokens_are_reported() -> None:
    fixture = (
        '<svg width="100%" viewBox="0 0 680 200">'
        '<rect class="box" x="10" y="10" width="50" height="50" fill="var(--not-a-token)"/>'
        "</svg>"
    )
    result = flatten_svg(fixture, "light")
    assert result is not None
    assert result.unresolved is True
    assert any("not-a-token" in warning for warning in result.warnings)


def test_flatten_returns_none_for_invalid_xml() -> None:
    assert flatten_svg("<svg><unclosed>", "light") is None


def test_with_explicit_pixel_size_sets_scaled_dimensions() -> None:
    sized = with_explicit_pixel_size(
        '<svg width="100%" viewBox="0 0 680 200"><rect/></svg>',
        width_px=680,
        height_px=200,
        scale=2.0,
    )
    assert 'width="1360"' in sized
    assert 'height="400"' in sized
    assert "100%" not in sized
    assert 'viewBox="0 0 680 200"' in sized
