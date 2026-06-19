from app.agent.config import ToolConfig
from app.agent.widget_validator import (
    SUPPORTED_COLOR_RAMP_CLASSES,
    VISUALIZER_RAW_SVG_KIND,
    build_template_instance_widget_payload,
    build_validated_template_widget_payload,
    build_widget_payload,
)
from app.core.errors import ValidationAppError


def build_tool_config() -> ToolConfig:
    return ToolConfig(name="show_widget", max_loading_messages=4, max_widget_code_chars=75_000)


def test_html_widget_with_inline_svg_stays_html() -> None:
    payload = build_widget_payload(
        title="dense_vs_moe_widget",
        loading_messages=["Building visual"],
        widget_code=(
            "<style>.wrap{padding:8px}</style>"
            "<div class='wrap'><svg viewBox='0 0 680 220'><rect x='10' y='10' width='140' height='60'/></svg></div>"
            "<script src='https://cdn.jsdelivr.net/npm/chart.js'></script>"
            "<script>window.sendPrompt?.('Explain expert routing');</script>"
        ),
        tool_config=build_tool_config(),
    )

    assert payload.kind == "html"
    assert payload.widget_code.startswith("<style>")
    assert "<script" in payload.widget_code


def test_rejects_standalone_svg_wrapped_in_top_level_style() -> None:
    try:
        build_widget_payload(
            title="dense_vs_moe_architecture",
            loading_messages=["Building visual"],
            widget_code=(
                "<style>.c-purple { fill: var(--color-text-info); }</style>"
                "<svg width='100%' viewBox='0 0 680 220'>"
                "<defs><marker id='arrow' viewBox='0 0 10 10'></marker></defs>"
                "<text class='th' x='40' y='40' dominant-baseline='central'>Dense</text>"
                "</svg>"
            ),
            tool_config=build_tool_config(),
        )
    except ValidationAppError as exc:
        assert "must start directly with <svg>" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_supported_color_ramp_class_allowlist_is_exact() -> None:
    assert SUPPORTED_COLOR_RAMP_CLASSES == {
        "c-purple",
        "c-teal",
        "c-amber",
        "c-coral",
        "c-blue",
        "c-green",
        "c-pink",
        "c-gray",
        "c-red",
    }


def test_svg_accepts_all_supported_color_ramp_classes() -> None:
    for ramp_class in sorted(SUPPORTED_COLOR_RAMP_CLASSES):
        payload = build_widget_payload(
            title=f"valid_{ramp_class.replace('-', '_')}",
            loading_messages=["Building visual"],
            widget_code=(
                "<svg width='100%' viewBox='0 0 680 140'>"
                "<defs><marker id='arrow' viewBox='0 0 10 10'></marker></defs>"
                f"<g class='{ramp_class}'>"
                "<rect x='40' y='30' width='120' height='44'></rect>"
                "<text class='th' x='100' y='52' dominant-baseline='central'>Good</text>"
                "</g>"
                "</svg>"
            ),
            tool_config=ToolConfig(),
        )

        assert payload.kind == "svg"


def test_html_widget_requires_style_before_scripts() -> None:
    try:
        build_widget_payload(
            title="bad_order_widget",
            loading_messages=["Building visual"],
            widget_code="<script>console.log('x')</script><style>.a{}</style><div>hello</div>",
            tool_config=build_tool_config(),
        )
    except ValidationAppError as exc:
        assert "start with a <style>" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_html_widget_rejects_position_fixed() -> None:
    try:
        build_widget_payload(
            title="fixed_layout_widget",
            loading_messages=["Building visual"],
            widget_code="<style>.a{position:fixed;top:0}</style><div class='a'>hello</div>",
            tool_config=build_tool_config(),
        )
    except ValidationAppError as exc:
        assert "position:fixed" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_html_widget_rejects_disallowed_script_cdn() -> None:
    try:
        build_widget_payload(
            title="bad_cdn_widget",
            loading_messages=["Building visual"],
            widget_code=(
                "<style>.wrap{padding:8px}</style>"
                "<div class='wrap'>Widget</div>"
                "<script src='https://example.com/widget.js'></script>"
                "<script>console.log('ok')</script>"
            ),
            tool_config=build_tool_config(),
        )
    except ValidationAppError as exc:
        assert "is not allowed" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_html_widget_rejects_external_script_after_inline_logic() -> None:
    try:
        build_widget_payload(
            title="bad_script_order_widget",
            loading_messages=["Building visual"],
            widget_code=(
                "<style>.wrap{padding:8px}</style>"
                "<div class='wrap'>Widget</div>"
                "<script>console.log('logic first')</script>"
                "<script src='https://cdn.jsdelivr.net/npm/chart.js'></script>"
            ),
            tool_config=build_tool_config(),
        )
    except ValidationAppError as exc:
        assert "before inline logic scripts" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_html_widget_rejects_disallowed_module_import_host() -> None:
    try:
        build_widget_payload(
            title="bad_module_import_widget",
            loading_messages=["Building visual"],
            widget_code=(
                "<style>.wrap{padding:8px}</style>"
                "<div class='wrap'>Widget</div>"
                "<script type='module'>import thing from 'https://example.com/mod.js'; console.log(thing)</script>"
            ),
            tool_config=build_tool_config(),
        )
    except ValidationAppError as exc:
        assert "module import" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_html_widget_rejects_link_tags() -> None:
    try:
        build_widget_payload(
            title="bad_link_widget",
            loading_messages=["Building visual"],
            widget_code=(
                "<style>.wrap{padding:8px}</style>"
                "<link rel='stylesheet' href='https://example.com/widget.css'>"
                "<div class='wrap'>Widget</div>"
                "<script>console.log('ok')</script>"
            ),
            tool_config=build_tool_config(),
        )
    except ValidationAppError as exc:
        assert "<link> tags" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_build_widget_payload_accepts_svg() -> None:
    payload = build_widget_payload(
        title="attention_mechanism",
        loading_messages=["Drawing the fan"],
        widget_code=(
            "<svg width='100%' viewBox='0 0 680 140'>"
            "<defs><marker id='arrow' viewBox='0 0 10 10'></marker></defs>"
            "<g class='node c-purple'>"
            "<rect x='40' y='30' width='180' height='44' rx='8' stroke-width='0.5'></rect>"
            "<text class='th' x='130' y='52' dominant-baseline='central'>Input</text>"
            "</g>"
            "<path d='M220 52 L300 52' class='arr' marker-end='url(#arrow)'></path>"
            "</svg>"
        ),
        tool_config=ToolConfig(),
    )

    assert payload.kind == "svg"
    assert payload.title == "attention_mechanism"


def test_svg_rejects_unsupported_css_variable_tokens() -> None:
    try:
        build_widget_payload(
            title="bad_svg_tokens",
            loading_messages=["Nope"],
            widget_code=(
                "<svg width='100%' viewBox='0 0 680 140'>"
                "<defs><marker id='arrow' viewBox='0 0 10 10'></marker></defs>"
                "<text class='th' x='40' y='40' dominant-baseline='central' fill='var(--c-purple-500)'>Bad</text>"
                "</svg>"
            ),
            tool_config=ToolConfig(),
        )
    except ValidationAppError as exc:
        assert "Unsupported CSS variable" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_svg_rejects_palette_stop_css_variable_tokens() -> None:
    try:
        build_widget_payload(
            title="bad_svg_palette_tokens",
            loading_messages=["Nope"],
            widget_code=(
                "<svg width='100%' viewBox='0 0 680 140'>"
                "<defs><marker id='arrow' viewBox='0 0 10 10'></marker></defs>"
                "<text class='th' x='40' y='40' dominant-baseline='central' fill='var(--color-blue-200)'>Bad</text>"
                "</svg>"
            ),
            tool_config=ToolConfig(),
        )
    except ValidationAppError as exc:
        assert "Unsupported CSS variable" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_svg_rejects_palette_stop_color_ramp_classes() -> None:
    try:
        build_widget_payload(
            title="bad_svg_ramp_class",
            loading_messages=["Nope"],
            widget_code=(
                "<svg width='100%' viewBox='0 0 680 140'>"
                "<defs><marker id='arrow' viewBox='0 0 10 10'></marker></defs>"
                "<rect class='c-teal-200' x='40' y='30' width='120' height='44'></rect>"
                "<text class='th' x='100' y='52' dominant-baseline='central'>Bad</text>"
                "</svg>"
            ),
            tool_config=ToolConfig(),
        )
    except ValidationAppError as exc:
        assert "Unsupported color ramp class" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_svg_rejects_text_without_injected_text_class() -> None:
    try:
        build_widget_payload(
            title="bad_svg_text_class",
            loading_messages=["Nope"],
            widget_code=(
                "<svg width='100%' viewBox='0 0 680 140'>"
                "<defs><marker id='arrow' viewBox='0 0 10 10'></marker></defs>"
                "<text class='label' x='40' y='40' dominant-baseline='central'>Bad</text>"
                "</svg>"
            ),
            tool_config=ToolConfig(),
        )
    except ValidationAppError as exc:
        assert "t, ts, or th" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_build_widget_payload_rejects_html_document_wrapper() -> None:
    try:
        build_widget_payload(
            title="bad_widget",
            loading_messages=["Nope"],
            widget_code="<!DOCTYPE html><html></html>",
            tool_config=ToolConfig(),
        )
    except ValidationAppError as exc:
        assert "document-level markup" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_svg_rejects_non_680_viewbox() -> None:
    try:
        build_widget_payload(
            title="bad_svg",
            loading_messages=["Nope"],
            widget_code=(
                "<svg width='100%' viewBox='0 0 640 140'>"
                "<defs><marker id='arrow'></marker></defs>"
                "<text class='th' x='40' y='40' dominant-baseline='central'>Bad</text>"
                "</svg>"
            ),
            tool_config=ToolConfig(),
        )
    except ValidationAppError as exc:
        assert "viewBox='0 0 680 H'" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


def test_template_instance_widget_payload_accepts_client_svg_shape() -> None:
    payload = build_template_instance_widget_payload(
        title="client_svg_template",
        loading_messages=["Selecting template", "Cloning", "Validating"],
        widget_code=(
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<svg viewBox='0 0 1920 1080' xmlns='http://www.w3.org/2000/svg'>"
            "<defs></defs><g id='slot_1'><text id='text_1'>Hello</text></g></svg>"
        ),
        tool_config=build_tool_config(),
    )

    assert payload.kind == "svg"
    assert payload.widget_code.startswith("<svg")
    assert "viewBox='0 0 1920 1080'" in payload.widget_code


def test_svg_geometry_violations_reproduce_orange_callout_case() -> None:
    """Reproduce the visualizer-agent failure where a callout text overflows its
    rect and the callout rect overlaps a sibling node. Both defects must be
    surfaced as HIGH violations on the ValidationAppError."""

    widget_code = (
        "<svg width='100%' viewBox='0 0 680 260'>"
        "<defs><marker id='arrow' viewBox='0 0 10 10'></marker></defs>"
        # Self-Attention node.
        "<g class='node c-purple'>"
        "<rect x='380' y='120' width='180' height='44'></rect>"
        "<text class='th' x='470' y='142' text-anchor='middle' dominant-baseline='central'>"
        "Self-Attention"
        "</text>"
        "</g>"
        # Orange callout sitting on top of the Self-Attention node with a
        # multi-line body that exits the callout rect on the right.
        "<g class='node c-coral'>"
        "<rect x='440' y='110' width='140' height='56'></rect>"
        "<text class='ts' x='510' y='136' text-anchor='middle' dominant-baseline='central'>"
        "<tspan x='510' dy='0'>The \"Complex Part\"</tspan>"
        "<tspan x='510' dy='16'>Learns to route each token to the best expert</tspan>"
        "</text>"
        "</g>"
        "</svg>"
    )

    try:
        build_widget_payload(
            title="dense_vs_moe_architecture",
            loading_messages=["Building visual"],
            widget_code=widget_code,
            tool_config=ToolConfig(),
        )
    except ValidationAppError as exc:
        details = exc.details
        assert details.get("kind") == VISUALIZER_RAW_SVG_KIND
        assert details.get("widget_title") == "dense_vs_moe_architecture"
        assert isinstance(details.get("source_svg"), str)
        geometry = details.get("geometry_violations")
        assert isinstance(geometry, list) and geometry
        codes = {entry["code"] for entry in geometry}
        assert "V-VIZ-TEXT-OVERFLOW-H" in codes
        assert "V-VIZ-SIBLING-OVERLAP" in codes
    else:
        raise AssertionError("Expected ValidationAppError")


def test_svg_reports_multiple_violations_together() -> None:
    try:
        build_widget_payload(
            title="bad_svg_many",
            loading_messages=["Nope"],
            widget_code=(
                "<svg viewBox='0 0 680 140'>"
                "<defs><marker id='arrow'></marker></defs>"
                "<!-- bad comment -->"
                "<text x='40' y='40'>Bad</text>"
                "</svg>"
            ),
            tool_config=ToolConfig(),
        )
    except ValidationAppError as exc:
        assert "HTML comments" in exc.message
        assert "width='100%'" in exc.message
        assert "dominant-baseline='central'" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")


SOURCE_TEMPLATE_SVG = """
<svg viewBox="0 0 1200 675" xmlns="http://www.w3.org/2000/svg">
  <g id="layout-root">
    <g id="slot-title">
      <text id="title-text" x="60" y="80">Source title</text>
    </g>
    <g id="slot-body">
      <text id="body-text" x="60" y="180">Source body</text>
    </g>
  </g>
</svg>
""".strip()


def test_validated_template_widget_payload_accepts_safe_clone() -> None:
    working_svg = SOURCE_TEMPLATE_SVG.replace("Source title", "Updated title")

    payload = build_validated_template_widget_payload(
        title="template_instance",
        loading_messages=["Validating clone"],
        widget_code=working_svg,
        template_id="list/list.svg",
        source_svg=SOURCE_TEMPLATE_SVG,
        tool_config=build_tool_config(),
    )

    assert payload.kind == "svg"
    assert "Updated title" in payload.widget_code


def test_validated_template_widget_payload_rejects_id_drift() -> None:
    working_svg = SOURCE_TEMPLATE_SVG.replace('id="slot-body"', 'id="slot-body-renamed"')

    try:
        build_validated_template_widget_payload(
            title="template_instance",
            loading_messages=["Validating clone"],
            widget_code=working_svg,
            template_id="list/list.svg",
            source_svg=SOURCE_TEMPLATE_SVG,
            tool_config=build_tool_config(),
        )
    except ValidationAppError as exc:
        assert "template_relative_path" in exc.details
        assert exc.details["source_svg"] == SOURCE_TEMPLATE_SVG
        assert "group_id_missing" in str(exc.details.get("violations"))
    else:
        raise AssertionError("Expected ValidationAppError")
