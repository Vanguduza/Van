"""Lane gates shared by the interaction router, the Stagehand adapter and the browser API.

Moved out of ``interaction_router`` (unit G2b, at unit G2a's request) so ``adapters.py`` and
``api.py`` can import them at module level instead of lazily: this module imports nothing
from ``adapters`` or ``api``. ``interaction_router`` re-exports every name, so existing
imports are unchanged.

* ``OwnerControlProbe`` — owner takeover preempts automation (owner decision 2026-09-29 §9).
* ``load_stagehand_production_gate`` — the Stagehand production gate (placement on
  van-browser-core AND the Stagehand slice of the production gate model), settings-first.
* ``load_jev_browser_effect_gate`` — VAN's own gate on Jev browser effect (review I2 N-7).
* ``step_gate_scope`` / ``step_gate_memo`` — one gate evaluation per router step (N-10).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import time
from typing import Any, AsyncIterator, Awaitable, Callable

from van_gateway.browser.models import BrowserTask

#: ``placement.stagehand_production_enabled`` reasons that mean "settings are fine, only the
#: worker's live /health is missing" — the one case where the endpoint may be contacted.
WORKER_HEALTH_PENDING_PREFIX = "VAN_BROWSER_CORE_UNAVAILABLE:"

#: Review I2 N-10 — gate verdicts already evaluated in the current router step. ``None``
#: outside a step, where every call evaluates afresh (the assignment path, the notebook
#: consumer, the health surface).
_STEP_GATE_VERDICTS: contextvars.ContextVar[dict[Any, Any] | None] = contextvars.ContextVar(
    "van_browser_step_gate_verdicts", default=None
)


@contextlib.asynccontextmanager
async def step_gate_scope() -> AsyncIterator[None]:
    """One router step: each gate is evaluated at most once inside it, and reused.

    A verdict never outlives the step, so nothing is cached across steps; within the step
    the lane decision and the adapter call it leads to read the *same* verdict instead of
    re-deriving it (and re-reading the worker's /health) three times.
    """
    token = _STEP_GATE_VERDICTS.set({})
    try:
        yield
    finally:
        _STEP_GATE_VERDICTS.reset(token)


async def step_gate_memo(key: Any, evaluate: Callable[[], Awaitable[Any]]) -> Any:
    """``await evaluate()``, memoised under ``key`` for the current step (if any).

    A raised gate is not memoised: the caller turns it into a closed verdict each time.
    """
    verdicts = _STEP_GATE_VERDICTS.get()
    if verdicts is None:
        return await evaluate()
    if key in verdicts:
        return verdicts[key]
    verdict = await evaluate()
    verdicts[key] = verdict
    return verdict


class OwnerControlProbe:
    """True when the owner holds control of a live interactive session on the task's profile.

    ADR-RB-007 "owner touch wins": the interactive session's control holder is the fence.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    async def __call__(self, task: BrowserTask) -> bool:
        now = int(time.time() * 1000)
        row = await self.store.fetchone(
            "SELECT 1 FROM browser_interactive_sessions WHERE profile_alias = ? "
            "AND control_holder = 'OWNER' AND terminated_at_ms IS NULL AND expires_at_ms > ? LIMIT 1",
            (task.profile_alias, now),
        )
        return row is not None


async def _fetch_stagehand_worker_health(stagehand: Any) -> dict[str, Any] | None:
    """GET the Stagehand worker's ``/health`` through the van-browser-core edge. None on any failure."""
    import httpx

    base = (getattr(stagehand, "base_url", "") or "").rstrip("/")
    if not base:
        return None
    kwargs_fn = getattr(stagehand, "client_kwargs", None)
    kwargs = kwargs_fn() if callable(kwargs_fn) else {
        "base_url": base, "transport": getattr(stagehand, "transport", None),
    }
    kwargs["timeout"] = 5.0
    try:
        async with httpx.AsyncClient(**kwargs) as client:
            response = await client.get("/health")
        if response.status_code != 200:
            return None
        body = response.json()
        return body if isinstance(body, dict) else None
    except Exception:  # noqa: BLE001 - unreachable health is absent health
        return None


def load_stagehand_production_gate(settings: Any, stagehand: Any = None) -> Callable[[], Any]:
    """The Stagehand lane's production gate: placement/model AND the production gate model.

    * unit M's ``stagehand_production_enabled(settings, worker_health=...)`` (placement on
      van-browser-core + model/provider-key rules), fed the worker's live ``/health``; absent
      module or absent health fails closed;
    * ``evaluate_production_gates()`` (owner decision §6; includes signed ingress and the
      §7/§8 blocker records) must report ``production_activation_permitted``.
    """

    async def gate() -> tuple[bool, str]:
        if stagehand is None:
            return await evaluate()
        # Keyed by the adapter and settings, so the router's lane gate and the adapter's own
        # canonical gate (the same function over the same adapter) share one evaluation.
        return await step_gate_memo(("stagehand_production_gate", id(stagehand), id(settings)), evaluate)

    async def evaluate() -> tuple[bool, str]:
        try:
            from van_gateway.automation import placement  # type: ignore[attr-defined]
        except ImportError:
            return False, "PLACEMENT_GATE_MISSING"
        fn = getattr(placement, "stagehand_production_enabled", None)
        if fn is None:
            return False, "PLACEMENT_GATE_MISSING"
        # Settings first (unit G2a): an undeclared zone, a loopback or plain-HTTP endpoint,
        # a missing mTLS identity or a non-decided model is closed on settings alone, without
        # contacting the endpoint. Only when fresh worker health is the one thing missing is
        # the worker's /health read.
        # Review I5 P2 — the placement check resolves the endpoint name, which blocks: it runs
        # on a worker thread so the event loop is never stalled by DNS.
        permitted, reason = await asyncio.to_thread(fn, settings, worker_health=None)
        if permitted is not True and not str(reason).startswith(WORKER_HEALTH_PENDING_PREFIX):
            return False, str(reason or "PRODUCTION_DISABLED")
        health = await _fetch_stagehand_worker_health(stagehand) if stagehand is not None else None
        permitted, reason = await asyncio.to_thread(fn, settings, worker_health=health)
        if permitted is not True:
            return False, str(reason or "PRODUCTION_DISABLED")
        try:
            from van_gateway.automation.production_gates import evaluate_production_gates
        except ImportError:
            return False, "PRODUCTION_GATE_MODEL_MISSING"
        # Review I2 N-8: the Stagehand *capability slice* of the gate model (its adoption
        # record, the Harness record it acts through, the Security Policy amendment) — the
        # scope /v1/browser/health reports for Stagehand. The global flag also covers n8n,
        # which does not bear on this lane; it stays the overall summary.
        verdict = capability_gate_verdict(evaluate_production_gates(), STAGEHAND_GATE_SLICE)
        if verdict[0] is not True:
            return verdict
        return True, str(reason)

    return gate


STAGEHAND_GATE_SLICE = "stagehand"
#: Review I2 N-7 — the gate model capability for Jev browser effect.
JEV_BROWSER_EFFECT_GATE_SLICE = "jev_browser_effect"


def capability_gate_verdict(gates: dict[str, Any], capability: str) -> tuple[bool, str]:
    """(permitted, reason) for one capability slice of ``evaluate_production_gates()``.

    Missing slice, unreadable model or any gate not GREEN is closed.
    """
    slice_ = (gates.get("capabilities") or {}).get(capability)
    if not isinstance(slice_, dict):
        return False, f"PRODUCTION_GATES_NOT_GREEN:{capability}:CAPABILITY_NOT_IN_GATE_MODEL"
    if slice_.get("production_activation_permitted") is not True:
        not_green = ",".join(slice_.get("gates_not_green") or [])[:200]
        detail = not_green or slice_.get("error") or gates.get("gate_model_error") or "UNKNOWN"
        return False, f"PRODUCTION_GATES_NOT_GREEN:{detail}"
    return True, f"{capability.upper()}_GATES_GREEN"


def load_jev_browser_effect_gate() -> Callable[[], Any]:
    """VAN's gate on acting on a Jev browser proposal (review I2 N-7).

    Blueprint §11: no Jev module can carry effect today, and PROPOSE_ACTION stays SHADOW
    until a separate owner decision. dial-jev's ``apply_effect: true`` under ACTIVE is its own
    report and is not that decision. This gate reads the ``jev_browser_effect`` slice of the
    production gate model (``VAN-JEV-BROWSER-EFFECT-001.yaml``, which starts SHADOW_ONLY, plus
    the Harness record Jev's actions go through and the Security Policy amendment). Anything
    not GREEN — including a missing model or record — keeps every Jev proposal a shadow.
    """

    async def gate() -> tuple[bool, str]:
        try:
            from van_gateway.automation.production_gates import evaluate_production_gates
        except ImportError:
            return False, "PRODUCTION_GATE_MODEL_MISSING"
        return capability_gate_verdict(evaluate_production_gates(), JEV_BROWSER_EFFECT_GATE_SLICE)

    return gate


__all__ = [
    "JEV_BROWSER_EFFECT_GATE_SLICE",
    "OwnerControlProbe",
    "STAGEHAND_GATE_SLICE",
    "WORKER_HEALTH_PENDING_PREFIX",
    "capability_gate_verdict",
    "load_jev_browser_effect_gate",
    "load_stagehand_production_gate",
    "step_gate_memo",
    "step_gate_scope",
]
