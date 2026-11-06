"""Registered owner HTTP catalog reads, source identity and bounded workers."""
import asyncio
from pathlib import Path
import sys,threading,time
import pytest

from test_trading_api import client,_env
from van_gateway.trading.instrument_catalog import InstrumentCatalogError,build_instrument_catalog_router
from van_gateway.trading.service import TradingService
from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'trading/tests'))
from test_native_symbol_catalog import SCOPE,captured,response
from vati.core import Ledger
from vati.market_data.catalog_store import NativeCatalogStore

PATH='/v1/trading/market/instruments'
QUERY={'environment':'DEMO','native_account_id':'12345'}


def seed(tmp_path,*,collide=False):
    path=tmp_path/'source # catalog.sqlite';now=int(time.time()*1000)-60000;rows=response()
    rows['archivedSymbol'][0]['utcLastUpdateTimestamp']=now-10000
    if collide:rows['symbol'][1]['symbolName']='EUR/USD'
    ledger=Ledger(path);receipt=NativeCatalogStore(ledger,clock=lambda:now+100).record('original',captured(response=rows,received_at_ms=now));ledger.close()
    return path,receipt,now


@pytest.mark.asyncio
async def test_registered_owner_discovery_retains_original_rows_and_frontend_native_identity(client,tmp_path):
    ac,app=client;path,receipt,now=seed(tmp_path);app.state.trading.native_catalog_ledger_path=str(path);original=path.read_bytes()
    result=await ac.get(PATH,params=QUERY)
    assert result.status_code==200,result.text
    body=result.json();assert body['receipt']==receipt and body['total_matches']==4
    assert [r['native_symbol_id'] for r in body['members']]==[1,2,3,4]
    from van_gateway.trading.chart_models import InstrumentRef
    ref=InstrumentRef.model_validate(body['members'][0]['instrument_ref'])
    assert ref.product_id=='1' and ref.account_id=='12345' and ref.contract_revision is None
    assert body['members'][2]['original']=={'symbolId':3} and body['members'][3]['listing_state']=='ARCHIVED'
    assert body['execution_authority'] is False and result.headers['cache-control']=='no-store'
    assert path.read_bytes()==original
    chosen=await ac.get(PATH,params=QUERY|{'alias':'EUR/USD','native_symbol_id':'1'})
    assert chosen.status_code==200 and chosen.json()['resolution_state']=='RESOLVED_NATIVE_IDENTITY'


@pytest.mark.asyncio
async def test_registered_catalog_route_requires_the_actual_paired_owner_device(client,tmp_path,monkeypatch):
    _,app=client
    monkeypatch.setattr(app.state.trading,'instrument_catalog',lambda **kw:(_ for _ in ()).throw(AssertionError('unauthorized read reached source')))
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as unpaired:
        result=await unpaired.get(PATH,params=QUERY)
        assert result.status_code in (401,403)


@pytest.mark.asyncio
async def test_alias_collision_is_explicit_even_when_page_contains_one_row(client,tmp_path):
    ac,app=client;path,_,_=seed(tmp_path,collide=True);app.state.trading.native_catalog_ledger_path=str(path)
    result=await ac.get(PATH,params=QUERY|{'alias':'EUR/USD','limit':'1'})
    assert result.status_code==200 and result.json()['resolution_state']=='AMBIGUOUS_NATIVE_ALIAS'
    assert result.json()['total_matches']==2 and len(result.json()['members'])==1
    other=await ac.get(PATH,params=QUERY|{'native_account_id':'999'})
    assert other.status_code==200 and other.json()['state']=='NO_CAPTURE' and other.json()['members']==[]


@pytest.mark.asyncio
async def test_pinned_pages_and_past_availability_remain_original_after_later_capture(client,tmp_path):
    ac,app=client;path,receipt,now=seed(tmp_path);app.state.trading.native_catalog_ledger_path=str(path)
    first=(await ac.get(PATH,params=QUERY|{'limit':'2'})).json()
    ledger=Ledger(path);rows=response();rows['archivedSymbol'][0]['utcLastUpdateTimestamp']=now-10000
    NativeCatalogStore(ledger,clock=lambda:now+300).record('second',captured(response=rows,received_at_ms=now+200));ledger.close()
    stale=await ac.get(PATH,params=QUERY|{'after':first['next_cursor']})
    assert stale.status_code==409 and stale.json()['detail']['code']=='NATIVE_CATALOG_SELECTION_CHANGED'
    second=await ac.get(PATH,params=QUERY|{'revision':'1','record_ref':receipt['record_ref'],'after':first['next_cursor'],'limit':'2'})
    assert second.status_code==200 and [r['native_symbol_id'] for r in second.json()['members']]==[3,4]
    past=await ac.get(PATH,params=QUERY|{'as_of_ms':str(now+99)})
    assert past.status_code==200 and past.json()['state']=='NO_CAPTURE'


@pytest.mark.asyncio
@pytest.mark.parametrize('extra',[{'path':'/etc/passwd'},{'provider':'MT5'},{'environment':'HISTORICAL'},
    {'native_account_id':'01'},{'native_symbol_id':'0'},{'limit':'257'},{'limit':'true'},
    {'alias':'\x00'},{'after':'x'},{'record_ref':'f'*63},{'revision':'1','as_of_ms':'1'},
    {'as_of_ms':'253402300799000'}])
async def test_invalid_scope_path_selector_and_capacity_never_reach_source(client,extra,monkeypatch):
    ac,app=client
    monkeypatch.setattr(app.state.trading,'instrument_catalog',lambda **kw:(_ for _ in ()).throw(AssertionError('invalid request reached source')))
    result=await ac.get(PATH,params=QUERY|extra)
    assert result.status_code==422,result.text
    assert result.headers['cache-control']=='no-store' and set(result.json()['detail'])=={'code'}


@pytest.mark.asyncio
async def test_duplicate_selectors_unconfigured_missing_corrupt_and_budget_states_are_explicit(client,tmp_path):
    ac,app=client
    duplicate=await ac.get(PATH,params=[*QUERY.items(),('native_account_id','999')]);assert duplicate.status_code==422
    unconfigured=await ac.get(PATH,params=QUERY);assert unconfigured.status_code==503 and unconfigured.json()['detail']['code']=='NATIVE_CATALOG_SOURCE_UNCONFIGURED'
    missing=tmp_path/'missing.sqlite';app.state.trading.native_catalog_ledger_path=str(missing)
    assert (await ac.get(PATH,params=QUERY)).status_code==503 and not missing.exists()
    path,_,_=seed(tmp_path);app.state.trading.native_catalog_ledger_path=str(path);app.state.trading.native_history_max_bytes=1
    assert (await ac.get(PATH,params=QUERY)).status_code==503
    app.state.trading.native_history_max_bytes=64*1024**2
    import sqlite3
    with sqlite3.connect(path) as db:db.execute("UPDATE events SET payload_json='{}'")
    corrupt=await ac.get(PATH,params=QUERY);assert corrupt.status_code==503 and str(tmp_path) not in corrupt.text


@pytest.mark.asyncio
async def test_disconnected_requests_retain_capacity_until_their_owned_reader_finishes():
    app=FastAPI();started=threading.Event();release=threading.Event();lock=threading.Lock();count={'n':0}
    def blocked(**query):
        with lock:
            count['n']+=1
            if count['n']==2:started.set()
        assert release.wait(5)
        raise InstrumentCatalogError('NATIVE_CATALOG_SOURCE_UNAVAILABLE')
    service=TradingService(':memory:');service.instrument_catalog=blocked;app.include_router(build_instrument_catalog_router(service))
    tasks=[]
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://fixture') as ac:
        try:
            tasks=[asyncio.create_task(ac.get(PATH,params=QUERY)) for _ in range(2)]
            assert await asyncio.to_thread(started.wait,3)
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            busy=await ac.get(PATH,params=QUERY)
            assert busy.status_code==503 and busy.json()['detail']['code']=='NATIVE_CATALOG_READ_BUSY' and count['n']==2
        finally:
            release.set()
            await asyncio.gather(*tasks,return_exceptions=True)
            # Drain the original shielded work; do not leave executor children
            # or a late exception beyond the owning test's event loop.
            owned=[t for t in asyncio.all_tasks() if t is not asyncio.current_task() and t.get_coro().__qualname__=='to_thread']
            await asyncio.gather(*owned,return_exceptions=True)
