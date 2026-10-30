"""Actual native reply availability must not be backdated to dispatch."""
from test_router_native_entry_deadline import flow
from vati.core import EventKind


def test_genuine_fill_received_after_mandate_expiry_retains_effect_and_actual_availability(tmp_path,eurusd):
    sdk,worker,a,clock,m,trade,approved,ledger,router=flow(tmp_path,eurusd)
    original=a.client._transport;late=m.expires_at_unix*1000+2000
    def delayed(request):
        response=original(request)
        if request['op']=='order_send_expiring':clock['ms']=late
        return response
    a.client._transport=delayed
    r=router.execute(trade,approved,m,now_ms=clock['ms'],entry_type='MARKET')
    assert r.status=='FILLED' and len(sdk.sent)==1
    assert r.broker_position_id in router.protection.rules, 'late real fills still require protection'
    e=next(ledger.iter(EventKind.EXECUTION_RECEIPT))
    assert r.received_time_unix_ms==late and e.received_time_ms==late, 'actual native result availability was backdated to dispatch'

import pytest

@pytest.mark.parametrize('bad',[True,None,'unavailable',-1,'throws'])
def test_clock_failure_after_a_real_fill_keeps_effect_and_protection_but_withholds_learning_time(tmp_path,eurusd,bad):
    sdk,worker,a,clock,m,trade,approved,ledger,router=flow(tmp_path,eurusd)
    original=a.client._transport;started=clock['ms']
    def delayed(request):
        response=original(request)
        if request['op']=='order_send_expiring':
            if bad=='throws':
                def unavailable():raise RuntimeError('fixture receive clock unavailable')
                router.clock=unavailable
            else:clock['ms']=bad
        return response
    a.client._transport=delayed
    r=router.execute(trade,approved,m,now_ms=clock['ms'],entry_type='MARKET')
    assert r.status=='FILLED' and len(sdk.sent)==1 and r.broker_position_id in router.protection.rules
    assert r.received_time_unix_ms is None and router.kill.halted
    ev=next(ledger.iter(EventKind.EXECUTION_RECEIPT));assert ev.payload['received_time_unix_ms'] is None
    assert ev.payload['receipt_availability']=={'state':'UNAVAILABLE','received_at_ms':None,'dispatch_lower_bound_ms':started}
    assert any(e.payload.get('reason')=='RECEIPT_AVAILABILITY_CLOCK_UNAVAILABLE'for e in ledger.iter(EventKind.KILL_SWITCH))
    from vati.app.trade_lifecycle import AccountTradeLifecycle
    assert AccountTradeLifecycle._receipt_from_payload(ev.payload).received_time_unix_ms is None
    assert r.sealed().receipt_hash==r.receipt_hash

def test_unknown_availability_retains_account_exposure_without_emitting_timed_learning(tmp_path,eurusd):
    from dataclasses import replace
    from decimal import Decimal
    from vati.app.trade_lifecycle import AccountTradeLifecycle
    sdk,worker,a,clock,m,trade,approved,ledger,router=flow(tmp_path,eurusd)
    r=router.execute(trade,approved,m,now_ms=clock['ms'],entry_type='MARKET')
    r=replace(r,received_time_unix_ms=None,receipt_hash='').sealed()
    life=AccountTradeLifecycle(ledger,a,router,router.protection,{'EURUSD':eurusd},{})
    life.record_entry(intent=trade,receipt=r,state=None,modelled_cost_pct=Decimal('0'),software_stop=False,decision=approved)
    assert life.entries[trade.trade_intent_id]['open'] is True
    assert life.entries[trade.trade_intent_id]['quantity']==r.filled_qty
    assert ledger.count(EventKind.TCA_RECORD)==0 and ledger.count(EventKind.TRADE_THESIS)==0
    assert life.families.for_intent(trade.trade_intent_id) is None

@pytest.mark.parametrize('qualified',[False,True])
def test_experience_rejects_unmeasured_availability_with_a_real_positive_control(tmp_path,eurusd,qualified):
    from vati.learning.episodes import episode_from_ledger,Environment
    sdk,worker,a,clock,m,trade,approved,ledger,router=flow(tmp_path,eurusd)
    # flow now publishes the complete original risk input itself. A second
    # incomplete approval would contradict the unique original binding.
    assert ledger.count(EventKind.RISK_DECISION)==1
    if not qualified:
        original=a.client._transport
        def delayed(request):
            response=original(request)
            if request['op']=='order_send_expiring':clock['ms']=None
            return response
        a.client._transport=delayed
    r=router.execute(trade,approved,m,now_ms=clock['ms'],entry_type='MARKET')
    ep=episode_from_ledger(ledger,trade.trade_intent_id,environment=Environment.DEMO)
    assert (ep is not None)==qualified
    if qualified:assert ep.execution['receipt_hash']==r.receipt_hash and ep.execution['fill']==str(r.average_fill)


def test_restart_restores_real_position_but_never_backfills_an_unknown_receipt_time(eurusd):
    from dataclasses import replace
    from decimal import Decimal
    from conftest import NOW,intent,mandate_dict,snapshot
    from vati.core import Ledger
    from vati.risk import RiskAuthority,TradingMandate,StrategyState,KillSwitch
    from vati.execution import ExecutionRouter,ProtectionManager
    from vati.execution.paper import PaperAdapter
    from vati.app.trade_lifecycle import AccountTradeLifecycle
    contract=replace(eurusd,venue='paper')
    mandate=TradingMandate.from_mapping(mandate_dict(venue='paper',mode='DEMO_TRADER'))
    trade=intent(venue='paper',strategy_state=StrategyState.DEMO)
    decision=RiskAuthority(mandate).evaluate(trade,snapshot(contract))
    ledger=Ledger();a=PaperAdapter(account_alias=trade.account_alias);clock={'ms':NOW*1000}
    original=a.submit
    def complete(cmd,**kwargs):
        receipt=original(cmd,**kwargs);clock['ms']=None;return receipt
    a.submit=complete
    router=ExecutionRouter(ledger=ledger,adapters={'paper':a},kill_switch=KillSwitch(),protection=ProtectionManager(),clock=lambda:clock['ms'])
    receipt=router.execute(trade,decision,mandate,now_ms=clock['ms'])
    assert receipt.status=='FILLED' and receipt.received_time_unix_ms is None
    recovered=AccountTradeLifecycle(ledger,a,router,ProtectionManager(),{'EURUSD':contract},{})
    restored,unresolved=recovered.recover_from_venue()
    assert restored==(trade.trade_intent_id,) and unresolved==()
    assert recovered.entries[trade.trade_intent_id]['open'] is True
    assert receipt.broker_position_id in recovered.protection.rules
    assert ledger.count(EventKind.TCA_RECORD)==0
    assert next(ledger.iter(EventKind.EXECUTION_RECEIPT)).payload['received_time_unix_ms'] is None
