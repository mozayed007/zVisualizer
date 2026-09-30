"""Bearer-token gate for the MCP streamable-HTTP transport.

Static-token auth matching the backend's CHAT_API_KEY contract: when the key is
configured, every HTTP request must send `Authorization: Bearer <key>`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope

ScopeDict = MutableMapping[str, Any]
Message = MutableMapping[str, Any]


class BearerTokenMiddleware:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._expected = f"Bearer {token}"

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Callable[[Message], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        if headers.get("authorization") != self._expected:
            response = JSONResponse(
                {"title": "UNAUTHORIZED", "detail": "Missing or invalid Authorization bearer token."},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
