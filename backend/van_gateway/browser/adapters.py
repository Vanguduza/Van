"""Rev 1.3 §§186-189, 379, 383, 418 — browser worker adapters.

Both workers are subordinate: they receive task-scoped instructions and return
observations. Neither can create a VAN command, raise an action class, read a
secret or reach a broker (§367.7).

Every adapter fails closed when its runtime is not configured or its feature flag
is off, and reports readiness through the same evidence-backed contract as n8n
(§§404-406), so "the code exists" can never read as READY.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from van_gateway.automation.external_runtime import (
    ExternalRuntimeRegistry,
    ExternalRuntimeStatus,
    RuntimeState,
)
from van_gateway.automation.payments import assert_not_automated_payment
from van_gateway.browser.lane_gates import load_stagehand_production_gate
from van_gateway.browser.models import AutonomyTier, BrowserObservation, BrowserTask
from van_gateway.browser.policy import BrowserPolicyError


class BrowserAdapterError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class HarnessInflight:
    """Harness calls sent under a fence that have not yet ended (review I5 F1).

    A fenced call runs as its own task, shielded from the caller's cancellation: when a
    ``/step`` hits its deadline the router stops waiting, but the HTTP request is not torn
    down mid-flight, and the step does not give its lease back until ``settle`` reports
    that every call it sent has ended.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self.unknown_outcome = False

    def track(self, task: "asyncio.Task[Any]") -> None:
        self._tasks.add(task)

        def _done(t: "asyncio.Task[Any]") -> None:
            self._tasks.discard(t)
            exc = None if t.cancelled() else t.exception()
            if t.cancelled() or (exc is not None and not (
                isinstance(exc, BrowserAdapterError) and not exc.code.endswith("_UNAVAILABLE")
            )):
                # No response (transport failure, timeout, cancellation): the Harness may
                # still be applying it. An HTTP error status is a response: the call ended.
                self.unknown_outcome = True

        task.add_done_callback(_done)

    @property
    def pending(self) -> int:
        return len(self._tasks)

    async def settle(
        self, keepalive: Callable[[], Awaitable[None]] | None = None, *,
        poll_seconds: float = 5.0, max_seconds: float = 300.0,
    ) -> bool:
        """Wait for every tracked call to end; True when each ended with a response.

        ``keepalive`` (the fence guard) runs between polls so the lease is renewed, not
        allowed to lapse, while a call is still at the Harness. False means a call ended
        without a response (or did not end within ``max_seconds``): the Harness may still
        apply it, so the caller must not release the lease early.
        """
        deadline = time.monotonic() + max_seconds
        while self._tasks:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.wait(set(self._tasks), timeout=min(poll_seconds, remaining))
            if self._tasks and keepalive is not None:
                try:
                    await keepalive()
                except Exception:  # noqa: BLE001 - lease already lost; keep waiting
                    pass
        return not self.unknown_outcome


@dataclass(frozen=True)
class HarnessLeaseFence:
    """The page lease a Harness call is made under (review I3 MAJOR-3, I4 MINOR-A).

    Sent in every Harness action envelope while it is set, so the Harness worker can refuse
    a call carrying a generation older than the newest it has seen for that profile: work
    still holding a lease the profile has since been re-leased past is not applied to
    whoever holds it now.

    ``guard`` (not part of equality) is awaited by the adapter before every Harness call
    made under the fence. ``broker_lease_fence`` builds it from the gateway broker: it
    asserts the lease is still the profile's live holding (``assert_lease_active``) and
    renews it when renewal is due, so a caller whose lease lapsed or was taken stops before
    it reaches the page even when the new holder has not yet touched the Harness.
    """

    profile_alias: str
    holder_id: str
    generation: int
    guard: Callable[[], Awaitable[None]] | None = field(default=None, compare=False, repr=False)
    inflight: HarnessInflight = field(default_factory=HarnessInflight, compare=False, repr=False)


def harness_fence_mac(key: bytes, alias: str, generation: int, holder_id: str) -> str:
    """Review I5 F3 — HMAC-SHA256 over the fence, verified by the Harness worker.

    Must match ``fence_mac`` in deploy/van-browser-core/browser/harness_service.py.
    """
    message = f"van-harness-fence/1\n{alias}\n{int(generation)}\n{holder_id}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def load_harness_fence_key(path: str) -> bytes | None:
    """The shared fence key from ``path`` (whitespace stripped); None when unset.

    A configured but unreadable or short (< 32 bytes) key raises: the gateway does not
    silently send unauthenticated fences that a production Harness would refuse anyway.
    """
    if not path:
        return None
    key = Path(path).read_bytes().strip()
    if len(key) < 32:
        raise ValueError("VAN_BROWSER_HARNESS_FENCE_KEY_FILE holds fewer than 32 bytes")
    return key


def harness_fence_key_from_settings(settings: Any) -> bytes | None:
    """The fence key named by settings, or None (unset, unreadable or too short).

    None means fences go out without a MAC; a production Harness (which requires one)
    then refuses every fenced call, so a broken key fails closed at the Harness rather
    than stopping the whole gateway from starting.
    """
    try:
        return load_harness_fence_key(getattr(settings, "browser_harness_fence_key_file", "") or "")
    except (OSError, ValueError):
        import logging

        logging.getLogger(__name__).error("BROWSER_HARNESS_FENCE_KEY_UNUSABLE")
        return None


_HARNESS_LEASE_FENCE: ContextVar[HarnessLeaseFence | None] = ContextVar(
    "van_harness_lease_fence", default=None
)


@contextmanager
def harness_lease_fence(fence: HarnessLeaseFence | None) -> Iterator[None]:
    """Run the enclosed Harness calls under ``fence``.

    Every gateway caller of a mutating Harness operation sets one: ``/interaction/step``,
    ``/assignments``, the watch runner and the notebook consumer (review I4 MINOR-A).
    """
    token = _HARNESS_LEASE_FENCE.set(fence)
    try:
        yield
    finally:
        _HARNESS_LEASE_FENCE.reset(token)


def current_harness_lease_fence() -> HarnessLeaseFence | None:
    return _HARNESS_LEASE_FENCE.get()


def broker_lease_fence(broker: Any, lease: Any) -> HarnessLeaseFence:
    """A fence for ``lease`` (a ``PageLease``) whose guard re-checks it with ``broker``.

    The guard runs before each Harness call: ``assert_lease_active`` (lease id, holder and
    generation must still match and it must not have expired), then ``renew_lease`` for the
    lease's own TTL once two thirds of it has elapsed. Any failure raises
    ``BROWSER_HARNESS_LEASE_LOST`` and nothing is sent to the Harness.
    """
    ttl_ms = max(30_000, int(lease.expires_at_ms) - int(lease.acquired_at_ms))
    state = {"expires_at_ms": int(lease.expires_at_ms)}

    async def guard() -> None:
        now = int(time.time() * 1000)
        try:
            await broker.assert_lease_active(
                lease_id=lease.lease_id, holder_id=lease.holder_id,
                generation=int(lease.generation), now_ms=now,
            )
            if state["expires_at_ms"] - now < (ttl_ms * 2) // 3:
                renewed = await broker.renew_lease(
                    lease_id=lease.lease_id, holder_id=lease.holder_id,
                    generation=int(lease.generation), ttl_seconds=ttl_ms // 1000, now_ms=now,
                )
                state["expires_at_ms"] = int(renewed.expires_at_ms)
        except BrowserPolicyError as exc:
            raise BrowserAdapterError("BROWSER_HARNESS_LEASE_LOST", str(exc)) from exc

    return HarnessLeaseFence(lease.profile_alias, lease.holder_id, int(lease.generation), guard)


#: Harness operations that change the page; the adapter refuses to send one unfenced.
HARNESS_MUTATING_PATHS = frozenset({"/navigate", "/click", "/fill", "/press", "/scroll", "/upload"})


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
    async def describe(self, task: BrowserTask, locator: str) -> dict[str, Any]: ...
    async def describe_focus(self, task: BrowserTask) -> dict[str, Any]: ...


#: Harness refusal codes (409) that mean "the target is not the one VAN classified, or the
#: page is outside the task scope" — nothing was actuated. Mapped to lane 4 by the router.
HARNESS_REFUSAL_PREFIXES = ("TARGET_", "TASK_SCOPE_", "FOCUS_", "PAGE_DIALOG")


def _scope_wire(task: BrowserTask) -> dict[str, Any] | None:
    """The task's recorded scope as the Harness receives it (None: the Harness refuses)."""
    scope = getattr(task, "scope", None)
    return scope.to_wire() if scope is not None else None


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return str(body.get("error")) if isinstance(body, dict) and body.get("error") else None


class _PinnedNetworkBackend:
    """Review I5 P1 — connect only to an address the placement check approved.

    httpcore asks the backend to ``connect_tcp(host, port)`` with the URL's host name; this
    resolves it through ``placement.checked_connect_addresses`` (the gate's own cached,
    classified answer) and opens the socket to that address. TLS is then started by
    httpcore with the URL's host as SNI and as the name the certificate is verified against,
    and the Host header is unchanged, so mTLS verification stays on the name while a DNS
    answer that changed after the check (rebinding) is never connected to.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def connect_tcp(self, host: str, port: int, timeout: float | None = None,
                          local_address: str | None = None, socket_options: Any = None) -> Any:
        from van_gateway.automation.placement import checked_connect_addresses

        try:
            addresses = await asyncio.to_thread(checked_connect_addresses, host)
        except PermissionError as exc:
            raise httpx.ConnectError(f"endpoint refused by placement: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - unresolvable fails closed
            raise httpx.ConnectError(f"endpoint unresolvable: {type(exc).__name__}") from exc
        if not addresses:
            raise httpx.ConnectError("endpoint unresolvable")
        return await self._inner.connect_tcp(addresses[0], port, timeout=timeout,
                                             local_address=local_address, socket_options=socket_options)

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> Any:
        raise httpx.ConnectError("unix sockets are not a cross-zone endpoint")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def pinned_transport(**kwargs: Any) -> httpx.AsyncHTTPTransport:
    """An httpx transport whose connections go only to placement-checked addresses (I5 P1)."""
    transport = httpx.AsyncHTTPTransport(**kwargs)
    pool = transport._pool  # httpcore.AsyncConnectionPool (httpx 0.28 / httpcore 1.0)
    pool._network_backend = _PinnedNetworkBackend(pool._network_backend)
    return transport


class _PrivateWorkerClient:
    """Shared plumbing for the two loopback worker processes.

    Both workers are reached only through the van-browser-core edge (owner decision
    2026-09-29 §1; deployment under ``deploy/van-browser-core/browser/``, formerly
    ``deploy/van-trading-core/browser/``); a public listener is forbidden by
    ``config/browser/domains.yaml``.
    """

    CAPABILITY = "worker"
    #: Review I5 P1 — connect only to the addresses the placement gate approved (HTTPS).
    PIN_ENDPOINT_DNS = False

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

    def client_kwargs(self) -> dict[str, Any]:
        """httpx client arguments, including the van-browser-core mTLS client identity.

        Owner decision 2026-09-29 §1: cross-zone access is the authenticated edge only. When
        settings name the edge CA and the gateway client cert/key files, every call (and the
        router's /health read) presents them; the key material stays in files.
        """
        kwargs: dict[str, Any] = {
            "base_url": self.base_url, "timeout": self.timeout_seconds, "transport": self.transport,
        }
        if self.transport is None and self.base_url.startswith("https://"):
            from van_gateway.config import get_settings

            settings = get_settings()
            ca = getattr(settings, "browser_core_ca_file", "") or ""
            cert = getattr(settings, "browser_core_client_cert_file", "") or ""
            key = getattr(settings, "browser_core_client_key_file", "") or ""
            if ca:
                kwargs["verify"] = ca
            if cert and key:
                kwargs["cert"] = (cert, key)
            if self.PIN_ENDPOINT_DNS:
                # A client given a transport ignores its own verify/cert: they move onto it.
                import ssl

                context = ssl.create_default_context(cafile=ca or None)
                if cert and key:
                    context.load_cert_chain(cert, key)
                kwargs.pop("verify", None)
                kwargs.pop("cert", None)
                kwargs["transport"] = pinned_transport(verify=context)
        return kwargs

    def _assert_usable(self) -> None:
        if not self.enabled:
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_DISABLED")
        if not self.configured:
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_UNCONFIGURED")

    async def _call(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_usable()
        try:
            async with httpx.AsyncClient(**self.client_kwargs()) as client:
                response = await client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_UNAVAILABLE", str(exc)) from exc
        if response.status_code >= 400:
            if response.status_code == 409 and _error_code(response) == "LEASE_GENERATION_STALE":
                # Review I3 MAJOR-3: the worker has seen a newer lease on this profile.
                raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_LEASE_GENERATION_STALE")
            if response.status_code == 428 and _error_code(response) == "LEASE_FENCE_REQUIRED":
                raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_LEASE_FENCE_REQUIRED")
            refusal = _error_code(response) if response.status_code == 409 else None
            if refusal and refusal.startswith(HARNESS_REFUSAL_PREFIXES):
                # Review I5 / owner decision 2026-09-30: the Harness refused to actuate the
                # bound target (binding, hit test, focus, task scope). Typed, so the router
                # hands the step to the owner rather than calling it an execution failure.
                raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_REFUSED", refusal)
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
        fence_key: bytes | None = None,
    ) -> None:
        super().__init__(
            registry,
            base_url=base_url,
            enabled=enabled,
            expected_version=expected_version,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        #: Review I5 F3 — shared with the Harness (VAN_HARNESS_FENCE_KEY_FILE there).
        self.fence_key = fence_key

    def _envelope(self, task: BrowserTask, **extra: Any) -> dict[str, Any]:
        envelope = {
            "task_id": task.task_id,
            "profile_alias": task.profile_alias,
            "target_domain": task.target_domain,
            # §381 — the worker is told, every call, that it is not allowed to
            # author helpers. The worker enforces it; the gateway asserts it.
            "mode": "PRODUCTION_ACTUATOR",
            "allow_helper_authoring": False,
            **extra,
        }
        fence = _HARNESS_LEASE_FENCE.get()
        if fence is not None and fence.profile_alias == task.profile_alias:
            # Review I3 MAJOR-3: the lease this call runs under; the worker refuses a
            # generation older than the newest it has seen for the profile.
            envelope["lease_holder_id"] = fence.holder_id
            envelope["lease_generation"] = int(fence.generation)
            if self.fence_key is not None:
                envelope["lease_mac"] = harness_fence_mac(
                    self.fence_key, fence.profile_alias, int(fence.generation), fence.holder_id,
                )
        return envelope

    async def _call(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        """Review I4 MINOR-A — fenced, and re-checked with the broker, before it is sent.

        A mutating operation without a fence for the task's profile is refused here (and by
        the worker). When the fence carries a guard it runs first, so a lease that lapsed or
        was taken stops the call before it reaches the page.
        """
        fenced = "lease_generation" in payload
        if path in HARNESS_MUTATING_PATHS and not fenced:
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_LEASE_FENCE_REQUIRED", path)
        fence = _HARNESS_LEASE_FENCE.get()
        if fenced and fence is not None and fence.guard is not None:
            await fence.guard()
        if not fenced or fence is None:
            return await super()._call(path, payload)
        # Review I5 F1 — the request runs to its end even if the caller is cancelled (a /step
        # deadline); the fence tracks it so the lease is not given back while it is in flight.
        call = asyncio.ensure_future(super()._call(path, payload))
        fence.inflight.track(call)
        return await asyncio.shield(call)

    async def navigate(self, task: BrowserTask, url: str) -> dict[str, Any]:
        scope = _scope_wire(task)
        extra = {"task_scope": scope} if scope is not None else {}
        return await self._call("/navigate", self._envelope(task, url=url, **extra))

    async def page_info(self, task: BrowserTask) -> dict[str, Any]:
        return await self._call("/page_info", self._envelope(task))

    async def click(self, task: BrowserTask, locator: str, *, binding: dict[str, Any] | None = None) -> dict[str, Any]:
        """Review I5 MAJOR-2 — acts on the node ``binding`` names (from ``describe``), under
        the task's scope; the Harness refuses without either."""
        return await self._call("/click", self._envelope(
            task, locator=locator, binding=binding, task_scope=_scope_wire(task)))

    async def fill_ref(
        self, task: BrowserTask, locator: str, value_ref: str, *, binding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """§407 — a *reference*, resolved inside the worker. The value never transits VAN."""
        if not value_ref.startswith("secretref://"):
            raise BrowserPolicyError("browser_fill_requires_secret_reference")
        return await self._call("/fill", self._envelope(
            task, locator=locator, value_ref=value_ref, binding=binding, task_scope=_scope_wire(task)))

    async def press(self, task: BrowserTask, key: str, *, binding: dict[str, Any] | None = None) -> dict[str, Any]:
        """Review I5 MAJOR-3 — ``binding`` is the focused element ``describe_focus`` bound."""
        return await self._call("/press", self._envelope(
            task, key=key, binding=binding, task_scope=_scope_wire(task)))

    async def scroll(self, task: BrowserTask, request: dict[str, Any]) -> dict[str, Any]:
        scope = _scope_wire(task)
        extra = {"task_scope": scope} if scope is not None else {}
        return await self._call("/scroll", self._envelope(task, request=request, **extra))

    async def screenshot(self, task: BrowserTask) -> dict[str, Any]:
        return await self._call("/screenshot", self._envelope(task))

    async def wait(self, task: BrowserTask, condition: dict[str, Any]) -> dict[str, Any]:
        return await self._call("/wait", self._envelope(task, condition=condition))

    async def upload(self, task: BrowserTask, locator: str, file_ref: str) -> dict[str, Any]:
        return await self._call("/upload", self._envelope(task, locator=locator, file_ref=file_ref))

    async def tabs(self, task: BrowserTask) -> dict[str, Any]:
        return await self._call("/tabs", self._envelope(task))

    async def describe(self, task: BrowserTask, locator: str) -> dict[str, Any]:
        """Review I4 — the element the Harness would act on for ``locator``, in the same
        shape as a ``page_info`` ``elements`` entry, for targets the bounded list omitted."""
        return await self._call("/describe", self._envelope(task, locator=locator))

    async def describe_focus(self, task: BrowserTask) -> dict[str, Any]:
        """Review I5 MAJOR-3 — ``document.activeElement`` (through open shadow roots), in
        the ``describe`` shape and bound the same way, so a key press is classified against
        the element that will receive it."""
        return await self._call("/describe", self._envelope(task, focus=True))

    async def status(self) -> ExternalRuntimeStatus:  # type: ignore[override]
        return await super().status("BROWSER_HARNESS_UNAVAILABLE")


#: Sentinel for "no gate argument": the adapter builds the canonical production gate.
CANONICAL_STAGEHAND_GATE: Any = object()

StagehandProductionGate = Callable[[], Any]


def canonical_stagehand_production_gate(
    adapter: "StagehandAdapter", settings: Any = None
) -> StagehandProductionGate:
    """The gate every production Stagehand call passes: the router's own composition.

    Owner decisions 2026-09-29 §§1, 2, 4-6: placement on van-browser-core proved by the
    worker's live ``/health`` (``placement.stagehand_production_enabled``) AND every
    production activation gate green (``production_gates.evaluate_production_gates``).
    It is ``lane_gates.load_stagehand_production_gate`` itself — the function the router
    re-exports and its Stagehand lane uses — so the two cannot drift apart. Anything missing
    fails closed.
    """

    async def gate() -> tuple[bool, str]:
        resolved = settings
        if resolved is None:
            from van_gateway.config import get_settings

            resolved = get_settings()
        # Settings-only placement is checked first inside the shared gate: an undeclared
        # zone, a loopback or plain-HTTP endpoint, missing mTLS identity or a non-decided
        # model is closed without contacting the worker at all.
        return await load_stagehand_production_gate(resolved, adapter)()

    return gate


class StagehandAdapter(_PrivateWorkerClient):
    """§§186-187, 379, 418 — semantic observation and typed extraction.

    ``act`` exists but is refused above the admitted ladder cap, and the model
    provider is always the one the gateway configured — page content can never
    choose it (§418).

    Review I B-1: every call that reaches the worker first passes the Stagehand
    production gate, *inside the adapter*, so no consumer (the assignment worker, the
    NotebookLM consumer, a future caller) can reach Stagehand while placement or the
    production gate model says PRODUCTION_DISABLED. Without a ``production_gate``
    argument the adapter uses ``canonical_stagehand_production_gate``; an explicit
    ``None`` means the gate is missing, which refuses every call. ``configured`` is
    False while the gate is closed, so the status surface reports the truth.
    """

    CAPABILITY = "stagehand"
    PIN_ENDPOINT_DNS = True

    def __init__(
        self,
        registry: ExternalRuntimeRegistry,
        *,
        base_url: str = "",
        enabled: bool = False,
        expected_version: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        max_tier: AutonomyTier = AutonomyTier.L5_STAGEHAND_AGENT,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        actuation_enabled: bool = False,
        production_gate: StagehandProductionGate | None = CANONICAL_STAGEHAND_GATE,
        settings: Any = None,
    ) -> None:
        super().__init__(
            registry,
            base_url=base_url,
            enabled=enabled,
            expected_version=expected_version,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        # Owner decision 2026-09-29 §4: the model comes from settings (the canonical
        # anthropic / claude-sonnet-5), never from a code default and never another model.
        # Unset in settings stays unset, which leaves the adapter unconfigured.
        if model_provider is None or model_name is None:
            from van_gateway.config import get_settings

            settings = get_settings()
            if model_provider is None:
                model_provider = getattr(settings, "browser_stagehand_model_provider", "") or ""
            if model_name is None:
                model_name = getattr(settings, "browser_stagehand_model_name", "") or ""
        self.model_provider = model_provider
        self.model_name = model_name
        self.max_tier = max_tier
        #: Owner decision 2026-09-29 §8 — Stagehand must not actuate on the production
        #: path. `act()` refuses unless a caller explicitly constructs the adapter with this
        #: set (non-production only). observe()/extract() are unaffected.
        self.actuation_enabled = actuation_enabled
        if production_gate is CANONICAL_STAGEHAND_GATE:
            production_gate = canonical_stagehand_production_gate(self, settings)
        self.production_gate: StagehandProductionGate | None = production_gate
        #: The last gate verdict. Closed until a gate evaluation says otherwise.
        self.production_gate_state: tuple[bool, str] = (False, "STAGEHAND_PRODUCTION_GATE_NOT_EVALUATED")

    @property
    def wiring_configured(self) -> bool:
        # §418 — an unconfigured provider is unconfigured Stagehand. The model is
        # never chosen at runtime, so "no provider" means the adapter cannot run.
        return bool(self.base_url and self.model_provider and self.model_name)

    @property
    def configured(self) -> bool:
        """Wired AND the production gate open at its last evaluation (review I B-1)."""
        return self.wiring_configured and self.production_gate_state[0] is True

    def _assert_usable(self) -> None:
        if not self.enabled:
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_DISABLED")
        if not self.wiring_configured:
            raise BrowserAdapterError(f"{self.CAPABILITY.upper()}_UNCONFIGURED")

    async def evaluate_production_gate(self) -> tuple[bool, str]:
        """Evaluate the gate, remember the verdict, never raise. Missing = closed."""
        gate = self.production_gate
        if gate is None:
            verdict: tuple[bool, str] = (False, "STAGEHAND_PRODUCTION_GATE_MISSING")
        else:
            try:
                outcome = gate()
                if inspect.isawaitable(outcome):
                    outcome = await outcome
                permitted, reason = outcome
            except Exception as exc:  # noqa: BLE001 - a gate fault is "not permitted"
                verdict = (False, f"STAGEHAND_PRODUCTION_GATE_FAILED:{type(exc).__name__}")
            else:
                verdict = (permitted is True, str(reason or "PRODUCTION_DISABLED"))
        self.production_gate_state = verdict
        return verdict

    async def _call(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_usable()
        permitted, reason = await self.evaluate_production_gate()
        if not permitted:
            raise BrowserAdapterError("STAGEHAND_PRODUCTION_DISABLED", reason)
        return await super()._call(path, payload)

    def _envelope(self, task: BrowserTask, **extra: Any) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "profile_alias": task.profile_alias,
            "target_domain": task.target_domain,
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
        if not self.actuation_enabled:
            raise BrowserPolicyError("stagehand_direct_actuation_disabled")
        assert_not_automated_payment(
            operation=str(action.get("kind", "")), goal=str(action.get("instruction", "")),
            url=str(action.get("url", "")), domain=task.target_domain, context="stagehand_act",
        )
        return await self._call("/act", self._envelope(task, action=action))

    async def agent(
        self, task: BrowserTask, goal: str, *, max_steps: int, assignment_id: str, turn_id: str
    ) -> dict[str, Any]:
        """Direct Stagehand agent loops are forbidden in production.

        L5 is implemented by `HybridBrowserWorker`: Stagehand proposes one observed
        action, `BrowserSubagentRunner` enforces Hermes's immutable assignment, then that
        one action is replayed. Keeping this method as a hard refusal preserves API
        compatibility while preventing a future caller from bypassing the per-step gate.
        """
        if self.max_tier.ordinal < AutonomyTier.L5_STAGEHAND_AGENT.ordinal:
            raise BrowserPolicyError("stagehand_agent_not_permitted_at_current_tier")
        if max_steps < 1 or max_steps > 50:
            raise BrowserPolicyError("stagehand_agent_requires_bounded_step_budget")
        assert_not_automated_payment(goal=goal, domain=task.target_domain, context="stagehand_agent")
        raise BrowserPolicyError("direct_stagehand_agent_loop_forbidden")

    async def status(self) -> ExternalRuntimeStatus:  # type: ignore[override]
        if self.enabled and self.wiring_configured:
            permitted, reason = await self.evaluate_production_gate()
            if not permitted:
                # Wired but not permitted: not "configured", and the reason is visible.
                return ExternalRuntimeStatus(
                    capability=self.CAPABILITY,
                    state=RuntimeState.POLICY_DISABLED,
                    configured=False,
                    egress_enabled=False,
                    credential_locus="gateway",
                    expected_version=self.expected_version,
                    detail=f"STAGEHAND_PRODUCTION_DISABLED:{reason}",
                    degraded_code="BROWSER_SEMANTIC_UNAVAILABLE",
                )
        return await super().status("BROWSER_SEMANTIC_UNAVAILABLE")


__all__ = [
    "CANONICAL_STAGEHAND_GATE",
    "canonical_stagehand_production_gate",
    "BrowserAdapterError",
    "BrowserHarnessAdapter",
    "HARNESS_MUTATING_PATHS",
    "HarnessInflight",
    "HarnessLeaseFence",
    "harness_fence_key_from_settings",
    "harness_fence_mac",
    "load_harness_fence_key",
    "broker_lease_fence",
    "HttpBrowserHarnessAdapter",
    "current_harness_lease_fence",
    "harness_lease_fence",
    "pinned_transport",
    "StagehandAdapter",
]
