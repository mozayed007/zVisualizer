"""PNG rendering for widget artifacts.

Two backends, best first:

1. Playwright (Chromium): renders the assembled standalone document. Works for
   both SVG and HTML widgets and is the only faithful option for HTML.
2. External rasterizer (`magick` | `inkscape` | `rsvg-convert`) fed a flattened,
   explicitly sized SVG. SVG only; raises `PngRendererUnavailable` otherwise.

All functions are synchronous; callers in async code should wrap them with
`asyncio.to_thread`.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

EXTERNAL_RENDERER_COMMANDS = ("magick", "inkscape", "rsvg-convert")
DEFAULT_RENDER_TIMEOUT_MS = 20_000


class PngRendererUnavailable(RuntimeError):
    """Raised when the requested PNG backend is not available on this machine."""


@dataclass(frozen=True, slots=True)
class PngRender:
    data: bytes
    width: int
    height: int
    renderer: str


def playwright_installed() -> bool:
    return find_spec("playwright") is not None


def external_renderer_name() -> str | None:
    for candidate in EXTERNAL_RENDERER_COMMANDS:
        if shutil.which(candidate) is not None:
            return candidate
    return None


def available_renderers() -> list[str]:
    names: list[str] = []
    if playwright_installed():
        names.append("playwright")
    external = external_renderer_name()
    if external is not None:
        names.append(external)
    return names


def render_document_to_png(
    html_document: str,
    *,
    width_px: int = 680,
    scale: float = 2.0,
    settle_ms: int = 400,
    timeout_ms: int = DEFAULT_RENDER_TIMEOUT_MS,
) -> PngRender:
    """Screenshot an assembled HTML document with headless Chromium."""
    if not playwright_installed():
        raise PngRendererUnavailable(
            "Playwright is not installed. Install the render extra and the browser: "
            "pip install 'visualizer-agent-backend[render]' && playwright install chromium"
        )

    from playwright.sync_api import sync_playwright  # noqa: PLC0415 - optional dependency

    viewport_width = max(1, int(width_px))
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment dependent
            raise PngRendererUnavailable(
                "Chromium for Playwright is not installed. Run: playwright install chromium"
            ) from exc
        try:
            page = browser.new_page(
                viewport={"width": viewport_width, "height": 400},
                device_scale_factor=max(1.0, scale),
            )
            page.set_default_timeout(max(1, timeout_ms))
            page.set_content(html_document, wait_until="load")
            try:
                page.evaluate("() => (document.fonts ? document.fonts.ready.then(() => true) : true)")
            except Exception:
                pass
            if settle_ms > 0:
                page.wait_for_timeout(settle_ms)
            size = page.evaluate(
                "() => ({"
                "  w: Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0),"
                "  h: Math.max(document.body ? document.body.scrollHeight : 0, 1)"
                "})"
            )
            clip_width = max(1, int(size.get("w", viewport_width)))
            clip_height = max(1, int(size.get("h", 1)))
            data = page.screenshot(clip={"x": 0, "y": 0, "width": clip_width, "height": clip_height})
            width = max(1, round(clip_width * scale))
            height = max(1, round(clip_height * scale))
        finally:
            browser.close()

    return PngRender(data=data, width=width, height=height, renderer="playwright")


def render_svg_to_png_with_external_tool(
    svg_markup: str,
    *,
    width_px: int = 680,
    height_px: int = 420,
    scale: float = 2.0,
    timeout_ms: int = DEFAULT_RENDER_TIMEOUT_MS,
) -> PngRender:
    """Rasterize an (already flattened, already sized) SVG with an external tool."""
    command_name = external_renderer_name()
    if command_name is None:
        raise PngRendererUnavailable(
            "No external SVG rasterizer found. Install ImageMagick (magick), Inkscape, or rsvg-convert, "
            "or install Playwright for the preferred renderer."
        )
    command_path = shutil.which(command_name)
    assert command_path is not None

    fd_svg, svg_path_str = tempfile.mkstemp(suffix=".svg")
    fd_png, png_path_str = tempfile.mkstemp(suffix=".png")
    import os  # noqa: PLC0415 - local to temp-file handling

    os.close(fd_svg)
    os.close(fd_png)
    svg_path = Path(svg_path_str)
    png_path = Path(png_path_str)
    try:
        svg_path.write_text(svg_markup, encoding="utf-8")
        if command_name == "magick":
            command = [command_path, str(svg_path), str(png_path)]
        elif command_name == "inkscape":
            command = [
                command_path,
                str(svg_path),
                "--export-type=png",
                f"--export-filename={png_path}",
            ]
        else:
            command = [command_path, "-o", str(png_path), str(svg_path)]
        subprocess.run(
            command,
            check=True,
            timeout=max(1, timeout_ms) / 1000,
            capture_output=True,
        )
        data = png_path.read_bytes()
    except (OSError, subprocess.SubprocessError) as exc:
        raise PngRendererUnavailable(f"External rasterizer '{command_name}' failed: {exc}") from exc
    finally:
        for path in (svg_path, png_path):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                continue

    if not data:
        raise PngRendererUnavailable(f"External rasterizer '{command_name}' produced no output.")

    return PngRender(
        data=data,
        width=max(1, round(width_px * scale)),
        height=max(1, round(height_px * scale)),
        renderer=command_name,
    )
