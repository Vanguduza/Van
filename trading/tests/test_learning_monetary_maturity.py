"""Unsettled money is not a qualified health observation or frozen episode fact."""
from decimal import Decimal as D

import pytest

from test_learning_evidence import Src
from test_restated_trade_projection import native_parent, STRATEGY
from vati.core import Ledger, EventKind
from vati.learning.episodes import Environment, ENVIRONMENT_WEIGHT, episode_from_ledger
from vati.learning.evidence import EvidenceClass, EvidenceError, make_evidence_ref
from vati.learning.health import StrategyHealthTracker


def unsettled():
    return {'parent_final':True, 'fees_final':False, 'cash_reconciled':False,
        'source_environment':'DEMO', 'account_currency':'USD', 'source':'PROVIDER_FINALITY_UNAVAILABLE'}


def test_an_explicitly_unsettled_native_review_is_not_a_demonstrated_health_sample():
    source=Src(Environment.DEMO)
    ref=source.review('unsettled',1,r='0.5',process_ok=True,cost='1',maturity=unsettled(),
        pnl_basis='PRICE_DERIVED_NET_RECORDED_CHARGES',broker_ok=True)
    tracker=StrategyHealthTracker()
    with pytest.raises(EvidenceError,match='maturity|settled|finality'):
        tracker.observe_evidence('unsettled',ref,resolver=source.resolver)
    assert tracker.verdict('unsettled').weighted_samples==0
    assert not tracker.evidence and not tracker._consumed


def test_an_unsettled_episode_cannot_reenter_health_through_cold_artifact_replay():
    source=Src(Environment.DEMO)
    digest=source.append(EventKind.TRADE_EXPERIENCE_ARTIFACT,{
        'environment':'DEMO','strategy_id':'unsettled',
        'outcome':{'r_multiple':'0.5','maturity':unsettled(),'pnl_basis':'PRICE_DERIVED_NET_RECORDED_CHARGES','broker_ok':True},
        'review':{'process_ok':True},'execution':{'tca':{'cost_ratio':'1'}}},'unsettled-1')
    tracker=StrategyHealthTracker()
    with pytest.raises(EvidenceError,match='maturity|settled|finality'):
        tracker.observe_evidence('unsettled',make_evidence_ref(EvidenceClass.VTIL_ARTIFACT,digest),resolver=source.resolver)
    assert tracker.verdict('unsettled').weighted_samples==0


@pytest.mark.parametrize('environment',[Environment.BACKTEST,Environment.REPLAY,Environment.COUNTERFACTUAL,Environment.SHADOW])
def test_explicit_historical_study_retains_its_modelled_outcome_and_cohort_weight(environment):
    source=Src(environment)
    ref=source.review('study',1,r='0.5',process_ok=True,cost='1',maturity=unsettled(),
        pnl_basis='PRICE_DERIVED_NET_RECORDED_CHARGES',broker_ok=True)
    tracker=StrategyHealthTracker()
    assert tracker.observe_evidence('study',ref,resolver=source.resolver).weighted_samples==ENVIRONMENT_WEIGHT[environment]
    assert tracker.live_adjustment('study') is None


def test_actual_settled_native_review_keeps_its_economic_readiness_in_the_episode(eurusd):
    ledger=Ledger();review,_,_,_=native_parent(ledger,eurusd)
    episode=episode_from_ledger(ledger,review.correlation_id,environment=Environment.DEMO,available_through=review.hash)
    assert episode is not None
    assert episode.outcome['maturity']==review.payload['maturity']
    assert episode.outcome['pnl_basis']==review.payload['pnl_basis']
    assert episode.outcome['broker_ok'] is review.payload['broker_ok']
    assert episode.review['thesis_evidence_basis']==review.payload['thesis_evidence_basis']
    assert episode.review['source_review_ref']==review.hash


@pytest.mark.parametrize('kind',['review','artifact'])
@pytest.mark.parametrize('damage',['absent','parent','fees','cash','truthy','broker','environment','currency','source','basis','basis-object'])
def test_unproven_monetary_labels_never_count_as_live_health(kind,damage):
    import copy
    source=Src(Environment.DEMO);values=source.settled_review_fields()
    if damage=='absent':values.pop('maturity')
    elif damage in {'parent','fees','cash','truthy'}:
        name={'parent':'parent_final','fees':'fees_final','cash':'cash_reconciled','truthy':'fees_final'}[damage]
        values['maturity'][name]='true' if damage=='truthy' else False
    elif damage=='broker':values['broker_ok']='true'
    elif damage=='environment':values['maturity']['source_environment']='LIVE'
    elif damage in {'currency','source'}:values['maturity']['account_currency' if damage=='currency' else 'source']=''
    elif damage=='basis':values['pnl_basis']='LEGACY_UNKNOWN_CONVENTION'
    else:values['pnl_basis']={}
    if kind=='review':
        source.append(EventKind.TCA_RECORD,{'learning_environment':'DEMO','cost_ratio':'1'},'labels-1')
        digest=source.append(EventKind.TRADE_REVIEW,{'strategy_id':'labels','r_multiple':'1','process_ok':True,**values},'labels-1')
        ref=make_evidence_ref(EvidenceClass.TRADE_REVIEW,digest)
    else:
        digest=source.append(EventKind.TRADE_EXPERIENCE_ARTIFACT,{'environment':'DEMO','strategy_id':'labels',
            'outcome':{'r_multiple':'1',**copy.deepcopy(values)},'review':{'process_ok':True},
            'execution':{'tca':{'cost_ratio':'1'}}},'labels-1')
        ref=make_evidence_ref(EvidenceClass.VTIL_ARTIFACT,digest)
    tracker=StrategyHealthTracker()
    with pytest.raises(EvidenceError,match='maturity|settled|finality'):
        tracker.observe_evidence('labels',ref,resolver=source.resolver)
    assert tracker.verdict('labels').weighted_samples==0


def test_genuine_session_order_cash_close_and_frozen_episode_remain_learnable(tmp_path,eurusd):
    from test_single_session_recovery import opened_service
    service,_,clock=opened_service(tmp_path,eurusd)
    try:
        c=service.runner.cycle;position=service.adapter.positions()[0]
        service.adapter.last_price[position.symbol]=position.entry_price+D('0.001')
        closed=service.adapter.close(position.position_id,None,now_ms=clock['now'],reason='NATIVE_PAPER_SETTLED_CLOSE')
        c._on_close(position.trade_intent_id,closed.average_fill,'NATIVE_PAPER_SETTLED_CLOSE',clock['now'])
        review=list(service._ledger.iter(EventKind.TRADE_REVIEW,correlation_id=position.trade_intent_id))[-1]
        from vati.learning.evidence import LedgerEvidenceResolver
        resolver=LedgerEvidenceResolver(service._ledger,session_environment=Environment.DEMO)
        tracker=StrategyHealthTracker()
        assert tracker.observe_evidence(review.payload['strategy_id'],make_evidence_ref(EvidenceClass.TRADE_REVIEW,review.hash),
            resolver=resolver).weighted_samples==D('0.5')
        episode=episode_from_ledger(service._ledger,position.trade_intent_id,environment=Environment.DEMO,available_through=review.hash)
        assert episode.outcome['maturity']['cash_reconciled'] is True
        assert episode.outcome['pnl_basis']==review.payload['pnl_basis']
    finally:service.close();service._ledger.close()
