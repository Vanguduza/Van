"""Rev 1.3 §§186-189, 379, 383, 418 — browser worker adapters.

Both workers are subordinate: they receive task-scoped instructions and return
observations. Neither can create a VAN command, raise an action class, read a
secret or reach a broker (§367.7).

Every adapter fails closed when its runtime is not configured or its feature flag
is off, and reports readiness through the same evidence-backed contract as n8n
(§§404-406), so "the code exists" can never read as READY.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from van_gateway.automation.external_runtime import (
    ExternalRuntimeRegistry,
    ExternalRuntimeStatus,
    RuntimeState,
)
from van_gateway.automation.payments import assert_not_automated_payment
from van_gateway.browser.models import AutonomyTier, BrowserObservation, BrowserTask
from van_gateway.browser.policy import BrowserPolicyError


class BrowserAdapterError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class BrowserHarnessAdapter(Protocol):
    """§383 — the narrow typed production surface.

    Deliberately absent: arbitrary shell, arbitrary helper source, arbitrary CDP
    commands, raw cookie dump, raw credential extraction. Privileged diagnostic
    CDP access is a separate engineering-only surface.
    """

    async def navigate(self, task: BrowserTask, url: str) -> dict[str, Any]: ...
    async def page_info(self, task: BrowserTask) -> dict[str, Any]: ...
    async def click(self, task: BrowserTask, locator: str) -> dict[str, Any]: ...
    async def fill_ref(self, task: BrowserTask, locator: str, value_ref: str) -> dict[str, Any]: ...
    async def press(self, task: BrowserTask, key: str) -> dict[str, Any]: ...
    async def scroll(self, task: BrowserTask, request: dict[str, Any]) -> dict[str, Any]: ...
    async def screenshot(self, task: BrowserTask) -> dict[str, Any]: ...
    async def wait(self, task: BrowserTask, condition: dict[str, Any]) -> dict[str, Any]: ...
    async def upload(self, task: BrowserTask, locator: str, file_ref: str) -> dict[str, Any]: ...
    async def tabs(self, task: BrowserTask) -> dict[str, Any]: ...


class _PrivateWorkerClient:
    """Shared plumbing for the two loopback worker processes.

    Both workers bind to 127.0.0.1 by deployment contract
    (``deploy/van-trading-core/browser/runtime.env.example``); a public listener
    is forbidden by ``config/browser/domains.yaml``.
    """

    CAPABILITY = "worker"

    def __init__(
        self,
        registry: ExternalRuntimeRegistry,
        *,
        base_url: str,
        enabled: bool,
        expected_version: str | None,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None,
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
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_DISABLED")
        if not self.configured:
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_UNCONFIGURED")

    async def _call(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_usable()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_UNAVAILABLE", str(exc)) from exc
        if response.status_code >= 400:
            raise BrowserAdapterError(
                f"{self.CAPABILITY.upper()}_REQUEST_FAILED", str(response.status_code)
            )
        return dict(response.json())

    async def status(self, degraded_code: str) -> ExternalRuntimeStatus:
        status = await self.registry.resolve(
            capability=self.CAPABILITY,
            configured=self.configured,
            egress_enabled=self.enabled,
            credential_locus="gateway",
            expected_version=self.expected_version,
            policy_enabled=self.enabled,
            degraded_code=degraded_code,
        )
        if status.state is RuntimeState.POLICY_DISABLED and not self.configured:
            return status.model_copy(update={"state": RuntimeState.UNCONFIGURED})
        return status


class HttpBrowserHarnessAdapter(_PrivateWorkerClient):
    """§§188, 380-383 — deterministic actuator over the pinned harness worker."""

    CAPABILITY = "browser_harness"

    def __init__(
        self,
        registry: ExternalRuntimeRegistry,
        *,
        base_url: str = "",
        enabled: bool = False,
        expected_version: str | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            registry,
            base_url=base_url,
            enabled=enabled,
            expected_version=expected_version,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )

    def _envelope(self, task: BrowserTask, **extra: Any) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "profile_alias": task.profile_alias,
            # §381 — the worker is told, every call, that it is not allowed to
            # author helpers. The worker enforces it; the gateway asserts it.
            "mode": "PRODUCTION_ACTUATOR",
            "allow_helper_authoring": False,
            **extra,
        }

    async def navigate(self, task: BrowserTask, url: str) -> dict[str, Any]:
        return await self._call("/navigate", self._envelope(task, url=url))

    async def page_info(self, task: BrowserTask) -> dict[str, Any]:
        return await self._call("/page_info", self._envelope(task))

    async def click(self, task: BrowserTask, locator: str) -> dict[str, Any]:
        return await self._call("/click", self._envelope(task, locator=locator))

    async def fill_ref(self, task: BrowserTask, locator: str, value_ref: str) -> dict[str, Any]:
        """§407 — a *reference*, resolved inside the worker. The value never transits VAN."""
        if not value_ref.startswith("secretref://"):
            raise BrowserPolicyError("browser_fill_requires_secret_reference")
        return await self._call("/fill", self._envelope(task, locator=locator, value_ref=value_ref))

    async def press(self, task: BrowserTask, key: str) -> dict[str, Any]:
        return await self._call("/press", self._envelope(task, key=key))

    async def scroll(self, task: BrowserTask, request: dict[str, Any]) -> dict[str, Any]:
        return await self._call("/scroll", self._envelope(task, request=request))

    async def screenshot(self, task: BrowserTask) -> dict[str, Any]:
        return await self._call("/screenshot", self._envelope(task))

    async def wait(self, task: BrowserTask, condition: dict[str, Any]) -> dict[str, Any]:
        return await self._call("/wait", self._envelope(task, condition=condition))

    async def upload(self, task: BrowserTask, locator: str, file_ref: str) -> dict[str, Any]:
        return await self._call("/upload", self._envelope(task, locator=locator, file_ref=file_ref))

    async def tabs(self, task: BrowserTask) -> dict[str, Any]:
        return await self._call("/tabs", self._envelope(task))

    async def status(self) -> ExternalRuntimeStatus:  # type: ignore[override]
        return await super().status("BROWSER_HARNESS_UNAVAILABLE")


class StagehandAdapter(_PrivateWorkerClient):
    """§§186-187, 379, 418 — semantic observation and typed extraction.

    ``act`` exists but is refused above the admitted ladder cap, and the model
    provider is always the one the gateway configured — page content can never
    choose it (§418).
    """

    CAPABILITY = "stagehand"

    def __init__(
        self,
        registry: ExternalRuntimeRegistry,
        *,
        base_url: str = "",
        enabled: bool = False,
        expected_version: str | None = None,
        model_provider: str = "",
        model_name: str = "",
        max_tier: AutonomyTier = AutonomyTier.L5_STAGEHAND_AGENT,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            registry,
            base_url=base_url,
            enabled=enabled,
            expected_version=expected_version,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        self.model_provider = model_provider
        self.model_name = model_name
        self.max_tier = max_tier

    @property
    def configured(self) -> bool:
        # §418 — an unconfigured provider is unconfigured Stagehand. The model is
        # never chosen at runtime, so "no provider" means the adapter cannot run.
        return bool(self.base_url and self.model_provider and self.model_name)

    def _envelope(self, task: BrowserTask, **extra: Any) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "profile_alias": task.profile_alias,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "allow_model_self_selection": False,
            "allow_unbounded_agent_loop": False,
            **extra,
        }

    async def observe(self, task: BrowserTask, instruction: str) -> BrowserObservation:
        payload = await self._call("/observe", self._envelope(task, instruction=instruction))
        return BrowserObservation(
            task_id=task.task_id,
            controls=list(payload.get("controls", [])),
            extraction=dict(payload.get("extraction", {})),
        )

    async def extract(
        self, task: BrowserTask, instruction: str, schema: dict[str, Any]
    ) -> BrowserObservation:
        payload = await self._call(
            "/extract", self._envelope(task, instruction=instruction, schema=schema)
        )
        return BrowserObservation(
            task_id=task.task_id, extraction=dict(payload.get("extraction", {}))
        )

    async def act(self, task: BrowserTask, action: dict[str, Any]) -> dict[str, Any]:
        """L4 — one model-selected action, still refused above the ladder cap."""
        if self.max_tier.ordinal < AutonomyTier.L4_STAGEHAND_ACT.ordinal:
            raise BrowserPolicyError("stagehand_act_not_permitted_at_current_tier")
        assert_not_automated_payment(
            operation=str(action.get("kind", "")), goal=str(action.get("instruction", "")),
            url=str(action.get("url", "")), domain=task.target_domain, context="stagehand_act",
        )
        return await self._call("/act", self._envelope(task, action=action))

    async def agent(
        self, task: BrowserTask, goal: str, *, max_steps: int, assignment_id: str, turn_id: str
    ) -> dict[str, Any]:
        """L5 — an assigned, bounded run.

        The assignment is mandatory: a bare "go and do this" has no budget and no
        attribution, which is the difference between a subagent and an independent
        loop. `BrowserSubagentRunner` is the supported caller.
        """
        if self.max_tier.ordinal < AutonomyTier.L5_STAGEHAND_AGENT.ordinal:
            raise BrowserPolicyError("stagehand_agent_not_permitted_at_current_tier")
        if max_steps < 1 or max_steps > 50:
            raise BrowserPolicyError("stagehand_agent_requires_bounded_step_budget")
        assert_not_automated_payment(goal=goal, domain=task.target_domain, context="stagehand_agent")
        return await self._call(
            "/agent",
            self._envelope(
                task, goal=goal, max_steps=max_steps,
                assignment_id=assignment_id, turn_id=turn_id,
            ),
        )

    async def status(self) -> ExternalRuntimeStatus:  # type: ignore[override]
        return await super().status("BROWSER_SEMANTIC_UNAVAILABLE")


__all__ = [
    "BrowserAdapterError",
    "BrowserHarnessAdapter",
    "HttpBrowserHarnessAdapter",
    "StagehandAdapter",
]
