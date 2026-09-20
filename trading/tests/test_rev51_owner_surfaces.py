from __future__ import annotations

from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger
from vati.readmodels.cognition import MODEL_HIERARCHY, build_cognition_read_model


def emit(ledger, kind, payload, ms, corr=""):
    ledger.append(make_event(
        kind, "test", payload, event_time_ms=ms,
        received_time_ms=ms, correlation_id=corr))


def test_empty_projection_is_honest_about_live_authority():
    ledger = Ledger(":memory:")
    model = build_cognition_read_model(ledger)
    assert model["authority"]["cognition_mode"] == "OFFLINE_EVOLUTION+SHADOW_LIVE"
    assert model["authority"]["live_advisory"] == "DISABLED"
    assert model["authority"]["live_status"] == "NOT_CLAIMED"
    assert [row["model_id"] for row in model["models"]] == list(MODEL_HIERARCHY)
    assert model["summary"]["assessments"] == 0
    assert model["decision_exam"] is None


def test_assessment_performance_and_handoff_are_projected_without_inference():
    ledger = Ledger(":memory:")
    emit(ledger, EventKind.COGNITIVE_ASSESSMENT, {
        "assessment": {
            "model_id": "fable-5.1", "verdict": "REDUCE",
            "reason_codes": ["EVIDENCE_THIN"], "confidence": "0.7",
            "produced_ms": 10, "seal": "a",
        }}, 10, "i1")
    emit(ledger, EventKind.COGNITIVE_PERFORMANCE, {
        "model_id": "fable-5.1", "qualified": False,
        "sample_sufficient": False, "total_delta_r": "0.0"}, 20, "fable-5.1")
    emit(ledger, EventKind.MODEL_HANDOFF, {
        "from_model_id": "fable-5.1", "to_model_id": "gpt-6-astra",
        "reason": "TIMEOUT", "control_profile": "rev51/1"}, 30, "ctx")
    model = build_cognition_read_model(ledger)
    fable = model["models"][0]
    assert fable["latest"]["verdict"] == "REDUCE"
    assert fable["performance"]["qualified"] is False
    assert model["handoffs"][0]["payload"]["reason"] == "TIMEOUT"


def test_research_and_evolution_join_on_durable_ids():
    ledger = Ledger(":memory:")
    emit(ledger, EventKind.RESEARCH_MISSION, {
        "mission_id": "m1", "state": "RUNNING", "hypothesis": "h"}, 10, "m1")
    emit(ledger, EventKind.RESEARCH_PACKET, {
        "packet_id": "rp1", "mission_id": "m1", "agent_role": "risk"}, 20, "m1")
    emit(ledger, EventKind.RESEARCH_SYNTHESIS, {
        "mission_id": "m1", "claims": []}, 30, "m1")
    emit(ledger, EventKind.IMPROVEMENT_PROPOSAL, {
        "proposal_id": "p1", "title": "candidate", "live_affecting": True}, 40, "p1")
    emit(ledger, EventKind.PROPOSAL_ADMISSION, {
        "proposal_id": "p1", "decision": "HOLD_OWNER_APPROVAL"}, 50, "p1")
    model = build_cognition_read_model(ledger)
    assert model["research"]["missions"][0]["mission_id"] == "m1"
    assert model["summary"]["research_packets"] == 1
    assert model["evolution"]["proposals"][0]["admission"]["decision"] == "HOLD_OWNER_APPROVAL"


def test_expansion_projection_never_claims_live_promotion():
    ledger = Ledger(":memory:")
    emit(ledger, EventKind.EXPANSION_ACTION, {
        "family_id": "f1", "mode": "SHADOW", "would_propose": True}, 10, "f1")
    model = build_cognition_read_model(ledger)
    assert model["expansion"]["mode_counts"] == {"SHADOW": 1}
    assert model["expansion"]["live_promotion_claimed"] is False


def test_read_model_has_no_order_or_risk_mutation_imports():
    import ast
    import inspect
    import vati.readmodels.cognition as module

    # Test executable dependencies rather than prose. The module deliberately
    # documents that these authority classes are absent, and the owner-facing
    # read model names the canonical execution authority as data.
    tree = ast.parse(inspect.getsource(module))
    forbidden_modules = (
        "vati.risk.authority", "vati.execution.router", "vati.execution.base",
    )
    imports = []
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.Call):
            calls.append(node.func)
    assert not any(name.startswith(forbidden_modules) for name in imports)
    assert not any(
        isinstance(fn, ast.Name)
        and fn.id in {"RiskAuthority", "ExecutionRouter", "VenueAdapter", "OrderCommand"}
        for fn in calls
    )
