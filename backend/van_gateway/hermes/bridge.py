from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from van_gateway.models import DegradedCode


class HermesBridgeError(Exception):
    def __init__(self, code: str, message: str, *, retry_safe: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_safe = retry_safe


class HermesBridge:
    """Talk to Hermes profile `van` only. Never launches models directly.

    `message_agent` and `create_council` were removed on 2026-09-19 under blueprint Gate 0.
    Councils and agent messaging are canonical on the Hermes side (`hermes/bot/councils.md`,
    `hermes/bot/message_agent.md`); this bridge duplicated them and had no caller in the
    gateway. Do not reintroduce them here without a gateway-side consumer."""

    def __init__(self, base_url: str, bearer_token: str, profile: str = "van", client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.profile = profile
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"X-Hermes-Profile": self.profile}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _url(self, path: str) -> str:
        """Route through Hermes' canonical multi-profile API surface."""
        normalized = "/" + path.lstrip("/")
        profile = self.profile.strip()
        if not profile or profile == "default":
            return f"{self.base_url}{normalized}"
        return f"{self.base_url}/p/{quote(profile, safe='')}{normalized}"

    async def health(self) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=5.0)
        owns = self._client is None
        try:
            resp = await client.get(self._url("/health"), headers=self._headers(), follow_redirects=False)
            if not 200 <= resp.status_code < 300:
                return {"ok": False, "degraded": DegradedCode.HERMES_OFFLINE.value, "status_code": resp.status_code}
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("Hermes health response must be an object")
            if "ok" in data and type(data["ok"]) is not bool:
                raise ValueError("Hermes health readiness must be a boolean")
            if data.get("ok") is False:
                return {**data, "ok": False, "degraded": DegradedCode.HERMES_OFFLINE.value}
            data["ok"] = True
            data["profile"] = self.profile
            return data
        except (httpx.HTTPError, ValueError) as exc:
            return {"ok": False, "degraded": DegradedCode.HERMES_OFFLINE.value, "error": str(exc)}
        finally:
            if owns:
                await client.aclose()

    async def create_run(self, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=60.0)
        owns = self._client is None
        payload = {
            "profile": self.profile,
            "input": text,
            "metadata": metadata or {},
        }
        try:
            resp = await client.post(self._url("/v1/runs"), json=payload, headers=self._headers(), follow_redirects=False)
            if not 200 <= resp.status_code < 300:
                raise HermesBridgeError(
                    "hermes_reject", f"Hermes rejected run: HTTP {resp.status_code}",
                    retry_safe=resp.status_code in {400, 401, 403, 404, 405, 410, 413, 415, 422, 429},
                )
            data = resp.json()
            if (not isinstance(data, dict) or not isinstance(data.get("id"), str)
                or not data["id"] or data["id"] != data["id"].strip() or any(ord(c) < 32 for c in data["id"])):
                raise ValueError("Hermes run response must include a non-empty run id")
            return data
        except ValueError as exc:
            raise HermesBridgeError("hermes_outcome_unknown", "Hermes returned an invalid run receipt") from exc
        except httpx.HTTPError as exc:
            raise HermesBridgeError(
                "hermes_offline", str(exc),
                retry_safe=isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)),
            ) from exc
        finally:
            if owns:
                await client.aclose()

    async def capabilities(self) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=10.0)
        owns = self._client is None
        try:
            resp = await client.get(self._url("/v1/capabilities"), headers=self._headers(), follow_redirects=False)
            if not 200 <= resp.status_code < 300:
                raise HermesBridgeError("capabilities_unavailable", f"HTTP {resp.status_code}")
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("Hermes capability response must be an object")
            return data
        except ValueError as exc:
            raise HermesBridgeError("capabilities_unavailable", "Hermes returned an invalid capability response") from exc
        except httpx.HTTPError as exc:
            raise HermesBridgeError("hermes_offline", str(exc)) from exc
        finally:
            if owns:
                await client.aclose()
