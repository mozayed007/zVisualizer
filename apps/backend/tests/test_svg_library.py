from pathlib import Path

from app.agent.config import ToolConfig
from app.agent.svg_library import SvgLibraryService
from app.core.errors import ValidationAppError


def _write_template(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_svg_library_selects_matching_category_and_returns_clone_widget(tmp_path: Path) -> None:
    library_root = tmp_path / "SVGs_Organized"
    _write_template(
        library_root / "versus" / "compare.svg",
        """
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">
  <g id="layout-root">
    <g id="text1-fadeinchars">
      <text id="title-left">____________________</text>
    </g>
    <g id="text2-fadeinchars">
      <text id="title-right">____________________</text>
    </g>
    <g id="desc1-fadeinchars">
      <text id="desc-left">____________________________</text>
    </g>
    <g id="desc2-fadeinchars">
      <text id="desc-right">____________________________</text>
    </g>
  </g>
</svg>
""".strip(),
    )
    _write_template(
        library_root / "list" / "list.svg",
        """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">
  <g id="layout-root">
    <text id="item-1">________________</text>
    <text id="item-2">________________</text>
  </g>
</svg>
""".strip(),
    )

    service = SvgLibraryService(library_root)
    result = service.build_widget_for_request(
        request_message="Compare SQL vs NoSQL for a system design review",
        tool_config=ToolConfig(),
    )

    assert result.template.category == "versus"
    assert result.widget.kind == "svg"
    assert result.widget.widget_code.startswith("<svg")
    assert 'id="layout-root"' in result.widget.widget_code
    assert "SQL" in result.widget.widget_code
    assert "NoSQL" in result.widget.widget_code
    assert result.validation.violations == []


def test_resolve_template_returns_matching_record(tmp_path: Path) -> None:
    library_root = tmp_path / "SVGs_Organized"
    _write_template(
        library_root / "list" / "list.svg",
        """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">
  <g id="layout-root">
    <text id="item-1">________________</text>
  </g>
</svg>
""".strip(),
    )

    service = SvgLibraryService(library_root)
    template = service.resolve_template("list/list.svg")

    assert template.relative_path == "list/list.svg"
    assert "layout-root" in service.read_source_svg(template)


def test_resolve_template_rejects_unknown_and_traversal(tmp_path: Path) -> None:
    library_root = tmp_path / "SVGs_Organized"
    _write_template(
        library_root / "list" / "list.svg",
        """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">
  <text id="item-1">________________</text>
</svg>
""".strip(),
    )
    service = SvgLibraryService(library_root)

    try:
        service.resolve_template("missing/list.svg")
    except ValidationAppError as exc:
        assert "Unknown template_id" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")

    try:
        service.resolve_template("../list/list.svg")
    except ValidationAppError as exc:
        assert "not allowed" in exc.message
    else:
        raise AssertionError("Expected ValidationAppError")
