"""C5 — LiveAdjustment evidence must be typed, hashed, ledger-resolved VATI evidence.

EXPERIENCE asks the question. EVIDENCE establishes what happened. AUTHORITY
decides what may change. Hindsight/OpenViking/DEIL output is never live evidence,
and a producer cannot mint evidence: identity is the hash of an authoritative
ledger event, resolved from the ledger."""
from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from vati.core import EventKind, Ledger
from vati.core.events import make_event
from vati.learning import BrokerLearner, Environment, HealthObservation, HermesMemoryBridge, MemoryBridgeError, StrategyHealthTracker
from vati.learning.boundary import LearningBoundary, LearningBoundaryError, LiveAdjustment, LiveAdjustmentProposal, LiveTarget
from vati.learning.evidence import (
    EVIDENCE_CLASS_SOURCES, CompositeEvidenceResolver, EvidenceClass, EvidenceError, EvidenceRecord, EvidenceRef, LedgerEvidenceResolver,
    ResolvedEvidenceCache, TrustedEvidenceResolver, make_evidence_ref, parse_evidence_ref,
)
from vati.learning.hooks import LearningHooks

D = Decimal
SID = "strat-1"
BKEY = "mt5-a:EURUSD:LONDON"
_SEQ = itertools.count(1)


class Src:
    """A real VATI ledger plus the runtime-bound resolver for it."""

    def __init__(self, env: Environment = Environment.LIVE) -> None:
        self.env = env
        self.ledger = Ledger()
        self.resolver = LedgerEvidenceResolver(self.ledger, session_environment=env)

    def append(self, kind: EventKind, payload: dict, corr: str, producer: str = "vati-cycle") -> str:
        ev = make_event(kind, producer, payload, event_time_ms=1_000, received_time_ms=1_000, correlation_id=corr)
        self.ledger.append(ev)
        return ev.hash

    def review(self, sid: str, i: int, *, r: str = "-1", process_ok: bool = False, cost: str = "2.5", **extra) -> str:
        """One closed trade as the runtime records it: its entry TCA_RECORD, then a TradeReview-shaped
        TRADE_REVIEW (no environment in its payload, as in production). The observed values live in
        the ledger, where the health tracker reads them (A-VATI M3)."""
        corr = f"{sid}-{i}"
        self.append(EventKind.TCA_RECORD, {"trade_intent_id": corr, "learning_environment": self.env.value, "cost_ratio": cost}, corr)
        h = self.append(EventKind.TRADE_REVIEW, {"trade_intent_id": corr, "strategy_id": sid, "r_multiple": r, "process_ok": process_ok, **extra}, corr)
        return make_evidence_ref(EvidenceClass.TRADE_REVIEW, h)

    def tca(self, broker: str, symbol: str, session: str, i: int, env: Environment | None = None, **extra) -> str:
        h = self.append(EventKind.TCA_RECORD, {"learning_environment": (env or self.env).value, "broker": broker, "symbol": symbol, "session": session,
                                               "event_window": "NORMAL", "cost_ratio": "1.5", "slippage": "1", "rejected": False, "seq": i, **extra}, f"tca-{i}")
        return make_evidence_ref(EvidenceClass.TCA_RECORD, h)


_SRCS: dict[Environment, Src] = {}


def _src(env: Environment) -> Src:
    return _SRCS.setdefault(env, Src(env))


def observe_review(t: StrategyHealthTracker, sid, r, *, env=Environment.LIVE, process_ok=True, cost=D("1"), fit=True, i=0):
    src = _src(env)
    ref = src.review(sid, i, r=str(r), process_ok=process_ok, cost=str(cost))
    return t.observe(HealthObservation(sid, env, D(str(r)), process_ok, cost, fit, ref), resolver=src.resolver)


def observe_fact(bl: BrokerLearner, *, broker, symbol, session, environment, cost_ratio, slippage_pips, rejected, in_event_window, i=None):
    src = _src(environment)
    ref = src.tca(broker, symbol, session, next(_SEQ) if i is None else i, cost_ratio=str(cost_ratio), slippage=str(slippage_pips),
                  rejected=rejected, event_window="PRE_BLACKOUT" if in_event_window else "NORMAL")
    return bl.observe(broker=broker, symbol=symbol, session=session, environment=environment, cost_ratio=cost_ratio, slippage_pips=slippage_pips,
                      rejected=rejected, in_event_window=in_event_window, evidence_ref=ref, resolver=src.resolver)


def health_evidence(src: Src, key=SID, n=30):
    return tuple(src.review(key, i) for i in range(n))


def tca_evidence(src: Src, key=BKEY, n=30, env=None):
    broker, symbol, session = key.split(":")
    return tuple(src.tca(broker, symbol, session, i, env=env) for i in range(n))


def hobs(ref, *, sid=SID, env=Environment.LIVE, r="-1"):
    return HealthObservation(sid, env, D(r), False, D("2.5"), False, ref)


# ------------------------------------------------------------ the defect
def test_repro_hindsight_reflection_with_forged_sample_count_is_rejected():
    adj = LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"),
                         evidence_refs=("hindsight-reflection: this strategy looks tired",),
                         environment_weighted_samples=D(30))
    with pytest.raises(LearningBoundaryError):
        LearningBoundary.check(adj)
    with pytest.raises(LearningBoundaryError, match="experiential"):
        LearningBoundary.check(adj, Src().resolver)


def test_reviewer_repro_30_hindsight_observations_are_rejected_at_observe():
    """Programme A review: 30× observe(evidence_ref='hindsight://reflection-42') demoted to SHADOW."""
    t, src = StrategyHealthTracker(sustain=1), Src()
    for _ in range(30):
        with pytest.raises(EvidenceError, match="experiential"):
            t.observe(hobs("hindsight://reflection-42"), resolver=src.resolver)
    assert t.verdict(SID).weighted_samples == 0 and t.live_adjustment(SID) is None and len(t.evidence) == 0


@pytest.mark.parametrize("ref", [
    "openviking://trading/strat-1", "deil://trading/strat-1", "trade-intent-0001", "this strategy looks tired", "a" * 64,
])
def test_non_ledger_sources_are_rejected_at_observe(ref):
    t, src = StrategyHealthTracker(), Src()
    with pytest.raises(EvidenceError):
        t.observe(hobs(ref), resolver=src.resolver)
    bl = BrokerLearner()
    with pytest.raises(EvidenceError):
        bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1.5"), slippage_pips=D("1"),
                   rejected=False, in_event_window=False, evidence_ref=ref, resolver=src.resolver)


def test_well_formed_ref_to_no_ledger_event_is_rejected_at_observe():
    t, src = StrategyHealthTracker(), Src()
    with pytest.raises(EvidenceError, match="unresolvable"):
        t.observe(hobs(make_evidence_ref(EvidenceClass.TRADE_REVIEW, "b" * 64)), resolver=src.resolver)
    # a derived class is not a source: STRATEGY_HEALTH_OBSERVATION cannot stand on itself
    with pytest.raises(EvidenceError, match="not a source event"):
        t.observe(hobs(make_evidence_ref(EvidenceClass.STRATEGY_HEALTH_OBSERVATION, "c" * 64)), resolver=src.resolver)
    # a real TCA record is not strategy-health evidence, and a real review is not an execution fact
    tca = src.tca("mt5-a", "EURUSD", "LONDON", 1)
    with pytest.raises(EvidenceError, match="not a source event"):
        t.observe(hobs(tca), resolver=src.resolver)
    with pytest.raises(EvidenceError, match="must cite a TCA_RECORD"):
        BrokerLearner().observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1"), slippage_pips=D("1"),
                                rejected=False, in_event_window=False, evidence_ref=src.review(SID, 1), resolver=src.resolver)


def test_same_real_trade_review_observed_30_times_counts_once():
    t, src = StrategyHealthTracker(sustain=1), Src()
    ref = src.review(SID, 7)
    for _ in range(30):
        t.observe(hobs(ref), resolver=src.resolver)
    assert t.verdict(SID).weighted_samples == D("1.0") and len(t._obs[SID]) == 1 and t.live_adjustment(SID) is None
    bl = BrokerLearner()
    fact = src.tca("mt5-a", "EURUSD", "LONDON", 7)
    for _ in range(40):
        p = bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1.5"), slippage_pips=D("1"),
                       rejected=False, in_event_window=False, evidence_ref=fact, resolver=src.resolver)
    assert p._w() == D("1.0") and len(p.samples) == 1 and bl.live_adjustment("mt5-a", "EURUSD", "LONDON") is None


def test_decimal_spelling_cannot_mint_identities():
    t, src = StrategyHealthTracker(), Src()
    ref = src.review(SID, 11, r="1")
    for r in ("1", "1.0", "1.00"):
        t.observe(hobs(ref, r=r), resolver=src.resolver)
    assert len(t._obs[SID]) == 1 and len(t.evidence) == 1
    bl = BrokerLearner()
    fact = src.tca("mt5-a", "EURUSD", "LONDON", 11, cost_ratio="1", slippage="1")
    for c in (D(1), D("1.0"), D("1.00")):
        bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=c, slippage_pips=c,
                   rejected=False, in_event_window=False, evidence_ref=fact, resolver=src.resolver)
    assert len(bl.profiles[("mt5-a", "EURUSD", "LONDON")].samples) == 1 and len(bl.evidence) == 1


def test_fabricated_registration_is_not_admitted():
    t = StrategyHealthTracker()
    assert not hasattr(t.evidence, "register")
    fake = EvidenceRecord.from_content(EvidenceClass.TRADE_REVIEW, {"strategy_id": SID, "environment": "LIVE"}, environment_ceiling=Environment.LIVE)

    class Forger:   # duck-typed resolver that returns invented content
        def resolve(self, ref, *, correlation_hint=None):
            return fake

    class SubclassForger(LedgerEvidenceResolver):   # even a subclass of the trusted type
        def resolve(self, ref, *, correlation_hint=None):
            return fake

    for bad in (Forger(), SubclassForger(Ledger(), session_environment=Environment.LIVE)):
        with pytest.raises(EvidenceError, match="only ledger-resolved"):
            t.evidence.admit(fake.ref, bad)
        with pytest.raises(EvidenceError):
            t.observe(hobs(fake.ref), resolver=bad)
        with pytest.raises(LearningBoundaryError, match="untrusted evidence resolver"):
            LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, (fake.ref,) ), bad)
    with pytest.raises(EvidenceError):
        CompositeEvidenceResolver((Forger(),))
    with pytest.raises(EvidenceError, match="VATI ledger"):
        LedgerEvidenceResolver({"not": "a ledger"})
    assert len(t.evidence) == 0 and t.live_adjustment(SID) is None


def test_hooks_learn_only_from_ledger_events_and_never_from_intent_ids():
    hooks = LearningHooks(environment=Environment.LIVE, broker="mt5-a", health=StrategyHealthTracker(sustain=1))
    led = Ledger()
    # no TRADE_REVIEW / TCA_RECORD on the ledger → nothing observed (no trade_intent_id fallback)
    for i in range(40):
        ep, adj = hooks.on_review(led, trade_intent_id=f"intent-{i}", strategy_id=SID, r_multiple=D("-1"), process_ok=False, cost_ratio=D("2.5"))
        assert adj is None
        assert hooks.on_tca(led, trade_intent_id=f"intent-{i}", symbol="EURUSD", session="LONDON", event_window="QUIET", cost_ratio=D("1.5"), slippage=D("1")) is None
    assert SID not in hooks.health._obs and hooks.brokers.profiles == {}
    # the same review re-seen 40 times is one sample
    led.append(make_event(EventKind.TCA_RECORD, "vati-cycle", {"trade_intent_id": "intent-x", "learning_environment": "LIVE", "cost_ratio": "2.5"}, event_time_ms=1, received_time_ms=1, correlation_id="intent-x"))
    led.append(make_event(EventKind.TRADE_REVIEW, "vati-cycle", {"trade_intent_id": "intent-x", "strategy_id": SID, "r_multiple": "-1", "process_ok": False}, event_time_ms=1, received_time_ms=1, correlation_id="intent-x"))
    for _ in range(40):
        hooks.on_review(led, trade_intent_id="intent-x", strategy_id=SID, r_multiple=D("-1"), process_ok=False, cost_ratio=D("2.5"))
    assert hooks.health.verdict(SID).weighted_samples == D("1.0") and hooks.refusals == []


def test_positive_path_30_distinct_real_trade_reviews_still_demote():
    hooks = LearningHooks(environment=Environment.LIVE, broker="mt5-a", health=StrategyHealthTracker(sustain=1))
    led = Ledger()
    adj = None
    for i in range(30):
        corr = f"intent-{i}"
        led.append(make_event(EventKind.TRADE_REVIEW, "vati-cycle", {"trade_intent_id": corr, "strategy_id": SID, "r_multiple": "-1", "process_ok": False}, event_time_ms=i, received_time_ms=i, correlation_id=corr))
        led.append(make_event(EventKind.TCA_RECORD, "vati-cycle", {"learning_environment": "LIVE", "broker": "mt5-a", "symbol": "EURUSD", "session": "LONDON", "event_window": "QUIET", "cost_ratio": "1.5",
                                                                   "slippage": "1", "rejected": False},
                              event_time_ms=i, received_time_ms=i, correlation_id=corr))
        _, adj = hooks.on_review(led, trade_intent_id=corr, strategy_id=SID, r_multiple=D("-1"), process_ok=False, cost_ratio=D("1.5"), regime_fit=False)
        badj = hooks.on_tca(led, trade_intent_id=corr, symbol="EURUSD", session="LONDON", event_window="QUIET", cost_ratio=D("1.5"), slippage=D("1"))
    assert adj is not None and adj.demote_to == "SHADOW" and adj.multiplier < D("0.4") and adj.environment_weighted_samples == D("30.0")
    assert all(parse_evidence_ref(r).evidence_class is EvidenceClass.TRADE_REVIEW for r in adj.evidence_refs) and len(set(adj.evidence_refs)) == 30
    assert LearningBoundary.check(adj, hooks.health.evidence) is adj
    assert badj is not None and badj.multiplier == D("0.7") and badj.environment_weighted_samples == D("30.0")
    assert hooks.refusals == []


# ----------------------------------------------------- boundary: grammar
def test_one_hindsight_reflection_and_a_fake_count_cannot_reduce_capsule_health():
    r = Src().resolver
    for ref in ("hindsight://reflection/strat-1/tired", "hindsight-reflection: this strategy looks tired"):
        with pytest.raises(LearningBoundaryError, match="experiential"):
            LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, (ref,), D(30)), r)
        with pytest.raises(LearningBoundaryError, match="experiential"):
            LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, (ref,)), r)


def test_openviking_ref_cannot_demote_a_strategy():
    src = Src()
    good = health_evidence(src)
    for ref in ("openviking://trading/strat-1/lesson", "viking://resources/strat-1"):
        with pytest.raises(LearningBoundaryError, match="experiential"):
            LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "SHADOW", (ref,)), src.resolver)
        with pytest.raises(LearningBoundaryError, match="experiential"):
            LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "SHADOW", good + (ref,)), src.resolver)


def test_deil_ref_cannot_change_broker_liquidity_multiplier():
    r = Src().resolver
    with pytest.raises(LearningBoundaryError, match="experiential"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, ("deil://trading/broker/mt5-a",)), r)
    with pytest.raises(LearningBoundaryError, match="experiential"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.BROKER_PROFILE, BKEY, D("0"), None, ("deil://trading/broker/mt5-a",), D(30)), r)


@pytest.mark.parametrize("ref", [
    "this strategy looks tired",                                            # free text
    "a" * 64,                                                               # bare hash, no class
    "broker-profile:mt5-a:EURUSD:LONDON",                                   # legacy free-form tag
    "vati-evidence:TRADE_REVIEW:" + "a" * 63,                               # short hash
    "vati-evidence:TRADE_REVIEW:" + "A" * 64,                               # upper-case hex
    "vati-evidence:TRADE_REVIEW:" + "g" * 64,                               # non-hex
    "vati-evidence:TRADE_REVIEW:" + "a" * 64 + "\n",                        # trailing junk
    "vati-evidence:MODEL_OPINION:" + "a" * 64,                              # class not allowlisted
])
def test_free_text_malformed_and_unknown_class_refs_are_rejected(ref):
    with pytest.raises(EvidenceError):
        parse_evidence_ref(ref)
    src = Src()
    with pytest.raises(LearningBoundaryError, match="live evidence rejected"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, health_evidence(src) + (ref,)), src.resolver)


def test_well_formed_but_unresolvable_hash_is_rejected():
    src = Src()
    ghost = make_evidence_ref(EvidenceClass.TRADE_REVIEW, "b" * 64)
    assert parse_evidence_ref(ghost).identity == "b" * 64
    with pytest.raises(LearningBoundaryError, match="unresolvable"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, (ghost,), D(1)), src.resolver)
    real = src.review(SID, 1)
    wrong_class = make_evidence_ref(EvidenceClass.PNL_ATTRIBUTION, parse_evidence_ref(real).identity)
    with pytest.raises(LearningBoundaryError, match="unresolvable"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.7"), None, (wrong_class,), D(1)), src.resolver)


def test_duplicate_evidence_cannot_inflate_the_sample_count():
    src = Src()
    one = health_evidence(src, n=1)
    with pytest.raises(LearningBoundaryError, match="!= 1.0 recomputed"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, one * 30, D(30)), src.resolver)
    with pytest.raises(LearningBoundaryError, match="insufficient"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, one * 30), src.resolver)


def test_caller_forged_sample_count_is_rejected():
    src = Src()
    refs = health_evidence(src, n=30)
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, refs, D(45)), src.resolver)
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, refs, D(29)), src.resolver)
    with pytest.raises(LearningBoundaryError, match="no EvidenceResolver"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, refs, D(30)))


def test_replay_and_counterfactual_weight_cannot_be_caller_forged():
    # counterfactual reviews that claim weight 1.0 in their own content still weigh 0.2
    cf = Src(Environment.COUNTERFACTUAL)
    refs = tuple(cf.review(SID, i, weight="1.0", label="SIMULATED_EVIDENCE_NOT_CAUSAL") for i in range(60))
    adj = LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("1"), None, refs), cf.resolver)
    assert adj.environment_weighted_samples == D("12.0")
    with pytest.raises(LearningBoundaryError, match="insufficient"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, refs), cf.resolver)
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), None, refs, D(60)), cf.resolver)
    # a counterfactual review cannot be observed as LIVE: environment comes from the resolved event
    with pytest.raises(EvidenceError, match="environment"):
        StrategyHealthTracker().observe(hobs(refs[0], env=Environment.LIVE), resolver=cf.resolver)
    # replayed execution facts weigh zero for the broker profile
    live = Src()
    rp = tca_evidence(live, n=100, env=Environment.REPLAY)
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, rp, D(30)), live.resolver)
    with pytest.raises(LearningBoundaryError, match="insufficient"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, rp), live.resolver)
    rec = live.resolver.resolve(parse_evidence_ref(rp[0]))
    with pytest.raises(EvidenceError, match="does not match"):
        EvidenceRecord.from_content(EvidenceClass.TCA_RECORD, {**rec.content, "payload": {**rec.content["payload"], "learning_environment": "LIVE"}}, identity=rec.identity)


def test_evidence_about_another_subject_does_not_count():
    src = Src()
    other = health_evidence(src, key="strat-2", n=40)
    with pytest.raises(LearningBoundaryError, match="not about"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "DEGRADED", other), src.resolver)
    with pytest.raises(EvidenceError, match="not about"):
        StrategyHealthTracker().observe(hobs(other[0]), resolver=src.resolver)


def test_valid_resolvable_evidence_meeting_threshold_still_passes_existing_rules():
    src = Src()
    refs = health_evidence(src, n=30)
    adj = LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "DEGRADED", refs), src.resolver)
    assert adj.environment_weighted_samples == D("30.0") and adj.demote_to == "DEGRADED" and adj.evidence_refs == refs
    assert LearningBoundary.check(adj, src.resolver) is adj
    with pytest.raises(LearningBoundaryError, match="reduce-only"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("1.1"), None, refs), src.resolver)
    with pytest.raises(LearningBoundaryError, match="promotion"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "CERTIFIED_LIVE", refs), src.resolver)
    with pytest.raises(LearningBoundaryError, match="only capsule health"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.5"), "SHADOW", tca_evidence(src)), src.resolver)
    with pytest.raises(LearningBoundaryError, match="may not touch"):
        LearningBoundary.admit(LiveAdjustmentProposal("LEVERAGE", SID, D("0.5"), None, refs), src.resolver)   # type: ignore[arg-type]
    b = LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, tca_evidence(src)), src.resolver)
    assert b.environment_weighted_samples == D("30.0")


def test_producers_emit_ledger_refs_and_window_bounds_the_cache():
    t = StrategyHealthTracker(sustain=1)
    for i in range(40):
        observe_review(t, SID, -1, process_ok=False, cost=D("2.5"), fit=False, i=1000 + i)
    adj = t.live_adjustment(SID)
    assert adj is not None and adj.environment_weighted_samples == t.verdict(SID).weighted_samples == D("40.0")
    assert all(parse_evidence_ref(r).evidence_class is EvidenceClass.TRADE_REVIEW for r in adj.evidence_refs)
    assert LearningBoundary.check(adj, t.evidence) is adj
    for i in range(100):
        observe_review(t, SID, -1, process_ok=False, cost=D("2.5"), fit=False, i=2000 + i)
    assert len(t.evidence) == t.window


def test_ledger_resolver_verifies_identity_kind_and_environment():
    src = Src(Environment.LIVE)
    tca_ref = src.tca("mt5-a", "EURUSD", "LONDON", 1)
    note = make_event(EventKind.NEWS_HEADLINE, "news", {"headline": "x"}, event_time_ms=2, received_time_ms=2)
    src.ledger.append(note)
    rec = src.resolver.resolve(parse_evidence_ref(tca_ref))
    assert rec.environment is Environment.LIVE and BKEY in rec.subjects and rec.identity == parse_evidence_ref(tca_ref).identity
    with pytest.raises(EvidenceError, match="unresolvable"):
        src.resolver.resolve(EvidenceRef(EvidenceClass.TRADE_REVIEW, rec.identity))
    with pytest.raises(EvidenceError, match="not resolvable"):   # LEDGER_EVENT is reserved: no "any kind" class (A-VATI M1)
        src.resolver.resolve(parse_evidence_ref(make_evidence_ref(EvidenceClass.LEDGER_EVENT, note.hash)))
    with pytest.raises(EvidenceError, match="no environment"):   # an unbound resolver cannot weigh anything
        LedgerEvidenceResolver(src.ledger)
    strict = LedgerEvidenceResolver(src.ledger, environment_ceiling=Environment.LIVE)   # replay binding: a review cannot be weighted
    with pytest.raises(EvidenceError, match="no environment"):
        strict.resolve(parse_evidence_ref(src.review(SID, 1)))
    both = CompositeEvidenceResolver((ResolvedEvidenceCache(), src.resolver))
    assert LearningBoundary.check(LiveAdjustment(LiveTarget.BROKER_PROFILE, BKEY, D("1"), None, (tca_ref,), D("1.0")), both).multiplier == 1
    assert isinstance(both, TrustedEvidenceResolver)


def test_every_allowlisted_class_is_mapped_to_a_vati_source():
    assert set(EVIDENCE_CLASS_SOURCES) == set(EvidenceClass)


# --------------------------------------- A-VATI (review D): M1 sources
def test_review_d_p2_research_synthesis_from_a_derived_producer_is_not_live_evidence():
    """Review D P2: 30 RESEARCH_SYNTHESIS events by producer 'hindsight-derived' whose
    payload says environment LIVE were admitted as 30.0 live samples via LEDGER_EVENT."""
    src = Src()
    refs = tuple(make_evidence_ref(EvidenceClass.LEDGER_EVENT,
                                   parse_evidence_ref(make_evidence_ref(EvidenceClass.TRADE_REVIEW, src.append(
                                       EventKind.RESEARCH_SYNTHESIS, {"strategy_id": "S2", "environment": "LIVE", "n": i}, f"r-{i}",
                                       producer="hindsight-derived"))).identity)
                 for i in range(30))
    with pytest.raises(LearningBoundaryError, match="not resolvable"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, "S2", D("0"), "SUSPENDED", refs), src.resolver)
    # and no allowlisted class resolves those events either
    for cls in (EvidenceClass.TRADE_REVIEW, EvidenceClass.VTIL_ARTIFACT, EvidenceClass.TCA_RECORD):
        with pytest.raises(EvidenceError):
            src.resolver.resolve(EvidenceRef(cls, parse_evidence_ref(refs[0]).identity))


@pytest.mark.parametrize("producer,match", [
    ("hindsight-derived", "derived source"),
    ("vati-research-synthesis", "derived source"),
    ("openviking-bridge", "derived source"),
    ("vati-lessons", "derived source"),
    ("some-tool", "not an allowlisted source"),
    ("vati-test", "not an allowlisted source"),
])
def test_allowlisted_kind_from_a_non_runtime_producer_is_not_evidence(producer, match):
    src = Src()
    refs = []
    for i in range(30):
        corr = f"{producer}-{i}"
        refs.append(make_evidence_ref(EvidenceClass.TRADE_REVIEW, src.append(
            EventKind.TRADE_REVIEW, {"trade_intent_id": corr, "strategy_id": SID, "r_multiple": "-1"}, corr, producer=producer)))
        refs.append(make_evidence_ref(EvidenceClass.VTIL_ARTIFACT, src.append(
            EventKind.TRADE_EXPERIENCE_ARTIFACT, {"episode_id": corr, "strategy_id": SID, "environment": "LIVE"}, corr, producer=producer)))
    with pytest.raises(LearningBoundaryError, match=match):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0"), "SUSPENDED", tuple(refs)), src.resolver)
    with pytest.raises(EvidenceError, match=match):
        StrategyHealthTracker().observe(hobs(refs[0]), resolver=src.resolver)


def test_payload_cannot_raise_its_environment_above_the_ledger_binding():
    """The environment is the ledger's runtime binding; a payload may lower it, never raise it."""
    demo = Src(Environment.DEMO)
    live_claims = tuple(demo.tca("mt5-a", "EURUSD", "LONDON", i, env=Environment.LIVE) for i in range(40))
    with pytest.raises(LearningBoundaryError, match="more authoritative"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("0.7"), None, live_claims), demo.resolver)
    # a lower environment recorded on the same ledger is accepted at its own (lower) weight
    replayed = tuple(demo.tca("mt5-a", "EURUSD", "LONDON", 100 + i, env=Environment.REPLAY) for i in range(40))
    adj = LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, BKEY, D("1"), None, replayed), demo.resolver)
    assert adj.environment_weighted_samples == 0


def test_replay_cannot_weigh_a_fact_above_the_restarted_runtime(tmp_path):
    from vati.learning.replay import restore_learning_runtime
    led = Ledger(tmp_path / "replay-ceiling.sqlite")
    for i in range(30):
        led.append(make_event(EventKind.TRADE_EXPERIENCE_ARTIFACT, "vati-cycle",
                              {"episode_id": f"i-{i}", "strategy_id": SID, "environment": "LIVE", "outcome": {"r_multiple": "-1"},
                               "review": {"process_ok": False}, "execution": {"tca": {"cost_ratio": "2.5"}}},
                              event_time_ms=i, received_time_ms=i, correlation_id=f"i-{i}"))
    demo = LearningHooks(environment=Environment.DEMO)
    assert restore_learning_runtime(led, demo, {}).health_observations == 0
    live = LearningHooks(environment=Environment.LIVE)
    assert restore_learning_runtime(led, live, {}).health_observations == 30


def test_source_allowlist_names_runtime_producers_and_no_derived_kind():
    from vati.cognition import attribution, shadow_book
    from vati.learning.evidence import DERIVED_EVENT_KINDS, EVIDENCE_SOURCE_ALLOWLIST
    assert EVIDENCE_SOURCE_ALLOWLIST[EvidenceClass.PNL_ATTRIBUTION][1] == {attribution.PRODUCER}
    assert EVIDENCE_SOURCE_ALLOWLIST[EvidenceClass.SHADOW_BOOK_OUTCOME][1] == {shadow_book.PRODUCER}
    assert EvidenceClass.LEDGER_EVENT not in EVIDENCE_SOURCE_ALLOWLIST
    assert not {k for k, _ in EVIDENCE_SOURCE_ALLOWLIST.values()} & DERIVED_EVENT_KINDS


# ----------------------------------- A-VATI (review D): M2 trade identity
def _trade_artifacts(src: Src, corr: str, sid: str = SID) -> tuple[str, str]:
    """The TRADE_REVIEW and the TRADE_EXPERIENCE_ARTIFACT of one trade, as the runtime writes them."""
    src.append(EventKind.TCA_RECORD, {"trade_intent_id": corr, "learning_environment": src.env.value, "cost_ratio": "2.5"}, corr)
    review = make_evidence_ref(EvidenceClass.TRADE_REVIEW, src.append(
        EventKind.TRADE_REVIEW, {"trade_intent_id": corr, "strategy_id": sid, "r_multiple": "-1", "process_ok": False}, corr))
    artifact = make_evidence_ref(EvidenceClass.VTIL_ARTIFACT, src.append(
        EventKind.TRADE_EXPERIENCE_ARTIFACT, {"episode_id": corr, "strategy_id": sid, "environment": src.env.value,
                                             "outcome": {"r_multiple": "-1"}, "review": {"process_ok": False},
                                             "execution": {"tca": {"cost_ratio": "2.5"}}}, corr))
    return review, artifact


def test_review_d_p1_one_trade_cited_by_two_artifacts_is_one_sample_at_the_boundary():
    """Review D P1: 15 trades, each cited by its TRADE_REVIEW and its experience artifact,
    were admitted as 30.0 samples and demoted to SUSPENDED."""
    src = Src()
    refs = tuple(r for i in range(15) for r in _trade_artifacts(src, f"t-{i}"))
    assert len(refs) == 30
    with pytest.raises(LearningBoundaryError, match=r"insufficient environment-weighted samples \(15\.0"):
        LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0"), "SUSPENDED", refs), src.resolver)
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, SID, D("0"), "SUSPENDED", refs, D(30)), src.resolver)
    # 30 distinct trades cited twice each are 30 samples, not 60
    refs30 = tuple(r for i in range(30) for r in _trade_artifacts(src, f"u-{i}"))
    adj = LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, SID, D("0.5"), "DEGRADED", refs30), src.resolver)
    assert adj.environment_weighted_samples == D("30.0")


def test_review_d_p1b_one_trade_observed_through_two_classes_counts_once_in_the_tracker():
    src = Src()
    t = StrategyHealthTracker()
    review, artifact = _trade_artifacts(src, "t-once")
    t.observe(hobs(review), resolver=src.resolver)
    v = t.observe(hobs(artifact), resolver=src.resolver)
    assert v.weighted_samples == D("1.0") and len(t._obs[SID]) == 1 and len(t.evidence) == 1


def test_one_trade_with_two_tca_records_is_one_broker_sample():
    src = Src()
    bl = BrokerLearner()
    refs = []
    for seq in (1, 2):   # e.g. a live TCA and a restart-recovered TCA of the same fill
        refs.append(make_evidence_ref(EvidenceClass.TCA_RECORD, src.append(EventKind.TCA_RECORD, {
            "trade_intent_id": "t-fill", "learning_environment": "LIVE", "broker": "mt5-a", "symbol": "EURUSD", "session": "LONDON",
            "event_window": "NORMAL", "cost_ratio": "1.5", "slippage": "1", "rejected": False, "seq": seq}, "t-fill")))
        p = bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1.5"), slippage_pips=D("1"),
                       rejected=False, in_event_window=False, evidence_ref=refs[-1], resolver=src.resolver)
    assert len(p.samples) == 1 and p._w() == D("1.0")
    with pytest.raises(LearningBoundaryError, match="caller-supplied"):
        LearningBoundary.check(LiveAdjustment(LiveTarget.BROKER_PROFILE, BKEY, D("1"), None, tuple(refs), D("2.0")), src.resolver)


def test_payload_naming_another_trade_than_its_ledger_correlation_is_refused():
    src = Src()
    bad = make_evidence_ref(EvidenceClass.TRADE_REVIEW, src.append(
        EventKind.TRADE_REVIEW, {"trade_intent_id": "t-A", "strategy_id": SID, "r_multiple": "-1"}, "t-B"))
    with pytest.raises(EvidenceError, match="disagrees with its ledger correlation_id"):
        src.resolver.resolve(parse_evidence_ref(bad))
    uncorrelated = make_evidence_ref(EvidenceClass.TRADE_REVIEW, src.append(
        EventKind.TRADE_REVIEW, {"strategy_id": SID, "r_multiple": "-1"}, ""))
    with pytest.raises(EvidenceError, match="names no trade"):
        src.resolver.resolve(parse_evidence_ref(uncorrelated))


# ------------------------------- A-VATI (review D): M3 values from evidence
def test_review_d_p3_observation_values_must_be_the_cited_reviews():
    """Review D P3: r=-50/process_ok=False citing a review whose payload says r=2.5/process_ok=True was accepted (health 0.000)."""
    src = Src()
    ref = src.review("S3", 1, r="2.5", process_ok=True, cost="1")
    t = StrategyHealthTracker()
    for r, proc, cost in ((D("-50"), False, D("10")), (D("-50"), True, D("1")), (D("2.5"), False, D("1")), (D("2.5"), True, D("3"))):
        with pytest.raises(EvidenceError, match="disagrees with its evidence"):
            t.observe(HealthObservation("S3", Environment.LIVE, r, proc, cost, True, ref), resolver=src.resolver)
    assert "S3" not in t._obs and t.verdict("S3").weighted_samples == 0
    v = t.observe(HealthObservation("S3", Environment.LIVE, D("2.50"), True, D("1.0"), True, ref), resolver=src.resolver)
    assert v.weighted_samples == D("1.0") and t._obs["S3"][0].r_multiple == D("2.5")
    # the evidence-only path reads the same values without a caller
    t2 = StrategyHealthTracker()
    t2.observe_evidence("S3", ref, resolver=src.resolver)
    assert (t2._obs["S3"][0].r_multiple, t2._obs["S3"][0].process_ok, t2._obs["S3"][0].cost_ratio) == (D("2.5"), True, D("1"))


def test_review_d_p3b_broker_execution_facts_must_be_the_cited_tca_records():
    src = Src()
    fact = src.tca("mt5-a", "EURUSD", "LONDON", 1, cost_ratio="1.0", slippage="0.1", rejected=False, event_window="NORMAL")
    bl = BrokerLearner()
    for cost, slip, rej, ev in ((D("9"), D("50"), True, True), (D("1.0"), D("0.1"), True, False), (D("1.0"), D("0.1"), False, True), (D("1.2"), D("0.1"), False, False)):
        with pytest.raises(EvidenceError, match="disagrees with its evidence"):
            bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=cost, slippage_pips=slip,
                       rejected=rej, in_event_window=ev, evidence_ref=fact, resolver=src.resolver)
    assert bl.profiles == {}
    p = bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1"), slippage_pips=D("0.10"),
                   rejected=False, in_event_window=False, evidence_ref=fact, resolver=src.resolver)
    assert p.samples == [(D("1.0"), D("1.0"), D("0.1"), False, False)]


@pytest.mark.parametrize("missing", ["r_multiple", "process_ok", "tca", "tca_cost"])
def test_a_value_the_evidence_does_not_record_is_refused_not_defaulted(missing):
    src = Src()
    corr = f"miss-{missing}"
    if missing != "tca":
        src.append(EventKind.TCA_RECORD, {"trade_intent_id": corr, "learning_environment": "LIVE",
                                          **({} if missing == "tca_cost" else {"cost_ratio": "1"})}, corr)
    payload = {"trade_intent_id": corr, "strategy_id": SID, "r_multiple": "-1", "process_ok": False}
    payload.pop(missing, None)
    ref = make_evidence_ref(EvidenceClass.TRADE_REVIEW, src.append(EventKind.TRADE_REVIEW, payload, corr))
    with pytest.raises(EvidenceError, match="records no|no TCA_RECORD"):
        StrategyHealthTracker().observe(HealthObservation(SID, Environment.LIVE, D("-1"), False, D("1"), True, ref), resolver=src.resolver)
    tca = src.tca("mt5-a", "EURUSD", "LONDON", 5)
    rec = src.resolver.resolve(parse_evidence_ref(tca))
    for key in ("cost_ratio", "slippage", "rejected", "event_window"):
        bare = {k: v for k, v in rec.content["payload"].items() if k != key}
        ref2 = make_evidence_ref(EvidenceClass.TCA_RECORD, src.append(EventKind.TCA_RECORD, {**bare, "seq": f"no-{key}"}, f"tca-no-{key}"))
        with pytest.raises(EvidenceError, match="records no"):
            BrokerLearner().observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1.5"), slippage_pips=D("1"),
                                    rejected=False, in_event_window=False, evidence_ref=ref2, resolver=src.resolver)


def test_decision_quality_verdict_is_the_process_evidence_when_the_ledger_holds_one():
    """GAP-F-003 keeps working: the runtime passes the decision-quality verdict, and that verdict is on the ledger."""
    src = Src()
    ref = src.review(SID, 77, process_ok=True)   # the review's own flag is the runtime's constant True
    src.append(EventKind.DECISION_QUADRANT, {"trade_intent_id": f"{SID}-77", "faults": ["STOP_WIDENED"]}, f"{SID}-77", producer="vati-decision-quality")
    t = StrategyHealthTracker()
    with pytest.raises(EvidenceError, match="disagrees"):
        t.observe(HealthObservation(SID, Environment.LIVE, D("-1"), True, D("2.5"), True, ref), resolver=src.resolver)
    assert t.observe(HealthObservation(SID, Environment.LIVE, D("-1"), False, D("2.5"), True, ref), resolver=src.resolver).weighted_samples == D("1.0")
    # a verdict from any other producer is not the decision-quality ledger
    ref2 = src.review(SID, 78, process_ok=True)
    src.append(EventKind.DECISION_QUADRANT, {"trade_intent_id": f"{SID}-78", "faults": ["X"]}, f"{SID}-78", producer="hindsight-derived")
    assert StrategyHealthTracker().observe(HealthObservation(SID, Environment.LIVE, D("-1"), True, D("2.5"), True, ref2), resolver=src.resolver).weighted_samples == D("1.0")


def test_hooks_refuse_a_disagreeing_close_without_interrupting_it():
    hooks = LearningHooks(environment=Environment.LIVE, broker="mt5-a")
    led = Ledger()
    led.append(make_event(EventKind.TCA_RECORD, "vati-cycle", {"trade_intent_id": "t-x", "learning_environment": "LIVE", "cost_ratio": "1"}, event_time_ms=1, received_time_ms=1, correlation_id="t-x"))
    led.append(make_event(EventKind.TRADE_REVIEW, "vati-cycle", {"trade_intent_id": "t-x", "strategy_id": SID, "r_multiple": "2.5", "process_ok": True}, event_time_ms=1, received_time_ms=1, correlation_id="t-x"))
    ep, adj = hooks.on_review(led, trade_intent_id="t-x", strategy_id=SID, r_multiple=D("-50"), process_ok=False, cost_ratio=D("10"))
    assert adj is None and SID not in hooks.health._obs and len(hooks.refusals) == 1 and "disagrees" in hooks.refusals[0]


# ------------------------- A-VATI (review D): minor, the health window
def test_review_d_evicted_trade_is_not_readmitted_as_a_new_sample():
    """Review D: after 61 trades, re-observing the first (aged out of the 60-item window) was accepted as a new sample."""
    src = Src()
    t = StrategyHealthTracker()
    refs = [src.review(SID, 5000 + i, r="-1", process_ok=True, cost="1") for i in range(t.window + 1)]
    for ref in refs:
        t.observe(HealthObservation(SID, Environment.LIVE, D("-1"), True, D("1"), True, ref), resolver=src.resolver)
    window_before, obs_before = list(t._refs[SID]), list(t._obs[SID])
    assert refs[0] not in window_before and len(window_before) == t.window
    for ref in (refs[0], refs[1], refs[-1]):   # evicted, evicted, still in the window
        t.observe(HealthObservation(SID, Environment.LIVE, D("-1"), True, D("1"), True, ref), resolver=src.resolver)
    assert t._refs[SID] == window_before and t._obs[SID] == obs_before and len(t.evidence) == t.window
    # an evicted trade re-cited through its other artifact is not a new sample either
    corr = f"{SID}-5000"
    art = make_evidence_ref(EvidenceClass.VTIL_ARTIFACT, src.append(EventKind.TRADE_EXPERIENCE_ARTIFACT, {
        "episode_id": corr, "strategy_id": SID, "environment": "LIVE", "outcome": {"r_multiple": "-1"}, "review": {"process_ok": True},
        "execution": {"tca": {"cost_ratio": "1"}}}, corr))
    t.observe(HealthObservation(SID, Environment.LIVE, D("-1"), True, D("1"), True, art), resolver=src.resolver)
    assert t._refs[SID] == window_before and len(t.evidence) == t.window
    # a genuinely new trade still enters and evicts the oldest
    new_ref = src.review(SID, 9999, r="-1", process_ok=True, cost="1")
    t.observe(HealthObservation(SID, Environment.LIVE, D("-1"), True, D("1"), True, new_ref), resolver=src.resolver)
    assert t._refs[SID] == window_before[1:] + [new_ref]


# ------------------------------------------------------- memory bridge
def test_owner_preference_continuity_record_is_rejected():
    b = HermesMemoryBridge()
    with pytest.raises(MemoryBridgeError, match="Owner Model"):
        b.remember(kind="OWNER_PREFERENCE", subject="owner", summary="prefers smaller size on Fridays", now_ms=1_000)
    assert b.records == {}
