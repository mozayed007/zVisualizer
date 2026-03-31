import asyncio

from pydantic import SecretStr

from app.core.settings import Settings
from app.models.chat import ChatRequest
from app.services import model_catalog
from app.services.model_catalog import ModelCatalogService


def test_chat_request_normalizes_model_name() -> None:
    request = ChatRequest(message="hello", model="  models/gemini-2.5-flash  ")

    assert request.model == "gemini-2.5-flash"


def test_model_catalog_service_lists_and_caches_models(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    calls: list[dict[str, object]] = []
    pages = [
        {
            "models": [
                {
                    "name": "models/gemini-2.5-flash",
                    "baseModelId": "gemini-2.5-flash",
                    "displayName": "Gemini 2.5 Flash",
                    "description": "Fast chat model",
                    "inputTokenLimit": 1_048_576,
                    "outputTokenLimit": 65_536,
                    "supportedGenerationMethods": ["generateContent"],
                    "thinking": True,
                },
                {
                    "name": "models/gemini-embedding-001",
                    "baseModelId": "gemini-embedding-001",
                    "displayName": "Gemini Embedding",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ],
            "nextPageToken": "page-2",
        },
        {
            "models": [
                {
                    "name": "models/gemini-3.1-flash-lite-preview",
                    "baseModelId": "gemini-3.1-flash-lite-preview",
                    "displayName": "Gemini 3.1 Flash-Lite",
                    "supportedGenerationMethods": ["generateContent"],
                    "thinking": True,
                }
            ]
        },
    ]

    class DummyResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class DummyAsyncClient:
        async def __aenter__(self) -> "DummyAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict[str, object]) -> DummyResponse:
            assert url == model_catalog._MODEL_LIST_URL
            calls.append(dict(params))
            return DummyResponse(pages[len(calls) - 1])

    monkeypatch.setattr(model_catalog.httpx, "AsyncClient", lambda timeout: DummyAsyncClient())

    settings = Settings(_env_file=None)
    settings.google_api_key = SecretStr("test-key")
    service = ModelCatalogService(settings)

    first = asyncio.run(service.list_models(default_model="gemini-3.1-flash-lite-preview"))
    second = asyncio.run(service.list_models(default_model="gemini-3.1-flash-lite-preview"))

    assert calls == [
        {"key": "test-key", "pageSize": 1000},
        {"key": "test-key", "pageSize": 1000, "pageToken": "page-2"},
    ]
    assert first is second
    assert [model.id for model in first.models] == [
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash",
        "gemini-embedding-001",
    ]
    assert first.models[0].is_default is True
    assert first.models[0].chat_compatible is True
    assert first.models[-1].chat_compatible is False
