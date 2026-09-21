"""G13 evolution/protected-path tests (TRD-REV51-123..128)."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.evolution.admission import AdmissionState, ProposalAdmissionControl, REQUIRED_GATES
from vati.evolution.archive import EvolutionArchive, EvolutionRecord
from vati.evolution.proposals import ProposalType, SystemImprovementProposal, SystemImprovementProposalEngine
from vati.evolution.protected_paths import ProtectedPathPolicy
from vati.observability.rejection_analytics import RejectionAnalyticsEngine
from vati.risk.growth import GrowthOptimalityDiagnostic

D = Decimal


def _proposal(*, live=False, paths=("trading/vati/cognition/context.py",)):
    return SystemImprovementProposal(
        proposal_id="p1", proposal_type=ProposalType.CONTEXT_RETRIEVAL,
        title="improve context", description="version the extra context section",
        evidence_refs=("research:1",), affected_paths=tuple(paths),
        live_affecting=live, proposed_by="fable-research", created_ms=10,
    ).sealed()


def _gates(value=True):
    return {g: value for g in REQUIRED_GATES}


def test_archive_is_immutable_and_keeps_supersession_history():
    a = EvolutionArchive()
    r1 = EvolutionRecord("c1", "v1", "v2", ("r1",), ("e1",), "tests-v1",
                         ("bt1",), ("sh1",), "REJECTED", "tail regression", "", 1)
    r2 = EvolutionRecord("c2", "v1", "v3", ("r2",), ("e2",), "tests-v1",
                         ("bt2",), ("sh2",), "ADMITTED", "", "c1", 2)
    a.append(r1); a.append(r2)
    assert [r.candidate_id for r in a.chain("c2")] == ["c2", "c1"]
    with pytest.raises(ValueError):
        a.append(EvolutionRecord(**{**r1.__dict__, "outcome": "ADMITTED"}))


def test_unclassified_live_impact_is_forbidden():
    p = _proposal()
    with pytest.raises(ValueError):
        p.__class__(**{**p.__dict__, "seal": "", "live_affecting": None}).sealed()


def test_protected_path_requires_authorised_review_for_live_change():
    p = _proposal(live=True, paths=("trading/vati/risk/authority.py",))
    rec = ProposalAdmissionControl().assess(
        p, gate_evidence=_gates(), owner_approved=False, now_ms=20)
    assert rec.state is AdmissionState.HELD_FOR_AUTHORISED_REVIEW
    assert rec.owner_approval_required


def test_protected_path_may_be_admitted_only_after_all_gates_and_owner_review():
    p = _proposal(live=True, paths=("trading/vati/execution/router.py",))
    rec = ProposalAdmissionControl().assess(
        p, gate_evidence=_gates(), owner_approved=True, now_ms=20)
    assert rec.state is AdmissionState.ADMITTED


def test_any_failed_gate_rejects_even_an_unprotected_proposal():
    gates = _gates(); gates["risk_regression"] = False
    rec = ProposalAdmissionControl().assess(
        _proposal(), gate_evidence=gates, now_ms=20)
    assert rec.state is AdmissionState.REJECTED
    assert "risk_regression" in ",".join(rec.reasons)


@pytest.mark.parametrize("path,text", [
    ("trading/vati/risk/authority.py", ""),
    ("trading/vati/execution/router.py", ""),
    ("trading/vati/execution/protection.py", "def widen_stop(): pass"),
    ("trading/vati/risk/mandate.py", "max_risk_per_trade = 1"),
    ("x.py", "EXPANSION_MODE = Mode.LIVE"),
    ("x.py", "class RiskAuthority: pass"),
])
def test_protected_scan_catches_authority_and_risk_mutations(path, text):
    scan = ProtectedPathPolicy().scan((path,), diff_text=text)
    assert scan.requires_authorised_review


def test_unknown_policy_is_not_silently_admitted():
    rec = ProposalAdmissionControl().assess(
        _proposal(), gate_evidence={}, now_ms=20)
    assert rec.state is AdmissionState.REJECTED
    assert any(r.startswith("MISSING_GATES:") for r in rec.reasons)


def test_growth_diagnostic_is_offline_and_cannot_change_risk():
    d = GrowthOptimalityDiagnostic().evaluate(
        diagnostic_id="g1", win_probability=D("0.55"), payoff_ratio=D("1.5"),
        current_risk_fraction=D("0.005"), drawdown_constraint=D("0.02"),
        data_window="2026Q3", regime_segments=("trend", "range"),
        assumptions=("iid within regime",), uncertainty="high",
        proposal_id="p-growth", now_ms=30)
    assert d.body()["live_authority"] is False
    assert not hasattr(d, "approved_size")


def test_rejection_analytics_separates_safety_from_capacity_and_data():
    a = RejectionAnalyticsEngine().compile(
        ["KILL_SWITCH", "PORTFOLIO_HEAT", "STALE_DATA", "EVENT_BLACKOUT"], now_ms=40)
    cats = dict(a.by_category)
    assert cats["safety"] == 1
    assert cats["capacity_risk_heat"] == 1
    assert cats["stale_or_unknown_data"] == 1
    assert cats["event_blackout"] == 1
    assert a.body()["may_weaken_guard"] is False


def test_evolution_modules_do_not_import_execution_or_live_authority():
    roots = [
        Path(__file__).resolve().parents[1] / "vati" / "evolution",
        Path(__file__).resolve().parents[1] / "vati" / "risk" / "growth.py",
        Path(__file__).resolve().parents[1] / "vati" / "observability" / "rejection_analytics.py",
    ]
    forbidden = ("vati.execution.router", "vati.execution.base", "vati.risk.authority")
    files = []
    for root in roots:
        files.extend(root.glob("*.py") if root.is_dir() else [root])
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Import):
                imports.extend(a.name for a in node.names)
        assert not any(i.startswith(forbidden) for i in imports), (path, imports)
        # Inspect executable syntax, not protection-vocabulary string literals.
        # protected_paths.py deliberately contains "OrderCommand(" as a marker
        # used to detect dangerous diffs; that does not make it an order sender.
        calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
        assert not any(isinstance(fn, ast.Name) and fn.id == "OrderCommand" for fn in calls)
        assert not any(isinstance(fn, ast.Attribute) and fn.attr == "submit" for fn in calls)


def test_admission_and_archive_events_are_ledgered():
    ledger = Ledger(":memory:")
    p = SystemImprovementProposalEngine(ledger=ledger).propose(_proposal())
    ProposalAdmissionControl(ledger=ledger).assess(p, gate_evidence=_gates(), now_ms=50)
    EvolutionArchive(ledger=ledger).append(
        EvolutionRecord("c1","v1","v2",("r",),("e",),"t",("b",),("s",),"REJECTED","x","",50))
    assert ledger.count(EventKind.IMPROVEMENT_PROPOSAL) == 1
    assert ledger.count(EventKind.PROPOSAL_ADMISSION) == 1
    assert ledger.count(EventKind.EVOLUTION_CANDIDATE) == 1



def test_rejection_analytics_can_refresh_from_the_durable_ledger():
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.observability.rejection_analytics import RejectionAnalyticsEngine

    ledger = Ledger(":memory:")
    ledger.append(make_event(
        EventKind.RISK_DECISION, "test",
        {"decision": {"decision": "REJECTED", "reason_code": "PORTFOLIO_HEAT"}},
        event_time_ms=1, received_time_ms=1))
    ledger.append(make_event(
        EventKind.PRETRADE_CONTROL, "test",
        {"verdict": "REJECT", "reason_code": "ROUTE_UNRESOLVED"},
        event_time_ms=2, received_time_ms=2))
    out = RejectionAnalyticsEngine(ledger=ledger).compile_ledger(
        ledger, now_ms=3)
    assert out.total == 2
    assert dict(out.by_category)["capacity_risk_heat"] == 1
    assert dict(out.by_category)["route_failure"] == 1
    assert ledger.count(EventKind.REJECTION_ANALYTICS) == 1
