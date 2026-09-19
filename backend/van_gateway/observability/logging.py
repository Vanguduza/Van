"""Structured application logging, with the fields an incident actually needs.

P3-OBS-001: the gateway emitted no application logs at all. The audit table was the only
trace, and it records owner-authority decisions rather than what the process did, so
reconstructing a request meant reading SQLite directly and inferring the rest.

Two rules make this useful rather than noisy, and both are enforced rather than advised:

**Every line is JSON with the same shape.** A log a human greps is a log a machine cannot
aggregate, and the point of adding logging to a system this size is being able to ask "how
many commands were refused for stale project truth this week" without writing a parser.

**Secrets never reach a log line.** `SECRET_FIELDS` names them and `_redact` removes them
from any payload, including nested ones. This is belt and braces over the existing
`redact_account_args`, because the reason secrets end up in logs is that somebody logged a
dict they had not looked inside.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

#: Field names whose values are never logged, at any depth. Matched case-insensitively and
#: by substring, because the ways a token is named are numerous and the cost of being
#: over-eager here is a redacted field that did not need to be.
SECRET_FIELDS = (
    "token", "secret", "password", "passwd", "signature", "private_key", "api_key",
    "refresh_token", "access_token", "client_secret", "bearer", "authorization",
    "device_secret", "fernet", "signing_key", "verification_code", "otp", "cookie",
)

REDACTED = "[REDACTED]"

#: The fields the blueprint's Gate 11 names. Present as keys even when None, so a log
#: aggregator can rely on the shape and an absent field is distinguishable from a field
#: nobody set.
CONTEXT_FIELDS = (
    "correlation_id", "command_id", "mission_id", "device_id", "action_class",
    "principal", "result", "degraded_code", "error_class",
)


def _redact(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in SECRET_FIELDS):
                out[key] = REDACTED
            else:
                out[key] = _redact(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(item, depth + 1) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the context fields always present."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": "van-gateway",
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            payload[field] = getattr(record, field, None)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload["detail"] = _redact(extra)
        if record.exc_info:
            payload["error_class"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


def configure(level: str = "INFO", stream=None) -> logging.Logger:
    """Install the formatter once. Safe to call repeatedly."""
    root = logging.getLogger("van")
    root.setLevel(level.upper())
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler(stream or sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.propagate = False
    return root


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    detail: dict[str, Any] | None = None,
    **context: Any,
) -> None:
    """Emit one structured line. Unknown context keys go into `detail` rather than being
    dropped, because a field nobody declared is usually the one that mattered."""
    known = {k: context.pop(k, None) for k in CONTEXT_FIELDS}
    payload = dict(detail or {})
    payload.update(context)
    logger.log(level, message, extra={**known, "extra_fields": payload or None})


__all__ = [
    "CONTEXT_FIELDS",
    "REDACTED",
    "SECRET_FIELDS",
    "JsonFormatter",
    "configure",
    "log_event",
]
