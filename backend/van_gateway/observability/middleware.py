"""Request latency and one structured log line per request.

Two details that a naive version gets wrong and this one does not.

**The route template is the label, not the path.** Labelling
`van_gateway_request_duration_ms` with `/v1/missions/9f3c.../events` produces one
time series per mission and a metrics endpoint that grows without bound —
cardinality explosion is the standard way an exporter takes down the thing it
was measuring. Starlette resolves the matched route, so the label reads
`/v1/missions/{mission_id}`. A request that matched no route is labelled
`unrouted` rather than by its path, for the same reason.

**A failed request is still measured.** Timing inside the `try` and recording in
`finally` means an exception produces a latency sample and an error line rather
than a gap; a metric that only records successes reports a system that is down as
a system that is fast.
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from van_gateway.observability import instruments
from van_gateway.observability.correlation import for_command
from van_gateway.observability.logging import log_event

LOGGER = logging.getLogger("van.request")

#: The command this request is about, when the client knows it. The correlation id
#: is *derived* from it rather than accepted from the client: a client-supplied
#: correlation id is a client-controlled log and metric field, and two clients that
#: send the same one merge two unrelated traces.
COMMAND_HEADER = b"x-van-command-id"


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    path_format = getattr(route, "path_format", None) or getattr(route, "path", None)
    return str(path_format) if path_format else "unrouted"


class MetricsMiddleware:
    """Pure ASGI rather than BaseHTTPMiddleware: the latter wraps the response in
    an anyio stream, which changes streaming behaviour and adds its own latency to
    the number being measured."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        command_id = headers.get(COMMAND_HEADER, b"").decode("latin-1") or None
        correlation_id = for_command(command_id) if command_id else None

        started = time.monotonic()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
            await send(message)

        error_class: str | None = None
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001 - re-raised below, recorded first
            error_class = type(exc).__name__
            raise
        finally:
            duration_ms = (time.monotonic() - started) * 1000.0
            status = status_holder.get("status", 500)
            result = f"{status // 100}xx" if not error_class else "exception"
            route = _route_template(scope)
            instruments.record_request(route, result, duration_ms)
            if error_class or status >= 500:
                instruments.record_error(error_class or "http_5xx", str(status))
            log_event(
                LOGGER,
                logging.WARNING if (error_class or status >= 500) else logging.INFO,
                "request",
                correlation_id=correlation_id,
                command_id=command_id,
                result=str(status),
                error_class=error_class,
                detail={
                    "method": scope.get("method"),
                    "route": route,
                    "duration_ms": round(duration_ms, 2),
                },
            )


__all__ = ["COMMAND_HEADER", "MetricsMiddleware"]
