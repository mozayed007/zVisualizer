"""End-to-end test over the real stdio MCP transport.

No Gemini calls: `validate_visual` and `render_visual` are fully local.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]

SVG = (
    '<svg width="100%" viewBox="0 0 680 200">'
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6">'
    '<path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>'
    '<g class="c-purple"><rect class="box" x="40" y="60" width="220" height="90"/>'
    '<text class="th" x="150" y="95" dominant-baseline="central">Router</text></g>'
    '<path class="arr" d="M 260 105 L 420 105" marker-end="url(#arrow)"/>'
    "</svg>"
)

EXPECTED_TOOLS = {
    "visualize",
    "render_visual",
    "validate_visual",
    "get_capabilities",
    "list_svg_templates",
    "get_svg_template",
}


async def test_stdio_server_round_trip(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp", "--transport", "stdio"],
        cwd=str(BACKEND_ROOT),
        env={**os.environ},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert EXPECTED_TOOLS <= tool_names

            validation = await session.call_tool(
                "validate_visual",
                {"widget_code": SVG, "title": "router_flow"},
            )
            assert validation.isError is False
            assert '"valid": true' in validation.content[0].text

            render = await session.call_tool(
                "render_visual",
                {
                    "widget_code": SVG,
                    "title": "router_flow",
                    "formats": ["svg", "html"],
                    "output_dir": str(tmp_path),
                },
            )
            assert render.isError is False
            assert (tmp_path / "router_flow.light.svg").exists()
            assert (tmp_path / "router_flow.light.html").exists()

            capabilities = await session.call_tool("get_capabilities", {})
            assert capabilities.isError is False
            assert '"default_agent_id": "visualizer"' in capabilities.content[0].text
