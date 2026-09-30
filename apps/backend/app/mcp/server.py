"""FastMCP server exposing the visualizer agent and its rendered outputs.

Run:
    visualizer-mcp --transport stdio          # local coding agents
    visualizer-mcp --transport http --port 8765
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from typing import Any, Literal

import orjson
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.utilities.types import Image
from mcp.types import ContentBlock, TextContent

from app.core.logging import configure_logging
from app.mcp.service import ServiceToolError, VisualizerMcpService

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = (
    "Visual explanation tools backed by the visualizer-agent. Use `visualize` to generate an "
    "illustration or interactive visual from a prompt; it writes .svg/.png/.html artifacts to disk "
    "and returns their paths. Use `validate_visual` and `render_visual` to check or re-render "
    "existing widget code without calling the model. Widget code must follow the host design "
    "contract: SVG with viewBox '0 0 680 H', width '100%', arrow marker defs, text classes "
    "t/ts/th; HTML fragments starting with <style>, CDN scripts only from the allowlisted hosts."
)

mcp = FastMCP(
    "visualizer-agent",
    instructions=SERVER_INSTRUCTIONS,
    host="127.0.0.1",
    port=8765,
)


@lru_cache(maxsize=1)
def get_service() -> VisualizerMcpService:
    # MCP stdio reserves stdout for JSON-RPC; logs must go to stderr.
    configure_logging(stream=sys.stderr)
    return VisualizerMcpService()


def _text_block(payload: str) -> list[ContentBlock]:
    return [TextContent(type="text", text=payload)]


async def _report(ctx: Context[Any, Any, Any], message: str) -> None:
    try:
        await ctx.info(message)
    except Exception:  # pragma: no cover - client may not accept logging
        logger.debug("mcp-progress-report-failed", exc_info=True)


@mcp.tool(structured_output=False)
async def visualize(
    prompt: str,
    ctx: Context[Any, Any, Any],
    agent_id: str = "visualizer",
    model: str | None = None,
    subject: str | None = None,
    conversation_id: str | None = None,
    theme: Literal["light", "dark"] = "light",
    formats: list[Literal["svg", "png", "html"]] | None = None,
    scale: float = 2.0,
    output_dir: str | None = None,
    include_code: bool = True,
    inline_image: bool = True,
    timeout_s: float = 240.0,
    settle_ms: int = 400,
) -> list[ContentBlock]:
    """Generate a visual (SVG illustration or interactive HTML widget) for a prompt.

    Returns artifact file paths (svg/png/html) plus the validated widget code. Pass the returned
    conversation_id back to continue the same thread. Set output_dir to write files into a project
    folder (for example ./docs/assets); otherwise files land in the artifact root.
    """
    service = get_service()

    async def progress(message: str) -> None:
        await _report(ctx, message)

    try:
        result, png_bytes = await service.visualize(
            prompt=prompt,
            agent_id=agent_id,
            model=model,
            subject=subject,
            conversation_id=conversation_id,
            theme=theme,
            formats=formats,
            scale=scale,
            output_dir=output_dir,
            include_code=include_code,
            timeout_s=timeout_s,
            settle_ms=settle_ms,
            on_progress=progress,
        )
    except ServiceToolError as exc:
        raise ToolError(exc.message) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    blocks: list[ContentBlock] = _text_block(result.model_dump_json(indent=2))
    if inline_image and png_bytes:
        blocks.append(Image(data=png_bytes, format="png").to_image_content())
    return blocks


@mcp.tool(structured_output=False)
def render_visual(
    widget_code: str,
    ctx: Context[Any, Any, Any],
    title: str | None = None,
    template_id: str | None = None,
    agent_id: str | None = None,
    theme: Literal["light", "dark"] = "light",
    formats: list[Literal["svg", "png", "html"]] | None = None,
    scale: float = 2.0,
    output_dir: str | None = None,
    settle_ms: int = 400,
) -> list[ContentBlock]:
    """Validate and render existing widget code into files. No model call.

    Use for widget code you already have (from a previous visualize result, a conversation, or
    hand-authored SVG/HTML). Pass template_id for svg-agent template instances.
    """
    del ctx  # no progress reporting needed for a local render
    service = get_service()
    try:
        result = service.render_visual(
            widget_code=widget_code,
            title=title,
            template_id=template_id,
            agent_id=agent_id,
            theme=theme,
            formats=formats,
            scale=scale,
            output_dir=output_dir,
            settle_ms=settle_ms,
        )
    except ServiceToolError as exc:
        raise ToolError(exc.message) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return _text_block(result.model_dump_json(indent=2))


@mcp.tool(structured_output=False)
def validate_visual(
    widget_code: str,
    ctx: Context[Any, Any, Any],
    title: str | None = None,
    template_id: str | None = None,
    agent_id: str | None = None,
) -> list[ContentBlock]:
    """Check widget code against the platform contract without rendering.

    Returns valid=true/false plus violations. Cheap preflight when you are authoring SVG/HTML
    yourself and want to know what would be rejected.
    """
    del ctx
    service = get_service()
    result = service.validate_visual(
        widget_code=widget_code,
        title=title,
        template_id=template_id,
        agent_id=agent_id,
    )
    return _text_block(result.model_dump_json(indent=2))


@mcp.tool(structured_output=False)
async def get_capabilities(ctx: Context[Any, Any, Any]) -> list[ContentBlock]:
    """List available agents, renderers on this machine, and the artifact root."""
    del ctx
    service = get_service()
    result = await service.capabilities()
    return _text_block(result.model_dump_json(indent=2))


@mcp.tool(structured_output=False)
def list_svg_templates(
    ctx: Context[Any, Any, Any],
    query: str | None = None,
    limit: int = 100,
) -> list[ContentBlock]:
    """List SVG template ids for the `svg` agent (optional query filter)."""
    del ctx
    service = get_service()
    try:
        templates = service.list_svg_templates(query=query, limit=limit)
    except ServiceToolError as exc:
        raise ToolError(exc.message) from exc
    payload = orjson.dumps([template.model_dump(mode="json") for template in templates], option=orjson.OPT_INDENT_2)
    return _text_block(payload.decode("utf-8"))


@mcp.tool(structured_output=False)
def get_svg_template(template_id: str, ctx: Context[Any, Any, Any]) -> list[ContentBlock]:
    """Fetch one SVG template's source and metadata. Pair with render_visual(template_id=...)."""
    del ctx
    service = get_service()
    try:
        template = service.get_svg_template(template_id=template_id)
    except ServiceToolError as exc:
        raise ToolError(exc.message) from exc
    return _text_block(template.model_dump_json(indent=2))
