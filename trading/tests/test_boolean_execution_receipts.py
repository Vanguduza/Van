"""False text and missing replies never prove a native protective effect."""
from decimal import Decimal as D

import pytest

from conftest import NOW,intent,mandate_dict,snapshot
from test_mt5_pull import bridge
from vati.core import Ledger
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_bridge import BridgeRequest,Mt5BridgeAdapter,Mt5BridgeClient
from vati.execution.protection import ProtectionManager
from vati.execution.router import ExecutionRouter,RouterError
from vati.risk import KillSwitch,KillSwitchTrigger,RiskAuthority,TradingMandate


def native_flow(contract,*,check=True,stop=True,modify=True):
    calls=[]
    def transport(request):
        assert client.verify(BridgeRequest(**request));calls.append(request['op'])
        data={'nonce':request['nonce'],'worker_time_ms':request['issued_ms']}
        if request['op']=='sync_account':
            return {**data,'entry_constraints':{'schema':'van.mt5.entry-constraints/1','explicit_deadline':True,'required_op':'order_send_expiring'},'account':{'equity':'10000','balance':'10000','currency':'USD',
                'verified':True,'hedging':True,'server_time_ms':request['issued_ms']}}
        if request['op']=='order_check':return {**data,'ok':check}
        if request['op']=='order_send_expiring':
            assert type(request['body']['expires_at_ms']) is int
            if request['body']['expires_at_ms']<=NOW*1000:
                return {**data,'status':'REJECTED','volume':'0','reason':'fixture original deadline expired'}
        if request['op']=='modify_sl_tp':return {**data,'ok':modify}
        return {**data,'status':'FILLED','volume':'0.18','price':'1.1001','order':'O1','position':'P1','sl_confirmed':stop}
    client=Mt5BridgeClient(signing_key=b'fixture-native-request-key',transport=transport)
    adapter=Mt5BridgeAdapter(client,clock=lambda:NOW*1000);mandate=TradingMandate.from_mapping(mandate_dict())
    trade=intent();native=snapshot(contract);authority=RiskAuthority(mandate);decision=authority.evaluate_safe(trade,native)
    from vati.execution.risk_refresh import CurrentRiskFacts
    # These native-parser fixtures state exact current facts; no truthy approval
    # may bypass the real RiskAuthority or the new native dispatch boundary.
    router=ExecutionRouter(ledger=Ledger(),adapters={'mt5':adapter},kill_switch=KillSwitch(),protection=ProtectionManager(),
        current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(native,NOW*1000),
        current_risk_authority=authority)
    return adapter,router,trade,decision,mandate,calls


def test_false_text_from_order_check_cannot_reach_the_actual_send(eurusd):
    adapter,router,trade,decision,mandate,calls=native_flow(eurusd,check='false')
    result=router.execute(trade,decision,mandate,now_ms=NOW*1000)
    assert result.status=='REJECTED' and calls==['sync_account','sync_account','order_check']


def test_unconfirmed_native_stop_is_not_reported_protected_and_uses_the_actual_flatten_path(eurusd):
    adapter,router,trade,decision,mandate,calls=native_flow(eurusd,stop='false')
    with pytest.raises(RouterError,match='flattened'):
        router.execute(trade,decision,mandate,now_ms=NOW*1000)
    assert calls==['sync_account','sync_account','order_check','order_send_expiring','close']
    assert KillSwitchTrigger.STOP_REJECTED in router.kill.active


def test_malformed_reply_after_a_sent_modification_stays_unknown(eurusd):
    adapter,*_=native_flow(eurusd,modify='false')
    result=adapter.modify_stop('P1',D('1.095'),now_ms=1000)
    assert result.status=='UNKNOWN' and result.protective_stop_confirmed is False
    assert result.protective_stop_price is None


@pytest.mark.parametrize('field',['trade_allowed','hedging'])
def test_actual_authenticated_ea_snapshot_cannot_coerce_false_text(bridge,field):
    queue,client,ea,adapter,clock=bridge
    native=ea.snapshot
    ea.snapshot=lambda:{**native(),field:'false'}
    assert ea.poll().status_code==200
    with pytest.raises(VenueUnavailable):adapter.sync_account()


def test_delayed_pull_modification_is_unknown_and_can_still_apply_after_the_wait(bridge):
    queue,client,ea,adapter,clock=bridge
    ea.positions[900]={'ticket':900,'symbol':'EURUSD','type':'BUY','volume':.1,'price_open':1.1,
        'sl':1.09,'tp':0,'comment':'vati:original','profit':0}
    assert ea.poll().status_code==200
    adapter.timeout_s=.02;adapter.poll_s=.005
    result=adapter.modify_stop('900',D('1.095'),now_ms=clock['ms'])
    assert result.status=='UNKNOWN' and result.protective_stop_confirmed is False
    assert ea.positions[900]['sl']==1.09
    assert ea.poll().status_code==200
    assert ea.positions[900]['sl']==1.095
