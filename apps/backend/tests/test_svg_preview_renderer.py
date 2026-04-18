from pathlib import Path

from app.agent.svg_preview_renderer import ExternalSvgPreviewRenderer


def test_svg_preview_renderer_detects_override_backend() -> None:
    renderer = ExternalSvgPreviewRenderer(command_override="C:\\tools\\inkscape.exe")

    assert renderer.backend_name == "inkscape"


def test_svg_preview_renderer_returns_png_preview_from_runner(tmp_path: Path) -> None:
    output_bytes = b"\x89PNG\r\n\x1a\nfake"

    def fake_runner(command: list[str], timeout_ms: int) -> None:
        del timeout_ms
        output_path = Path(command[-1] if command[0].endswith("magick.exe") else command[-1])
        if command[0].endswith("magick.exe"):
            output_path = Path(command[2])
        output_path.write_bytes(output_bytes)

    renderer = ExternalSvgPreviewRenderer(
        command_override="C:\\tools\\magick.exe",
        runner=fake_runner,
    )

    preview = renderer.render("<svg xmlns='http://www.w3.org/2000/svg'></svg>")

    assert preview is not None
    assert preview.mime_type == "image/png"
    assert preview.data == output_bytes
    assert "magick" in preview.description.lower()


def test_svg_preview_renderer_returns_none_for_unknown_override() -> None:
    renderer = ExternalSvgPreviewRenderer(command_override="C:\\tools\\custom-svg.exe")

    assert renderer.backend_name is None
    assert renderer.render("<svg xmlns='http://www.w3.org/2000/svg'></svg>") is None
