"""Native-source data through the real session recovery actor and journal.

The source session and isolated P256 issuer are fixtures; this is not a
production native runtime, device grant, broker execution or acceptance.
"""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from test_runtime_recovery_actor import runtime
from test_mt5_funding_runtime import setup
from test_native_risk_history_inputs import record
from conftest import snapshot, intent, mandate_dict
from vati.core import EventKind, make_event
from vati.execution.base import Health
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.lockouts import ACCOUNT_SCOPE
from vati.risk.physical_runtime import PhysicalRiskRuntime
from vati.app.runtime_control_actor import process_recovery_requests


def native_source(runtime,tmp_path,eurusd):
    service,clock,request=runtime;c=service.runner.cycle
    unused,adapter,account=setup(tmp_path);unused.close()
    current=replace(account,account_alias=c.cfg.account_alias,
        funding_mark=replace(account.funding_mark,account_alias=c.cfg.account_alias))
    adapter.account_alias=c.cfg.account_alias
    adapter.sync_account=lambda:current
    adapter.heartbeat=lambda **_:Health(True,0,clock['ms'])
    adapter.positions=lambda:[]
    capture=capture_cached_mt5(c.ledger,current,now_ms=clock['ms'])
    context=context_for_account(c.ledger,adapter,current,now_ms=clock['ms'],mt5_capture=capture)
    facts=snapshot(replace(eurusd,venue=adapter.venue),now_unix=clock['ms']//1000,
        account_alias=current.account_alias,equity=current.equity,balance=current.balance,
        native_account_context=context)
    c.cfg=replace(c.cfg,contract=facts.symbol_contract,venue=adapter.venue)
    c.adapter=adapter
    return service,clock,request,current,facts


def loss(service,clock,facts,trade):
    c=service.runner.cycle
    event=record(c.ledger,facts,now_ms=clock['ms'],request=intent(
        trade_intent_id=trade,account_alias=facts.account_alias,venue=facts.symbol_contract.venue),
        grant=mandate_dict(account_alias=facts.account_alias,venue=facts.symbol_contract.venue,
            signed_at_unix=clock['ms']//1000-60,expires_at_unix=clock['ms']//1000+86400))
    assert event.payload['decision']['decision'] in {'APPROVED','REDUCED'},event.payload['decision']
    close=make_event(EventKind.TRADE_REVIEW,'vati-cycle',{'account_alias':facts.account_alias,
        'trade_intent_id':trade,'strategy_id':event.payload['inputs']['intent']['strategy_id'],
        'pnl':'-10','pnl_basis':'VENUE_NATIVE_ESTIMATE','broker_ok':True,'record_revision':0},
        event_time_ms=clock['ms'],received_time_ms=clock['ms'],correlation_id=trade)
    c.ledger.append(close)


def refresh(service,clock,facts):
    c=service.runner.cycle
    state=PhysicalRiskRuntime(c.ledger,facts.native_account_context,c.streaks.policy,now_ms=clock['ms'])
    c._physical_risk_runtime=state;c.streaks=state.streaks
    c.peak_equity=state.book.projection(clock['ms']).peak


@pytest.mark.parametrize('missing_source',[False,True])
def test_actual_native_source_actor_applies_original_owner_reset_or_refuses_unavailable_source(runtime,tmp_path,eurusd,missing_source):
    service,clock,request,account,facts=native_source(runtime,tmp_path,eurusd)
    loss(service,clock,facts,'original-own-loss');refresh(service,clock,facts)
    journal,original=request('reset_loss_streak',{'scope':ACCOUNT_SCOPE})
    if missing_source:
        service.runner.cycle.adapter.sync_account=lambda:replace(account,funding_mark=None)
    process_recovery_requests(service)
    result=journal.status(original.proof.operation_id,original.intent.device_id)
    if missing_source:
        assert result.phase=='REFUSED' and result.result['reason_code']=='PRECONDITION_UNMET'
        assert result.result['effect_refs']==[]
        assert service.runner.cycle.streaks._scopes[ACCOUNT_SCOPE].losses==1
    else:
        assert result.phase=='APPLIED' and result.result['reason_code']=='APPLIED'
        assert service.runner.cycle.streaks._scopes[ACCOUNT_SCOPE].losses==0
        effect=next(e for e in service._ledger.iter(EventKind.SESSION) if e.hash==result.result['effect_refs'][0])
        assert effect.payload['native_account_context']['account_alias']==service.cfg.account_alias
        count=service._ledger.count(EventKind.SESSION)
        process_recovery_requests(service)
        assert service._ledger.count(EventKind.SESSION)==count
    assert result.result['entry_authority_granted'] is False
    assert service._ledger.count(EventKind.ORDER_COMMAND)==0


def test_actor_rechecks_new_native_loss_before_applying_reviewed_reset(runtime,tmp_path,eurusd):
    service,clock,request,_,facts=native_source(runtime,tmp_path,eurusd)
    loss(service,clock,facts,'first');refresh(service,clock,facts)
    journal,original=request('reset_loss_streak',{'scope':ACCOUNT_SCOPE})
    loss(service,clock,facts,'later-original-loss')
    process_recovery_requests(service)
    result=journal.status(original.proof.operation_id,original.intent.device_id)
    assert result.phase=='REFUSED' and result.result['reason_code']=='STATE_CHANGED'
    assert result.result['effect_refs']==[]
    assert service.runner.cycle.streaks._scopes[ACCOUNT_SCOPE].losses==2
