"""Read-only public web-acquisition runtime adapter.

This adapter is intentionally separate from BrowserSessionBroker: it has no
credential/profile mutation surface. Account-visible acquisition remains in the
existing Browser Harness/Stagehand plane.
"""
from __future__ import annotations

from typing import Any

import httpx

from van_gateway.automation.external_runtime import (
    ExternalRuntimeRegistry,
    ExternalRuntimeStatus,
)
from van_gateway.browser.acquisition import WebWorkItem


class AcquisitionRuntimeError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class HttpAcquisitionRuntimeAdapter:
    CAPABILITY = "web_acquisition"

    def __init__(
        self,
        registry: ExternalRuntimeRegistry,
        *,
        base_url: str,
        enabled: bool,
        expected_version: str | None = None,
        timeout_seconds: float = 65.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.registry = registry
        self.base_url = (base_url or "").rstrip("/")
        self.enabled = enabled
        self.expected_version = expected_version
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def _assert_usable(self) -> None:
        if not self.enabled:
            raise AcquisitionRuntimeError("WEB_ACQUISITION_DISABLED")
        if not self.configured:
            raise AcquisitionRuntimeError("WEB_ACQUISITION_UNCONFIGURED")

    @staticmethod
    def _envelope(item: WebWorkItem, **extra: Any) -> dict[str, Any]:
        if item.profile_alias != "public_research":
            raise AcquisitionRuntimeError("WEB_ACQUISITION_PUBLIC_PROFILE_REQUIRED")
        return {
            "mode": "READ_ONLY_ACQUISITION",
            "item_id": item.item_id,
            "target_domain": item.domain,
            "url": item.canonical_url,
            **extra,
        }

    async def _call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        self._assert_usable()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout_seconds or self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise AcquisitionRuntimeError("WEB_ACQUISITION_UNAVAILABLE", str(exc)) from exc
        if response.status_code >= 400:
            try:
                detail = str(response.json().get("error") or response.status_code)
            except Exception:
                detail = str(response.status_code)
            typed = {
                "CRAWLEE_BUSY",
                "CRAWLEE_TIMEOUT",
                "CRAWLEE_CRAWL_FAILED",
                "CRAWLEE_RUNTIME_UNAVAILABLE",
                "SCRAPLING_HTTP_FAILED",
                "SCRAPLING_BROWSER_FAILED",
                "KATANA_RUNTIME_UNAVAILABLE",
                "KATANA_RECON_FAILED",
                "NON_PUBLIC_DESTINATION_FORBIDDEN",
                "CROSS_DOMAIN_REDIRECT_REQUIRES_RECON",
                "SENSITIVE_QUERY_FORBIDDEN",
            }
            code = detail if detail in typed else "WEB_ACQUISITION_REQUEST_FAILED"
            raise AcquisitionRuntimeError(code, detail)
        data = response.json()
        if not isinstance(data, dict):
            raise AcquisitionRuntimeError("WEB_ACQUISITION_RESPONSE_INVALID")
        if data.get("contains_secrets") is not False:
            raise AcquisitionRuntimeError("WEB_ACQUISITION_SECRET_BOUNDARY_VIOLATION")
        return dict(data)

    async def probe_health(self) -> dict[str, Any]:
        self._assert_usable()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=min(self.timeout_seconds, 10.0),
                transport=self.transport,
            ) as client:
                response = await client.get("/health")
        except httpx.HTTPError as exc:
            raise AcquisitionRuntimeError("WEB_ACQUISITION_UNAVAILABLE", str(exc)) from exc
        if response.status_code >= 400:
            raise AcquisitionRuntimeError(
                "WEB_ACQUISITION_HEALTH_FAILED", str(response.status_code)
            )
        data = response.json()
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise AcquisitionRuntimeError("WEB_ACQUISITION_HEALTH_INVALID")
        if data.get("auth_surface") is not False:
            raise AcquisitionRuntimeError("WEB_ACQUISITION_AUTH_SURFACE_FORBIDDEN")
        if data.get("challenge_solver_enabled") is not False:
            raise AcquisitionRuntimeError("WEB_ACQUISITION_CHALLENGE_SOLVER_FORBIDDEN")
        return dict(data)

    async def fetch_http(self, item: WebWorkItem) -> dict[str, Any]:
        return await self._call("/fetch/http", self._envelope(item))

    async def fetch_browser(self, item: WebWorkItem) -> dict[str, Any]:
        return await self._call("/fetch/browser", self._envelope(item))

    async def recon(self, item: WebWorkItem, *, depth: int = 2) -> dict[str, Any]:
        depth = max(1, min(int(depth), 3))
        return await self._call("/recon/katana", self._envelope(item, depth=depth))

    async def crawl(
        self,
        item: WebWorkItem,
        *,
        max_pages: int = 100,
        max_depth: int = 3,
        max_concurrency: int = 6,
        max_tasks_per_minute: int = 120,
        timeout_seconds: int = 300,
        respect_robots_txt: bool = True,
    ) -> dict[str, Any]:
        bounded_timeout = max(30, min(int(timeout_seconds), 1800))
        return await self._call(
            "/crawl/crawlee",
            self._envelope(
                item,
                max_pages=max(1, min(int(max_pages), 1000)),
                max_depth=max(0, min(int(max_depth), 6)),
                max_concurrency=max(1, min(int(max_concurrency), 12)),
                max_tasks_per_minute=max(1, min(int(max_tasks_per_minute), 240)),
                timeout_seconds=bounded_timeout,
                respect_robots_txt=bool(respect_robots_txt),
            ),
            timeout_seconds=bounded_timeout + 15,
        )

    async def status(self) -> ExternalRuntimeStatus:
        return await self.registry.resolve(
            capability=self.CAPABILITY,
            configured=self.configured,
            egress_enabled=self.enabled,
            credential_locus="none_public_read_only",
            expected_version=self.expected_version,
            policy_enabled=self.enabled,
            degraded_code="WEB_ACQUISITION_UNAVAILABLE",
        )


__all__ = ["AcquisitionRuntimeError", "HttpAcquisitionRuntimeAdapter"]
