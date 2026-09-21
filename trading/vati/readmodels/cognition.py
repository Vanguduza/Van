"""Owner-facing Rev 5.1 trading cognition read model (TRD-REV51-129).

This module folds ledger evidence into an owner-readable projection. It is read-only:
no method imports RiskAuthority, ExecutionRouter, VenueAdapter or mutation services.
Missing evidence is represented as missing evidence, never as success.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from vati.cognition.performance_ledger import MIN_DIVERGENCES_FOR_QUALIFICATION
from vati.core.events import EventKind

READ_MODEL_VERSION = "trading-cognition-readmodel/5.1.0"
MODEL_HIERARCHY = ("fable-5.1", "gpt-6-astra", "claude-opus-5", "gpt-5.6-sol")


def _events(ledger, kind: EventKind) -> list:
    try:
        return list(ledger.iter(kind))
    except Exception:
        return []


def _latest_payload(ledger, kind: EventKind) -> dict[str, Any] | None:
    rows = _events(ledger, kind)
    return dict(rows[-1].payload) if rows else None


def _tail(rows: list, n: int = 20) -> list[dict[str, Any]]:
    return [
        {
            "event_time_ms": ev.event_time_ms,
            "correlation_id": ev.correlation_id,
            "event_hash": ev.hash,
            "payload": dict(ev.payload),
        }
        for ev in rows[-n:]
    ]


def build_cognition_read_model(ledger) -> dict[str, Any]:
    assessments = _events(ledger, EventKind.COGNITIVE_ASSESSMENT)
    shadow = _events(ledger, EventKind.SHADOW_DECISION)
    performance = _events(ledger, EventKind.COGNITIVE_PERFORMANCE)
    handoffs = _events(ledger, EventKind.MODEL_HANDOFF)
    exams = _events(ledger, EventKind.DECISION_EXAM)
    missions = _events(ledger, EventKind.RESEARCH_MISSION)
    packets = _events(ledger, EventKind.RESEARCH_PACKET)
    syntheses = _events(ledger, EventKind.RESEARCH_SYNTHESIS)
    yields = _events(ledger, EventKind.RESEARCH_YIELD)
    proposals = _events(ledger, EventKind.IMPROVEMENT_PROPOSAL)
    admissions = _events(ledger, EventKind.PROPOSAL_ADMISSION)
    rejection = _latest_payload(ledger, EventKind.REJECTION_ANALYTICS)
    expansion = _events(ledger, EventKind.EXPANSION_ACTION)

    by_model: dict[str, dict[str, Any]] = {}
    for ev in assessments:
        payload = ev.payload or {}
        assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else payload
        model = str(assessment.get("model_id") or payload.get("model_id") or "unknown")
        row = by_model.setdefault(model, {"model_id": model, "assessments": 0, "latest": None})
        row["assessments"] += 1
        row["latest"] = {
            "verdict": assessment.get("verdict"),
            "reason_codes": assessment.get("reason_codes") or [],
            "confidence": assessment.get("confidence"),
            "produced_ms": assessment.get("produced_ms") or ev.event_time_ms,
            "assessment_seal": assessment.get("seal"),
        }
    for ev in performance:
        model = str((ev.payload or {}).get("model_id") or ev.correlation_id or "unknown")
        row = by_model.setdefault(model, {"model_id": model, "assessments": 0, "latest": None})
        perf = dict(ev.payload)
        # Older durable performance events predate the explicit top-level owner
        # fields. Normalise them here from their canonical evidence rather than
        # showing "unknown" or duplicating qualification logic in Android.
        qualification = perf.get("qualification")
        if "qualified" not in perf and isinstance(qualification, dict):
            perf["qualified"] = qualification.get("qualified")
        if "sample_sufficient" not in perf:
            try:
                perf["sample_sufficient"] = (
                    int(perf.get("resolved_divergences") or 0)
                    >= MIN_DIVERGENCES_FOR_QUALIFICATION
                )
            except (TypeError, ValueError):
                perf["sample_sufficient"] = False
        row["performance"] = perf
    for model in MODEL_HIERARCHY:
        by_model.setdefault(model, {"model_id": model, "assessments": 0, "latest": None})

    mission_state: dict[str, dict[str, Any]] = {}
    for ev in missions:
        mid = str((ev.payload or {}).get("mission_id") or ev.correlation_id)
        if mid:
            mission_state[mid] = dict(ev.payload)
    admission_state: dict[str, dict[str, Any]] = {}
    for ev in admissions:
        pid = str((ev.payload or {}).get("proposal_id") or ev.correlation_id)
        if pid:
            admission_state[pid] = dict(ev.payload)

    proposal_state: list[dict[str, Any]] = []
    for ev in proposals[-50:]:
        payload = dict(ev.payload)
        pid = str(payload.get("proposal_id") or ev.correlation_id)
        payload["admission"] = admission_state.get(pid)
        proposal_state.append(payload)

    shadow_status = Counter(str((ev.payload or {}).get("status") or "UNKNOWN") for ev in shadow)
    expansion_modes = Counter(str((ev.payload or {}).get("mode") or "UNKNOWN") for ev in expansion)
    exam_latest = dict(exams[-1].payload) if exams else None

    return {
        "read_model_version": READ_MODEL_VERSION,
        "authority": {
            "cognition_mode": "OFFLINE_EVOLUTION+SHADOW_LIVE",
            "live_advisory": "DISABLED",
            "live_status": "NOT_CLAIMED",
            "model_hierarchy": list(MODEL_HIERARCHY),
            "execution_authority": "VATI_RISK_AUTHORITY_AND_EXECUTION_ROUTER_ONLY",
        },
        "summary": {
            "assessments": len(assessments), "shadow_decisions": len(shadow),
            "performance_records": len(performance), "handoffs": len(handoffs),
            "decision_exams": len(exams), "research_missions": len(mission_state),
            "research_packets": len(packets), "research_syntheses": len(syntheses),
            "improvement_proposals": len(proposals), "proposal_admissions": len(admissions),
        },
        "models": [by_model[k] for k in sorted(by_model, key=lambda x: (MODEL_HIERARCHY.index(x) if x in MODEL_HIERARCHY else 999, x))],
        "shadow": {"by_status": dict(sorted(shadow_status.items())), "recent": _tail(shadow)},
        "handoffs": _tail(handoffs),
        "decision_exam": exam_latest,
        "research": {
            "missions": [mission_state[k] for k in sorted(mission_state)],
            "recent_packets": _tail(packets), "recent_syntheses": _tail(syntheses),
            "latest_yield": dict(yields[-1].payload) if yields else None,
        },
        "evolution": {"proposals": proposal_state, "recent_admissions": _tail(admissions)},
        "rejections": rejection or {"total": 0, "by_category": {}, "by_reason": {}},
        "expansion": {
            "mode_counts": dict(sorted(expansion_modes.items())), "recent": _tail(expansion),
            "live_promotion_claimed": False,
        },
    }


__all__ = ["MODEL_HIERARCHY", "READ_MODEL_VERSION", "build_cognition_read_model"]
