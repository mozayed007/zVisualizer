from dataclasses import dataclass

from app.agent.config import ToolConfig
from app.agent.svg_preview_renderer import SvgRenderedPreview
from app.agent.svg_vision_repair import SvgVisionRepairService
from app.core.errors import ValidationAppError

SOURCE_SVG = """
<svg viewBox="0 0 1200 675" xmlns="http://www.w3.org/2000/svg">
  <g id="layout-root">
    <g id="slot-title">
      <text id="title-text">____________________</text>
    </g>
    <g id="slot-body">
      <text id="body-text">____________________________</text>
    </g>
  </g>
</svg>
""".strip()

WORKING_SVG_WITH_DRIFT = """
<svg viewBox="0 0 1200 675" xmlns="http://www.w3.org/2000/svg">
  <g id="layout-root">
    <g id="slot-title">
      <text id="title-text">Updated title</text>
      <text id="body-text">Moved body</text>
    </g>
    <g id="slot-body"></g>
  </g>
</svg>
""".strip()

REPAIRED_SVG = """
<svg viewBox="0 0 1200 675" xmlns="http://www.w3.org/2000/svg">
  <g id="layout-root">
    <g id="slot-title">
      <text id="title-text">Updated title</text>
    </g>
    <g id="slot-body">
      <text id="body-text">Repaired body</text>
    </g>
  </g>
</svg>
""".strip()


@dataclass
class _FakeResponse:
    text: str


class _FakeGenerateClient:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict[str, object]] = []

    def generate_content(self, *, model, contents, config):  # noqa: ANN001
        self.calls.append(
            {
                "model": model,
                "contents": contents,
                "config": config,
            }
        )
        return _FakeResponse(self.response_text)


class _FakePreviewRenderer:
    def render(self, svg_markup: str) -> SvgRenderedPreview | None:
        del svg_markup
        return SvgRenderedPreview(
            mime_type="image/png",
            data=b"\x89PNG\r\n\x1a\nfake",
            description="PNG preview",
        )


def build_error() -> ValidationAppError:
    return ValidationAppError(
        "SVG template instance validation failed.",
        details={
            "request_message": "Compare SQL vs NoSQL",
            "widget_title": "versus_compare",
            "template_relative_path": "versus/compare.svg",
            "content_lines": ["SQL", "NoSQL"],
            "source_svg": SOURCE_SVG,
            "working_svg": WORKING_SVG_WITH_DRIFT,
            "violations": [
                {
                    "code": "hierarchy_drift",
                    "message": "Element 'body-text' changed parent or hierarchy position in the working SVG.",
                }
            ],
        },
    )


def test_svg_vision_repair_returns_valid_widget_from_model_svg_response() -> None:
    client = _FakeGenerateClient(REPAIRED_SVG)
    service = SvgVisionRepairService(
        api_key="test-key",
        model_name="gemini-3.1-pro-preview",
        generate_content_client=client,
    )

    widget = service.repair_from_validation_error(
        error=build_error(),
        tool_config=ToolConfig(),
    )

    assert widget is not None
    assert widget.kind == "svg"
    assert "Repaired body" in widget.widget_code
    assert client.calls


def test_svg_vision_repair_returns_none_when_model_does_not_return_svg() -> None:
    client = _FakeGenerateClient("No repair available.")
    service = SvgVisionRepairService(
        api_key="test-key",
        model_name="gemini-3.1-pro-preview",
        generate_content_client=client,
    )

    widget = service.repair_from_validation_error(
        error=build_error(),
        tool_config=ToolConfig(),
    )

    assert widget is None


def test_svg_vision_repair_includes_preview_part_when_renderer_is_available() -> None:
    client = _FakeGenerateClient(REPAIRED_SVG)
    service = SvgVisionRepairService(
        api_key="test-key",
        model_name="gemini-3.1-pro-preview",
        preview_renderer=_FakePreviewRenderer(),
        generate_content_client=client,
    )

    widget = service.repair_from_validation_error(
        error=build_error(),
        tool_config=ToolConfig(),
    )

    assert widget is not None
    contents = client.calls[0]["contents"]
    assert isinstance(contents, list)
    assert len(contents) >= 3
