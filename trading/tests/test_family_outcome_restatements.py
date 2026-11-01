"""SOURCE synthetic native OWNER facts, not live certificates or activation."""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal as D

import pytest

from conftest_owner_authority import owner_keypair
from test_family_governed_workflow import admitted_source_world
from vati.authority import OwnerAuthorityVerifier, sign_token, OwnerAuthorityError
from vati.core import EventKind
from vati.core.canonical import canonical_hash
from vati.execution.family_economics import SourceFamilyEconomicObservations, EconomicObservationError, SCHEMA, subject
from vati.execution.recovery_scope import NativePositionHistory
from vati.execution.review import review_trade, economic_outcome_final
from vati.learning.episodes import Environment
from vati.learning.scope import LearningScope
from vati.learning.restatement import RestatedTradeProjection
from vati.lifecycle.family_outcome import publish_family_outcome


class SyntheticNativeOwner:
    """Independent SOURCE witness derives original native deal provenance."""
    def __init__(self,w,time):
        self.w,self.time=w,time;self.key,pem=owner_keypair();self.key_id='synthetic-native-owner-source-only'
        self.reader=SourceFamilyEconomicObservations(w.ledger,w.adapter,
            issuer=OwnerAuthorityVerifier({self.key_id:pem}),clock=lambda:time[0])

    def observation(self,family_id,*,fee_delta=D(0)):
        history=NativePositionHistory(self.w.ledger,account_alias=self.w.adapter.account_alias,venue='paper')
        receipts=tuple(history.events(EventKind.EXECUTION_RECEIPT));deals=[]
        for close in self.w.adapter.closed:
            exit=next(e for e in receipts if e.payload.get('exit_action')=='CLOSE'
                and e.payload.get('broker_position_id')==close['position_id']
                and D(str(e.payload['filled_qty']))==close['qty']
                and D(str(e.payload['average_fill']))==close['exit']
                and e.payload['received_time_unix_ms']==close['closed_ms'])
            entry=next(e for e in receipts if not e.payload.get('exit_action')
                and e.payload.get('broker_position_id')==close['position_id'])
            deals.append(dict(native_deal_id=close['close_id'],entry_ref=entry.hash,exit_ref=exit.hash,
                position_id=close['position_id'],trade_intent_id=close['intent'],symbol=close['symbol'],
                quantity=str(close['qty']),execution_price=str(close['exit']),net_cash_delta=str(close['pnl']),
                currency=self.w.adapter.currency,source_revision='SYNTHETIC_SOURCE_NATIVE_CASH_V1'))
        deals[-1]['net_cash_delta']=str(D(deals[-1]['net_cash_delta'])-fee_delta)
        previous=self.reader.latest(family_id)
        body=dict(schema=SCHEMA,evidence_domain='SOURCE',environment='PAPER',
            account_alias=self.w.adapter.account_alias,venue='paper',family_id=family_id,root_intent_id='ti-e2e-1',
            currency=self.w.adapter.currency,sequence=previous.payload['observation']['sequence']+1 if previous else 0,
            previous_ref=previous.hash if previous else None,
            effective_at_ms=max(e['closed_ms'] for e in self.w.adapter.closed),available_at_ms=self.time[0],
            source_owner_id=self.key_id,source_revision='SYNTHETIC_SOURCE_NATIVE_CASH_V1',
            source_hash=canonical_hash({'fixture':'synthetic-native-owner','deals':deals}),deals=deals)
        return body

    def record(self,body):
        signature=sign_token(self.key,act='native-family-economics-source',subject=subject(body),
            key_id=self.key_id,issued_at_unix=self.time[0]//1000,lifetime_seconds=120)
        return self.reader.record(body,signature)


def closed_source_family(tmp_path,*,pending=False):
    w,store,time,admitted,plan,history=admitted_source_world(tmp_path,
        actual_runtime_lease=True,add_child=True,max_quantity='.20')
    w.learning.account_alias=w.adapter.account_alias
    family=w.lifecycle.families.get(plan.snapshot.family_id)
    if pending:
        # Native closes remain confirmed; current settlement read is temporarily unavailable.
        close=w.adapter.close
        def final_disconnect(pid,*args,**kwargs):
            receipt=close(pid,*args,**kwargs)
            if not w.adapter.positions():w.adapter.inject_disconnect=True
            return receipt
        w.adapter.close=final_disconnect
    result=w.lifecycle.request_family_reduction(family.family_id,action_key='source-full-close',
        action='FULL_CLOSE',now_ms=time[0])
    assert result['state']=='COMPLETE'
    return w,time,family


def test_pending_actual_owner_read_then_first_qualified_outcome_one_trial(tmp_path):
    w,time,family=closed_source_family(tmp_path,pending=True)
    try:
        assert not list(w.ledger.iter(EventKind.TRADE_REVIEW,correlation_id='ti-e2e-1'))
        pending=[e for e in w.ledger.iter(EventKind.SESSION,correlation_id=family.family_id)
            if e.payload.get('state')=='CLOSED_NATIVE_ECONOMICS_PENDING']
        assert len(pending)==1 and not w.learning.episodes
        w.adapter.inject_disconnect=False;time[0]+=1000
        review=publish_family_outcome(w.lifecycle,family.family_id,reason='READBACK',now_ms=time[0])
        assert review.kind is EventKind.TRADE_REVIEW and D(str(review.payload['initial_money_risk']))==D('40')
        assert len(list(w.ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT,correlation_id='ti-e2e-1')))==1
        assert pending[0].hash==next(e.hash for e in w.ledger.iter(EventKind.SESSION,correlation_id=family.family_id)
            if e.payload.get('state')=='CLOSED_NATIVE_ECONOMICS_PENDING')
    finally:w.ledger.close()


def test_source_owner_late_cash_revision_replaces_same_parent_without_new_trial(tmp_path):
    w,time,family=closed_source_family(tmp_path)
    try:
        original=next(w.ledger.iter(EventKind.TRADE_REVIEW,correlation_id='ti-e2e-1'))
        assert original.payload['artifact_hash']==canonical_hash({k:v for k,v in original.payload.items() if k!='artifact_hash'})
        original_pnl=D(str(original.payload['pnl']));original_episode=next(w.ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT,correlation_id='ti-e2e-1'))
        native=SyntheticNativeOwner(w,time);w.lifecycle.native_economic_observations=native.reader
        time[0]+=2000;body=native.observation(family.family_id,fee_delta=D('2'))
        fact=native.record(body)
        revision=publish_family_outcome(w.lifecycle,family.family_id,reason='LATE_SOURCE_FACT',now_ms=time[0])
        assert revision.kind is EventKind.TRADE_REVIEW_REVISION
        assert revision.payload['record_revision']==1 and revision.payload['supersedes_review_ref']==original.payload['artifact_hash']
        assert D(str(revision.payload['pnl']))==original_pnl-D('2')
        assert revision.payload['family_outcome']['native_economic_observation_ref']==fact.hash
        assert revision.payload['family_outcome']['production_native_correction_owner']=='NOT_QUALIFIED'
        assert not economic_outcome_final(revision.payload['maturity'],revision.payload['pnl_basis'])
        assert fact.event_time_ms<fact.received_time_ms==revision.received_time_ms
        projection=RestatedTradeProjection(w.ledger,LearningScope(w.ledger,w.adapter.account_alias,Environment.DEMO))
        projection.catch_up();state=projection.snapshot['state']
        assert state['aggregates']['AS_DECIDED']['USD']['count']==1
        assert state['aggregates']['RESTATED_ANALYSIS']['USD']['count']==1
        assert D(state['aggregates']['AS_DECIDED']['USD']['net_pnl'])==original_pnl
        assert D(state['aggregates']['RESTATED_ANALYSIS']['USD']['net_pnl'])==original_pnl-D('2')
        assert len(list(w.ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT,correlation_id='ti-e2e-1')))==1
        assert next(w.ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT,correlation_id='ti-e2e-1')).hash==original_episode.hash
        assert publish_family_outcome(w.lifecycle,family.family_id,reason='REPLAY',now_ms=time[0]+1).hash==revision.hash
        assert native.record(body).hash==fact.hash
    finally:w.ledger.close()


@pytest.mark.parametrize('damage',['currency','deal','quantity','source-ref','sequence','environment'])
def test_source_native_owner_cannot_substitute_deal_scope_or_sequence(tmp_path,damage):
    w,time,family=closed_source_family(tmp_path)
    try:
        native=SyntheticNativeOwner(w,time);time[0]+=1000;body=native.observation(family.family_id)
        if damage=='currency':body['currency']='EUR'
        elif damage=='deal':body['deals'][0]['native_deal_id']='foreign-deal'
        elif damage=='quantity':body['deals'][0]['quantity']='99'
        elif damage=='source-ref':body['deals'][0]['exit_ref']='foreign-receipt'
        elif damage=='sequence':body['sequence']=2
        else:body['environment']='LIVE'
        before=w.ledger.count()
        with pytest.raises(EconomicObservationError):native.record(body)
        assert w.ledger.count()==before
    finally:w.ledger.close()


def test_legacy_review_hash_shape_stays_unchanged():
    review=review_trade(trade_intent_id='legacy',strategy_id='legacy',entry=D(10),exit_price=D(11),
        stop=D(9),direction_long=True,pnl=D(1),thesis_correct=True,process_ok=True)
    assert 'family_outcome' not in asdict(review)
    assert review.artifact_hash==canonical_hash({k:v for k,v in asdict(review).items() if k!='artifact_hash'})
