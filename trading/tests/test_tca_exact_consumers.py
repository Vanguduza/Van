"""The existing lifecycle, durable SQL evidence resolver and cold learning."""
from dataclasses import asdict
from decimal import Decimal as D,localcontext,Inexact,Rounded
from fractions import Fraction as F
from types import SimpleNamespace

import pytest

from test_account_lifecycle import _lifecycle
from test_tca_exact_arithmetic import original
from vati.core import EventKind,Ledger,make_event
from vati.learning import Environment
from vati.learning.hooks import LearningHooks
from vati.learning.replay import restore_learning_runtime
from vati.risk.contracts import Direction,TradeIntent,StrategyState


def lifecycle_cost_path(ledger):
    from vati.execution.paper import PaperAdapter
    receipt=original(status='FILLED',broker_position_id='P1')
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',asdict(receipt),
        event_time_ms=1001,received_time_ms=1001,correlation_id=receipt.trade_intent_id))
    intent=TradeIntent(trade_intent_id=receipt.trade_intent_id,idempotency_key='exact-cost-key',
        account_alias='acct',venue='paper',symbol='EURUSD',direction=Direction.LONG,
        strategy_id='FX-TREND-PULLBACK-01',strategy_version='1.0.0',strategy_state=StrategyState.DEMO,
        entry=receipt.decision_price,stop=D('99'),requested_risk_pct=D('0.005'),
        decision_hash=receipt.decision_hash,market_snapshot_hash='m'*64)
    life=_lifecycle(ledger,PaperAdapter(venue='paper',account_alias='acct'))
    life.learning=LearningHooks(Environment.DEMO)
    life.record_entry(intent=intent,receipt=receipt,
        state=SimpleNamespace(session=SimpleNamespace(value='LONDON'),event_window=SimpleNamespace(value='NONE')),
        modelled_cost_pct=D('0.0003'),software_stop=False)
    rows=list(ledger.iter(EventKind.TCA_RECORD));assert len(rows)==1
    cost=rows[0];p=cost.payload
    expected=(F(receipt.average_fill)-F(receipt.decision_price))*F(receipt.filled_qty)*100000+F(receipt.fees)
    assert F(D(p['implementation_shortfall']))==expected
    assert cost.producer=='vati-account-lifecycle' and p['arithmetic']['execution_authority'] is False
    assert cost.received_time_ms==receipt.received_time_unix_ms
    assert not life.learning.refusals
    key=('paper','EURUSD','LONDON')
    assert len(life.learning.brokers.profiles[key].samples)==1
    before=ledger.count()
    with localcontext() as context:
        context.prec=3;context.traps[Inexact]=True;context.traps[Rounded]=True
        cold=LearningHooks(Environment.DEMO)
        report=restore_learning_runtime(ledger,cold,{})
    assert report.tca_observations==1
    assert cold.brokers.profiles[key].samples==life.learning.brokers.profiles[key].samples
    assert cold.brokers.profiles[key].evidence_refs==life.learning.brokers.profiles[key].evidence_refs
    assert ledger.count()==before and ledger.count(EventKind.ORDER_COMMAND)==0
    assert ledger.verify_chain()[0]
    return cost,receipt


def test_actual_lifecycle_to_sqlite_cold_learning_preserves_original_cost(tmp_path):
    path=tmp_path/'cost.sqlite3';ledger=Ledger(path)
    try:cost,receipt=lifecycle_cost_path(ledger)
    finally:ledger.close()
    cold=Ledger(path)
    try:
        assert list(cold.iter(EventKind.TCA_RECORD))[0].hash==cost.hash
        count=cold.count();hooks=LearningHooks(Environment.DEMO)
        assert restore_learning_runtime(cold,hooks,{}).tca_observations==1
        assert restore_learning_runtime(cold,hooks,{}).tca_observations==1
        assert len(hooks.brokers.profiles[('paper','EURUSD','LONDON')].samples)==1
        assert cold.count()==count
    finally:cold.close()


@pytest.mark.parametrize('damage',['component','direction','flags','extra','ratio','missing'])
def test_exact_basis_corruption_is_refused_after_original_sqlite_readback(tmp_path,damage):
    import copy
    from vati.execution.tca import validate_tca_arithmetic
    ledger=Ledger(tmp_path/'original.sqlite3')
    try:
        cost,_=lifecycle_cost_path(ledger);payload=copy.deepcopy(cost.payload)
        if damage=='component':payload['arithmetic']['components']['delay']['numerator']='999'
        elif damage=='direction':payload['arithmetic']['direction']='SIDEWAYS'
        elif damage=='flags':payload['arithmetic']['settlement_qualified']=True
        elif damage=='extra':payload['arithmetic']['extra']='invented'
        elif damage=='ratio':payload['arithmetic']['cost_ratio_fraction']['denominator']='0'
        else:del payload['arithmetic']['direct_cost']
        with pytest.raises(ValueError,match='exact arithmetic'):validate_tca_arithmetic(payload)
        assert list(ledger.iter(EventKind.TCA_RECORD))[0].hash==cost.hash
    finally:ledger.close()
