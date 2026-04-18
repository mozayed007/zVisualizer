from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

# Redact query-string secrets (e.g. Google ?key=, generic api_key / token / access_token /
# authorization). Matches the value up to the next '&' or whitespace / quote boundary so we
# don't eat the rest of the structured log line.
_SECRET_QUERY_PATTERN = re.compile(
    r"(?i)(?P<name>key|api_key|apikey|access_token|auth_token|token|authorization)"
    r"=(?P<value>[^&\s\"']+)"
)
_REDACTED = "[REDACTED]"


def _redact_secrets(value: str) -> str:
    return _SECRET_QUERY_PATTERN.sub(lambda m: f"{m.group('name')}={_REDACTED}", value)


class SecretRedactionFilter(logging.Filter):
    """Strip secret-looking query parameters (key=..., token=...) from log records.

    Third-party libraries such as ``httpx`` log request URLs at INFO, which in the
    ``google-genai`` case includes the raw ``?key=<GOOGLE_API_KEY>`` in plaintext.
    This filter runs before formatting so both `msg` and rendered `args` are scrubbed.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "=" in record.msg:
            record.msg = _redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    _redact_secrets(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    key: _redact_secrets(val) if isinstance(val, str) else val
                    for key, val in record.args.items()
                }
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id is not None:
            payload["request_id"] = request_id
        extra = getattr(record, "extra_data", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = _redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactionFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    # Also install the filter on the root logger so propagated records from
    # uvicorn/httpx are scrubbed even before reaching the handler.
    for existing_filter in list(root_logger.filters):
        if isinstance(existing_filter, SecretRedactionFilter):
            root_logger.removeFilter(existing_filter)
    root_logger.addFilter(SecretRedactionFilter())
