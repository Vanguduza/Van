"""The original mandate lifetime must reach the final native dispatch boundary."""
from dataclasses import replace
import pytest
from conftest import NOW, mandate_dict, snapshot, intent
from test_mt5_worker_funding import connection
from vati.core import Ledger, EventKind
from vati.execution import ExecutionRouter, ProtectionManager
from vati.execution.risk_refresh import CurrentRiskFacts
from vati.risk import RiskAuthority, TradingMandate, KillSwitch, Decision


def flow(tmp_path, eurusd):
    sdk, worker, adapter, clock = connection(tmp_path)
    clock['ms'] = NOW * 1000
    grant=mandate_dict(venue='mt5', account_alias='native', expires_at_unix=NOW+1)
    mandate = TradingMandate.from_mapping(grant)
    authority = RiskAuthority(mandate)
    trade = intent(venue='mt5', account_alias='native')
    ledger = Ledger()
    from vati.funding.mt5_runtime import capture_cached_mt5
    from vati.risk.account_context import context_for_account
    from test_native_risk_history_inputs import record
    account=adapter.sync_account()
    cached=capture_cached_mt5(ledger,account,now_ms=clock['ms'])
    context=context_for_account(ledger,adapter,account,now_ms=clock['ms'],mt5_capture=cached)
    facts = snapshot(replace(eurusd, venue='mt5'), account_alias='native',native_account_context=context)
    original=record(ledger,facts,request=trade,grant=grant)
    approved = authority.evaluate_safe(trade, facts)
    assert approved.decision in {Decision.APPROVED, Decision.REDUCED}
    assert original.payload['decision']['decision_hash']==approved.decision_hash
    router = ExecutionRouter(ledger=ledger, adapters={'mt5':adapter}, kill_switch=KillSwitch(),
        protection=ProtectionManager(), clock=lambda:clock['ms'], current_risk_authority=authority,
        current_risk_facts_provider=lambda *a, **kw:CurrentRiskFacts(facts,clock['ms']))
    return sdk, worker, adapter, clock, mandate, trade, approved, ledger, router


def test_original_router_mandate_deadline_is_in_the_actual_signed_native_request(tmp_path, eurusd):
    sdk, worker, adapter, clock, mandate, trade, approved, ledger, router = flow(tmp_path, eurusd)
    result = router.execute(trade, approved, mandate, now_ms=clock['ms'], entry_type='MARKET')
    assert result.status=='FILLED' and len(sdk.sent)==1
    sent = [r for r in adapter.client.sent if r.op.startswith('order_send')]
    assert len(sent)==1 and sent[0].op=='order_send_expiring'
    assert sent[0].body['expires_at_ms']==mandate.expires_at_unix*1000
    original = next(ledger.iter(EventKind.ORDER_COMMAND))
    assert original.payload['expires_at_ms']==sent[0].body['expires_at_ms']


def test_native_quote_after_router_preflight_cannot_outlive_the_original_mandate(tmp_path, eurusd):
    sdk, worker, adapter, clock, mandate, trade, approved, ledger, router = flow(tmp_path, eurusd)
    native_quote = sdk.symbol_info_tick
    calls=[]
    def delayed(symbol):
        value=native_quote(symbol);calls.append(symbol)
        if len(calls)==2:clock['ms']=mandate.expires_at_unix*1000
        return value
    sdk.symbol_info_tick=delayed
    result=router.execute(trade,approved,mandate,now_ms=clock['ms'],entry_type='MARKET')
    assert len(calls)>=2, 'fixture must delay the native send quote after the read-only precheck'
    assert result.status=='REJECTED' and sdk.sent==[], 'native adapter preparation renewed an expired mandate'
    assert ledger.count(EventKind.ORDER_COMMAND)==1 and ledger.count(EventKind.EXECUTION_RECEIPT)==1


@pytest.mark.parametrize('late', [False, True])
def test_original_quote_lifetime_is_not_renewed_inside_native_adapter_io(tmp_path, eurusd, late):
    from vati.execution.pretrade import MarketReference
    sdk, worker, adapter, clock, mandate, trade, approved, ledger, router = flow(tmp_path, eurusd)
    started=clock['ms']; original=sdk.symbol_info_tick; calls=[]
    def quote(symbol):
        value=original(symbol);calls.append(symbol)
        if late and len(calls)==2:clock['ms']=started+101
        return value
    sdk.symbol_info_tick=quote
    result=router.execute(trade,approved,mandate,now_ms=started,entry_type='MARKET',
        market_reference=MarketReference(trade.entry,0,100))
    sent=next(r for r in adapter.client.sent if r.op=='order_send_expiring')
    assert sent.body['expires_at_ms']==started+101
    assert result.status==('REJECTED' if late else 'FILLED') and len(sdk.sent)==(0 if late else 1)
