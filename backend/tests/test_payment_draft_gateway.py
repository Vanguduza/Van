"""Registered owner draft routes, real ledger readback and private failures."""
import asyncio
from contextlib import closing
from dataclasses import replace
import json
import threading

from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient
import pytest

from test_trading_api import client,_env
from test_payment_contracts import intent
from van_gateway.trading.payment_draft_api import FundingDraftError,build_funding_draft_router
from vati.core import Ledger,EventKind

PATH='/v1/trading/funding/drafts'


def body():
    value=intent()
    return {'intent':replace(value,quote=replace(value.quote,beneficiary=replace(value.quote.beneficiary,owner_ref='owner'))).body()}


def provision(app):
    with closing(Ledger(app.state.trading.ledger_path)):pass
    app.state.funding_drafts.clock=lambda:1500


def count(app):
    with closing(Ledger(app.state.trading.ledger_path)) as ledger:return ledger.count()


@pytest.mark.asyncio
async def test_registered_draft_write_cold_receipt_and_expired_replay_never_approve_or_trade(client):
    ac,app=client;provision(app);payload=body()
    saved=await ac.post(PATH,json=payload);assert saved.status_code==200,saved.text
    receipt=saved.json();assert receipt['state']=='DRAFT_STORED_NOT_APPROVED'
    assert receipt['execution_authority'] is receipt['provider_qualified'] is False
    assert saved.headers['cache-control']=='no-store' and saved.headers['x-content-type-options']=='nosniff'
    target=PATH+'/'+payload['intent']['request_id']
    read=await ac.get(target);assert read.status_code==200 and read.json()['intent']==payload['intent']
    assert read.json()['receipt']==receipt and read.json()['current_payment_eligibility']=='NOT_ADMITTED'
    assert (await ac.get(target+'/receipt')).json()==receipt
    app.state.funding_drafts.clock=lambda:2100
    assert (await ac.post(PATH,json=payload)).json()==receipt
    assert (await ac.get(target)).json()['claimed_quote_time_state']=='EXPIRED'
    assert count(app)==1
    with closing(Ledger(app.state.trading.ledger_path)) as ledger:
        assert all(ledger.count(kind)==0 for kind in [EventKind.ORDER_COMMAND,EventKind.FINANCIAL_MOVEMENT,EventKind.EXECUTION_RECEIPT])


@pytest.mark.asyncio
async def test_changed_request_and_foreign_owner_refuse_with_original_draft_intact(client):
    ac,app=client;provision(app);payload=body();first=await ac.post(PATH,json=payload);assert first.status_code==200
    payload['intent']['operation']='TRANSFER'
    conflict=await ac.post(PATH,json=payload);assert conflict.status_code==409
    assert conflict.json()['detail']['code']=='FUNDING_DRAFT_ORIGINAL_REQUEST_CONFLICT'
    payload=body();payload['intent']['quote']['beneficiary']['owner_ref']='owner:foreign'
    # A changed nested quote with its old hash is malformed before scope admission.
    malformed=await ac.post(PATH,json=payload);assert malformed.status_code==422
    value=intent();payload={'intent':replace(value,quote=replace(value.quote,
        beneficiary=replace(value.quote.beneficiary,owner_ref='owner:foreign'))).body()}
    foreign=await ac.post(PATH,json=payload);assert foreign.status_code==403
    assert count(app)==1 and (await ac.get(PATH+'/request:original/receipt')).json()==first.json()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['approval','instrument','token-field','extra-path','numeric-false','password','private-key','wallet-key'])
async def test_unsafe_or_unsupported_input_is_private_and_has_no_durable_effect(client,bad):
    ac,app=client;provision(app);payload=body();secret='fixture-token-value-never-retained'
    if bad=='approval':payload['intent']['state']='APPROVED'
    elif bad=='instrument':payload['intent']['quote']['reference']='4111 1111 1111 1111';secret='4111'
    elif bad=='token-field':payload['intent']['payment_token']=secret
    elif bad=='extra-path':payload['ledger_path']=secret
    elif bad in ('password','private-key','wallet-key'):
        value={'password':'password='+secret,'private-key':'-----BEGIN PRIVATE KEY----- '+secret+' -----END PRIVATE KEY-----',
            'wallet-key':'wallet_private_key='+secret}[bad]
        payload['intent']['quote']['reference']=value
    else:payload['intent']['execution_authority']=0
    refused=await ac.post(PATH,json=payload)
    assert refused.status_code==422 and secret not in refused.text
    assert refused.headers['cache-control']=='no-store' and refused.headers['x-content-type-options']=='nosniff'
    assert count(app)==0 and (await ac.get(PATH+'/request:original')).status_code==404


@pytest.mark.asyncio
async def test_missing_or_ephemeral_store_is_explicitly_unavailable_without_autoprovisioning(client,tmp_path):
    ac,app=client;path=tmp_path/'missing-native.sqlite';app.state.trading.ledger_path=str(path)
    refused=await ac.post(PATH,json=body());assert refused.status_code==503 and not path.exists()
    assert str(path) not in refused.text
    app.state.trading.ledger_path=':memory:'
    refused=await ac.post(PATH,json=body());assert refused.status_code==503


@pytest.mark.asyncio
async def test_memory_inventory_does_not_hide_or_claim_erasure_of_saved_native_drafts(client):
    ac,app=client;provision(app);saved=await ac.post(PATH,json=body());assert saved.status_code==200
    inventory=await ac.get('/v1/context/memory');assert inventory.status_code==200
    assert 'native_funding_drafts' in inventory.json()['kept_deliberately']
    assert 'not yet qualified' in inventory.json()['kept_deliberately']['native_funding_drafts']
    assert (await ac.get(PATH+'/request:original/receipt')).json()==saved.json() and count(app)==1


@pytest.mark.asyncio
async def test_no_unpaired_request_can_reach_draft_storage(client,monkeypatch):
    _,app=client
    monkeypatch.setattr(app.state.funding_drafts,'call',lambda *a,**kw:pytest.fail('unauthenticated request reached storage'))
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://fixture') as naked:
        assert (await naked.get(PATH+'/request:original')).status_code==401
        assert (await naked.post(PATH,json=body())).status_code==401


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['duplicate','constant','oversize','query'])
async def test_ambiguous_or_over_budget_owner_input_refuses_before_storage(client,bad):
    ac,app=client;provision(app);raw=json.dumps(body())
    if bad=='duplicate':raw=raw.replace('"owner_ref": "owner"','"owner_ref": "owner", "owner_ref": "owner"')
    elif bad=='constant':raw=raw.replace('"revision": 1','"revision": NaN')
    elif bad=='oversize':raw=' '* (512*1024)+raw
    target=PATH+'?owner_ref=owner:foreign' if bad=='query' else PATH
    refused=await ac.post(target,content=raw,headers={'Content-Type':'application/json'})
    assert refused.status_code==(413 if bad=='oversize' else 422)
    assert count(app)==0 and refused.headers['cache-control']=='no-store'


@pytest.mark.asyncio
async def test_request_cancellation_cannot_reopen_a_slot_while_original_draft_work_continues():
    active={'now':0,'calls':0};lock=threading.Lock();started=threading.Event();release=threading.Event()
    class Blocking:
        def call(self,*args,**kwargs):
            with lock:
                active['now']+=1;active['calls']+=1
                if active['now']==2:started.set()
            try:
                assert release.wait(5),'owned draft worker not released'
                raise FundingDraftError('FUNDING_DRAFT_STORE_UNAVAILABLE')
            finally:
                with lock:active['now']-=1
    app=FastAPI();app.include_router(build_funding_draft_router(Blocking()))
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://fixture') as ac:
        first=asyncio.create_task(ac.post(PATH,json=body()));second=asyncio.create_task(ac.post(PATH,json=body()))
        try:
            assert await asyncio.to_thread(started.wait,3)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):await first
            busy=await ac.post(PATH,json=body())
            assert busy.status_code==503 and busy.json()['detail']['code']=='FUNDING_DRAFT_BUSY'
            assert active['calls']==2
        finally:
            release.set();await asyncio.gather(first,second,return_exceptions=True)
        for _ in range(50):
            if active['now']==0:break
            await asyncio.sleep(.01)
        assert active['now']==0
