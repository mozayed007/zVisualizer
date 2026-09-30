"""Tests for MCP artifact storage layout and manifest writing."""

from __future__ import annotations

import orjson

from app.mcp.artifacts import (
    MANUAL_GROUP,
    sanitize_segment,
    widget_output_dir,
    write_manifest,
)


def test_sanitize_segment_blocks_path_traversal() -> None:
    assert sanitize_segment("../../etc/passwd") == "etc_passwd"
    assert "/" not in sanitize_segment("a/b")
    assert "\\" not in sanitize_segment("a\\b")
    assert sanitize_segment("!!!") == "unnamed"
    assert sanitize_segment("  spaced title  ") == "spaced_title"


def test_sanitize_segment_bounds_length() -> None:
    assert len(sanitize_segment("x" * 500)) <= 80


def test_widget_output_dir_uses_conversation_group(tmp_path) -> None:
    directory = widget_output_dir(root=tmp_path, conversation_id="abc-123", title="my visual")
    assert directory == tmp_path / "abc-123" / "my_visual"


def test_widget_output_dir_falls_back_to_manual_group(tmp_path) -> None:
    directory = widget_output_dir(root=tmp_path, conversation_id=None, title="my_visual")
    assert directory == tmp_path / MANUAL_GROUP / "my_visual"


def test_write_manifest_round_trips_json(tmp_path) -> None:
    path = write_manifest(directory=tmp_path / "widget", payload={"title": "x", "files": []})
    assert path.exists()
    loaded = orjson.loads(path.read_bytes())
    assert loaded["title"] == "x"
    assert loaded["files"] == []
