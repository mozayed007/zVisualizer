from app.agent.svg_geometry_validator import validate_svg_geometry


def _codes(svg: str) -> list[str]:
    return [violation.code for violation in validate_svg_geometry(svg)]


def test_passing_svg_has_no_violations() -> None:
    svg = (
        "<svg width='100%' viewBox='0 0 680 140'>"
        "<defs><marker id='arrow'/></defs>"
        "<g class='node c-purple'>"
        "<rect x='40' y='30' width='180' height='44'/>"
        "<text class='th' x='130' y='52' text-anchor='middle' dominant-baseline='central'>Input</text>"
        "</g>"
        "</svg>"
    )
    assert validate_svg_geometry(svg) == []


def test_text_horizontal_overflow_is_flagged() -> None:
    svg = (
        "<svg width='100%' viewBox='0 0 680 140'>"
        "<g class='c-coral'>"
        # rect only 120px wide but the label needs far more.
        "<rect x='400' y='40' width='120' height='48'/>"
        "<text class='th' x='460' y='64' text-anchor='middle' dominant-baseline='central'>"
        "Learns to route each token to the best expert"
        "</text>"
        "</g>"
        "</svg>"
    )
    codes = _codes(svg)
    assert "V-VIZ-TEXT-OVERFLOW-H" in codes
    assert "V-VIZ-BOX-WIDTH-FORMULA" in codes


def test_sibling_node_overlap_is_flagged() -> None:
    svg = (
        "<svg width='100%' viewBox='0 0 680 200'>"
        "<g class='node c-purple'>"
        "<rect x='120' y='80' width='200' height='44'/>"
        "<text class='th' x='220' y='102' text-anchor='middle' dominant-baseline='central'>Self-Attention</text>"
        "</g>"
        "<g class='node c-coral'>"
        # Callout rect that sits on top of the Self-Attention node.
        "<rect x='260' y='70' width='200' height='60'/>"
        "<text class='ts' x='360' y='100' text-anchor='middle' dominant-baseline='central'>callout</text>"
        "</g>"
        "</svg>"
    )
    codes = _codes(svg)
    assert "V-VIZ-SIBLING-OVERLAP" in codes


def test_viewbox_escape_is_flagged() -> None:
    svg = (
        "<svg width='100%' viewBox='0 0 680 140'>"
        "<g class='c-blue'>"
        "<rect x='600' y='40' width='200' height='40'/>"
        "<text class='th' x='700' y='60' text-anchor='middle' dominant-baseline='central'>X</text>"
        "</g>"
        "</svg>"
    )
    assert "V-VIZ-VIEWBOX-ESCAPE" in _codes(svg)


def test_wordcount_cap_is_flagged_for_th() -> None:
    svg = (
        "<svg width='100%' viewBox='0 0 680 200'>"
        "<g class='c-teal'>"
        "<rect x='20' y='20' width='640' height='140'/>"
        "<text class='th' x='340' y='90' text-anchor='middle' dominant-baseline='central'>"
        "<tspan x='340' dy='0'>one two three</tspan>"
        "<tspan x='340' dy='18'>four five six seven eight nine</tspan>"
        "</text>"
        "</g>"
        "</svg>"
    )
    assert "V-VIZ-TEXT-WORDCOUNT" in _codes(svg)


def test_box_width_formula_flagged_when_rect_too_narrow() -> None:
    svg = (
        "<svg width='100%' viewBox='0 0 680 120'>"
        "<g class='node c-amber'>"
        # 14-char label needs >=140px but rect is only 120px.
        "<rect x='60' y='30' width='120' height='44'/>"
        "<text class='th' x='120' y='52' text-anchor='middle' dominant-baseline='central'>"
        "Validate input"
        "</text>"
        "</g>"
        "</svg>"
    )
    assert "V-VIZ-BOX-WIDTH-FORMULA" in _codes(svg)


def test_unparseable_svg_returns_empty_list() -> None:
    # Missing closing tag — validator must not raise.
    assert validate_svg_geometry("<svg><rect></svg>") == []
