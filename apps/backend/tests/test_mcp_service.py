"""Tests for the MCP service layer (validation, render, visualize)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.mcp.models import VisualizeResultModel
from app.mcp.service import ServiceToolError, VisualizerMcpService
from app.mcp.turn import VisualTurn

SVG = (
    '<svg width="100%" viewBox="0 0 680 200">'
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6">'
    '<path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>'
    '<g class="c-purple"><rect class="box" x="40" y="60" width="220" height="90"/>'
    '<text class="th" x="150" y="95" dominant-baseline="central">Router</text></g>'
    '<path class="arr" d="M 260 105 L 420 105" marker-end="url(#arrow)"/>'
    "</svg>"
)

BAD_SVG = '<svg width="100%" viewBox="0 0 100 100"><text>no defs</text></svg>'


@pytest.fixture(scope="module")
def service() -> VisualizerMcpService:
    return VisualizerMcpService()


def test_validate_visual_accepts_contract_compliant_svg(service: VisualizerMcpService) -> None:
    report = service.validate_visual(widget_code=SVG, title="router_flow")
    assert report.valid is True
    assert report.kind == "svg"
    assert report.errors == []


def test_validate_visual_reports_violations(service: VisualizerMcpService) -> None:
    report = service.validate_visual(widget_code=BAD_SVG, title="bad_one")
    assert report.valid is False
    assert report.errors
    assert any("viewBox" in error or "defs" in error for error in report.errors)


def test_validate_visual_flags_non_snake_case_title(service: VisualizerMcpService) -> None:
    report = service.validate_visual(widget_code=SVG, title="NotSnake")
    assert report.valid is False


def test_render_visual_writes_files_and_manifest(service: VisualizerMcpService, tmp_path: Path) -> None:
    result = service.render_visual(
        widget_code=SVG,
        title="router_flow",
        formats=["svg", "html"],
        output_dir=str(tmp_path),
    )
    assert result.kind == "svg"
    svg_path = tmp_path / "router_flow.light.svg"
    html_path = tmp_path / "router_flow.light.html"
    assert svg_path.exists()
    assert html_path.exists()
    assert result.manifest_path is not None

    root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    html = html_path.read_text(encoding="utf-8")
    assert 'class="light"' in html
    assert "visualizer:prompt" in html  # standalone bridge present


def test_render_visual_rejects_invalid_code(service: VisualizerMcpService, tmp_path: Path) -> None:
    with pytest.raises(ServiceToolError):
        service.render_visual(widget_code=BAD_SVG, output_dir=str(tmp_path))


def test_render_visual_rejects_unknown_format(service: VisualizerMcpService, tmp_path: Path) -> None:
    with pytest.raises(ServiceToolError):
        service.render_visual(widget_code=SVG, formats=["pdf"], output_dir=str(tmp_path))


async def test_visualize_renders_turn_widget(
    service: VisualizerMcpService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run_visual_turn(*args, **kwargs) -> VisualTurn:  # type: ignore[no-untyped-def]
        return VisualTurn(
            status="ok",
            conversation_id="conv-9",
            title="router_flow",
            kind="svg",
            widget_code=SVG,
            loading_messages=["Rendering"],
            assistant_text="Router sends tokens to experts.",
            follow_up_chips=["Zoom in"],
        )

    monkeypatch.setattr("app.mcp.service.run_visual_turn", fake_run_visual_turn)

    result, png_bytes = await service.visualize(
        prompt="draw the MoE router",
        formats=["svg", "html"],
        output_dir=str(tmp_path),
    )

    assert isinstance(result, VisualizeResultModel)
    assert result.status == "ok"
    assert result.conversation_id == "conv-9"
    assert result.title == "router_flow"
    assert result.widget_code == SVG
    assert png_bytes is None
    assert (tmp_path / "router_flow.light.svg").exists()
    manifest = (tmp_path / "manifest.json").read_text(encoding="utf-8")
    assert "mcp:visualize" in manifest


async def test_visualize_without_widget_returns_no_visual(
    service: VisualizerMcpService, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run_visual_turn(*args, **kwargs) -> VisualTurn:  # type: ignore[no-untyped-def]
        return VisualTurn(
            status="no_visual",
            conversation_id="conv-10",
            assistant_text="No visual this time.",
            warnings=["The agent answered without producing a compliant visual for this turn."],
        )

    monkeypatch.setattr("app.mcp.service.run_visual_turn", fake_run_visual_turn)

    result, png_bytes = await service.visualize(prompt="draw something")
    assert result.status == "no_visual"
    assert result.files == []
    assert png_bytes is None


async def test_visualize_surfaces_turn_errors(service: VisualizerMcpService, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mcp.turn import TurnError

    async def fake_run_visual_turn(*args, **kwargs) -> VisualTurn:  # type: ignore[no-untyped-def]
        return VisualTurn(
            status="no_visual",
            error=TurnError(title="RATE_LIMITED", detail="Too many requests"),
        )

    monkeypatch.setattr("app.mcp.service.run_visual_turn", fake_run_visual_turn)

    with pytest.raises(ServiceToolError, match="RATE_LIMITED"):
        await service.visualize(prompt="draw something")


async def test_visualize_times_out(service: VisualizerMcpService, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    async def slow_run_visual_turn(*args, **kwargs) -> VisualTurn:  # type: ignore[no-untyped-def]
        await asyncio.sleep(10)
        raise AssertionError("unreachable")

    monkeypatch.setattr("app.mcp.service.run_visual_turn", slow_run_visual_turn)

    with pytest.raises(ServiceToolError, match="budget"):
        await service.visualize(prompt="draw something", timeout_s=0.05)


async def test_capabilities_reports_agents_and_renderers(service: VisualizerMcpService) -> None:
    capabilities = await service.capabilities()
    agent_ids = {agent.id for agent in capabilities.agents}
    assert {"visualizer", "svg"} <= agent_ids
    assert capabilities.default_agent_id == "visualizer"
    assert capabilities.artifact_root


def test_list_svg_templates_lists_library(service: VisualizerMcpService) -> None:
    templates = service.list_svg_templates()
    if not templates:
        pytest.skip("SVG template library is not present in this checkout (data/ is gitignored)")
    assert all(template.id.endswith(".svg") for template in templates)
    assert all(template.category for template in templates)


def test_list_svg_templates_query_filter(service: VisualizerMcpService) -> None:
    templates = service.list_svg_templates()
    if not templates:
        pytest.skip("SVG template library is not present in this checkout (data/ is gitignored)")
    target = templates[0]
    filtered = service.list_svg_templates(query=target.category, limit=5)
    assert filtered
    assert len(filtered) <= 5


def test_get_svg_template_round_trips_source(service: VisualizerMcpService) -> None:
    templates = service.list_svg_templates()
    if not templates:
        pytest.skip("SVG template library is not present in this checkout (data/ is gitignored)")
    detail = service.get_svg_template(template_id=templates[0].id)
    assert "<svg" in detail.svg_source
    with pytest.raises(ServiceToolError):
        service.get_svg_template(template_id="../../etc/passwd")
