"""An in-process stand-in for DIAL's Development Projection API v1 (VAN-DEV-001/002).

Not a test module. It is what `test_dial_dev_*.py` put behind the gateway's DIAL client via
`httpx.MockTransport`, so the gateway is exercised over real HTTP semantics (status codes,
bodies, headers, streams) without a network. It records every request, so a test can ask
what the gateway actually sent DIAL — which is where a leaked device header or a missing
bearer would show up.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx

#: Long enough for the gateway's 32-character floor, and distinctive enough to grep for.
DIAL_TOKEN = "dial-scoped-credential-" + "Z9" * 24
DIAL_BASE_URL = "http://dial-control.test:9180"


def envelope(data: Any, *, revision: str = "sha256:rev-1", degraded: list | None = None,
             freshness_ms: int = 1800) -> dict:
    return {
        "projection_revision": revision,
        "observed_at": "2026-09-24T12:00:00Z",
        "sources": {
            "project_truth_hash": "pt-1", "stage_plan_revision": 12,
            "active_work_graph_revision": 481, "spmrf_cursor": "c-1",
            "lease_index_revision": 207, "orca_runtime_id": "orca-1",
        },
        "freshness_ms": freshness_ms,
        "degraded": degraded or [],
        "data": data,
    }


class FakeDial:
    """Routes keyed by (method, path). A value is a response, or a callable making one."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], Any] = {}
        #: When set, raised for every request instead of answering.
        self.fail_with: Exception | None = None

    def json(self, method: str, path: str, body: Any, status: int = 200) -> None:
        self.routes[(method, path)] = httpx.Response(
            status, content=json.dumps(body).encode(), headers={"content-type": "application/json"}
        )

    def raw(self, method: str, path: str, response: httpx.Response | Callable) -> None:
        self.routes[(method, path)] = response

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        route = self.routes.get((request.method, request.url.path))
        if route is None:
            return httpx.Response(404, json={"error": "not_found"})
        if callable(route):
            return route(request)
        # A fresh copy each time, because a streamed body can only be consumed once.
        return httpx.Response(route.status_code, content=route.content, headers=route.headers)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path == path]
