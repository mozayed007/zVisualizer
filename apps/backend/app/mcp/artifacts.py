"""Artifact storage layout for MCP renders.

    <root>/<conversation_id or "manual">/<widget_title>/
        manifest.json
        <widget_title>.<theme>.svg
        <widget_title>.<theme>.png
        <widget_title>.<theme>.html

Default root: ~/.visualizer-agent/artifacts, overridable per call (`output_dir`)
or globally with VISUALIZER_MCP_ARTIFACT_DIR.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import orjson

ARTIFACT_DIR_ENV = "VISUALIZER_MCP_ARTIFACT_DIR"
MANUAL_GROUP = "manual"

_SEGMENT_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_SEGMENT_LENGTH = 80


def default_artifact_root() -> Path:
    override = os.environ.get(ARTIFACT_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".visualizer-agent" / "artifacts"


def sanitize_segment(value: str) -> str:
    cleaned = _SEGMENT_SANITIZE_PATTERN.sub("_", value.strip())
    cleaned = cleaned.strip("._-")
    if not cleaned:
        return "unnamed"
    return cleaned[:_MAX_SEGMENT_LENGTH]


def widget_output_dir(*, root: Path, conversation_id: str | None, title: str) -> Path:
    group = sanitize_segment(conversation_id) if conversation_id else MANUAL_GROUP
    return root.expanduser() / group / sanitize_segment(title)


def write_manifest(*, directory: Path, payload: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))
    return path
