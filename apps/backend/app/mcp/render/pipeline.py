"""Widget -> artifact files orchestration.

Turns a validated `WidgetPayload` into `.svg` / `.png` / `.html` files on disk
for use outside the web app, with soft degradation when an optional renderer is
not available on this machine.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.mcp.render.html_document import build_png_document, build_standalone_document
from app.mcp.render.png import (
    PngRendererUnavailable,
    playwright_installed,
    render_document_to_png,
    render_svg_to_png_with_external_tool,
)
from app.mcp.render.svg_export import build_exportable_svg
from app.mcp.render.svg_flatten import flatten_svg, with_explicit_pixel_size
from app.mcp.render.theme import ThemeMode
from app.models.chat import WidgetPayload

logger = logging.getLogger(__name__)

FormatName = Literal["svg", "png", "html"]

DEFAULT_WIDGET_WIDTH_PX = 680
DEFAULT_SVG_HEIGHT_PX = 420

_VIEWBOX_HEIGHT_PATTERN = re.compile(
    r"viewBox\s*=\s*['\"]\s*0\s+0\s+680\s+(\d+(?:\.\d+)?)\s*['\"]",
    re.IGNORECASE,
)


class RenderPipelineError(RuntimeError):
    """Raised when a validated widget cannot be exported at all."""


@dataclass(frozen=True, slots=True)
class FileArtifact:
    format: FormatName
    path: Path
    bytes: int
    width: int | None = None
    height: int | None = None
    renderer: str | None = None


@dataclass(frozen=True, slots=True)
class RenderOutcome:
    files: list[FileArtifact] = field(default_factory=list)
    png_bytes: bytes | None = None
    warnings: list[str] = field(default_factory=list)


def svg_viewbox_height(widget_code: str) -> float:
    match = _VIEWBOX_HEIGHT_PATTERN.search(widget_code)
    if match is None:
        return float(DEFAULT_SVG_HEIGHT_PX)
    return float(match.group(1))


def _write_file(path: Path, data: bytes) -> FileArtifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return FileArtifact(format=_format_for_suffix(path.suffix), path=path, bytes=len(data))


def _format_for_suffix(suffix: str) -> FormatName:
    lowered = suffix.lower().lstrip(".")
    if lowered == "svg":
        return "svg"
    if lowered == "png":
        return "png"
    return "html"


def _render_png(
    *,
    widget: WidgetPayload,
    theme: ThemeMode,
    scale: float,
    settle_ms: int,
) -> tuple[bytes | None, int | None, int | None, str | None, list[str]]:
    """Best-effort PNG bytes. Returns (data, width, height, renderer, warnings)."""
    warnings: list[str] = []
    width_px = DEFAULT_WIDGET_WIDTH_PX

    if playwright_installed():
        document = build_png_document(content=widget.widget_code, title=widget.title, theme=theme)
        try:
            render = render_document_to_png(
                document,
                width_px=width_px,
                scale=scale,
                settle_ms=settle_ms,
            )
            return render.data, render.width, render.height, render.renderer, warnings
        except PngRendererUnavailable as exc:
            warnings.append(f"Playwright PNG rendering unavailable: {exc}")
        except Exception as exc:  # pragma: no cover - environment dependent
            warnings.append(f"Playwright PNG rendering failed: {exc}")

    if widget.kind == "svg":
        flattened = flatten_svg(widget.widget_code, theme)
        if flattened is None:
            warnings.append("SVG could not be parsed for the external rasterizer fallback; skipping PNG.")
            return None, None, None, None, warnings
        if flattened.unresolved:
            warnings.extend(flattened.warnings)
            warnings.append(
                "Flattened SVG still contains unresolved CSS variables; skipping the external "
                "rasterizer fallback to avoid wrong colors."
            )
            return None, None, None, None, warnings

        height_px = int(round(svg_viewbox_height(widget.widget_code)))
        sized_svg = with_explicit_pixel_size(
            flattened.svg,
            width_px=width_px,
            height_px=height_px,
            scale=scale,
        )
        try:
            render = render_svg_to_png_with_external_tool(
                sized_svg,
                width_px=width_px,
                height_px=height_px,
                scale=scale,
            )
            return render.data, render.width, render.height, render.renderer, warnings
        except PngRendererUnavailable as exc:
            warnings.append(f"External rasterizer unavailable: {exc}")
            return None, None, None, None, warnings

    warnings.append(
        "PNG for HTML widgets requires Playwright (headless Chromium). "
        "Install it with: pip install 'visualizer-agent-backend[render]' && playwright install chromium"
    )
    return None, None, None, None, warnings


def render_widget_outcome(
    *,
    widget: WidgetPayload,
    theme: ThemeMode,
    formats: Sequence[FormatName],
    scale: float,
    output_dir: Path,
    basename: str,
    settle_ms: int = 400,
) -> RenderOutcome:
    """Write the requested artifact formats for a validated widget payload."""
    files: list[FileArtifact] = []
    warnings: list[str] = []
    png_bytes: bytes | None = None

    exported_svg: str | None = None
    if widget.kind == "svg":
        exported_svg = build_exportable_svg(widget.widget_code, theme)
        if exported_svg is None:
            raise RenderPipelineError("Widget kind is 'svg' but widget_code does not start with <svg; cannot export.")

    if "svg" in formats:
        if exported_svg is None:
            warnings.append("SVG export skipped: widget kind is 'html'.")
        else:
            artifact = _write_file(
                output_dir / f"{basename}.{theme}.svg",
                exported_svg.encode("utf-8"),
            )
            files.append(artifact)

    if "html" in formats:
        document = build_standalone_document(
            content=exported_svg if exported_svg is not None else widget.widget_code,
            title=widget.title,
            theme=theme,
        )
        artifact = _write_file(output_dir / f"{basename}.{theme}.html", document.encode("utf-8"))
        files.append(artifact)

    if "png" in formats:
        data, width, height, renderer, png_warnings = _render_png(
            widget=widget,
            theme=theme,
            scale=scale,
            settle_ms=settle_ms,
        )
        warnings.extend(png_warnings)
        if data is not None:
            artifact = _write_file(output_dir / f"{basename}.{theme}.png", data)
            artifact = FileArtifact(
                format="png",
                path=artifact.path,
                bytes=artifact.bytes,
                width=width,
                height=height,
                renderer=renderer,
            )
            files.append(artifact)
            png_bytes = data

    return RenderOutcome(files=files, png_bytes=png_bytes, warnings=warnings)
