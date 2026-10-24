"""Signed worker admission must survive native reads up to the final SDK call."""
import pytest

from test_mt5_physical_identity import build
from test_mt5_worker import worker_mod
from vati.execution.mt5_bridge import BridgeRequest


@pytest.mark.parametrize('drift',['expired','physical_account','permissions','disconnected'])
def test_native_read_cannot_make_the_final_sdk_entry_use_stale_authority(tmp_path,drift):
    worker,signer,native=build(tmp_path);clock={'now':1000000};worker.clock=lambda:clock['now']
    tick=native.symbol_info_tick
    def native_read(symbol):
        result=tick(symbol)
        if drift=='expired':clock['now']+=worker_mod.SKEW_MS+1
        elif drift=='physical_account':native.server='Another-Broker'
        elif drift=='permissions':native.trade_allowed=False
        else:native.connected=False
        return result
    native.symbol_info_tick=native_read
    request=signer.sign(BridgeRequest('order_send',1,1000000,{'alias':'fx_primary','symbol':'EURUSD',
        'type':'BUY','volume':'0.1','price':'1.1','sl':'1.09','order_type':'MARKET'}))
    result=worker.handle(request.__dict__)
    assert result.get('status')=='REJECTED' and not native.sent,result


def test_current_signed_entry_still_reaches_exactly_one_native_sdk_send(tmp_path):
    worker,signer,native=build(tmp_path)
    request=signer.sign(BridgeRequest('order_send',1,1000000,{'alias':'fx_primary','symbol':'EURUSD',
        'type':'BUY','volume':'0.1','price':'1.1','sl':'1.09','order_type':'MARKET'}))
    result=worker.handle(request.__dict__)
    assert result['status']=='FILLED' and len(native.sent)==1


def test_final_native_account_read_cannot_extend_the_signed_time_window(tmp_path):
    worker,signer,native=build(tmp_path);clock={'now':1000000,'reads':0};worker.clock=lambda:clock['now']
    account=native.account_info
    def delayed_account():
        clock['reads']+=1
        result=account()
        if clock['reads']==3:clock['now']+=worker_mod.SKEW_MS+1
        return result
    native.account_info=delayed_account
    request=signer.sign(BridgeRequest('order_send',1,1000000,{'alias':'fx_primary','symbol':'EURUSD',
        'type':'BUY','volume':'0.1','price':'1.1','sl':'1.09','order_type':'MARKET'}))
    result=worker.handle(request.__dict__)
    assert result.get('status')=='REJECTED' and clock['reads']==3 and not native.sent,result
