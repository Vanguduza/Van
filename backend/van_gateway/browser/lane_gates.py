"""Lane gates shared by the interaction router, the Stagehand adapter and the browser API.

Moved out of ``interaction_router`` (unit G2b, at unit G2a's request) so ``adapters.py`` and
``api.py`` can import them at module level instead of lazily: this module imports nothing
from ``adapters`` or ``api``. ``interaction_router`` re-exports every name, so existing
imports are unchanged.

* ``OwnerControlProbe`` — owner takeover preempts automation (owner decision 2026-09-29 §9).
* ``load_stagehand_production_gate`` — the Stagehand production gate (placement on
  van-browser-core AND the production gate model), settings-first.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from van_gateway.browser.models import BrowserTask

#: ``placement.stagehand_production_enabled`` reasons that mean "settings are fine, only the
#: worker's live /health is missing" — the one case where the endpoint may be contacted.
WORKER_HEALTH_PENDING_PREFIX = "VAN_BROWSER_CORE_UNAVAILABLE:"


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
        permitted, reason = fn(settings, worker_health=None)
        if permitted is not True and not str(reason).startswith(WORKER_HEALTH_PENDING_PREFIX):
            return False, str(reason or "PRODUCTION_DISABLED")
        health = await _fetch_stagehand_worker_health(stagehand) if stagehand is not None else None
        permitted, reason = fn(settings, worker_health=health)
        if permitted is not True:
            return False, str(reason or "PRODUCTION_DISABLED")
        try:
            from van_gateway.automation.production_gates import evaluate_production_gates
        except ImportError:
            return False, "PRODUCTION_GATE_MODEL_MISSING"
        gates = evaluate_production_gates()
        if gates.get("production_activation_permitted") is not True:
            not_green = ",".join(gates.get("production_gates_not_green") or [])[:200]
            return False, f"PRODUCTION_GATES_NOT_GREEN:{not_green or gates.get('gate_model_error') or 'UNKNOWN'}"
        return True, str(reason)

    return gate


__all__ = [
    "OwnerControlProbe",
    "WORKER_HEALTH_PENDING_PREFIX",
    "load_stagehand_production_gate",
]
