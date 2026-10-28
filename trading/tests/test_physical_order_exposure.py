"""All-origin exposure is original order/receipt data, never a new grant."""
from dataclasses import asdict,replace
from decimal import Decimal as D

import pytest

from conftest import NOW,intent
from test_native_risk_history_inputs import native_facts,record
from test_native_risk_history_index import other_context
from vati.core import EventKind,make_event
from vati.execution.base import OrderCommand,ExecutionReceipt,StopMode
from vati.risk.contracts import Direction,LossModel
from vati.risk.physical_orders import physical_order_exposure
from vati.risk.serde import _enc


def command(ledger,facts,trade,*,publish=True):
    original=record(ledger,replace(facts,peak_equity=facts.equity,
        day_start_equity=facts.equity,week_start_equity=facts.equity),
        request=intent(trade_intent_id=trade,idempotency_key='original-key-'+trade,
            account_alias=facts.account_alias,venue=facts.symbol_contract.venue))
    p=original.payload;request=p['inputs']['intent'];decision=p['decision']
    assert decision['decision'] in {'APPROVED','REDUCED'}
    value=OrderCommand(trade,decision['decision_hash'],request['idempotency_key'],
        facts.account_alias,request['venue'],request['symbol'],Direction(request['direction']),
        'MARKET',D(decision['approved_size']),D(request['entry']),D(request['stop']),
        StopMode.VENUE,LossModel.STOP_DISTANCE,strategy_id=request['strategy_id'],
        strategy_version=request['strategy_version'],lease_epoch=1).sealed()
    event=make_event(EventKind.ORDER_COMMAND,'vati-execution-router',_enc(asdict(value)),
        event_time_ms=NOW*1000+1,received_time_ms=NOW*1000+1,correlation_id=trade)
    if publish:ledger.append(event)
    return event,value


def receipt(ledger,cmd,*,status,filled='0',when=2,**extra):
    r=ExecutionReceipt(cmd.trade_intent_id,cmd.decision_hash,cmd.venue,status,D(filled),
        cmd.entry_price if D(filled)>0 else None,cmd.entry_price,cmd.entry_price,cmd.entry_price,
        True,NOW*1000+when,NOW*1000+when,broker_position_id='source-position' if D(filled)>0 else '').sealed()
    p=_enc(asdict(r));p.update(extra)
    event=make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',p,
        event_time_ms=NOW*1000+when,received_time_ms=NOW*1000+when,correlation_id=cmd.trade_intent_id)
    ledger.append(event);return event


def exposure(ledger,facts):
    return physical_order_exposure(ledger,facts.native_account_context,available_at_ms=NOW*1000+100)


def test_alias_change_retains_original_unconfirmed_order_without_inventing_zero_margin(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    first,c1=command(ledger,a,'original-a')
    b=other_context(ledger,adapter,account,a,alias='second_alias')
    second,c2=command(ledger,b,'original-b')
    before=ledger.count();value=exposure(ledger,b)
    assert [o.origin_alias for o in value.orders]==[a.account_alias,b.account_alias]
    assert value.unpriced_order_refs==(first.hash,second.hash) and value.unresolved_refs==()
    for o in value.orders:
        assert o.state=='UNCONFIRMED' and o.reported_filled_quantity is None
        assert o.reported_unfilled_quantity is None and o.active_quantity_bound==o.quantity
        assert o.required_margin is None and o.execution_authority is False
    assert ledger.count()==before


@pytest.mark.parametrize('state',['ACCEPTED','PARTIAL','FILLED','UNKNOWN'])
def test_reported_entry_states_retain_full_exposure_until_native_coverage(state,tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'original')
    filled=str(cmd.quantity/2) if state=='PARTIAL' else str(cmd.quantity) if state=='FILLED' else '0'
    r=receipt(ledger,cmd,status=state,filled=filled)
    value=exposure(ledger,facts);o=value.orders[0]
    assert o.state=={'ACCEPTED':'PENDING','PARTIAL':'PARTIAL','FILLED':'OPEN','UNKNOWN':'UNCERTAIN'}[state]
    assert o.last_reported_status==state and o.receipt_refs==(r.hash,)
    assert o.reported_filled_quantity==D(filled) and o.active_quantity_bound==cmd.quantity
    assert o.required_margin is None and value.unresolved_refs==()


@pytest.mark.parametrize('status',['REJECTED','CANCELLED','EXPIRED'])
def test_original_zero_fill_terminal_no_effect_keeps_its_durable_receipt(status,tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'original')
    r=receipt(ledger,cmd,status=status)
    value=exposure(ledger,facts);o=value.orders[0]
    assert o.state=='NO_EFFECT' and o.active_quantity_bound==0
    assert o.reported_filled_quantity==0 and o.receipt_refs==(r.hash,)
    assert value.unpriced_order_refs==() and o.execution_authority is False


def test_an_accepted_order_needs_original_native_no_effect_reconciliation_before_release(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'original')
    receipt(ledger,cmd,status='ACCEPTED')
    receipt(ledger,cmd,status='CANCELLED',when=3)
    assert exposure(ledger,facts).orders[0].state=='UNCERTAIN'
    receipt(ledger,cmd,status='CANCELLED',when=4,native_entry_observation={
        'schema':'vati.native-entry-observation/1','command_hash':cmd.command_hash,'source':'ORIGINAL_NATIVE_RESULT'})
    assert exposure(ledger,facts).orders[0].state=='NO_EFFECT'


def test_bad_receipt_seal_or_unknown_availability_never_releases_original_exposure(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'original')
    bad=receipt(ledger,cmd,status='REJECTED',receipt_hash='0'*64)
    value=exposure(ledger,facts)
    assert bad.hash in value.unresolved_refs and value.orders[0].state=='UNCERTAIN'
    assert value.orders[0].reported_filled_quantity is None


def test_another_proven_physical_account_with_same_alias_is_not_local_exposure(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd);local,_=command(ledger,a,'a')
    b=other_context(ledger,adapter,account,a,alias=a.account_alias,server='Other-Broker-Demo')
    foreign,_=command(ledger,b,'b')
    value=exposure(ledger,a)
    assert [o.command_ref for o in value.orders]==[local.hash]
    assert foreign.hash not in value.unresolved_refs


@pytest.mark.parametrize('changes',[{'entry_price':D('0')},{'entry_price':D('NaN')},
    {'stop_mode':'MISSING'},{'loss_model':'MISSING'}])
def test_self_sealed_but_invalid_native_command_cannot_be_an_original_exposure(tmp_path,eurusd,changes):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'original',publish=False)
    bad=replace(cmd,**changes,command_hash='').sealed()
    e=make_event(EventKind.ORDER_COMMAND,'vati-execution-router',_enc(asdict(bad)),
        event_time_ms=NOW*1000+3,received_time_ms=NOW*1000+3,correlation_id=cmd.trade_intent_id)
    ledger.append(e)
    assert e.hash in exposure(ledger,facts).unresolved_refs


def test_native_result_without_known_local_arrival_cannot_release_collateral_early(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'original')
    r=ExecutionReceipt(cmd.trade_intent_id,cmd.decision_hash,cmd.venue,'REJECTED',D(0),
        None,cmd.entry_price,cmd.entry_price,cmd.entry_price,True,NOW*1000+2,None).sealed()
    event=make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',_enc(asdict(r)),
        event_time_ms=NOW*1000+2,received_time_ms=NOW*1000+2,correlation_id=cmd.trade_intent_id)
    ledger.append(event);value=exposure(ledger,facts)
    assert event.hash in value.unresolved_refs and value.orders[0].state=='UNCERTAIN'
    assert value.orders[0].active_quantity_bound==cmd.quantity
