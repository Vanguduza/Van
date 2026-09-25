from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


class JevProjectionError(RuntimeError):
    pass


class JevProjectionClient:
    def __init__(self, *, base_url: str, token_file: str, enabled: bool, timeout_seconds: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._token_file = token_file
        self._enabled = enabled
        self._timeout = timeout_seconds

    @property
    def configured(self) -> bool:
        return self._enabled and bool(self._base_url) and bool(self._token_file)

    def _token(self) -> str:
        if not self._token_file:
            raise JevProjectionError("jev_token_file_unconfigured")
        token = Path(self._token_file).read_text(encoding="utf-8").strip()
        if not token:
            raise JevProjectionError("jev_token_empty")
        return token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        if not self.configured:
            raise JevProjectionError("jev_projection_unconfigured")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"X-Dial-Jev-Token": self._token()},
            )
        if response.status_code >= 400:
            raise JevProjectionError(f"jev_projection_http_{response.status_code}")
        body = response.json()
        if not isinstance(body, dict):
            raise JevProjectionError("jev_projection_invalid_payload")
        return body

    async def _post(self, path: str, payload: dict[str, Any]) -> dict:
        if not self.configured:
            raise JevProjectionError("jev_projection_unconfigured")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}{path}",
                json=payload,
                headers={"X-Dial-Jev-Token": self._token()},
            )
        if response.status_code >= 400:
            detail = response.text[:240]
            raise JevProjectionError(f"jev_projection_http_{response.status_code}:{detail}")
        body = response.json()
        if not isinstance(body, dict):
            raise JevProjectionError("jev_projection_invalid_payload")
        return body

    async def health(self) -> dict:
        if not self._enabled or not self._base_url:
            return {"status": "disabled", "enabled": False}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/health")
        if response.status_code >= 400:
            raise JevProjectionError(f"jev_health_http_{response.status_code}")
        body = response.json()
        return body if isinstance(body, dict) else {"status": "invalid"}

    async def status(self) -> dict:
        return await self._get("/v1/status")

    async def provider(self) -> dict:
        return await self._get("/v1/provider")

    async def modules(self) -> dict:
        return await self._get("/v1/modules")

    async def module(self, module_id: str) -> dict:
        return await self._get(f"/v1/modules/{module_id}")

    async def activity(self, *, project_id: str, limit: int = 100) -> dict:
        return await self._get("/v1/activity", {"project_id": project_id, "limit": limit})

    async def outcomes(self, *, project_id: str, limit: int = 100) -> dict:
        return await self._get("/v1/outcomes", {"project_id": project_id, "limit": limit})

    async def performance(self, *, project_id: str, module_id: str | None = None) -> dict:
        params: dict[str, Any] = {"project_id": project_id}
        if module_id:
            params["module_id"] = module_id
        return await self._get("/v1/performance", params)

    async def contribution(self, *, project_id: str, module_id: str) -> dict:
        return await self._get("/v1/contribution", {"project_id": project_id, "module_id": module_id})

    async def evaluation_packet(self, *, project_id: str, module_id: str) -> dict:
        return await self._get("/v1/evaluation/packet", {"project_id": project_id, "module_id": module_id})

    async def evaluation_proposals(self, *, module_id: str | None = None, limit: int = 100) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if module_id:
            params["module_id"] = module_id
        return await self._get("/v1/evaluation/proposals", params)

    async def transition_module(
        self, *, module_id: str, target_state: str, authority_ref: str,
        reason: str | None = None, owner_approved: bool = False,
    ) -> dict:
        return await self._post(
            f"/v1/modules/{module_id}/transition",
            {
                "to": target_state,
                "authority_ref": authority_ref,
                "reason": reason,
                "owner_approved": owner_approved,
                "evidence_refs": [authority_ref],
            },
        )

    async def global_control(
        self, *, authority_ref: str, owner_active: bool | None = None,
        bypassed: bool | None = None, project_id: str | None = None,
        project_enabled: bool | None = None, reason: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"authority_ref": authority_ref, "reason": reason}
        if owner_active is not None:
            payload["owner_active"] = owner_active
        if bypassed is not None:
            payload["bypassed"] = bypassed
        if project_id is not None:
            payload["project_id"] = project_id
        if project_enabled is not None:
            payload["project_enabled"] = project_enabled
        return await self._post("/v1/control/global", payload)
