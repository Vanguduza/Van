"""Gateway adapter for the read-only VATI cognition projection (TRD-REV51-131).

GAP-F-004 corrected here as well as in the trading process. This read model used
to answer `cognition_mode: "OFFLINE_EVOLUTION+SHADOW_LIVE"` and
`live_advisory: "DISABLED"` on every host, and advertise a four-model hierarchy,
while no provider invoker existed anywhere in production — so the owner surface
described an active shadow-cognition system that was structurally empty. Two
different things were being conflated: what this build *supports* and what this
host is *configured to do*.

They are now reported separately. `cognition_invoker` is the invoker the running
account service actually constructed (`none`, `http_json` or `hermes_run`), read
from the `COGNITION_INVOKER` session event the service writes at startup, and
`invoker_state` is `MODEL_INVOKER_UNCONFIGURED` whenever that invoker is `none`.
`model_hierarchy` is kept but relabelled `supported_model_hierarchy`, because a
list of models a build could route to is not evidence that any of them answered.
"""
from __future__ import annotations

from typing import Any

#: The Rev 5.1 hierarchy this build can route to. Availability routing only:
#: every rung carries identical authority (INV-MODEL-001). Listing it says
#: nothing about whether an invoker is configured on this host.
SUPPORTED_MODEL_HIERARCHY = ["fable-5.1", "gpt-6-astra", "claude-opus-5", "gpt-5.6-sol"]

#: What the read model says when no invoker was constructed. GAP-F-004's
#: acceptance criterion: without one, the abstention is stated explicitly.
UNCONFIGURED = "MODEL_INVOKER_UNCONFIGURED"

INVOKER_MODES = ("none", "http_json", "hermes_run")


def _authority(invoker: str = "none", detail: dict[str, Any] | None = None) -> dict[str, Any]:
    configured = invoker in INVOKER_MODES and invoker != "none"
    return {
        # The actual state of this host, not a constant.
        "cognition_invoker": invoker if invoker in INVOKER_MODES else "none",
        "invoker_state": "CONFIGURED" if configured else UNCONFIGURED,
        # Retained for the existing Android surface, now honest about what it
        # means: shadow measurement is live only when something can be invoked.
        "cognition_mode": (
            "OFFLINE_EVOLUTION+SHADOW_LIVE" if configured else "OFFLINE_EVOLUTION_ONLY"),
        "live_advisory": "DISABLED",
        "live_status": "NOT_CLAIMED",
        "supported_model_hierarchy": list(SUPPORTED_MODEL_HIERARCHY),
        "execution_authority": "VATI_RISK_AUTHORITY_AND_EXECUTION_ROUTER_ONLY",
        **(detail or {}),
    }


def empty_cognition_read_model() -> dict[str, Any]:
    return {
        "ledger_available": False,
        "read_model_version": "trading-cognition-readmodel/5.1.0",
        "authority": _authority(),
        "summary": {}, "models": [], "shadow": {"by_status": {}, "recent": []},
        "handoffs": [], "decision_exam": None,
        "research": {"missions": [], "recent_packets": [], "recent_syntheses": [], "latest_yield": None},
        "evolution": {"proposals": [], "recent_admissions": []},
        "rejections": {"total": 0, "by_category": {}, "by_reason": {}},
        "expansion": {"mode_counts": {}, "recent": [], "live_promotion_claimed": False},
    }


def invoker_state_from_ledger(ledger) -> dict[str, Any]:
    """The invoker the trading process last reported building, from the ledger.

    The account service writes one `COGNITION_INVOKER` session event on every
    start. Reading it here means the gateway reports what the trading process
    actually constructed rather than what this build is capable of — which is
    exactly the confusion GAP-F-004 recorded.
    """
    from vati.core.events import EventKind

    invoker, detail = "none", {}
    for event in ledger.iter(EventKind.SESSION):
        if event.payload.get("event") != "COGNITION_INVOKER":
            continue
        invoker = str(event.payload.get("cognition_invoker", "none"))
        detail = {
            "endpoint_configured": bool(event.payload.get("endpoint_configured")),
            "credential_configured": bool(event.payload.get("credential_configured")),
            "model_id": event.payload.get("model_id"),
            "reported_ms": event.event_time_ms,
        }
    return _authority(invoker, detail)


def cognition_from_ledger(ledger) -> dict[str, Any]:
    from vati.readmodels.cognition import build_cognition_read_model

    built = build_cognition_read_model(ledger)
    # The projection's own `authority` block is replaced rather than merged:
    # one place decides what this host claims about its cognition, and a stale
    # constant underneath it would be the defect all over again.
    built["authority"] = invoker_state_from_ledger(ledger)
    return {"ledger_available": True, **built}


__all__ = [
    "SUPPORTED_MODEL_HIERARCHY", "UNCONFIGURED", "cognition_from_ledger",
    "empty_cognition_read_model", "invoker_state_from_ledger",
]
