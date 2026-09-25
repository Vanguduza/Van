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

    async def modules(self) -> dict:
        return await self._get("/v1/modules")

    async def module(self, module_id: str) -> dict:
        return await self._get(f"/v1/modules/{module_id}")

    async def outcomes(self, *, project_id: str, limit: int = 100) -> dict:
        return await self._get("/v1/outcomes", {"project_id": project_id, "limit": limit})

    async def contribution(self, *, project_id: str, module_id: str) -> dict:
        return await self._get("/v1/contribution", {"project_id": project_id, "module_id": module_id})
