from app.agent.svg_template_validator import validate_svg_template_instance
from app.core.errors import ValidationAppError

SOURCE_SVG = """
<svg viewBox="0 0 1200 675" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="clip-main">
      <rect id="clip-rect" x="40" y="120" width="1120" height="420" />
    </clipPath>
  </defs>
  <g id="layout-root">
    <g id="slot-title">
      <text id="title-text" x="60" y="80">Source title</text>
    </g>
    <g id="slot-body" clip-path="url(#clip-main)">
      <text id="body-text" x="60" y="180">Source body</text>
    </g>
    <g id="slot-caption">
      <text id="caption-text" x="60" y="620">Source caption</text>
    </g>
  </g>
</svg>
""".strip()


def test_validates_clone_with_content_updates_only() -> None:
    working_svg = SOURCE_SVG.replace("Source title", "Updated title").replace(
        "Source body",
        "Updated body copy",
    )

    result = validate_svg_template_instance(
        source_svg=SOURCE_SVG,
        working_svg=working_svg,
    )

    assert result.violations == []
    assert result.checked_group_ids == 4
    assert result.checked_ids >= 7


def test_rejects_group_id_rename() -> None:
    working_svg = SOURCE_SVG.replace('id="slot-body"', 'id="slot-body-renamed"')

    try:
        validate_svg_template_instance(source_svg=SOURCE_SVG, working_svg=working_svg)
    except ValidationAppError as exc:
        violations = exc.details["violations"]
        assert any(violation["code"] == "group_id_missing" for violation in violations)
    else:
        raise AssertionError("Expected ValidationAppError")


def test_rejects_hierarchy_drift_when_element_is_reparented() -> None:
    working_svg = SOURCE_SVG.replace(
        '<g id="slot-title">\n      <text id="title-text" x="60" y="80">Source title</text>\n    </g>',
        '<g id="slot-title">\n      <text id="title-text" x="60" y="80">Source title</text>\n'
        '      <text id="body-text" x="60" y="180">Source body</text>\n    </g>',
    ).replace(
        (
            '<g id="slot-body" clip-path="url(#clip-main)">\n'
            '      <text id="body-text" x="60" y="180">Source body</text>\n'
            "    </g>"
        ),
        '<g id="slot-body" clip-path="url(#clip-main)"></g>',
    )

    try:
        validate_svg_template_instance(source_svg=SOURCE_SVG, working_svg=working_svg)
    except ValidationAppError as exc:
        violations = exc.details["violations"]
        assert any(violation["code"] == "hierarchy_drift" for violation in violations)
    else:
        raise AssertionError("Expected ValidationAppError")


def test_rejects_sibling_order_drift() -> None:
    working_svg = """
<svg viewBox="0 0 1200 675" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="clip-main">
      <rect id="clip-rect" x="40" y="120" width="1120" height="420" />
    </clipPath>
  </defs>
  <g id="layout-root">
    <g id="slot-title">
      <text id="title-text" x="60" y="80">Source title</text>
    </g>
    <g id="slot-caption">
      <text id="caption-text" x="60" y="620">Source caption</text>
    </g>
    <g id="slot-body" clip-path="url(#clip-main)">
      <text id="body-text" x="60" y="180">Source body</text>
    </g>
  </g>
</svg>
""".strip()

    try:
        validate_svg_template_instance(source_svg=SOURCE_SVG, working_svg=working_svg)
    except ValidationAppError as exc:
        violations = exc.details["violations"]
        assert any(violation["code"] == "sibling_order_drift" for violation in violations)
    else:
        raise AssertionError("Expected ValidationAppError")


def test_rejects_viewbox_drift() -> None:
    working_svg = SOURCE_SVG.replace('viewBox="0 0 1200 675"', 'viewBox="0 0 1000 600"')

    try:
        validate_svg_template_instance(source_svg=SOURCE_SVG, working_svg=working_svg)
    except ValidationAppError as exc:
        violations = exc.details["violations"]
        assert any(violation["code"] == "viewbox_drift" for violation in violations)
    else:
        raise AssertionError("Expected ValidationAppError")
