"""C5 — LiveAdjustment evidence must be typed, hashed, resolvable VATI evidence.

EXPERIENCE asks the question. EVIDENCE establishes what happened. AUTHORITY
decides what may change. Hindsight/OpenViking/DEIL output is never live evidence."""
from __future__ import annotations

from decimal import Decimal

import pytest

from vati.core import EventKind, Ledger
from vati.core.events import make_event
from vati.learning import Environment, HealthObservation, HermesMemoryBridge, MemoryBridgeError, StrategyHealthTracker, BrokerLearner
from vati.learning.boundary import LearningBoundary, LearningBoundaryError, LiveAdjustment, LiveAdjustmentProposal, LiveTarget
from vati.learning.evidence import (
    EVIDENCE_CLASS_SOURCES, CompositeEvidenceResolver, EvidenceClass, EvidenceError, EvidenceRecord, InMemoryEvidenceStore,
    LedgerEvidenceResolver, make_evidence_ref, parse_evidence_ref,
)

D = Decimal
SID = "strat-1"
BKEY = "mt5-a:EURUSD:LONDON"


def health_evidence(store, key=SID, n=30, env=Environment.LIVE, extra=None):
    return tuple(store.register(EvidenceClass.STRATEGY_HEALTH_OBSERVATION,
                                {"strategy_id": key, "environment": env, "r_multiple": "-1", "observation_seq": i, **(extra or {})})
                 for i in range(n))


def tca_evidence(store, key=BKEY, n=30, env=Environment.LIVE):
    broker, symbol, session = key.split(":")
    return tuple(store.register(EvidenceClass.TCA_RECORD,
                                {"broker": broker, "symbol": symbol, "session": session, "environment": env, "cost_ratio": "1.5", "observation_seq": i})
                 for i in range(n))


# ------------------------------------------------------------ the defect
def test_repro_hindsight_reflection_with_forged_sample_count_is_rejected():
    adj = LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"),
                         evidence_refs=("hindsight-reflection: this strategy looks tired",),
                         environment_weighted_samples=D(30))
    with pytest.raises(LearningBoundaryError):
        LearningBoundary.check(adj)
    # even with a resolver present, the reflection is not evidence
    with pytest.raises(LearningBoundaryError, match="experiential"):
        LearningBoundary.check(adj, InMemoryEvidenceStore())


def test_one_hindsight_reflection_and_a_fake_count_cannot_reduce_capsule_health():
    store = InMemoryEvidenceStore()
    for ref in ("hindsight://reflection/strat-1/tired", "hindsight-reflection: this strategy looks tired"):
        with pytest.raises(LearningBoundaryError, match="experiential"):
            LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, (ref,), D(30)), store)
        with pytest.raises(LearningBoundaryError, match="experiential"):
            LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, (ref,)), store)


def test_openviking_ref_cannot_demote_a_strategy():
    store = InMemoryEvidenceStore()
    good = health_evidence(store)
    for ref in ("openviking://trading/strat-1/lesson", "viking://resources/strat-1"):
        with pytest.raises(LearningBoundaryError, match="experiential"):
            LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "SHADOW", (ref,)), store)
        # mixing it into otherwise valid evidence still rejects the whole adjustment
        with pytest.raises(LearningBoundaryError, match="experiential"):
            LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "SHADOW", good + (ref,)), store)


def test_deil_ref_cannot_change_broker_liquidity_multiplier():
    store = InMemoryEvidenceStore()
    with pytest.raises(LearningBoundaryError, match="experiential"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, ("deil://trading/broker/mt5-a",)), store)
    with pytest.raises(LearningBoundaryError, match="experiential"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.BROKER_PROFILE, BKEY, D("0"), None, ("deil://trading/broker/mt5-a",), D(30)), store)


@pytest.mark.parametrize("ref", [
    "this strategy looks tired",                                            # free text
    "a" * 64,                                                               # bare hash, no class
    "broker-profile:mt5-a:EURUSD:LONDON",                                   # legacy free-form tag
    "vati-evidence:STRATEGY_HEALTH_OBSERVATION:" + "a" * 63,                # short hash
    "vati-evidence:STRATEGY_HEALTH_OBSERVATION:" + "A" * 64,                # upper-case hex
    "vati-evidence:STRATEGY_HEALTH_OBSERVATION:" + "g" * 64,                # non-hex
    "vati-evidence:STRATEGY_HEALTH_OBSERVATION:" + "a" * 64 + "\n",         # trailing junk
    "vati-evidence:MODEL_OPINION:" + "a" * 64,                              # class not allowlisted
])
def test_free_text_malformed_and_unknown_class_refs_are_rejected(ref):
    with pytest.raises(EvidenceError):
        parse_evidence_ref(ref)
    store = InMemoryEvidenceStore()
    with pytest.raises(LearningBoundaryError, match="live evidence rejected"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, health_evidence(store) + (ref,)), store)


def test_well_formed_but_unresolvable_hash_is_rejected():
    store = InMemoryEvidenceStore()
    ghost = make_evidence_ref(EvidenceClass.STRATEGY_HEALTH_OBSERVATION, "b" * 64)
    assert parse_evidence_ref(ghost).identity == "b" * 64   # grammar is fine
    with pytest.raises(LearningBoundaryError, match="unresolvable"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, (ghost,), D(1)), store)
    # a real record cited under the wrong class does not resolve either
    real = health_evidence(store, n=1)[0]
    wrong_class = make_evidence_ref(EvidenceClass.TCA_RECORD, parse_evidence_ref(real).identity)
    with pytest.raises(LearningBoundaryError, match="unresolvable"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.7"), None, (wrong_class,), D(1)), store)


def test_duplicate_evidence_cannot_inflate_the_sample_count():
    store = InMemoryEvidenceStore()
    one = health_evidence(store, n=1)
    # 30 citations of one LIVE record is one sample, not thirty
    with pytest.raises(LearningBoundaryError, match="!= 1.0 recomputed"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, one * 30, D(30)), store)
    with pytest.raises(LearningBoundaryError, match="insufficient"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, one * 30), store)
    # registering the same content again yields the same identity, not a new sample
    again = health_evidence(store, n=1)
    assert again == one and len(store) == 1


def test_caller_forged_sample_count_is_rejected():
    store = InMemoryEvidenceStore()
    refs = health_evidence(store, n=30)
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, refs, D(45)), store)   # higher
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, refs, D(29)), store)   # lower
    # no resolver at all → no authority, whatever the count says
    with pytest.raises(LearningBoundaryError, match="no EvidenceResolver"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, refs, D(30)))


def test_replay_and_counterfactual_weight_cannot_be_caller_forged():
    store = InMemoryEvidenceStore()
    # 60 counterfactual records that claim a weight of 1.0 in their own content
    cf = health_evidence(store, n=60, env=Environment.COUNTERFACTUAL, extra={"weight": "1.0", "label": "SIMULATED_EVIDENCE_NOT_CAUSAL"})
    adj = LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("1"), None, cf), store)
    assert adj.environment_weighted_samples == D("12.0")   # 60 × 0.2 from ENVIRONMENT_WEIGHT, not 60 × 1.0
    with pytest.raises(LearningBoundaryError, match="insufficient"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, cf), store)
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, cf, D(60)), store)
    # replayed execution facts weigh zero for the broker profile
    rp = tca_evidence(store, n=100, env=Environment.REPLAY)
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, rp, D(30)), store)
    with pytest.raises(LearningBoundaryError, match="insufficient"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, rp), store)
    # a record's identity is its content: the environment cannot be swapped after hashing
    rec = store.resolve(parse_evidence_ref(cf[0]))
    with pytest.raises(EvidenceError, match="does not match"):
        EvidenceRecord.from_content(EvidenceClass.STRATEGY_HEALTH_OBSERVATION, {**rec.content, "environment": "LIVE"}, identity=rec.identity)


def test_evidence_about_another_subject_does_not_count():
    store = InMemoryEvidenceStore()
    other = health_evidence(store, key="strat-2", n=40)
    with pytest.raises(LearningBoundaryError, match="not about"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "DEGRADED", other), store)


def test_valid_resolvable_evidence_meeting_threshold_still_passes_existing_rules():
    store = InMemoryEvidenceStore()
    refs = health_evidence(store, n=30)
    adj = LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "DEGRADED", refs), store)
    assert adj.environment_weighted_samples == D("30.0") and adj.demote_to == "DEGRADED" and adj.evidence_refs == refs
    assert LearningBoundary.check(adj, store) is adj
    # existing rules still hold with good evidence
    with pytest.raises(LearningBoundaryError, match="reduce-only"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("1.1"), None, refs), store)
    with pytest.raises(LearningBoundaryError, match="promotion"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "CERTIFIED_LIVE", refs), store)
    with pytest.raises(LearningBoundaryError, match="only capsule health"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.5"), "SHADOW", tca_evidence(store)), store)
    with pytest.raises(LearningBoundaryError, match="may not touch"):
        LearningBoundary.admit(LiveAdjustmentProposal("LEVERAGE", SID, D("0.5"), None, refs), store)   # type: ignore[arg-type]
    # broker profile with 30 LIVE TCA facts
    b = LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, tca_evidence(store)), store)
    assert b.environment_weighted_samples == D("30.0")


def test_producers_emit_typed_resolvable_evidence():
    t = StrategyHealthTracker(sustain=1)
    for i in range(40):
        t.observe(HealthObservation(SID, Environment.LIVE, D("-1"), False, D("2.5"), False, f"ev-{i}"))
    adj = t.live_adjustment(SID)
    assert adj is not None and adj.environment_weighted_samples == t.verdict(SID).weighted_samples == D("40.0")
    assert all(parse_evidence_ref(r).evidence_class is EvidenceClass.STRATEGY_HEALTH_OBSERVATION for r in adj.evidence_refs)
    assert LearningBoundary.check(adj, t.evidence) is adj
    # the window bounds both the buffer and the store
    for i in range(100):
        t.observe(HealthObservation(SID, Environment.LIVE, D("-1"), False, D("2.5"), False, f"ev2-{i}"))
    assert len(t.evidence) == t.window
    bl = BrokerLearner()
    for _ in range(40):
        bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1.5"), slippage_pips=D("1"), rejected=False, in_event_window=False)
    b = bl.live_adjustment("mt5-a", "EURUSD", "LONDON")
    assert b.environment_weighted_samples == D("40.0") and len(b.evidence_refs) == 40
    assert all(parse_evidence_ref(r).evidence_class is EvidenceClass.TCA_RECORD for r in b.evidence_refs)


def test_ledger_resolver_verifies_identity_and_kind():
    led = Ledger()
    tca = make_event(EventKind.TCA_RECORD, "cycle", {"learning_environment": "LIVE", "broker": "mt5-a", "symbol": "EURUSD", "session": "LONDON", "cost_ratio": "1.4"},
                     event_time_ms=1, received_time_ms=1)
    led.append(tca)
    note = make_event(EventKind.NEWS_HEADLINE, "news", {"headline": "x"}, event_time_ms=2, received_time_ms=2)
    led.append(note)
    r = LedgerEvidenceResolver(led)
    rec = r.resolve(parse_evidence_ref(make_evidence_ref(EvidenceClass.TCA_RECORD, tca.hash)))
    assert rec.environment is Environment.LIVE and BKEY in rec.subjects and rec.identity == tca.hash
    with pytest.raises(EvidenceError, match="unresolvable"):   # right hash, wrong class/kind
        r.resolve(parse_evidence_ref(make_evidence_ref(EvidenceClass.TRADE_REVIEW, tca.hash)))
    with pytest.raises(EvidenceError, match="no environment"):   # a ledger event with no environment cannot be weighted
        r.resolve(parse_evidence_ref(make_evidence_ref(EvidenceClass.LEDGER_EVENT, note.hash)))
    both = CompositeEvidenceResolver((InMemoryEvidenceStore(), r))
    adj = LearningBoundary.check(LiveAdjustment(LiveTarget.BROKER_PROFILE, BKEY, D("1"), None, (make_evidence_ref(EvidenceClass.TCA_RECORD, tca.hash),), D("1.0")), both)
    assert adj.multiplier == 1


def test_every_allowlisted_class_is_mapped_to_a_vati_source():
    assert set(EVIDENCE_CLASS_SOURCES) == set(EvidenceClass)


# ------------------------------------------------------- memory bridge
def test_owner_preference_continuity_record_is_rejected():
    b = HermesMemoryBridge()
    with pytest.raises(MemoryBridgeError, match="Owner Model"):
        b.remember(kind="OWNER_PREFERENCE", subject="owner", summary="prefers smaller size on Fridays", now_ms=1_000)
    assert b.records == {}
