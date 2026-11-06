"""Original source binding, conservative unknowns and per-leg close accounting."""
from copy import deepcopy
from dataclasses import asdict,replace
from decimal import Decimal as D

import pytest

from test_ctrader import FakeCtrader
from test_ctrader_close_fee_knowledge import account_close_review,entry_lifecycle
from test_native_receipt_fee_knowledge import native_fill
from vati.core import Ledger,EventKind,make_event
from vati.execution.recorded_close_costs import recorded_close_cost_entry
from vati.execution.review import closed_trade_pnl
from vati.app.trade_lifecycle import AccountTradeLifecycle


@pytest.mark.parametrize('defect',['alias','position','future','bad-seal','conflicting-cost','future-receipt-time'])
def test_unbound_or_unavailable_close_cannot_supply_known_charges(tmp_path,defect):
    ledger=Ledger(tmp_path/'unbound-close.sqlite')
    try:
        out=account_close_review(ledger)
        entry=deepcopy(out['original_entry_row']);alias=out['command'].account_alias;now=out['closed_at_ms']
        close=next(e for e in ledger.iter(EventKind.EXECUTION_RECEIPT) if e.payload.get('exit_action')=='CLOSE')
        if defect=='alias':alias='foreign'
        elif defect=='position':entry['broker_position_id']='another-position'
        elif defect=='future':now-=1
        else:
            payload=deepcopy(close.payload)
            if defect=='bad-seal':payload['fees']='99'
            else:
                receipt=AccountTradeLifecycle._receipt_from_payload(payload)
                receipt=replace(receipt,**({'fees':D('99')} if defect=='conflicting-cost'
                    else {'received_time_unix_ms':now+9999}),receipt_hash='').sealed()
                payload.update(asdict(receipt))
            ledger.append(make_event(EventKind.EXECUTION_RECEIPT,close.producer,payload,
                event_time_ms=now,received_time_ms=now,correlation_id=close.correlation_id))
        count=ledger.count()
        measured=recorded_close_cost_entry(ledger,entry,trade_intent_id=out['command'].trade_intent_id,
            venue='ctrader',account_alias=alias,available_at_ms=now)
        assert measured['fees'] is None and measured['recorded_close_costs']['state']=='RECORDED_CHARGES_UNAVAILABLE'
        assert measured['recorded_close_costs']['fees_final'] is measured['recorded_close_costs']['cash_reconciled'] is False
        assert ledger.count()==count and ledger.verify_chain()[0]
    finally:ledger.close()


def test_independent_reported_net_cash_keeps_precedence_over_missing_charge_decomposition(tmp_path):
    ledger=Ledger(tmp_path/'net-cash.sqlite')
    try:
        out=account_close_review(ledger,missing=('commission',))
        entry=recorded_close_cost_entry(ledger,out['original_entry_row'],
            trade_intent_id=out['command'].trade_intent_id,venue='ctrader',
            account_alias=out['command'].account_alias,available_at_ms=out['closed_at_ms'])
        entry['trade_intent_id']=out['command'].trade_intent_id
        measured=closed_trade_pnl(entry,out['receipt'].average_fill,out['life'].contracts['EURUSD'],
            [{'intent':out['command'].trade_intent_id,'pnl':D('12.34'),'pnl_basis':'NET_CONFIRMED'}])
        assert entry['fees'] is None and measured.amount==D('12.34') and measured.basis=='REPORTED_NET_CONFIRMED'
    finally:ledger.close()


@pytest.mark.parametrize('missing_last,duplicate_last',[(False,False),(True,False),(False,True)])
def test_actual_partial_then_full_native_closes_use_every_price_and_charge_once(tmp_path,missing_last,duplicate_last):
    from vati.lifecycle.family import FamilyMember,MemberRole
    ledger=Ledger(tmp_path/'partial-native-costs.sqlite')
    try:
        with native_fill(commission=-100) as (adapter,command,entry):
            life=entry_lifecycle(ledger,adapter,command,entry)
            peer=adapter.transport._connector.__self__;original=peer.handle;closed=[]
            def handle(name,body,cid):
                if name!='ProtoOAClosePositionReq':return original(name,body,cid)
                pid=body['positionId'];before=deepcopy(peer.positions[pid]);volume=body['volume']
                remaining=before['tradeData']['volume']-volume;index=len(closed)
                assert remaining>=0
                if remaining:
                    peer.positions[pid]['tradeData']['volume']=remaining
                    position=deepcopy(peer.positions[pid])
                else:
                    peer.positions.pop(pid);position={**before,'positionStatus':'POSITION_STATUS_CLOSED'}
                order_id=1001+index;price=(1.102,1.105)[index]
                deal={'dealId':2001 if duplicate_last else 2001+index,'orderId':order_id,'positionId':pid,'symbolId':before['tradeData']['symbolId'],
                    'volume':volume,'filledVolume':volume,'tradeSide':'SELL','dealStatus':'FILLED',
                    'createTimestamp':1700000000000,'executionTimestamp':1700000001000+index,
                    'executionPrice':price,'commission':(-125,-200)[index],'moneyDigits':2}
                if missing_last and index==1:deal.pop('commission')
                closed.append(deepcopy(deal))
                return FakeCtrader.send(peer,'ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,
                    'executionType':'ORDER_FILLED','position':position,
                    'order':{'orderId':order_id,'tradeData':{**before['tradeData'],'volume':volume,'tradeSide':'SELL'},
                        'orderType':'MARKET','orderStatus':'ORDER_STATUS_FILLED','closingOrder':True},'deal':deal},cid)
            peer.handle=handle
            first=life.router.apply_preservation('ctrader',position_id=entry.broker_position_id,
                trade_intent_id=command.trade_intent_id,action='PARTIAL_CLOSE',quantity=D('.04'),
                now_ms=1700000001000,reason='PARTIAL')
            assert first.status=='FILLED' and first.filled_qty==D('.04') and first.fees==D('1.25'), first.reject_reason
            assert first.protective_stop_confirmed and adapter.positions()[0].quantity==D('.06')
            family=life.families.for_intent(command.trade_intent_id)
            life.families.apply(family.family_id,FamilyMember('actual-first-close',MemberRole.PARTIAL_EXIT,
                first.filled_qty,first.average_fill,1700000001000,command.trade_intent_id),now_ms=1700000001000)
            life.entries[command.trade_intent_id]['quantity']=family.net_quantity
            second=life.router.apply_preservation('ctrader',position_id=entry.broker_position_id,
                trade_intent_id=command.trade_intent_id,action='FULL_CLOSE',now_ms=1700000002000,reason='FULL')
            assert second.status=='FILLED' and second.filled_qty==D('.06') and adapter.positions()==[]
            life._on_close(command.trade_intent_id,second.average_fill,'FULL',1700000002000)
            review=life.reviews[-1]
            if missing_last or duplicate_last:
                assert second.fees==(None if missing_last else D('2'))
                assert review.pnl_basis=='UNKNOWN_CHARGES' and review.broker_ok is False
            else:
                assert second.fees==D('2') and review.pnl==D('32.95')
                assert review.pnl_basis=='PRICE_DERIVED_NET_RECORDED_CHARGES'
            assert len(closed)==2 and ledger.verify_chain()[0]
    finally:ledger.close()
