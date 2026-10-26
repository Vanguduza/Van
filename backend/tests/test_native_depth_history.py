"""Registered owner HTTP history, original native scope and bounded read ownership."""
import asyncio
import json
from pathlib import Path
import threading
import time

import pytest
from fastapi import FastAPI
from httpx import AsyncClient,ASGITransport

from test_trading_api import client,_env
from van_gateway.config import get_settings
from van_gateway.trading.service import TradingService
from van_gateway.trading.native_depth_history import DepthHistoryError,build_depth_history_router

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'trading/tests'))
from test_native_depth_archive import sample
from test_native_market_archive import contract
from vati.market_data.native_depth import NativeDepthArchive,NativeDepthCollector

PATH='/v1/trading/market/depth-history'
QUERY={'environment':'DEMO','native_account_id':'123','native_symbol_id':'12'}


def seed(tmp_path,*,second=False):
    root=tmp_path/'native-sources';c=contract();book=NativeDepthArchive(root,clock=lambda:250000)
    first=book.record('original',c,sample(c))
    if second:NativeDepthArchive(root,clock=lambda:400000).record('second',c,sample(c,now=300000))
    return root,c,first


def files(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.asyncio
async def test_registered_owner_route_reads_original_scope_and_preserves_capture_policy(client,tmp_path,monkeypatch):
    ac,app=client;root,c,first=seed(tmp_path,second=True);app.state.trading.native_source_root=str(root)
    before=files(root)
    def forbidden(*args,**kwargs):raise AssertionError('historical HTTP read attempted broker collection')
    monkeypatch.setattr(NativeDepthCollector,'collect',forbidden)
    result=await ac.get(PATH,params={**QUERY,'revision':'1'})
    assert result.status_code==200,result.text
    body=result.json();assert body['snapshot']['receipt']==first and body['scope']==c.native_scope
    assert body['snapshot']['observation']['depth']['bids'][0]['native_quote_id']=='9007199254740993'
    assert body['snapshot']['observation']['limit']==100
    assert body['provider_qualified'] is body['normalized_prices_available'] is False
    assert body['current_freshness']=='NOT_EVALUATED_HISTORICAL_RECORD' and body['authority_effect']=='NONE'
    assert result.headers['cache-control']=='no-store' and result.headers['x-content-type-options']=='nosniff'
    assert files(root)==before
    earlier=await ac.get(PATH,params={**QUERY,'as_of_ms':'249999'})
    assert earlier.status_code==200 and earlier.json()['state']=='NO_CAPTURE' and earlier.json()['snapshot'] is None
    at=await ac.get(PATH,params={**QUERY,'as_of_ms':'250000'})
    assert at.json()['snapshot']['receipt']==first


@pytest.mark.asyncio
@pytest.mark.parametrize('changed',[{'environment':'LIVE'},{'native_account_id':'124'},{'native_symbol_id':'13'}])
async def test_another_native_scope_cannot_reuse_a_saved_ladder(client,tmp_path,changed):
    ac,app=client;root,c,first=seed(tmp_path);app.state.trading.native_source_root=str(root)
    result=await ac.get(PATH,params={**QUERY,**changed})
    assert result.status_code==200 and result.json()['state']=='NO_CAPTURE' and result.json()['snapshot'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('extra',[{'native_account_id':'1.0'},{'native_account_id':'01'},{'native_account_id':'true'},
    {'native_account_id':'9223372036854775808'},{'native_symbol_id':'-1'},{'environment':'PAPER'},
    {'revision':'0'},{'revision':'10001'},{'revision':'1','as_of_ms':'200000'},
    {'as_of_ms':'253402300799000'},{'as_of_ms':'-1'},{'path':'/untrusted/request/root'},
    {'limit':'1'},{'max_history_bytes':'999999999'}])
async def test_invalid_or_ambiguous_query_cannot_change_scope_root_or_original_policy(client,extra):
    ac,app=client
    result=await ac.get(PATH,params={**QUERY,**extra})
    assert result.status_code==422,result.text
    assert result.headers['cache-control']=='no-store' and set(result.json()['detail'])=={'code'}


@pytest.mark.asyncio
async def test_duplicate_native_identity_query_is_refused(client):
    ac,_=client;result=await ac.get(PATH,params=[*QUERY.items(),('native_account_id','124')])
    assert result.status_code==422 and result.json()['detail']['code']=='NATIVE_DEPTH_QUERY_INVALID'


@pytest.mark.asyncio
async def test_unconfigured_or_missing_source_is_unavailable_without_path_details(client,tmp_path):
    ac,app=client
    result=await ac.get(PATH,params=QUERY)
    assert result.status_code==503 and result.json()['detail']['code']=='NATIVE_DEPTH_SOURCE_UNCONFIGURED'
    app.state.trading.native_source_root=str(tmp_path/'not-provisioned')
    result=await ac.get(PATH,params=QUERY)
    assert result.status_code==503 and str(tmp_path) not in result.text and result.headers['cache-control']=='no-store'


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['corrupt','budget'])
async def test_storage_integrity_and_read_capacity_refuse_without_changing_history(client,tmp_path,bad):
    ac,app=client;root,c,first=seed(tmp_path);app.state.trading.native_source_root=str(root)
    if bad=='corrupt':
        record=next(root.rglob('00000000000000000001-*.json'));record.write_bytes(record.read_bytes()+b' ')
    else:app.state.trading.native_history_max_bytes=1
    before=files(root);result=await ac.get(PATH,params=QUERY)
    assert result.status_code==503 and result.json()['detail']['code']=='NATIVE_DEPTH_HISTORY_UNAVAILABLE'
    assert str(root) not in result.text and files(root)==before and result.headers['cache-control']=='no-store'


@pytest.mark.asyncio
async def test_historical_route_requires_existing_ingress_and_paired_owner_authority(client,tmp_path):
    ac,app=client;root,c,first=seed(tmp_path);app.state.trading.native_source_root=str(root)
    assert (await ac.get(PATH,params=QUERY)).status_code==200
    ingress=ac.headers.pop('X-Van-Ingress-Token')
    assert (await ac.get(PATH,params=QUERY)).status_code==401
    ac.headers['X-Van-Ingress-Token']=ingress;ac.headers.pop('X-Van-Device-Token')
    assert (await ac.get(PATH,params=QUERY)).status_code==401


@pytest.mark.asyncio
async def test_missing_derived_index_does_not_trigger_http_repair_or_broker_refresh(client,tmp_path):
    ac,app=client;root,c,first=seed(tmp_path);app.state.trading.native_source_root=str(root)
    head=next(root.rglob('head.json'));head.unlink();before=files(root)
    result=await ac.get(PATH,params=QUERY)
    assert result.status_code==200 and result.json()['snapshot']['receipt']['record_ref']==first['record_ref']
    assert result.json()['snapshot']['receipt']['index_state']=='MISSING'
    assert not head.exists() and files(root)==before


@pytest.mark.parametrize('values',[
    {'environment':['DEMO']},{'native_account_id':True},{'native_symbol_id':1.0},
    {'revision':True},{'revision':1,'as_of_ms':1},{'as_of_ms':-1}])
def test_direct_service_validates_scope_and_selectors_before_source_access(values):
    service=TradingService(ledger_path=':memory:')
    args={'environment':'DEMO','native_account_id':123,'native_symbol_id':12,**values}
    with pytest.raises(DepthHistoryError) as error:service.native_depth_history(**args)
    assert error.value.status==422


@pytest.mark.asyncio
async def test_application_settings_provision_the_root_without_owner_request_paths(tmp_path,monkeypatch):
    from van_gateway.app import create_app
    root,c,first=seed(tmp_path)
    monkeypatch.setenv('VAN_VATI_NATIVE_SOURCE_ROOT',str(root));monkeypatch.setenv('VAN_VATI_NATIVE_HISTORY_MAX_BYTES','65536')
    get_settings.cache_clear()
    try:
        app=create_app()
        assert app.state.trading.native_source_root==str(root) and app.state.trading.native_history_max_bytes==65536
        body=app.state.trading.native_depth_history(environment='DEMO',native_account_id=123,native_symbol_id=12)
        assert body['snapshot']['receipt']==first
    finally:get_settings.cache_clear()


@pytest.mark.asyncio
async def test_cancelled_call_keeps_its_original_worker_slot_until_the_read_finishes():
    started=threading.Event();release=threading.Event();lock=threading.Lock();state={'active':0,'count':0}
    class Blocking:
        def native_depth_history(self,**request):
            with lock:
                state['active']+=1;state['count']+=1
                if state['active']==2:started.set()
            try:
                assert release.wait(5),'owned read control was not released'
                raise DepthHistoryError('NATIVE_DEPTH_SOURCE_UNCONFIGURED')
            finally:
                with lock:state['active']-=1
    app=FastAPI();app.include_router(build_depth_history_router(Blocking()))
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://fixture') as ac:
        first=asyncio.create_task(ac.get(PATH,params=QUERY));second=asyncio.create_task(ac.get(PATH,params=QUERY))
        try:
            assert await asyncio.to_thread(started.wait,3)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):await first
            busy=await ac.get(PATH,params=QUERY)
            assert busy.status_code==503 and busy.json()['detail']['code']=='NATIVE_DEPTH_HISTORY_BUSY'
            assert state['count']==2 and busy.headers['cache-control']=='no-store'
        finally:
            release.set()
            await asyncio.gather(first,second,return_exceptions=True)
            for attempt in range(100):
                if state['active']==0:break
                await asyncio.sleep(.01)
            assert state['active']==0
        assert (await ac.get(PATH,params=QUERY)).json()['detail']['code']=='NATIVE_DEPTH_SOURCE_UNCONFIGURED'
