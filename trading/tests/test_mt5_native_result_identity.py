"""Actual signed worker/adapter contract with controlled native SDK effects."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as NS
import pytest
from test_mt5_observation_integrity import rig
from test_account_lifecycle import _command
from vati.risk.contracts import Direction


def command(name='native-original'):
    return replace(_command(name),account_alias='fx_primary',venue='mt5',entry_type='MARKET',command_hash='').sealed()


def distinct_native(worker,monkeypatch,*,stop=1.09,rows='known'):
    native=worker.t.mt5
    position=NS(ticket=42,identifier=900,symbol='EURUSD',type=0,volume=.1,price_open=1.10008,sl=stop,tp=0,comment='vati:native-original',magic=1,profit=0)
    def send(request):
        native.sent.append(request);native.pos[42]=position
        return NS(retcode=10009,order=11,deal=77,volume=.1,price=1.10008,comment='native original')
    monkeypatch.setattr(native,'order_send',send)
    def history(*args,**kwargs):
        assert kwargs=={'ticket':11},'native history query is scoped by order, then exact deal matched'
        return None if rows=='unavailable' else [] if rows=='empty' else [NS(ticket=77,order=11,position_id=900,symbol='EURUSD')]
    monkeypatch.setattr(native,'history_deals_get',history)
    return position


def test_worker_maps_the_exact_deal_identifier_to_the_actual_position_ticket(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path);distinct_native(worker,monkeypatch)
    result=adapter.submit(command(),now_ms=1000000)
    assert result.status=='FILLED' and result.broker_order_id=='11' and result.broker_position_id=='42'
    assert result.protective_stop_confirmed is True
    assert len(worker.t.mt5.sent)==1


@pytest.mark.parametrize('change',['unavailable','empty','different-symbol','positions-unavailable'])
def test_unresolved_native_position_never_falls_back_to_order_id(tmp_path,monkeypatch,change):
    worker,client,adapter=rig(tmp_path)
    position=distinct_native(worker,monkeypatch,rows=change)
    if change=='different-symbol':position.symbol='USDJPY'
    if change=='positions-unavailable':monkeypatch.setattr(worker.t.mt5,'positions_get',lambda *a,**k:None)
    result=adapter.submit(command(),now_ms=1000000)
    assert result.status=='FILLED' and result.filled_qty==D('.1')
    assert result.broker_position_id=='' and result.protective_stop_confirmed is False


def test_worker_rejects_a_weaker_native_stop_as_confirmation(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path);distinct_native(worker,monkeypatch,stop=1.08)
    result=adapter.submit(command(),now_ms=1000000)
    assert result.broker_position_id=='42' and result.protective_stop_confirmed is False


@pytest.mark.parametrize('operation',['entry','modify','close'])
def test_native_timeout_retcode_after_effect_is_unknown(tmp_path,monkeypatch,operation):
    worker,client,adapter=rig(tmp_path);native=worker.t.mt5
    if operation!='entry':opened=adapter.submit(command(),now_ms=1000000)
    send=native.order_send
    def lost_ack(request):
        result=send(request)
        return NS(**{**result.__dict__,'retcode':10012})
    monkeypatch.setattr(native,'order_send',lost_ack)
    if operation=='entry':
        result=adapter.submit(command(),now_ms=1000000);assert native.pos
    elif operation=='modify':
        result=adapter.modify_stop(opened.broker_position_id,D('1.091'),now_ms=1000001)
        assert str(native.pos[int(opened.broker_position_id)].sl)=='1.091'
    else:
        result=adapter.close(opened.broker_position_id,None,now_ms=1000001,reason='protective')
        assert not native.pos
    assert result.status=='UNKNOWN' and result.protective_stop_confirmed is False


def test_worker_does_not_confirm_a_stop_change_without_observed_effect(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path);opened=adapter.submit(command(),now_ms=1000000)
    monkeypatch.setattr(worker.t.mt5,'order_send',lambda request:NS(retcode=10009,comment='ack without visible effect'))
    result=adapter.modify_stop(opened.broker_position_id,D('1.091'),now_ms=1000001)
    assert result.status=='UNKNOWN' and result.protective_stop_confirmed is False


def test_worker_cannot_remove_a_sell_stop_with_zero(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path)
    sell=replace(command(),direction=Direction.SHORT,protective_stop=D('1.12'),command_hash='').sealed()
    opened=adapter.submit(sell,now_ms=1000000);sent=len(worker.t.mt5.sent)
    result=adapter.modify_stop(opened.broker_position_id,D('0'),now_ms=1000001)
    assert result.status=='REJECTED' and len(worker.t.mt5.sent)==sent


def test_native_pending_order_requires_observed_stop(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path)
    monkeypatch.setattr(worker.t.mt5,'order_send',lambda request:NS(retcode=10008,order=11,deal=0,volume=0,price=0,comment='placed'))
    monkeypatch.setattr(worker.t.mt5,'orders_get',lambda *args,**kwargs:None)
    result=adapter.submit(replace(command(),entry_type='LIMIT',command_hash='').sealed(),now_ms=1000000)
    assert result.status=='ACCEPTED' and result.protective_stop_confirmed is False


@pytest.mark.parametrize('exposure',['position','pending','unknown'])
def test_worker_netting_entry_refuses_existing_or_unknown_exposure(tmp_path,monkeypatch,exposure):
    worker,client,adapter=rig(tmp_path);native=worker.t.mt5
    info=native.account_info
    monkeypatch.setattr(native,'account_info',lambda:NS(**{**info().__dict__,'margin_mode':0}))
    if exposure=='position':
        native.pos[42]=NS(ticket=42,identifier=42,symbol='EURUSD',sl=1.09,type=0)
    elif exposure=='pending':monkeypatch.setattr(native,'orders_get',lambda *a,**k:[NS(symbol='EURUSD')])
    else:monkeypatch.setattr(native,'positions_get',lambda *a,**k:None)
    result=adapter.submit(command(),now_ms=1000000)
    assert result.status=='REJECTED' and not native.sent


def test_empty_netting_native_account_can_still_open_its_first_order(tmp_path,monkeypatch):
    worker,client,adapter=rig(tmp_path);native=worker.t.mt5;info=native.account_info
    monkeypatch.setattr(native,'account_info',lambda:NS(**{**info().__dict__,'margin_mode':0}))
    result=adapter.submit(command(),now_ms=1000000)
    assert result.status=='FILLED' and result.protective_stop_confirmed and len(native.sent)==1


@pytest.mark.parametrize(('field','value'),[('volume','-.1'),('sl','NaN'),('sl','0'),
    ('type','INVALID'),('order_type','STOP'),('deviation','-.0001')])
def test_worker_checks_native_entry_parameters_before_any_sdk_effect(tmp_path,field,value):
    worker,client,adapter=rig(tmp_path)
    body={'alias':'fx_primary','symbol':'EURUSD','type':'BUY','volume':'.1','price':'1.1',
          'sl':'1.09','magic':1,'comment':'source-fixture','order_type':'MARKET','deviation':'.0002'}
    body[field]=value
    result=client.call('order_send',body,now_ms=1000000)
    assert result.get('status')=='REJECTED' and not worker.t.mt5.sent
