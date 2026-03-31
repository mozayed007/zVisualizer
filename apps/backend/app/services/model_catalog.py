from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from app.core.errors import ServiceUnavailableAppError
from app.core.settings import Settings
from app.models.chat import AvailableModel, ModelCatalogResponse

_MODEL_LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_CACHE_TTL = timedelta(minutes=5)


def _normalize_model_entry(raw_model: dict[str, object], default_model: str) -> AvailableModel:
    resource_name = str(raw_model.get("name") or "").strip()
    base_model_id = str(raw_model.get("baseModelId") or "").strip()
    model_id = base_model_id or resource_name.removeprefix("models/")
    display_name = str(raw_model.get("displayName") or model_id).strip() or model_id
    description = raw_model.get("description")
    input_token_limit = raw_model.get("inputTokenLimit")
    output_token_limit = raw_model.get("outputTokenLimit")
    methods = [
        str(method)
        for method in (raw_model.get("supportedGenerationMethods") or [])
        if isinstance(method, str)
    ]
    chat_compatible = "generateContent" in methods
    return AvailableModel(
        id=model_id,
        resource_name=resource_name or f"models/{model_id}",
        display_name=display_name,
        description=str(description) if isinstance(description, str) else None,
        input_token_limit=input_token_limit if isinstance(input_token_limit, int) else None,
        output_token_limit=output_token_limit if isinstance(output_token_limit, int) else None,
        supported_generation_methods=methods,
        thinking=bool(raw_model.get("thinking")),
        chat_compatible=chat_compatible,
        is_default=model_id == default_model,
    )


def _sort_models(models: list[AvailableModel]) -> list[AvailableModel]:
    return sorted(
        models,
        key=lambda model: (
            not model.chat_compatible,
            not model.is_default,
            model.display_name.lower(),
            model.id.lower(),
        ),
    )


class ModelCatalogService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: ModelCatalogResponse | None = None
        self._cache_expires_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def list_models(self, *, default_model: str) -> ModelCatalogResponse:
        now = datetime.now(UTC)
        if (
            self._cache is not None
            and self._cache_expires_at is not None
            and self._cache_expires_at > now
            and self._cache.default_model == default_model
        ):
            return self._cache

        async with self._lock:
            now = datetime.now(UTC)
            if (
                self._cache is not None
                and self._cache_expires_at is not None
                and self._cache_expires_at > now
                and self._cache.default_model == default_model
            ):
                return self._cache

            catalog = await self._fetch_models(default_model=default_model)
            self._cache = catalog
            self._cache_expires_at = now + _CACHE_TTL
            return catalog

    async def _fetch_models(self, *, default_model: str) -> ModelCatalogResponse:
        api_key = self.settings.require_google_api_key()
        params: dict[str, str | int] = {"key": api_key, "pageSize": 1000}
        collected: list[dict[str, object]] = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                while True:
                    response = await client.get(_MODEL_LIST_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    raw_models = payload.get("models", [])
                    if isinstance(raw_models, list):
                        collected.extend(item for item in raw_models if isinstance(item, dict))
                    next_page_token = payload.get("nextPageToken")
                    if not isinstance(next_page_token, str) or not next_page_token:
                        break
                    params["pageToken"] = next_page_token
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or f"Gemini API returned {exc.response.status_code}."
            raise ServiceUnavailableAppError(
                f"Could not load Gemini models: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableAppError(
                "Could not load Gemini models from the Gemini API."
            ) from exc

        catalog = ModelCatalogResponse(
            default_model=default_model,
            models=_sort_models(
                [_normalize_model_entry(raw_model, default_model) for raw_model in collected]
            ),
        )
        return catalog
