from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil

from app.core.errors import RateLimitAppError, ValidationAppError
from app.core.settings import Settings


def estimate_tokens(text: str) -> int:
    return max(1, ceil(len(text) / 4))


@dataclass(slots=True)
class TokenReservation:
    created_at: datetime
    reserved_tokens: int


@dataclass(slots=True)
class DailyReservation:
    created_at: datetime


class GeminiRateLimiter:
    """Per-client (IP / forwarded-for) RPM, TPM, and RPD limits."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._minute_requests: dict[str, deque[datetime]] = {}
        self._minute_tokens: dict[str, deque[TokenReservation]] = {}
        self._day_requests: dict[str, deque[DailyReservation]] = {}

    def _deques(
        self, client_id: str
    ) -> tuple[deque[datetime], deque[TokenReservation], deque[DailyReservation]]:
        if client_id not in self._minute_requests:
            self._minute_requests[client_id] = deque()
            self._minute_tokens[client_id] = deque()
            self._day_requests[client_id] = deque()
        return (
            self._minute_requests[client_id],
            self._minute_tokens[client_id],
            self._day_requests[client_id],
        )

    def check_and_reserve(self, estimated_input_tokens: int, *, client_id: str) -> None:
        if estimated_input_tokens > self.settings.google_max_input_tokens:
            raise ValidationAppError(
                "Prompt plus retained history is too large for the configured "
                "Gemini budget.",
                details={
                    "estimated_input_tokens": estimated_input_tokens,
                    "max_input_tokens": self.settings.google_max_input_tokens,
                },
            )

        minute_requests, minute_tokens, day_requests = self._deques(client_id)

        now = datetime.now(UTC)
        minute_cutoff = now - timedelta(minutes=1)
        day_cutoff = now - timedelta(days=1)

        while minute_requests and minute_requests[0] < minute_cutoff:
            minute_requests.popleft()
        while minute_tokens and minute_tokens[0].created_at < minute_cutoff:
            minute_tokens.popleft()
        while day_requests and day_requests[0].created_at < day_cutoff:
            day_requests.popleft()

        if len(minute_requests) >= self.settings.google_requests_per_minute_limit:
            retry_after_seconds = max(
                1,
                ceil((minute_requests[0] + timedelta(minutes=1) - now).total_seconds()),
            )
            raise RateLimitAppError(retry_after_seconds)

        if len(day_requests) >= self.settings.google_requests_per_day_limit:
            retry_after_seconds = max(
                1,
                ceil((day_requests[0].created_at + timedelta(days=1) - now).total_seconds()),
            )
            raise RateLimitAppError(retry_after_seconds)

        reserved_tokens = estimated_input_tokens + self.settings.google_reserved_output_tokens
        minute_tokens_used = sum(item.reserved_tokens for item in minute_tokens)
        if minute_tokens_used + reserved_tokens > self.settings.google_tokens_per_minute_limit:
            retry_after_seconds = max(
                1,
                ceil(
                    (
                        minute_tokens[0].created_at + timedelta(minutes=1) - now
                    ).total_seconds()
                ),
            )
            raise RateLimitAppError(retry_after_seconds)

        minute_requests.append(now)
        minute_tokens.append(
            TokenReservation(created_at=now, reserved_tokens=reserved_tokens)
        )
        day_requests.append(DailyReservation(created_at=now))
