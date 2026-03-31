from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    message: str
    code: str
    status_code: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, request_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.code,
            "status": self.status_code,
            "detail": self.message,
        }
        if request_id is not None:
            payload["request_id"] = request_id
        if self.details:
            payload["details"] = self.details
        return payload


class ValidationAppError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            details=details or {},
        )


class NotFoundAppError(AppError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code="NOT_FOUND",
            status_code=HTTPStatus.NOT_FOUND,
        )


class RateLimitAppError(AppError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            message="Rate limit exceeded",
            code="RATE_LIMITED",
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            details={"retry_after_seconds": retry_after_seconds},
        )


class ServiceUnavailableAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )
