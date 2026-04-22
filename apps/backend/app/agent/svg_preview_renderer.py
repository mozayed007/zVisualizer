from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class SvgRenderedPreview:
    mime_type: str
    data: bytes
    description: str


class SvgPreviewRenderer(Protocol):
    def render(self, svg_markup: str) -> SvgRenderedPreview | None: ...


class NoopSvgPreviewRenderer:
    def render(self, svg_markup: str) -> SvgRenderedPreview | None:
        del svg_markup
        return None


@dataclass(frozen=True, slots=True)
class _RendererBackend:
    name: str
    command_path: str


class ExternalSvgPreviewRenderer:
    def __init__(
        self,
        *,
        command_override: str | None = None,
        timeout_ms: int = 4000,
        which: Callable[[str], str | None] | None = None,
        runner: Callable[[list[str], int], None] | None = None,
    ) -> None:
        self.timeout_ms = timeout_ms
        self._which = which or shutil.which
        self._runner = runner or self._run_command
        self._backend = self._detect_backend(command_override)

    @property
    def backend_name(self) -> str | None:
        return self._backend.name if self._backend is not None else None

    def render(self, svg_markup: str) -> SvgRenderedPreview | None:
        backend = self._backend
        if backend is None:
            return None

        fd_svg, svg_path_str = tempfile.mkstemp(suffix=".svg")
        fd_png, png_path_str = tempfile.mkstemp(suffix=".png")
        os.close(fd_svg)
        os.close(fd_png)
        svg_path = Path(svg_path_str)
        png_path = Path(png_path_str)
        try:
            svg_path.write_text(svg_markup, encoding="utf-8")
            command = self._build_command(backend, svg_path, png_path)
            self._runner(command, self.timeout_ms)
            if not png_path.exists():
                return None
            data = png_path.read_bytes()
            if not data:
                return None
            return SvgRenderedPreview(
                mime_type="image/png",
                data=data,
                description=f"Rendered PNG preview generated with {backend.name}.",
            )
        except (OSError, subprocess.SubprocessError):
            return None
        finally:
            for path in (svg_path, png_path):
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    continue

    def _detect_backend(self, command_override: str | None) -> _RendererBackend | None:
        if command_override:
            return self._backend_from_path(command_override)

        for candidate in ("magick", "inkscape", "rsvg-convert"):
            resolved = self._which(candidate)
            if resolved:
                return _RendererBackend(name=candidate, command_path=resolved)
        return None

    def _backend_from_path(self, command_path: str) -> _RendererBackend | None:
        base_name = Path(command_path).name.lower()
        if base_name in {"magick", "magick.exe"}:
            return _RendererBackend(name="magick", command_path=command_path)
        if base_name in {"inkscape", "inkscape.exe"}:
            return _RendererBackend(name="inkscape", command_path=command_path)
        if base_name in {"rsvg-convert", "rsvg-convert.exe"}:
            return _RendererBackend(name="rsvg-convert", command_path=command_path)
        return None

    def _build_command(
        self,
        backend: _RendererBackend,
        svg_path: Path,
        png_path: Path,
    ) -> list[str]:
        if backend.name == "magick":
            return [backend.command_path, str(svg_path), str(png_path)]
        if backend.name == "inkscape":
            return [
                backend.command_path,
                str(svg_path),
                "--export-type=png",
                f"--export-filename={png_path}",
            ]
        return [backend.command_path, "-o", str(png_path), str(svg_path)]

    def _run_command(self, command: list[str], timeout_ms: int) -> None:
        subprocess.run(
            command,
            check=True,
            timeout=max(1, timeout_ms) / 1000,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PAGER": "cat"},
        )
