"""Gateway adapter for the read-only VATI cognition projection (TRD-REV51-131)."""
from __future__ import annotations
from typing import Any


def empty_cognition_read_model() -> dict[str, Any]:
    return {
        "ledger_available": False,
        "read_model_version": "trading-cognition-readmodel/5.1.0",
        "authority": {
            "cognition_mode": "OFFLINE_EVOLUTION+SHADOW_LIVE",
            "live_advisory": "DISABLED",
            "live_status": "NOT_CLAIMED",
            "model_hierarchy": ["fable-5.1", "gpt-6-astra", "claude-opus-5", "gpt-5.6-sol"],
            "execution_authority": "VATI_RISK_AUTHORITY_AND_EXECUTION_ROUTER_ONLY",
        },
        "summary": {}, "models": [], "shadow": {"by_status": {}, "recent": []},
        "handoffs": [], "decision_exam": None,
        "research": {"missions": [], "recent_packets": [], "recent_syntheses": [], "latest_yield": None},
        "evolution": {"proposals": [], "recent_admissions": []},
        "rejections": {"total": 0, "by_category": {}, "by_reason": {}},
        "expansion": {"mode_counts": {}, "recent": [], "live_promotion_claimed": False},
    }


def cognition_from_ledger(ledger) -> dict[str, Any]:
    from vati.readmodels.cognition import build_cognition_read_model
    return {"ledger_available": True, **build_cognition_read_model(ledger)}


__all__ = ["cognition_from_ledger", "empty_cognition_read_model"]
