"""Widget theme contract for out-of-browser rendering.

The CSS and token tables are generated from the frontend source of truth
(`apps/frontend/src/lib/designTokens.ts`) by `bun run export:theme`; see
`apps/frontend/scripts/export-theme.ts`. Do not hand-edit the generated assets.

`WidgetTheme.resolve()` turns `var(--token)` references into literal values so
SVG rasterizers (librsvg, ImageMagick, Inkscape) that lack CSS custom property
support can still render widgets with correct colors.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
THEME_CSS_PATH = ASSETS_DIR / "widget-theme.css"
THEME_JSON_PATH = ASSETS_DIR / "widget-theme.json"

ThemeMode = Literal["light", "dark"]

_VAR_PATTERN = re.compile(r"var\(\s*(--[A-Za-z0-9-]+)\s*\)")
_MAX_RESOLVE_DEPTH = 8


class ThemeAssetError(RuntimeError):
    """Raised when the generated theme assets are missing or malformed."""


@dataclass(frozen=True, slots=True)
class RampColors:
    fill: str
    stroke: str
    title: str
    subtitle: str


@lru_cache(maxsize=1)
def _load_theme_payload() -> dict[str, object]:
    if not THEME_CSS_PATH.exists() or not THEME_JSON_PATH.exists():
        raise ThemeAssetError(
            "Generated theme assets are missing. Run `bun run export:theme` in apps/frontend "
            f"(expected {THEME_CSS_PATH} and {THEME_JSON_PATH})."
        )
    with THEME_JSON_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or "tokens" not in payload or "ramps" not in payload:
        raise ThemeAssetError(f"Malformed theme asset: {THEME_JSON_PATH}")
    return payload


@lru_cache(maxsize=1)
def widget_theme_css() -> str:
    if not THEME_CSS_PATH.exists():
        raise ThemeAssetError(
            f"Generated theme CSS is missing. Run `bun run export:theme` in apps/frontend (expected {THEME_CSS_PATH})."
        )
    return THEME_CSS_PATH.read_text(encoding="utf-8")


class WidgetTheme:
    """Token and ramp tables for light/dark widget rendering."""

    def __init__(self) -> None:
        payload = _load_theme_payload()
        tokens = payload["tokens"]
        ramps = payload["ramps"]
        assert isinstance(tokens, dict) and isinstance(ramps, dict)
        self._light: dict[str, str] = {str(k): str(v) for k, v in dict(tokens["light"]).items()}
        self._dark_overrides: dict[str, str] = {str(k): str(v) for k, v in dict(tokens["dark"]).items()}
        self._ramps: dict[str, dict[str, str]] = {
            str(name): {str(step): str(value) for step, value in dict(steps).items()} for name, steps in ramps.items()
        }

    def tokens(self, mode: ThemeMode) -> dict[str, str]:
        if mode == "dark":
            return {**self._light, **self._dark_overrides}
        return dict(self._light)

    def token_value(self, mode: ThemeMode, name: str) -> str | None:
        return self.tokens(mode).get(name)

    def resolve(self, value: str | None, mode: ThemeMode) -> str | None:
        """Replace var(--token) references with literal values for the given mode.

        Unknown references are left untouched; callers should treat any remaining
        `var(` as "unresolved" and degrade gracefully.
        """
        if value is None or "var(" not in value:
            return value
        token_map = self.tokens(mode)
        resolved = value
        for _ in range(_MAX_RESOLVE_DEPTH):
            match = _VAR_PATTERN.search(resolved)
            if match is None:
                break
            replacement = token_map.get(match.group(1))
            if replacement is None:
                break
            resolved = resolved[: match.start()] + replacement + resolved[match.end() :]
        return resolved

    def has_unresolved_var(self, value: str) -> bool:
        return "var(" in value

    def ramp_names(self) -> list[str]:
        return sorted(self._ramps)

    def ramp(self, name: str, mode: ThemeMode, *, variant: Literal["class", "direct"] = "class") -> RampColors:
        """Colors for a ramp class, matching buildRampClasses() in designTokens.ts.

        `class` variant: `.c-X .box` / `.c-X .th` etc. (stroke ramp[600] light,
        ramp[200] dark). `direct` variant: the documented direct-child rules
        (`.c-X>rect`), which keep stroke ramp[600] in both modes.
        """
        steps = self._ramps.get(name)
        if steps is None:
            raise KeyError(f"Unknown color ramp: {name}")
        stroke = steps["600"] if (mode == "light" or variant == "direct") else steps["200"]
        fill = steps["50"] if mode == "light" else steps["800"]
        title = steps["800"] if mode == "light" else steps["100"]
        subtitle = steps["600"] if mode == "light" else steps["200"]
        return RampColors(fill=fill, stroke=stroke, title=title, subtitle=subtitle)


@lru_cache(maxsize=1)
def widget_theme() -> WidgetTheme:
    return WidgetTheme()
