"""Native SDK uncertainty must not become empty exposure or a zero-effect refusal."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from test_account_lifecycle import _command
from test_mt5_worker import make_worker,KEY
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_bridge import Mt5BridgeClient,Mt5BridgeAdapter


def rig(tmp_path):
    worker,_=make_worker(tmp_path,lambda:1000000)
    client=Mt5BridgeClient(signing_key=KEY,transport=worker.handle)
    return worker,client,Mt5BridgeAdapter(client,account_alias='fx_primary',clock=lambda:1000000)


@pytest.mark.parametrize('operation,method,field',[('positions','positions_get','positions'),
    ('orders','orders_get','orders'),('history','history_deals_get','deals')])
def test_failed_native_collection_read_cannot_report_a_successful_empty_collection(tmp_path,monkeypatch,operation,method,field):
    worker,client,adapter=rig(tmp_path)
    monkeypatch.setattr(worker.t.mt5,method,lambda *args,**kwargs:None)
    response=client.call(operation,{'alias':'fx_primary','from_s':0,'to_s':1},now_ms=1000000)
    assert 'error' in response and field not in response


def test_native_send_with_an_effect_but_no_sdk_reply_remains_unknown(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path);native_send=worker.t.mt5.order_send
    def acknowledgement_lost(request):
        native_send(request)
        return None
    monkeypatch.setattr(worker.t.mt5,'order_send',acknowledgement_lost)
    command=replace(_command('native-ack-lost'),account_alias='fx_primary',venue='mt5',entry_type='MARKET',command_hash='').sealed()
    result=adapter.submit(command,now_ms=1000000)
    assert worker.t.mt5.pos,'fixture must actually execute the native SDK effect before losing its reply'
    assert result.status=='UNKNOWN'


@pytest.mark.parametrize('operation',['modify','close'])
def test_native_protective_effect_with_no_sdk_reply_cannot_report_no_effect(tmp_path,monkeypatch,operation):
    worker,client,adapter=rig(tmp_path)
    command=replace(_command('protective-ack-lost'),account_alias='fx_primary',venue='mt5',entry_type='MARKET',command_hash='').sealed()
    opened=adapter.submit(command,now_ms=1000000);assert opened.status=='FILLED'
    native_send=worker.t.mt5.order_send
    def acknowledgement_lost(request):
        native_send(request)
        return None
    monkeypatch.setattr(worker.t.mt5,'order_send',acknowledgement_lost)
    if operation=='modify':
        result=adapter.modify_stop(opened.broker_position_id,command.protective_stop+D('.001'),now_ms=1000001)
        assert str(worker.t.mt5.pos[int(opened.broker_position_id)].sl)=='1.091'
        assert result.status=='UNKNOWN' and result.protective_stop_confirmed is False
    else:
        result=adapter.close(opened.broker_position_id,None,now_ms=1000001,reason='SOURCE_PROTECTION')
        assert not worker.t.mt5.pos
        assert result.status=='UNKNOWN'
        assert result.protective_stop_confirmed is False


def test_native_partial_close_is_not_labeled_a_complete_fill(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path)
    command=replace(_command('native-partial-close'),account_alias='fx_primary',venue='mt5',entry_type='MARKET',command_hash='').sealed()
    opened=adapter.submit(command,now_ms=1000000);assert opened.status=='FILLED'
    def partial_close(request):
        worker.t.mt5.pos[request['position']].volume=.05
        return NS(retcode=worker.t.mt5.TRADE_RETCODE_DONE_PARTIAL,volume=.05,price=request['price'],comment='native partial close')
    monkeypatch.setattr(worker.t.mt5,'order_send',partial_close)
    result=adapter.close(opened.broker_position_id,None,now_ms=1000001,reason='SOURCE_PARTIAL')
    assert worker.t.mt5.pos[int(opened.broker_position_id)].volume==.05
    assert result.status=='PARTIAL' and result.filled_qty==D('.05')


@pytest.mark.parametrize('scope',['account-expert','python-api'])
def test_other_native_algorithmic_permission_denials_prevent_entry(tmp_path,monkeypatch,scope):
    worker,client,adapter=rig(tmp_path)
    if scope=='account-expert':
        account_info=worker.t.mt5.account_info
        def restricted():
            account=account_info();account.trade_expert=False;return account
        monkeypatch.setattr(worker.t.mt5,'account_info',restricted)
        monkeypatch.setattr(worker.t.mt5,'terminal_info',lambda:NS(connected=True,trade_allowed=True,tradeapi_disabled=False),raising=False)
    else:
        monkeypatch.setattr(worker.t.mt5,'terminal_info',lambda:NS(connected=True,trade_allowed=True,tradeapi_disabled=True),raising=False)
    command=replace(_command('native-permission-denied'),account_alias='fx_primary',venue='mt5',entry_type='MARKET',command_hash='').sealed()
    result=adapter.submit(command,now_ms=1000000)
    assert result.status=='REJECTED' and not worker.t.mt5.sent


@pytest.mark.parametrize('connected',[False,None,1,'true'])
def test_a_cached_account_identity_is_not_a_current_broker_connection(tmp_path,monkeypatch,connected):
    worker,client,adapter=rig(tmp_path)
    monkeypatch.setattr(worker.t.mt5,'terminal_info',lambda:NS(connected=connected,trade_allowed=True,tradeapi_disabled=False),raising=False)
    with pytest.raises(VenueUnavailable):adapter.sync_account()
    assert not worker.t.mt5.sent


def test_terminal_disabled_algorithmic_trading_refuses_before_native_send(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path)
    monkeypatch.setattr(worker.t.mt5,'terminal_info',lambda:NS(connected=True,trade_allowed=False,tradeapi_disabled=False),raising=False)
    command=replace(_command('terminal-readonly'),account_alias='fx_primary',venue='mt5',entry_type='MARKET',command_hash='').sealed()
    result=adapter.submit(command,now_ms=1000000)
    assert result.status=='REJECTED' and not worker.t.mt5.sent


def test_successful_empty_reads_still_report_known_empty_not_unavailability(tmp_path):
    worker,client,adapter=rig(tmp_path)
    assert adapter.sync_account().verified
    for operation,field in [('positions','positions'),('orders','orders'),('history','deals')]:
        response=client.call(operation,{'alias':'fx_primary','from_s':0,'to_s':1},now_ms=1000000)
        assert 'error' not in response and response[field]==[]
