"""Rev 1.3 §§38, 157-158, 372-374, 404 — the local n8n management client.

§38: the local API is VAN's **deployment target, not Hermes's direct tool**.
Nothing in this module is reachable from a Hermes prompt; it is called by the
AutomationCompiler after an artifact has been validated.

The client fails closed in every direction it can:

* no base URL or API key configured → every call raises, nothing silently no-ops;
* the URL must resolve to loopback or a private interface (§14) — a management
  API on a public address is refused rather than used;
* dispatch disabled by feature flag → refused before any socket is opened.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from van_gateway.automation.external_runtime import (
    ExternalRuntimeRegistry,
    ExternalRuntimeStatus,
    RuntimeState,
)


class N8nClientError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class N8nManagementClient:
    """Create/update/activate/inspect workflows on the local n8n instance."""

    CAPABILITY = "n8n"
    #: §158 — bounded retry. Management calls are control-plane, not hot path.
    MAX_ATTEMPTS = 3
    BACKOFF_SECONDS = (0.25, 1.0)

    def __init__(
        self,
        registry: ExternalRuntimeRegistry,
        *,
        base_url: str,
        api_key: str,
        enabled: bool = False,
        expected_version: str | None = None,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_non_private_host: bool = False,
        webhook_base_url: str = "",
    ) -> None:
        self.registry = registry
        self.base_url = (base_url or "").rstrip("/")
        self._api_key = (api_key or "").strip()
        self.enabled = enabled
        self.expected_version = expected_version
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.allow_non_private_host = allow_non_private_host
        self.webhook_base_url = (webhook_base_url or "").rstrip("/")

    # ---------------------------------------------------------------- policy

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self._api_key)

    def _assert_usable(self) -> None:
        if not self.enabled:
            raise N8nClientError("AUTOMATION_FABRIC_DISABLED")
        if not self.configured:
            raise N8nClientError("AUTOMATION_FABRIC_UNCONFIGURED")
        self._assert_private_host()

    def _assert_private_host(self) -> None:
        """§14 — management API binds to loopback or a dedicated private interface.

        The test is ``is_global`` rather than ``not is_private``: Python treats
        reserved and documentation ranges (TEST-NET, benchmarking) as "private",
        which would wave through addresses that are not really a private
        interface. Refusing anything globally routable is the property §14 wants.
        """
        if self.allow_non_private_host:
            return
        host = urlparse(self.base_url).hostname or ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            try:
                address = ipaddress.ip_address(socket.gethostbyname(host))
            except (OSError, ValueError) as exc:
                raise N8nClientError("AUTOMATION_MANAGEMENT_HOST_UNRESOLVABLE", host) from exc
        if address.is_global:
            raise N8nClientError("AUTOMATION_MANAGEMENT_HOST_NOT_PRIVATE", str(address))

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
            headers={"X-N8N-API-KEY": self._api_key, "Accept": "application/json"},
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        self._assert_usable()
        last: Exception | None = None
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                async with self._client() as client:
                    response = await client.request(method, path, **kwargs)
                if response.status_code in (429, 502, 503, 504) and attempt + 1 < self.MAX_ATTEMPTS:
                    last = N8nClientError("AUTOMATION_FABRIC_UNAVAILABLE", str(response.status_code))
                elif response.status_code == 401:
                    raise N8nClientError("AUTOMATION_CREDENTIAL_EXPIRED")
                elif response.status_code >= 400:
                    raise N8nClientError("AUTOMATION_REQUEST_FAILED", f"{response.status_code}")
                else:
                    return response
            except httpx.HTTPError as exc:
                last = exc
            if attempt + 1 < self.MAX_ATTEMPTS:
                # P3-OPS-006: this was `time.sleep`, inside an `async def`, inside the
                # gateway's single event loop. Every other request the gateway was
                # serving stopped for the duration — including the owner's — because
                # one n8n call got a 503. `asyncio.sleep` yields instead of blocking.
                await asyncio.sleep(
                    self.BACKOFF_SECONDS[min(attempt, len(self.BACKOFF_SECONDS) - 1)]
                )
        raise N8nClientError("AUTOMATION_FABRIC_UNAVAILABLE", str(last) if last else None)

    # ------------------------------------------------------------ operations

    async def create_workflow(self, graph: dict[str, Any]) -> str:
        response = await self._request("POST", "/workflows", json=graph)
        workflow_id = response.json().get("id")
        if not workflow_id:
            raise N8nClientError("AUTOMATION_RESPONSE_MALFORMED")
        return str(workflow_id)

    async def update_workflow(self, workflow_id: str, graph: dict[str, Any]) -> None:
        await self._request("PUT", f"/workflows/{workflow_id}", json=graph)

    async def activate(self, workflow_id: str) -> None:
        await self._request("POST", f"/workflows/{workflow_id}/activate")

    async def deactivate(self, workflow_id: str) -> None:
        await self._request("POST", f"/workflows/{workflow_id}/deactivate")

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        return dict((await self._request("GET", f"/workflows/{workflow_id}")).json())

    async def get_execution(self, execution_id: str) -> dict[str, Any]:
        return dict((await self._request("GET", f"/executions/{execution_id}")).json())

    def webhook_url(self, path: str) -> str:
        """The production webhook URL for a trigger path.

        The management API lives under `/api/v1`; webhooks do not. Deriving one
        from the other rather than adding a second setting keeps them from drifting
        apart on a host where only one was updated.
        """
        root = self.webhook_base_url or self.base_url.split("/api/v1")[0].rstrip("/")
        return f"{root}/webhook/{path.lstrip('/')}"

    async def trigger_path(self, workflow_id: str) -> str:
        """The webhook path n8n will actually listen on for this workflow.

        Read from the deployed workflow rather than from VAN's artifact, because
        what matters is the path the running n8n has, not the one VAN compiled — a
        workflow edited in the n8n UI is exactly the case where those differ, and
        posting to the compiled path would silently do nothing.
        """
        workflow = await self.get_workflow(workflow_id)
        for node in workflow.get("nodes") or []:
            if str(node.get("type", "")).endswith("n8n-nodes-base.webhook"):
                path = (node.get("parameters") or {}).get("path")
                if path:
                    return str(path)
        raise N8nClientError("AUTOMATION_WORKFLOW_NOT_INVOCABLE", workflow_id)

    async def run_workflow(self, workflow_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
        """§159 — invoke an admitted workflow with its run envelope and grant.

        P3-OPS-007: this posted to `POST /workflows/{id}/run`, which does not exist.
        n8n's public REST API can create, update, activate, deactivate and read a
        workflow; it cannot execute one. Execution is what the workflow's own
        trigger is for, and every workflow VAN compiles for dispatch is built on
        `n8n-nodes-base.webhook` (see `compiler.PRIMITIVE_NODES`). So the real
        invocation is a POST to that webhook's production URL, carrying the same
        run envelope and run-scoped grant in the body.

        A workflow with no webhook trigger is refused rather than invoked by some
        other means: VAN dispatching work it cannot start is the failure this
        finding is about, and a workflow it cannot address is that failure with a
        different endpoint.
        """
        self._assert_usable()
        path = await self.trigger_path(workflow_id)
        url = self.webhook_url(path)
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds, transport=self.transport
        ) as client:
            response = await client.post(url, json=envelope)
        if response.status_code == 404:
            # n8n answers 404 on a webhook whose workflow is not active. That is a
            # deployment fault with a specific remedy, not a generic request failure.
            raise N8nClientError("AUTOMATION_WORKFLOW_NOT_ACTIVE", workflow_id)
        if response.status_code >= 400:
            raise N8nClientError("AUTOMATION_REQUEST_FAILED", str(response.status_code))
        try:
            payload = response.json()
        except ValueError:
            # A webhook node configured to return plain text is legitimate; the run
            # still happened, and the dispatcher's verifier is what judges it.
            return {"body": response.text}
        return payload if isinstance(payload, dict) else {"body": payload}

    async def runtime_version(self) -> str:
        """Used by the canary; also how §274 drift is detected."""
        payload = (await self._request("GET", "/settings")).json()
        version = payload.get("versionCli") or payload.get("version")
        if not version:
            raise N8nClientError("AUTOMATION_RESPONSE_MALFORMED", "no version in /settings")
        return str(version)

    # --------------------------------------------------------------- status

    async def status(self) -> ExternalRuntimeStatus:
        """§§371, 415 — configuration alone never reports READY."""
        status = await self.registry.resolve(
            capability=self.CAPABILITY,
            configured=self.configured,
            egress_enabled=self.enabled,
            credential_locus="gateway",
            expected_version=self.expected_version,
            policy_enabled=self.enabled,
            degraded_code="AUTOMATION_FABRIC_UNAVAILABLE",
        )
        if status.state is RuntimeState.POLICY_DISABLED and not self.configured:
            return status.model_copy(update={"state": RuntimeState.UNCONFIGURED})
        return status


__all__ = ["N8nClientError", "N8nManagementClient"]
