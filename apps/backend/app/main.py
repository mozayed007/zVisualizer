from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware import Middleware

from app.core.errors import AppError, NotFoundAppError
from app.core.logging import configure_logging
from app.core.settings import BACKEND_ENV_PATH, ROOT_ENV_PATH, get_settings
from app.models.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.model_catalog import ModelCatalogService

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)
chat_service = ChatService(settings=settings)
model_catalog_service = ModelCatalogService(settings=settings)

_SSE_DONE = "data: [DONE]\n\n"
_bearer = HTTPBearer(auto_error=False)


def _sse_with_done(body: AsyncIterator[str]) -> AsyncIterator[str]:
    async def gen() -> AsyncIterator[str]:
        async for chunk in body:
            yield chunk
        yield _SSE_DONE

    return gen()


async def _verify_chat_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    expected = settings.chat_api_key
    if expected is None:
        return
    token = credentials.credentials if credentials else ""
    if token != expected.get_secret_value():
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _client_id_from_request(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("app-started", extra={"extra_data": {"environment": settings.environment}})
    yield
    logger.info("app-stopped")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    middleware=[
        Middleware(
            cast(Any, CORSMiddleware),
            allow_origins=[settings.frontend_origin],
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
    ],
)


@app.middleware("http")
async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(NotFoundAppError)
async def not_found_handler(request: Request, exc: NotFoundAppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(getattr(request.state, "request_id", None)),
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "app-error",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "extra_data": exc.to_dict(getattr(request.state, "request_id", None)),
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(getattr(request.state, "request_id", None)),
    )


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def readiness() -> JSONResponse:
    checks = {
        "config": "ok",
        "google_api_key": "ok" if settings.google_api_key is not None else "missing",
    }
    status_code = 200 if checks["google_api_key"] == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if status_code == 200 else "degraded",
            "checks": checks,
        },
    )


@app.get("/api/runtime")
async def runtime_status() -> dict[str, object]:
    primary_model = chat_service._resolve_primary_model_name()
    return {
        "ready": settings.google_api_key is not None,
        "environment": settings.environment,
        "model": primary_model,
        "configuredModel": chat_service.config.agent.model,
        "fallbackModel": settings.resolve_google_visual_recovery_model_name(primary_model),
        "limits": {
            "requestsPerMinute": settings.google_requests_per_minute_limit,
            "tokensPerMinute": settings.google_tokens_per_minute_limit,
            "requestsPerDay": settings.google_requests_per_day_limit,
            "maxInputTokens": settings.google_max_input_tokens,
            "reservedOutputTokens": settings.google_reserved_output_tokens,
            "maxHistoryTokens": settings.google_max_history_tokens,
        },
        "envSources": [
            str(ROOT_ENV_PATH),
            str(BACKEND_ENV_PATH),
        ],
    }


@app.get("/api/models")
async def available_models() -> dict[str, object]:
    default_model = chat_service._resolve_primary_model_name()
    catalog = await model_catalog_service.list_models(default_model=default_model)
    return {
        "defaultModel": catalog.default_model,
        "models": [model.model_dump(by_alias=False) for model in catalog.models],
    }


@app.post("/api/chat")
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    _: None = Depends(_verify_chat_api_key),
) -> StreamingResponse:
    client_id = _client_id_from_request(request)
    if payload.conversation_id is not None:
        existing = await chat_service.repository.get(payload.conversation_id)
        if existing is None:
            raise NotFoundAppError("Conversation", payload.conversation_id)

    return StreamingResponse(
        _sse_with_done(chat_service.stream_chat(payload, client_id=client_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
