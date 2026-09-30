"""CLI entrypoint for the visualizer MCP server.

python -m app.mcp --transport stdio
python -m app.mcp --transport http --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

import uvicorn

from app.core.settings import get_settings
from app.mcp.http_auth import BearerTokenMiddleware
from app.mcp.server import mcp

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def build_http_app(*, token: str | None) -> Any:
    """Streamable-HTTP ASGI app, optionally gated by a static bearer token."""
    app = mcp.streamable_http_app()
    if token:
        return BearerTokenMiddleware(app, token)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(prog="visualizer-mcp", description="Visualizer-agent MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="Transport: stdio for local agents, http for streamable-http clients (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port (default: 8765)")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    settings = get_settings()
    chat_api_key = settings.chat_api_key
    if chat_api_key is None and args.host not in _LOCAL_HOSTS:
        logger.warning(
            "mcp-http-unauthenticated-bind",
            extra={
                "extra_data": {
                    "host": args.host,
                    "detail": "CHAT_API_KEY is not set; anyone who can reach this port can call the agent.",
                }
            },
        )
    app = build_http_app(token=chat_api_key.get_secret_value() if chat_api_key is not None else None)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
