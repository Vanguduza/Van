from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.auth.control_scopes import ControlScope, require_scoped_internal
from van_gateway.config import Settings


class TemporalBridgeError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class DurableStartBody(BaseModel):
    """Start one critical durable coordination workflow.

    workflow_id is supplied by the caller so retries after a lost HTTP response address
    the same Temporal execution. process_kind is a bounded semantic label, not executable
    code. Payload remains evidence/context; the Temporal worker owns only durable waits,
    retries and state, never trading/order authority.
    """

    workflow_id: str = Field(min_length=3, max_length=256)
    process_kind: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=86_400, ge=1, le=30 * 24 * 3600)


class DurableSignalBody(BaseModel):
    command: str = Field(pattern="^(COMPLETE|FAIL|CANCEL|CHECKPOINT)$")
    detail: str = Field(default="", max_length=4000)
    evidence_pointer: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class TemporalBridgeClient:
    """Narrow gateway client for the self-hosted Temporal runtime.

    No Temporal credential, namespace token or server address enters Hermes/Android. The
    runtime host exposes only this bridge and protects it with its own bearer token.
    """

    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.temporal_enabled
        self.base_url = settings.temporal_bridge_url.rstrip("/")
        self.token = settings.temporal_bridge_token
        self.timeout = settings.temporal_timeout_seconds

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.base_url) and bool(self.token)

    def _require_configured(self) -> None:
        if not self.enabled:
            raise TemporalBridgeError("TEMPORAL_DISABLED")
        if not self.base_url or not self.token:
            raise TemporalBridgeError("TEMPORAL_UNCONFIGURED")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_configured()
        headers = {"x-van-temporal-token": self.token}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    json=json,
                )
        except httpx.HTTPError as exc:
            raise TemporalBridgeError("TEMPORAL_UNREACHABLE", str(exc)) from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {"detail": response.text[:500]}
        if response.status_code >= 400:
            detail = payload.get("detail", payload)
            raise TemporalBridgeError(
                "TEMPORAL_RUNTIME_REFUSED",
                detail if isinstance(detail, str) else str(detail),
            )
        return payload

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def start(self, body: DurableStartBody) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/workflows/start",
            json=body.model_dump(mode="json"),
        )

    async def status(self, workflow_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/workflows/{workflow_id}")

    async def signal(self, workflow_id: str, body: DurableSignalBody) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/v1/workflows/{workflow_id}/signal",
            json=body.model_dump(mode="json"),
        )


class TemporalAutomationApi:
    """Internal-control surface for durable workflows selected by the automation router."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = TemporalBridgeClient(settings)
        self.router = APIRouter(prefix="/v1/automation/temporal", tags=["automation-temporal"])
        self._install()

    def _require_internal(self, token: str | None) -> None:
        require_scoped_internal(self.settings, token, ControlScope.AUTOMATION)

    @staticmethod
    def _translate(exc: TemporalBridgeError) -> HTTPException:
        status = 503 if exc.code in {
            "TEMPORAL_DISABLED", "TEMPORAL_UNCONFIGURED", "TEMPORAL_UNREACHABLE"
        } else 502
        return HTTPException(
            status_code=status,
            detail={"error": exc.code, "detail": exc.detail},
        )

    def _install(self) -> None:
        router = self.router

        @router.get("/health")
        async def temporal_health(
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            if not self.client.configured:
                return {
                    "state": "UNCONFIGURED",
                    "implemented": True,
                    "enabled": self.client.enabled,
                }
            try:
                return await self.client.health()
            except TemporalBridgeError as exc:
                raise self._translate(exc) from exc

        @router.post("/start")
        async def temporal_start(
            body: DurableStartBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                return await self.client.start(body)
            except TemporalBridgeError as exc:
                raise self._translate(exc) from exc

        @router.get("/{workflow_id}")
        async def temporal_status(
            workflow_id: str,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                return await self.client.status(workflow_id)
            except TemporalBridgeError as exc:
                raise self._translate(exc) from exc

        @router.post("/{workflow_id}/signal")
        async def temporal_signal(
            workflow_id: str,
            body: DurableSignalBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                return await self.client.signal(workflow_id, body)
            except TemporalBridgeError as exc:
                raise self._translate(exc) from exc


__all__ = [
    "DurableSignalBody",
    "DurableStartBody",
    "TemporalAutomationApi",
    "TemporalBridgeClient",
    "TemporalBridgeError",
]
