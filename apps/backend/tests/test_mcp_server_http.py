"""HTTP transport tests: bearer gate wiring on the streamable-HTTP app."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("mcp")

from starlette.testclient import TestClient  # noqa: E402

from app.mcp.__main__ import build_http_app  # noqa: E402
from app.mcp.http_auth import BearerTokenMiddleware  # noqa: E402


@pytest.fixture(scope="module")
def auth_client() -> Iterator[TestClient]:
    # The streamable-HTTP session manager can only run once per process, so all
    # HTTP round trips share one client. base_url keeps the SDK's host check happy.
    app = build_http_app(token="secret-token")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client


def test_http_app_rejects_requests_without_bearer_token(auth_client: TestClient) -> None:
    assert auth_client.get("/mcp").status_code == 401
    assert auth_client.get("/mcp", headers={"Authorization": "Bearer wrong-token"}).status_code == 401


def test_http_app_passes_authenticated_requests_to_mcp(auth_client: TestClient) -> None:
    response = auth_client.get("/mcp", headers={"Authorization": "Bearer secret-token"})
    # 406 = reached the MCP endpoint but the request lacked MCP Accept headers.
    assert response.status_code == 406


def test_http_app_has_no_middleware_without_configured_token() -> None:
    app = build_http_app(token=None)
    assert not isinstance(app, BearerTokenMiddleware)


def test_http_app_wraps_middleware_when_token_configured() -> None:
    app = build_http_app(token="secret-token")
    assert isinstance(app, BearerTokenMiddleware)
