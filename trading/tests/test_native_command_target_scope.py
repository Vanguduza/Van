"""A native adapter's account and venue are not transferred by a foreign command."""
from dataclasses import replace
from decimal import Decimal
import pytest
from vati.execution.base import OrderCommand,StopMode
from vati.risk.contracts import Direction,LossModel


def command(alias,venue):
    return OrderCommand('target-scope','a'*64,'scope-key',alias,venue,'EURUSD',Direction.LONG,
        'MARKET',Decimal('.1'),Decimal('1.1'),Decimal('1.09'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()


@pytest.mark.parametrize('damage',['account','venue'])
def test_actual_signed_worker_adapter_rejects_foreign_target_before_native_io(tmp_path,damage):
    from test_mt5_worker_funding import connection
    sdk,worker,adapter,clock=connection(tmp_path)
    cmd=command(adapter.account_alias,adapter.venue)
    cmd=replace(cmd,**({'account_alias':'other-owner-account'} if damage=='account' else {'venue':'paper'}),command_hash='').sealed()
    result=adapter.submit(cmd,now_ms=clock['ms'])
    assert result.status=='REJECTED' and 'target' in result.reject_reason.lower()
    assert adapter.client.sent==[] and sdk.sent==[]


@pytest.mark.parametrize('damage',['account','venue'])
def test_actual_ctrader_adapter_rejects_foreign_target_before_native_io(damage):
    from test_ctrader_original_outcomes import NativeOutcomes,adapter as bind
    native=NativeOutcomes();adapter=bind(native)
    cmd=command(adapter.account_alias,adapter.venue)
    cmd=replace(cmd,**({'account_alias':'other-owner-account'} if damage=='account' else {'venue':'paper'}),command_hash='').sealed()
    result=adapter.submit(cmd,now_ms=1000)
    assert result.status=='REJECTED' and 'target' in result.reject_reason.lower()
    assert native.requests==[]


def test_native_target_refusal_leaves_the_real_signed_worker_send_available(tmp_path):
    from test_mt5_worker_funding import connection
    sdk,worker,adapter,clock=connection(tmp_path)
    original=command(adapter.account_alias,adapter.venue)
    foreign=replace(original,account_alias='other-account',command_hash='').sealed()
    assert adapter.submit(foreign,now_ms=clock['ms']).status=='REJECTED'
    assert not adapter.client.sent and not sdk.sent
    valid=adapter.submit(original,now_ms=clock['ms'])
    assert valid.status=='FILLED' and valid.filled_qty==original.quantity
    assert len(sdk.sent)==1 and [r.op for r in adapter.client.sent]==['sync_account','order_check','sync_account','order_send']


@pytest.mark.parametrize('damage',['account','venue','disabled','false-text','true-integer'])
def test_legacy_deriv_receiver_does_not_bypass_target_or_entry_disable_without_identity(damage):
    from vati.execution.deriv import DerivAdapter
    requests=[]
    def native(message):
        requests.append(message)
        return {'proposal':{'id':'fixture-proposal'}} if 'proposal' in message else {'buy':{'buy_price':'25','contract_id':7}}
    adapter=DerivAdapter(transport=native)
    cmd=replace(command(adapter.account_alias,adapter.venue),symbol='frxEURUSD',entry_type='CONTRACT_BUY',
        quantity=Decimal('25'),loss_model=LossModel.FULL_STAKE,protective_stop=None,command_hash='').sealed()
    if damage=='account':cmd=replace(cmd,account_alias='other-account',command_hash='').sealed()
    elif damage=='venue':cmd=replace(cmd,venue='paper',command_hash='').sealed()
    elif damage=='disabled':adapter.entry_enabled=False
    elif damage=='false-text':adapter.entry_enabled='false'
    else:adapter.entry_enabled=1
    result=adapter.submit(cmd,now_ms=1000)
    assert result.status=='REJECTED' and requests==[] and adapter.sent==[]


@pytest.mark.parametrize('damage',['account','venue'])
def test_router_misconfigured_native_map_refuses_before_io_key_or_order(tmp_path,eurusd,damage):
    from conftest import NOW,intent,snapshot,mandate_dict
    from test_mt5_worker_funding import connection
    from vati.core import Ledger,EventKind
    from vati.execution import ExecutionRouter,ProtectionManager,RouterError
    from vati.execution.risk_refresh import CurrentRiskFacts
    from vati.risk import RiskAuthority,TradingMandate,KillSwitch
    sdk,worker,adapter,clock=connection(tmp_path);clock['ms']=NOW*1000
    venue='paper' if damage=='venue' else 'mt5'
    trade=intent(account_alias='native',venue=venue)
    facts=snapshot(replace(eurusd,venue=venue),account_alias='native')
    mandate=TradingMandate.from_mapping(mandate_dict(account_alias='native',venue=venue))
    authority=RiskAuthority(mandate);decision=authority.evaluate_safe(trade,facts)
    from vati.risk import Decision
    assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
    if damage=='account':adapter.account_alias='misconfigured-native-alias'
    ledger=Ledger();kill=KillSwitch()
    router=ExecutionRouter(ledger=ledger,adapters={venue:adapter},kill_switch=kill,protection=ProtectionManager(),clock=lambda:clock['ms'],
        current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(facts,clock['ms']),current_risk_authority=authority)
    with pytest.raises(RouterError,match='target'):router.execute(trade,decision,mandate,now_ms=clock['ms'],entry_type='MARKET')
    assert not adapter.client.sent and not sdk.sent
    assert ledger.count(EventKind.ORDER_COMMAND)==0 and trade.idempotency_key not in router._seen
    assert not kill.halted,'a local target-map error was reported as a broker disconnection'
