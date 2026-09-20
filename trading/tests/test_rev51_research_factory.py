"""G12 research-factory integration tests (TRD-REV51-118..122)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from vati.cognition.handoff import HandoffRecorder
from vati.cognition.providers import QuotaScheduler, default_registry
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.research.agents import ResearchAgentFactory
from vati.research.director import FableResearchDirector, ResearchTrigger
from vati.research.missions import MissionLedger, MissionState, PacketState, ResearchContractError
from vati.research.synthesis import ClaimStatus, ResearchSynthesiser
from vati.research.yield_ledger import ResearchYieldLedger, ResearchYieldRecord


def _mission(*, ledger=None, now=1_000):
    store = MissionLedger(ledger=ledger)
    director = FableResearchDirector(store)
    mission = director.open(
        ResearchTrigger(
            "drift", "does the edge still exist?",
            evidence_ids=("e1",), data_domains=("external_web", "repository"),
            specialist_roles=("evidence", "contradiction"),
        ),
        now_ms=now,
    )
    return store, mission


def _good(_lease, _mission, _spec):
    return {
        "claims": ["edge persists"],
        "source_ids": ["official:a", "official:b"],
        "retrieval_timestamps_ms": [2_000, 2_001],
        "evidence_refs": ["sha:a", "sha:b"],
        "counterevidence": [],
        "limitations": ["short window"],
        "methods": ["replay"],
        "code_data_artifacts": ["artifact:1"],
        "reproducibility": {"seed": 7},
    }


def test_mission_is_sealed_and_replays_from_the_ledger():
    ledger = Ledger(":memory:")
    store, mission = _mission(ledger=ledger)
    store.transition(mission.mission_id, MissionState.RUNNING, now_ms=1_100)
    rebuilt = MissionLedger().rebuild(ledger.iter())
    assert rebuilt.mission(mission.mission_id).state is MissionState.RUNNING
    assert rebuilt.mission(mission.mission_id).seal_ok()


def test_mission_cannot_relax_the_live_action_prohibitions():
    _store, mission = _mission()
    with pytest.raises(ResearchContractError):
        mission.__class__(**{
            **mission.__dict__, "seal": "",
            "prohibited_live_actions": ("ORDER",),
        }).sealed()


def test_agent_success_is_a_sealed_packet_and_is_ledgered():
    ledger = Ledger(":memory:")
    store, mission = _mission(ledger=ledger)
    factory = ResearchAgentFactory(QuotaScheduler(default_registry()))
    packet = factory.run(mission, "evidence", invoke=_good, now_ms=2_000)
    store.add_packet(packet)
    assert packet.state is PacketState.COMPLETE and packet.seal_ok()
    assert ledger.count(EventKind.RESEARCH_PACKET) == 1


def test_agent_failure_is_explicit_when_all_providers_fail():
    _store, mission = _mission()
    scheduler = QuotaScheduler(default_registry())
    handoffs = HandoffRecorder()
    factory = ResearchAgentFactory(scheduler, handoffs=handoffs)
    def fail(*_args):
        raise RuntimeError("transport down")
    packet = factory.run(mission, "evidence", invoke=fail, now_ms=2_000)
    assert packet.state is PacketState.FAILED
    assert packet.failure_reason
    assert len(handoffs.all()) == 3


def test_provider_fallback_preserves_the_control_profile():
    _store, mission = _mission()
    scheduler = QuotaScheduler(default_registry())
    seen = []
    def invoke(lease, *_):
        seen.append((lease.model_id, lease.control_profile))
        if lease.model_id == "fable-5.1":
            raise TimeoutError("deadline")
        return _good(lease, None, None)
    packet = ResearchAgentFactory(scheduler).run(
        mission, "evidence", invoke=invoke, now_ms=2_000)
    assert [m for m, _ in seen] == ["fable-5.1", "gpt-6-astra"]
    assert len({profile for _, profile in seen}) == 1
    assert packet.model_id == "gpt-6-astra"


def test_deadline_exhaustion_never_becomes_a_hidden_success():
    _store, mission = _mission(now=1_000)
    packet = ResearchAgentFactory(QuotaScheduler(default_registry())).run(
        mission, "evidence", invoke=_good, now_ms=mission.deadline_ms)
    assert packet.state is PacketState.FAILED
    assert packet.failure_reason == "mission_deadline_expired"


def test_contradictory_agents_are_reported_not_majority_voted_away():
    _store, mission = _mission()
    factory = ResearchAgentFactory(QuotaScheduler(default_registry()))
    a = factory.run(mission, "evidence", invoke=_good, now_ms=2_000)
    def contrary(lease, m, spec):
        out = dict(_good(lease, m, spec))
        out["claims"] = ["different claim"]
        out["counterevidence"] = ["edge persists"]
        return out
    b = factory.run(mission, "contradiction", invoke=contrary, now_ms=2_001)
    synthesis = ResearchSynthesiser().synthesise(mission, [a, b], now_ms=3_000)
    edge = next(c for c in synthesis.claims if c.claim == "edge persists")
    assert edge.status is ClaimStatus.CONTESTED


def test_unsupported_single_source_claim_is_not_admitted():
    _store, mission = _mission()
    def thin(lease, m, spec):
        out = dict(_good(lease, m, spec))
        out["source_ids"] = ["one"]
        out["retrieval_timestamps_ms"] = [2_000]
        out["evidence_refs"] = ["one"]
        return out
    p = ResearchAgentFactory(QuotaScheduler(default_registry())).run(
        mission, "evidence", invoke=thin, now_ms=2_000)
    s = ResearchSynthesiser().synthesise(mission, [p], now_ms=3_000)
    assert s.claims[0].status is ClaimStatus.INSUFFICIENT_EVIDENCE
    assert not s.admitted_claims


def test_duplicate_packet_is_idempotent_not_double_evidence():
    store, mission = _mission()
    packet = ResearchAgentFactory(QuotaScheduler(default_registry())).run(
        mission, "evidence", invoke=_good, now_ms=2_000)
    store.add_packet(packet)
    store.add_packet(packet)
    assert len(store.packets(mission.mission_id)) == 1


def test_yield_ledger_is_diagnostic_not_authority():
    y = ResearchYieldLedger()
    y.record(ResearchYieldRecord("m", 12, 2, 1, 1, 0, 1, "unknown", 5))
    summary = y.summary()
    assert summary["missions"] == 1
    assert summary["is_authority"] is False


def test_research_modules_have_no_order_or_live_config_path():
    root = Path(__file__).resolve().parents[1] / "vati" / "research"
    forbidden_imports = (
        "vati.execution.router", "vati.execution.base", "vati.risk.authority",
        "vati.app.account_service",
    )
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        assert not any(i.startswith(forbidden_imports) for i in imported), (path, imported)
        text = path.read_text(encoding="utf-8")
        assert "OrderCommand(" not in text
        assert ".submit(" not in text
