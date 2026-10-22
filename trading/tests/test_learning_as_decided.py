"""Late analysis cannot silently rewrite the observations originally learned."""
from decimal import Decimal as D

import pytest

from test_learning_evidence import Src
from vati.core.events import EventKind
from vati.learning.episodes import Environment
from vati.learning.evidence import EvidenceClass, EvidenceError, make_evidence_ref
from vati.learning.health import StrategyHealthTracker
from vati.learning.hooks import LearningHooks
from vati.learning.replay import restore_learning_runtime


def quality(source, trade, *, bad):
    return source.append(EventKind.DECISION_QUADRANT,
        {"trade_intent_id":trade,"faults":["THESIS_ABSENT"] if bad else []},trade,producer="vati-decision-quality")


@pytest.mark.parametrize("original_bad", [False, True])
def test_actual_cold_learning_restore_keeps_the_original_quality_cutoff(original_bad):
    """Native-envelope fixtures, not live market or authority qualifications."""
    source = Src(Environment.LIVE)
    warm = StrategyHealthTracker()
    for number in range(30):
        trade = f"intent-{number}"
        quality(source,trade,bad=original_bad)
        digest = source.append(EventKind.TRADE_EXPERIENCE_ARTIFACT,
            {"environment":"LIVE","strategy_id":"cutoff","outcome":{"r_multiple":"0.5"},
             "review":{"process_ok":True},"execution":{"tca":{"cost_ratio":"1"}}},trade)
        warm.observe_evidence("cutoff",make_evidence_ref(EvidenceClass.VTIL_ARTIFACT,digest),resolver=source.resolver)
    # A correction is a separate analytical fact. Without an explicit restated
    # projection it cannot become what was available at the original decision.
    for number in range(30):quality(source,f"intent-{number}",bad=not original_bad)
    cold = LearningHooks(environment=Environment.LIVE)
    result = restore_learning_runtime(source.ledger,cold,{})
    assert result.health_observations == 30
    assert cold.health.verdict("cutoff") == warm.verdict("cutoff")
    assert all(o.process_ok is (not original_bad) for o in cold.health._obs["cutoff"])


def test_explicit_historical_cost_lookup_is_distinct_from_current_analysis():
    source = Src()
    ref = source.review("cutoff",1,r="0.5",cost="1",process_ok=True)
    source.append(EventKind.TCA_RECORD,{"learning_environment":"LIVE","cost_ratio":"9"},"cutoff-1")
    from vati.learning.evidence import parse_evidence_ref
    historical = source.resolver.trade_fact(EvidenceClass.TCA_RECORD,"cutoff-1",available_through=parse_evidence_ref(ref).identity)
    current = source.resolver.trade_fact(EvidenceClass.TCA_RECORD,"cutoff-1")
    assert D(historical.content["payload"]["cost_ratio"]) == D("1")
    assert D(current.content["payload"]["cost_ratio"]) == D("9")


def test_missing_or_wrong_trade_cutoff_refuses_instead_of_using_future_history():
    source = Src()
    quality(source,"one",bad=True)
    other = source.append(EventKind.SESSION,{"event":"another trade"},"two")
    for anchor in ("f"*64, other):
        with pytest.raises(EvidenceError,match="anchor"):
            source.resolver.decision_quality("one",available_through=anchor)


def test_tampered_quality_event_cannot_override_native_historical_process_evidence():
    source = Src()
    digest = quality(source,"one",bad=True)
    # A forged plaintext edit retains the old envelope hash. The resolver must
    # refuse it even though its producer string is still the native one.
    source.ledger._conn.execute("UPDATE events SET payload_json = ? WHERE event_hash = ?",
        ('{"trade_intent_id":"one","faults":[]}',digest))
    with pytest.raises(EvidenceError,match="seal"):
        source.resolver.decision_quality("one")


@pytest.mark.parametrize("regime_fit", [True,False])
def test_actual_hook_captures_once_even_when_new_quality_arrives_before_episode_persistence(mandate,eurusd,regime_fit):
    from conftest import intent,snapshot
    from vati.risk import RiskAuthority
    from vati.risk.serde import intent_to_dict,snapshot_to_dict
    from vati.learning.hooks import to_payload
    source = Src()
    i,s = intent(trade_intent_id="persist-window"),snapshot(eurusd)
    decision = RiskAuthority(mandate).evaluate(i,s)
    source.append(EventKind.RISK_DECISION,{"inputs":{"intent":intent_to_dict(i),"snapshot":snapshot_to_dict(s)},
        "decision":decision.to_dict()},i.trade_intent_id)
    source.append(EventKind.TCA_RECORD,{"learning_environment":"LIVE","cost_ratio":"1"},i.trade_intent_id)
    source.append(EventKind.TRADE_REVIEW,{"trade_intent_id":i.trade_intent_id,"strategy_id":i.strategy_id,
        "r_multiple":"0.5","process_ok":True},i.trade_intent_id)
    original = quality(source,i.trade_intent_id,bad=False)
    live = LearningHooks(environment=Environment.LIVE)
    episode,_ = live.on_review(source.ledger,trade_intent_id=i.trade_intent_id,strategy_id=i.strategy_id,
        r_multiple=D("0.5"),process_ok=True,cost_ratio=D("1"),regime_fit=regime_fit)
    assert episode is not None and episode.learning_cutoff_ref == original
    quality(source,i.trade_intent_id,bad=True)
    # This is where the real cycle/account caller persists the returned episode.
    source.append(EventKind.TRADE_EXPERIENCE_ARTIFACT,to_payload(episode),i.trade_intent_id)
    cold = LearningHooks(environment=Environment.LIVE)
    assert restore_learning_runtime(source.ledger,cold,{}).health_observations == 1
    assert cold.health.verdict(i.strategy_id) == live.health.verdict(i.strategy_id)
    assert cold.health._obs[i.strategy_id][0].process_ok


def test_an_artifact_cannot_claim_a_quality_anchor_published_in_its_future():
    from vati.core.events import make_event
    source = Src()
    future = make_event(EventKind.DECISION_QUADRANT,"vati-decision-quality",
        {"trade_intent_id":"future","faults":[]},event_time_ms=2,received_time_ms=2,correlation_id="future")
    digest = source.append(EventKind.TRADE_EXPERIENCE_ARTIFACT,
        {"environment":"LIVE","strategy_id":"cutoff","outcome":{"r_multiple":"0.5"},
         "review":{"process_ok":True},"execution":{"tca":{"cost_ratio":"1"}},
         "learning_cutoff_ref":future.hash},"future")
    source.ledger.append(future)
    with pytest.raises(EvidenceError,match="outside original artifact"):
        StrategyHealthTracker().observe_evidence("cutoff",make_evidence_ref(EvidenceClass.VTIL_ARTIFACT,digest),resolver=source.resolver)
