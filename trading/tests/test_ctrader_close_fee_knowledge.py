"""Framed native close charges retain their own precision and actual execution."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal as D

import pytest

from test_ctrader import FakeCtrader
from test_native_receipt_fee_knowledge import native_fill


@contextmanager
def native_close(*,missing=(),commission=-325,digits=2,close_with=None):
    with native_fill(commission=-100,digits=2) as (adapter,command,entry):
        assert entry.fees==D('1')
        peer=adapter.transport._connector.__self__
        def send(name,body,cid=None):
            body=deepcopy(body)
            if name=='ProtoOAExecutionEvent' and (body.get('order') or {}).get('closingOrder') is True:
                body['deal'].update(commission=commission,moneyDigits=digits)
                for key in missing:body['deal'].pop(key,None)
            return FakeCtrader.send(peer,name,body,cid)
        peer.send=send
        receipt=(close_with(adapter,command,entry) if close_with is not None else
            adapter.close(entry.broker_position_id,None,now_ms=entry.received_time_unix_ms+1000,reason='OWNER'))
        assert receipt.status=='FILLED' and receipt.filled_qty==entry.filled_qty==D('.10')
        assert receipt.broker_order_id=='2' and receipt.broker_position_id==entry.broker_position_id
        assert receipt.protective_stop_confirmed and adapter.positions()==[]
        yield adapter,command,entry,receipt


@pytest.mark.parametrize('missing',[('commission',),('moneyDigits',),('commission','moneyDigits')])
def test_missing_close_charge_fields_do_not_become_measured_zero_or_erase_fill(missing):
    with native_close(missing=missing) as (adapter,command,entry,receipt):
        assert receipt.fees is None
        assert receipt.receipt_hash==receipt.sealed().receipt_hash


@pytest.mark.parametrize('commission,expected',[(0,D(0)),(-325,D('3.25')),(325,D('3.25'))])
def test_measured_close_charge_uses_its_own_scale_and_existing_magnitude_convention(commission,expected):
    with native_close(commission=commission) as (adapter,command,entry,receipt):
        assert receipt.fees==expected


def test_unsupported_close_row_precision_keeps_execution_and_unknown_charge():
    with native_close(digits=19) as (adapter,command,entry,receipt):
        assert receipt.fees is None


def entry_lifecycle(ledger,adapter,command,entry):
    from dataclasses import asdict,replace
    from types import SimpleNamespace
    from test_account_lifecycle import _lifecycle,_append_command
    from vati.core import EventKind,make_event
    from vati.risk.contracts import TradeIntent,StrategyState
    _append_command(ledger,command,now=entry.received_time_unix_ms-1)
    from vati.execution.ctrader.charge_source import receipt_charge_evidence
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',
        {**asdict(entry),**receipt_charge_evidence(adapter,entry)},
        event_time_ms=entry.broker_time_unix_ms,received_time_ms=entry.received_time_unix_ms,
        correlation_id=command.trade_intent_id))
    life=_lifecycle(ledger,adapter);life.router.adapters={'ctrader':adapter}
    life.contracts={k:replace(v,venue='ctrader') for k,v in life.contracts.items()}
    intent=TradeIntent(trade_intent_id=command.trade_intent_id,idempotency_key=command.idempotency_key,
        account_alias=command.account_alias,venue=command.venue,symbol=command.symbol,direction=command.direction,
        strategy_id=command.strategy_id,strategy_version='1.0.0',strategy_state=StrategyState.DEMO,
        entry=command.entry_price,stop=command.protective_stop,requested_risk_pct=D('.005'),
        decision_hash=command.decision_hash,market_snapshot_hash='m'*64)
    life.record_entry(intent=intent,receipt=entry,
        state=SimpleNamespace(session=SimpleNamespace(value='LONDON'),event_window=SimpleNamespace(value='NONE')),
        modelled_cost_pct=D('.0003'),software_stop=False)
    return life


def account_close_review(ledger,*,missing=(),commission=-325):
    output={}
    def close(adapter,command,entry):
        life=entry_lifecycle(ledger,adapter,command,entry)
        output['original_entry_row']=deepcopy(life.entries[command.trade_intent_id])
        now=entry.received_time_unix_ms+1000
        receipt=life.router.apply_preservation('ctrader',position_id=entry.broker_position_id,
            trade_intent_id=command.trade_intent_id,action='FULL_CLOSE',now_ms=now,reason='OWNER')
        life._on_close(command.trade_intent_id,receipt.average_fill,'OWNER',now)
        output.update(life=life,adapter=adapter,command=command,entry=entry,receipt=receipt,
            review=life.reviews[-1],closed_at_ms=now)
        return receipt
    with native_close(missing=missing,commission=commission,close_with=close):pass
    return output


def test_actual_account_close_review_does_not_invent_known_net_charges(tmp_path):
    from vati.core import Ledger
    ledger=Ledger(tmp_path/'close-cost-review.sqlite')
    try:
        out=account_close_review(ledger,missing=('commission',))
        assert out['receipt'].fees is None and out['receipt'].status=='FILLED'
        assert out['review'].pnl_basis=='UNKNOWN_CHARGES'
        assert out['review'].broker_ok is False
        assert out['command'].trade_intent_id not in out['life'].entries
        assert ledger.verify_chain()[0]
    finally:ledger.close()


def test_actual_account_review_includes_recorded_exit_charge_once(tmp_path):
    from vati.core import Ledger
    ledger=Ledger(tmp_path/'close-cost-known.sqlite')
    try:
        out=account_close_review(ledger)
        contract=out['life'].contracts['EURUSD']
        expected=(out['receipt'].average_fill-out['entry'].average_fill)*out['entry'].filled_qty*contract.value_per_price_unit_per_lot
        expected-=out['entry'].fees+out['receipt'].fees
        assert out['receipt'].fees==D('3.25') and out['entry'].fees==D('1')
        assert out['review'].pnl==expected
        assert out['review'].pnl_basis=='PRICE_DERIVED_NET_RECORDED_CHARGES'
        assert ledger.verify_chain()[0]
    finally:ledger.close()


@pytest.mark.parametrize('missing',[(),('commission',)])
def test_native_close_cost_projection_reopens_original_sql_without_provider_io(tmp_path,missing):
    from vati.core import Ledger
    from vati.app.trade_lifecycle import AccountTradeLifecycle
    from vati.execution.recorded_close_costs import recorded_close_cost_entry
    ledger=Ledger(tmp_path/'durable-close-cost.sqlite');cold=None
    try:
        out=account_close_review(ledger,missing=missing)
        cold=Ledger(ledger.path);count=ledger.count();sent=out['adapter'].transport.sent
        projected=recorded_close_cost_entry(cold,out['original_entry_row'],
            trade_intent_id=out['command'].trade_intent_id,venue='ctrader',
            account_alias=out['command'].account_alias,available_at_ms=out['closed_at_ms'])
        assert projected['fees']==(None if missing else D('4.25'))
        assert out['original_entry_row']['fees']==D('1')
        from vati.core import EventKind
        exits=[e for e in cold.iter(EventKind.EXECUTION_RECEIPT) if e.payload.get('exit_action')=='CLOSE']
        assert len(exits)==1
        restored=AccountTradeLifecycle._receipt_from_payload(exits[0].payload)
        assert restored.receipt_hash==out['receipt'].receipt_hash and restored.fees==out['receipt'].fees
        assert projected['recorded_close_costs']['exit_receipt_refs']==[exits[0].hash]
        assert projected['recorded_close_costs']['fees_final'] is False
        assert ledger.count()==count and out['adapter'].transport.sent==sent and cold.verify_chain()[0]
    finally:
        if cold is not None:cold.close()
        ledger.close()


@pytest.mark.parametrize('missing',[(),('commission',)])
def test_actual_single_symbol_review_consumes_original_exit_costs(tmp_path,missing):
    from dataclasses import replace
    from vati.core import Ledger
    from vati.app.cycle import DecisionCycle
    from vati.intelligence.events import EventMatrix
    from vati.market_data import FX_CALENDAR
    from test_backtest_runner_cli import fx_cfg,fx_engine
    ledger=Ledger(tmp_path/'single-close-cost.sqlite')
    try:
        out=account_close_review(ledger,missing=missing)
        original_cfg=fx_cfg(out['life'].contracts['EURUSD'])
        cfg=replace(original_cfg,venue='ctrader',account_alias=out['command'].account_alias,
                    contract=out['life'].contracts['EURUSD'])
        cycle=DecisionCycle(cfg=cfg,adapter=out['adapter'],ledger=ledger,engine=fx_engine(cfg),
            cost_fn=lambda state:D('.0003'),calendar=FX_CALENDAR,events=EventMatrix())
        cycle._entries[out['command'].trade_intent_id]=deepcopy(out['original_entry_row'])
        cycle._on_close(out['command'].trade_intent_id,out['receipt'].average_fill,'OWNER',out['closed_at_ms'])
        review=cycle.reviews[-1]
        assert review.pnl_basis==('UNKNOWN_CHARGES' if missing else 'PRICE_DERIVED_NET_RECORDED_CHARGES')
        assert review.broker_ok is (not bool(missing))
        if not missing:assert review.pnl==D('44.95')
        assert out['command'].trade_intent_id not in cycle._entries and ledger.verify_chain()[0]
    finally:ledger.close()


def test_replayed_identical_exit_receipt_does_not_charge_the_parent_twice(tmp_path):
    from dataclasses import asdict
    from vati.core import Ledger,EventKind,make_event
    from vati.execution.recorded_close_costs import recorded_close_cost_entry
    ledger=Ledger(tmp_path/'replayed-close-cost.sqlite')
    try:
        out=account_close_review(ledger)
        original=next(e for e in ledger.iter(EventKind.EXECUTION_RECEIPT) if e.payload.get('exit_action')=='CLOSE')
        ledger.append(make_event(EventKind.EXECUTION_RECEIPT,original.producer,original.payload,
            event_time_ms=out['closed_at_ms']+1,received_time_ms=out['closed_at_ms']+1,
            correlation_id=original.correlation_id))
        entry=recorded_close_cost_entry(ledger,out['original_entry_row'],trade_intent_id=original.correlation_id,
            venue='ctrader',account_alias=out['command'].account_alias,available_at_ms=out['closed_at_ms']+1)
        assert entry['fees']==D('4.25') and len(entry['recorded_exit_fills'])==1
        assert entry['recorded_close_costs']['exit_receipt_refs']==[original.hash]
        assert ledger.verify_chain()[0]
    finally:ledger.close()
