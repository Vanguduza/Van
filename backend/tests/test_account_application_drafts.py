"""Actual paired HTTP/SQLite LAC-135 previews; no provider/native execution."""
import asyncio
import json
import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport,AsyncClient

from test_device_proof_enforcement import _settings,_paired,_base_headers,_bind,_proof_headers
from van_gateway.app import create_app
from van_gateway.artifacts.service import ArtifactService
from van_gateway.context.forget import OwnerMemory
from van_gateway.storage.db import Store
from van_gateway.trading.account_application_drafts import (AccountApplicationDrafts,DraftError,DraftInput,PREFIX,FAMILY,SOURCE_TYPE,TTL_MS,_key)

PATH='/v1/trading/accounts/application-drafts'


def body(**changes):
    return {'operation_id':uuid.uuid4().hex,'family_id':uuid.uuid4().hex,'expected_revision':0,
        'variant':'OPEN_NEW_LIVE','broker_kind':'CTRADER',**changes}


@pytest_asyncio.fixture
async def client(_settings):
    app=create_app();await app.state.store.migrate()
    device=await _paired(app)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as ac:
        yield ac,app,device
    await app.state.account_application_drafts.drain()


async def publish(client,payload=None):
    ac,app,device=client;payload=payload or body()
    result=await ac.post(PATH,json=payload,headers=_base_headers(device))
    assert result.status_code==200,result.text
    return payload,result.json()


@pytest.mark.asyncio
async def test_real_paired_http_atomic_preview_cold_readback_and_no_effect(client):
    ac,app,device=client;payload,receipt=await publish(client)
    assert receipt['state']=='DRAFT_STORED_NOT_SUBMITTED'
    assert receipt['execution_authority'] is receipt['provider_qualified'] is False
    read=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))
    assert read.status_code==200,read.text
    data=read.json();assert data['receipt']==receipt and data['body']['request']==payload
    assert data['body']['context']['device_id']==device.device.device_id
    assert data['body']['context']['profile_context']['account_profile_ref'] is None
    assert data['body']['provider_selection']['state']=='UNRESOLVED'
    assert data['effect_confirmation_eligible'] is False and read.headers['cache-control']=='no-store'
    assert len(await app.state.store.fetchall('SELECT * FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==1
    assert not await app.state.store.fetchall('SELECT * FROM mission_activities')
    assert not await app.state.store.fetchall("SELECT * FROM runtime_meta WHERE key GLOB 'owner_approval:*'")
    original=app.state.account_application_drafts
    restarted=AccountApplicationDrafts(Store(app.state.store.path),ArtifactService(Store(app.state.store.path)),original.authorize)
    caller={'owner_id':'owner','device_id':device.device.device_id,'access_token_hash':__import__('hashlib').sha256(device.access_token.encode()).hexdigest(),'proved':False}
    cold=await restarted.inspect(payload['operation_id'],caller)
    assert cold['receipt']==receipt and cold['body']==data['body']


@pytest.mark.asyncio
async def test_same_id_concurrent_replay_and_new_generation_keeps_history(client):
    ac,app,device=client;payload=body();headers=_base_headers(device)
    results=await asyncio.gather(*[ac.post(PATH,json=payload,headers=headers) for _ in range(2)])
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    original=results[0].json();assert original==results[1].json()
    changed={**payload,'broker_kind':'DERIV'}
    refusal=await ac.post(PATH,json=changed,headers=headers);assert refusal.status_code==409
    next_body=body(family_id=payload['family_id'],expected_revision=1,broker_kind='DERIV')
    newer=await ac.post(PATH,json=next_body,headers=headers);assert newer.status_code==200,newer.text
    old=await ac.get(PATH+'/'+payload['operation_id'],headers=headers)
    assert old.json()['selection_current'] is False and old.json()['receipt']==original
    selection=await ac.get(PATH+'/selections/'+payload['family_id'],headers=headers)
    assert selection.json()['revision']==2 and selection.json()['draft_id']==newer.json()['draft_id']
    assert (await ac.post(PATH,json=payload,headers=headers)).json()==original
    assert len(await app.state.store.fetchall('SELECT * FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==2


@pytest.mark.asyncio
async def test_expiry_is_not_retention_or_replay_renewal_and_delete_is_explicit(client):
    ac,app,device=client;service=app.state.account_application_drafts
    service.clock=lambda:1000;payload,receipt=await publish(client)
    service.clock=lambda:1000+TTL_MS
    assert (await ac.post(PATH,json=payload,headers=_base_headers(device))).json()==receipt
    read=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device));assert read.json()['freshness']=='EXPIRED'
    memory=OwnerMemory(app.state.store);inventory=await memory.inventory()
    assert 'account_application_drafts' in inventory['kept_deliberately']
    await memory.forget_all()
    assert (await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))).json()['receipt']==receipt
    erased=await ac.request('DELETE',PATH+'/'+payload['operation_id'],json={'expected_digest':receipt['body_digest']},headers=_base_headers(device))
    assert erased.status_code==200,erased.text
    assert erased.json()['canonical_bodies_removed']==erased.json()['projections_removed']==1
    assert not await app.state.store.fetchall('SELECT * FROM owner_artifacts WHERE artifact_id=?',(receipt['artifact_id'],))
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(_key(PREFIX,'owner',payload['operation_id']),))
    assert 'body' not in json.loads(row['value']) and payload['family_id'] not in row['value']
    assert (await ac.post(PATH,json=payload,headers=_base_headers(device))).status_code==410
    read=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device));assert read.json()['state']=='ERASED'


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('url','https://not-admitted.invalid/kyc'),('password','sensitive-password'),
    ('date_of_birth','1980-01-01'),('tax_id','sensitive-tax'),('documents',{'private':'data'}),
    ('bank_account','sensitive-bank'),('owner_id','foreign-owner'),('profile_ref','foreign-profile'),
    ('expires_at_ms',9999999999999),('provider_descriptor_ref','unadmitted')])
async def test_unknown_sensitive_context_or_deadline_fields_refuse_before_retention(client,field,value):
    ac,app,device=client;payload=body();payload[field]=value
    result=await ac.post(PATH,json=payload,headers=_base_headers(device))
    assert result.status_code==422 and str(value) not in result.text
    assert not await app.state.store.fetchall('SELECT key FROM runtime_meta WHERE key GLOB ?',(PREFIX+'*',))
    assert not await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,))


@pytest.mark.asyncio
async def test_duplicate_oversized_invalid_variant_and_raw_credential_fail_private(client):
    ac,app,device=client;headers={**_base_headers(device),'Content-Type':'application/json'}
    payload=body();raw=json.dumps(payload)[:-1]+',"broker_kind":"DERIV"}'
    for raw,status in [(raw,422),('{"password":"'+'private-secret-'*300+'"}',413),('[]',422),('NaN',422)]:
        result=await ac.post(PATH,content=raw,headers=headers)
        assert result.status_code==status and 'private-secret' not in result.text
    result=await ac.post(PATH,json={**payload,'variant':'SUBMIT_APPLICATION'},headers=headers)
    assert result.status_code==422
    assert not await app.state.store.fetchall('SELECT key FROM runtime_meta WHERE key GLOB ?',(PREFIX+'*',))


@pytest.mark.asyncio
async def test_bound_exact_proof_legacy_and_strict_absent_policy(client):
    from van_gateway.config import get_settings
    ac,app,device=client
    # Existing legitimate paired legacy policy works without an invented binding.
    await publish(client)
    get_settings().require_device_binding=True
    refused=await ac.post(PATH,json=body(),headers=_base_headers(device))
    assert refused.status_code==403
    get_settings().require_device_binding=False
    key=await _bind(app,device.device.device_id);payload=body();raw=json.dumps(payload).encode()
    refused=await ac.post(PATH,content=raw,headers={**_base_headers(device),'Content-Type':'application/json'})
    assert refused.status_code==401
    headers={**_base_headers(device),'Content-Type':'application/json',**_proof_headers(key,method='POST',path=PATH,device_id=device.device.device_id,body=raw)}
    accepted=await ac.post(PATH,content=raw,headers=headers);assert accepted.status_code==200,accepted.text
    assert (await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))).status_code==200


@pytest.mark.asyncio
async def test_current_owner_history_is_distinct_from_original_caller_mutation(client):
    ac,app,first=client;payload,receipt=await publish(client)
    second=await _paired(app,label='replacement-owner')
    read=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(second))
    assert read.status_code==200 and read.json()['receipt']==receipt
    replay=await ac.post(PATH,json=payload,headers=_base_headers(second))
    assert replay.status_code==403
    await app.state.store.execute('UPDATE devices SET revoked_at_unix=1 WHERE device_id=?',(second.device.device_id,))
    assert (await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(second))).status_code==401
    assert (await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(first))).status_code==200


@asynccontextmanager
async def held_writer(service,monkeypatch):
    original=service.store.connection;waiting=asyncio.Event()
    class Proxy:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        async def execute(self,sql,*args):
            if sql=='BEGIN IMMEDIATE':waiting.set()
            return await self.db.execute(sql,*args)
    @asynccontextmanager
    async def intercepted():
        async with original() as db:yield Proxy(db)
    async with original() as db:
        await db.execute('BEGIN IMMEDIATE')
        monkeypatch.setattr(service.store,'connection',intercepted)
        yield db,waiting


@pytest.mark.asyncio
async def test_waiting_writer_expiry_is_original_durable_refusal_not_renewal(client,monkeypatch):
    ac,app,device=client;service=app.state.account_application_drafts;service.clock=lambda:1000;payload=body()
    async with held_writer(service,monkeypatch) as (db,waiting):
        task=asyncio.create_task(ac.post(PATH,json=payload,headers=_base_headers(device)))
        await asyncio.wait_for(waiting.wait(),5);service.clock=lambda:1000+TTL_MS
        await db.commit();result=await task
    assert result.status_code==409,result.text
    original=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))
    assert original.json()['state']=='REFUSED' and original.json()['expires_at_ms']==1000+TTL_MS
    assert (await ac.post(PATH,json=payload,headers=_base_headers(device))).status_code==409
    assert not await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,))
    await publish(client,body(family_id=payload['family_id']))


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['token','revocation'])
async def test_live_caller_change_while_waiting_refuses_in_actual_writer(client,monkeypatch,change):
    ac,app,device=client;service=app.state.account_application_drafts
    async with held_writer(service,monkeypatch) as (db,waiting):
        task=asyncio.create_task(ac.post(PATH,json=body(),headers=_base_headers(device)))
        await asyncio.wait_for(waiting.wait(),5)
        sql='UPDATE devices SET '+('access_token_hash=?' if change=='token' else 'revoked_at_unix=?')+' WHERE device_id=?'
        await db.execute(sql,('changed' if change=='token' else 1,device.device.device_id));await db.commit()
        result=await task
    assert result.status_code==403,result.text
    assert not await app.state.store.fetchall('SELECT key FROM runtime_meta WHERE key GLOB ?',(PREFIX+'*',))
    assert not await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,))


@pytest.mark.asyncio
@pytest.mark.parametrize('after_commit',[False,True])
async def test_real_commit_ack_loss_rereads_original_or_unknown_without_partial_projection(client,monkeypatch,after_commit):
    ac,app,device=client;store=app.state.store;original=store.connection;first=True
    class Proxy:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        async def commit(self):
            nonlocal first
            if first:
                first=False
                if after_commit:await self.db.commit()
                raise OSError('SOURCE commit acknowledgement loss')
            return await self.db.commit()
    @asynccontextmanager
    async def intercepted():
        async with original() as db:yield Proxy(db)
    monkeypatch.setattr(store,'connection',intercepted);payload=body()
    result=await ac.post(PATH,json=payload,headers=_base_headers(device))
    assert result.status_code==(200 if after_commit else 503),result.text
    artifacts=await store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,))
    assert len(artifacts)==(1 if after_commit else 0)
    repeat=await ac.post(PATH,json=payload,headers=_base_headers(device));assert repeat.status_code==200,repeat.text
    if after_commit:assert repeat.json()==result.json()
    assert len(await store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==1


@pytest.mark.asyncio
async def test_http_cancellation_after_insert_keeps_exact_original_for_restart(client,monkeypatch):
    ac,app,device=client;service=app.state.account_application_drafts;original=service.artifacts.ensure_projection
    saved=asyncio.Event();release=asyncio.Event()
    async def paused(**kwargs):
        result=await original(**kwargs);saved.set();await release.wait();return result
    monkeypatch.setattr(service.artifacts,'ensure_projection',paused);payload=body()
    request=asyncio.create_task(ac.post(PATH,json=payload,headers=_base_headers(device)))
    await asyncio.wait_for(saved.wait(),5);request.cancel()
    with pytest.raises(asyncio.CancelledError):await request
    release.set();await service.drain()
    read=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))
    assert read.status_code==200 and read.json()['body']['request']==payload
    receipt=read.json()['receipt']
    assert (await ac.post(PATH,json=payload,headers=_base_headers(device))).json()==receipt
    assert len(await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==1


@pytest.mark.asyncio
@pytest.mark.parametrize('damage',['body-shape','digest','profile','artifact','family','tombstone'])
async def test_corrupt_original_holds_unknown_and_never_recreates(client,damage):
    ac,app,device=client;payload,receipt=await publish(client);store=app.state.store;key=_key(PREFIX,'owner',payload['operation_id'])
    row=await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,));record=json.loads(row['value'])
    if damage=='body-shape':record['body']=[]
    elif damage=='digest':record['body_digest']='0'*64
    elif damage=='profile':record['body']['context']['profile_context']=[]
    elif damage=='artifact':await store.execute('UPDATE owner_artifacts SET canonical_source_digest=? WHERE artifact_id=?',('0'*64,receipt['artifact_id']))
    elif damage=='family':await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps({'revision':99,'draft_id':receipt['draft_id']}),_key(FAMILY,'owner',payload['family_id'])))
    else:record={'state':'ERASED','body_digest':receipt['body_digest'],'receipt':{},'body':record['body']}
    if damage not in ('artifact','family'):await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps(record),key))
    read=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))
    replay=await ac.post(PATH,json=payload,headers=_base_headers(device))
    if damage=='family':
        assert read.status_code==200 and read.json()['receipt']==receipt
        assert read.json()['current_selection_state']=='UNKNOWN' and read.json()['selection_current'] is None
        assert replay.status_code==200 and replay.json()==receipt
        changed=await ac.post(PATH,json=body(family_id=payload['family_id'],expected_revision=99),headers=_base_headers(device))
        assert changed.status_code==503 and read.json()['effect_confirmation_eligible'] is False
    else:
        assert read.status_code==503,read.text
        assert replay.status_code==503,replay.text
    assert len(await store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==1


@pytest.mark.asyncio
async def test_stale_selection_refuses_and_private_owner_context_is_server_derived(client):
    ac,app,device=client;payload,receipt=await publish(client)
    stale=await ac.post(PATH,json=body(family_id=payload['family_id']),headers=_base_headers(device))
    assert stale.status_code==409
    before=(await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))).json()
    from van_gateway.config import get_settings
    get_settings().owner_device_package='changed-config-package'
    again=(await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))).json()
    assert again['body']==before['body'] and again['receipt']==receipt
    changed=await ac.post(PATH,json=body(family_id=payload['family_id'],expected_revision=1),headers=_base_headers(device))
    assert changed.status_code==200
    newer=(await ac.get(PATH+'/'+changed.json()['operation_id'],headers=_base_headers(device))).json()
    assert newer['body']['context']['profile_context']['configuration_digest']!=before['body']['context']['profile_context']['configuration_digest']
    assert newer['body']['context']['profile_context']['account_profile_ref'] is None
    assert newer['effect_confirmation_eligible'] is False


@pytest.mark.asyncio
async def test_retired_binding_wins_actual_queued_writer_after_valid_proof(client,monkeypatch):
    ac,app,device=client;key=await _bind(app,device.device.device_id)
    raw=json.dumps(body()).encode();headers={**_base_headers(device),'Content-Type':'application/json',
        **_proof_headers(key,method='POST',path=PATH,device_id=device.device.device_id,body=raw)}
    service=app.state.account_application_drafts
    # Pause only after the normal HTTP proof nonce is durably consumed. Holding
    # SQLite earlier would block proof itself rather than exercise this writer.
    service.store=Store(app.state.store.path);original=service.store.connection
    entered=asyncio.Event();release=asyncio.Event()
    @asynccontextmanager
    async def before_writer():
        entered.set();await release.wait()
        async with original() as db:yield db
    monkeypatch.setattr(service.store,'connection',before_writer)
    task=asyncio.create_task(ac.post(PATH,content=raw,headers=headers))
    await asyncio.wait_for(entered.wait(),5)
    await app.state.store.execute("UPDATE owner_device_bindings SET status='REVOKED' WHERE device_id=?",(device.device.device_id,))
    release.set();result=await task
    assert result.status_code==403,result.text
    assert not await app.state.store.fetchall('SELECT key FROM runtime_meta WHERE key GLOB ?',(PREFIX+'*',))


@pytest.mark.asyncio
async def test_direct_worker_cancel_before_commit_rolls_back_body_and_projection(client,monkeypatch):
    _,app,device=client;service=app.state.account_application_drafts;original=service.artifacts.ensure_projection
    reached=asyncio.Event();pause=asyncio.Event()
    async def stopped(**kwargs):
        value=await original(**kwargs);reached.set();await pause.wait();return value
    monkeypatch.setattr(service.artifacts,'ensure_projection',stopped)
    caller={'owner_id':'owner','device_id':device.device.device_id,'access_token_hash':__import__('hashlib').sha256(device.access_token.encode()).hexdigest(),'proved':False}
    request=DraftInput.model_validate(body());task=asyncio.create_task(service.create(request,caller,service.clock()))
    await asyncio.wait_for(reached.wait(),5);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert not await app.state.store.fetchall('SELECT key FROM runtime_meta WHERE key GLOB ?',(PREFIX+'*',))
    assert not await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,))


@pytest.mark.asyncio
async def test_explicit_erase_lost_commit_ack_readback_and_exact_repeat(client,monkeypatch):
    ac,app,device=client;payload,receipt=await publish(client);store=app.state.store;original=store.connection;once=True
    class Proxy:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        async def commit(self):
            nonlocal once
            await self.db.commit()
            if once:once=False;raise OSError('SOURCE erase acknowledgement lost')
    @asynccontextmanager
    async def intercepted():
        async with original() as db:yield Proxy(db)
    monkeypatch.setattr(store,'connection',intercepted)
    erased=await ac.request('DELETE',PATH+'/'+payload['operation_id'],json={'expected_digest':receipt['body_digest']},headers=_base_headers(device))
    assert erased.status_code==503 and erased.json()['detail']['code']=='ACCOUNT_DRAFT_HISTORY_UNKNOWN'
    read=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))
    assert read.status_code==200 and read.json()['state']=='ERASED'
    repeat=await ac.request('DELETE',PATH+'/'+payload['operation_id'],json={'expected_digest':receipt['body_digest']},headers=_base_headers(device))
    assert repeat.status_code==200 and repeat.json()['canonical_bodies_removed']==1
    assert (await ac.post(PATH,json=payload,headers=_base_headers(device))).status_code==410


@pytest.mark.asyncio
async def test_erase_exact_old_selection_preserves_newer_and_unrelated_drafts(client):
    ac,app,device=client;headers=_base_headers(device);first,receipt=await publish(client)
    second,newer=await publish(client,body(family_id=first['family_id'],expected_revision=1,broker_kind='DERIV'))
    other,unrelated=await publish(client)
    denied=await ac.request('DELETE',PATH+'/'+first['operation_id'],json={'expected_digest':'0'*64},headers=headers)
    assert denied.status_code==409
    deleted=await ac.request('DELETE',PATH+'/'+first['operation_id'],json={'expected_digest':receipt['body_digest']},headers=headers)
    assert deleted.status_code==200
    current=await ac.get(PATH+'/selections/'+first['family_id'],headers=headers)
    assert current.json()['revision']==2 and current.json()['draft_id']==newer['draft_id']
    assert (await ac.get(PATH+'/'+second['operation_id'],headers=headers)).json()['receipt']==newer
    assert (await ac.get(PATH+'/'+other['operation_id'],headers=headers)).json()['receipt']==unrelated
    assert len(await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==2


@pytest.mark.asyncio
async def test_missing_canonical_original_does_not_adopt_or_duplicate_orphan_projection(client):
    ac,app,device=client;payload,receipt=await publish(client)
    await app.state.store.execute('DELETE FROM runtime_meta WHERE key=?',(_key(PREFIX,'owner',payload['operation_id']),))
    replay=await ac.post(PATH,json=payload,headers=_base_headers(device))
    assert replay.status_code==503 and replay.json()['detail']['code']=='ACCOUNT_DRAFT_HISTORY_UNKNOWN'
    retarget={**payload,'family_id':uuid.uuid4().hex}
    assert (await ac.post(PATH,json=retarget,headers=_base_headers(device))).status_code==503
    assert len(await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==1


@pytest.mark.asyncio
async def test_openapi_has_typed_non_effect_contract_and_safe_field_refusal(client):
    ac,_,device=client;spec=(await ac.get('/openapi.json',headers=_base_headers(device))).json()
    operation=spec['paths'][PATH]['post'];schema=operation['responses']['200']['content']['application/json']['schema']
    assert schema['$ref'].endswith('/DraftReceipt')
    assert spec['components']['schemas']['DraftInput']['additionalProperties'] is False
    result=await ac.post(PATH,json={**body(),'broker_kind':'not-a-provider'},headers=_base_headers(device))
    assert result.status_code==422 and result.json()['detail']['field']=='broker_kind'
    assert 'not-a-provider' not in result.text


@pytest.mark.asyncio
async def test_null999_selection_cannot_admit_unproven_generation(client):
    ac,app,device=client;payload,receipt=await publish(client)
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',
        (json.dumps({'revision':999,'draft_id':None}),_key(FAMILY,'owner',payload['family_id'])))
    read=await ac.get(PATH+'/'+payload['operation_id'],headers=_base_headers(device))
    result=await ac.post(PATH,json=body(family_id=payload['family_id'],expected_revision=999,broker_kind='DERIV'),headers=_base_headers(device))
    assert result.status_code==503,result.text
    assert read.status_code==200 and read.json()['receipt']==receipt
    assert read.json()['current_selection_state']=='UNKNOWN' and read.json()['selection_current'] is None
    assert len(await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==1


@pytest.mark.asyncio
@pytest.mark.parametrize('damage',['missing-head','false-empty-one','stale-selected','stale-empty','missing-after-erase'])
async def test_selection_requires_complete_original_history_in_both_states(client,damage):
    ac,app,device=client;payload,receipt=await publish(client);store=app.state.store;headers=_base_headers(device)
    family_key=_key(FAMILY,'owner',payload['family_id']);expected=0;read_id=payload['operation_id'];erased=False
    if damage=='missing-head':await store.execute('DELETE FROM runtime_meta WHERE key=?',(family_key,))
    elif damage=='false-empty-one':
        expected=1;await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps({'revision':1,'draft_id':None}),family_key))
    elif damage=='stale-selected':
        await publish(client,body(family_id=payload['family_id'],expected_revision=1));expected=1
        await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps({'revision':1,'draft_id':receipt['draft_id']}),family_key))
    else:
        result=await ac.request('DELETE',PATH+'/'+payload['operation_id'],json={'expected_digest':receipt['body_digest']},headers=headers)
        assert result.status_code==200
        if damage=='stale-empty':
            newer,new_receipt=await publish(client,body(family_id=payload['family_id'],expected_revision=2))
            read_id=newer['operation_id'];receipt=new_receipt;expected=2
            await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps({'revision':2,'draft_id':None}),family_key))
        else:
            erased=True;await store.execute('DELETE FROM runtime_meta WHERE key=?',(family_key,))
    before=len(await store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))
    read=await ac.get(PATH+'/'+read_id,headers=headers);assert read.status_code==200,read.text
    if erased:assert read.json()['state']=='ERASED'
    else:
        assert read.json()['receipt']==receipt and read.json()['current_selection_state']=='UNKNOWN'
        assert read.json()['selection_current'] is None
    assert (await ac.get(PATH+'/selections/'+payload['family_id'],headers=headers)).status_code==503
    attempt=await ac.post(PATH,json=body(family_id=payload['family_id'],expected_revision=expected),headers=headers)
    assert attempt.status_code==503,attempt.text
    assert len(await store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,)))==before


@pytest.mark.asyncio
@pytest.mark.parametrize('revision',[0,2,999])
async def test_never_created_family_does_not_trust_an_unsupported_empty_head(client,revision):
    ac,app,device=client;payload=body()
    await app.state.store.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,0)',
        (_key(FAMILY,'owner',payload['family_id']),json.dumps({'revision':revision,'draft_id':None})))
    result=await ac.post(PATH,json={**payload,'expected_revision':revision},headers=_base_headers(device))
    assert result.status_code==503,result.text
    assert not await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,))


@pytest.mark.asyncio
async def test_proven_erase_empty_family_and_later_generations_preserve_original_history(client):
    ac,app,device=client;headers=_base_headers(device);payload,receipt=await publish(client)
    for expected in (2,4):
        erased=await ac.request('DELETE',PATH+'/'+payload['operation_id'],json={'expected_digest':receipt['body_digest']},headers=headers)
        assert erased.status_code==200,erased.text
        selection=await ac.get(PATH+'/selections/'+payload['family_id'],headers=headers)
        assert selection.status_code==200 and selection.json()['revision']==expected and selection.json()['draft_id'] is None
        record=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(_key(PREFIX,'owner',payload['operation_id']),))
        tomb=json.loads(record['value']);assert 'body' not in tomb
        assert payload['family_id'] not in record['value'] and 'broker_kind' not in record['value']
        assert tomb['selection_witness']['erase_revision']==expected
        old_id=payload['operation_id'];old_receipt=receipt
        payload,receipt=await publish(client,body(family_id=payload['family_id'],expected_revision=expected))
        assert receipt['selection_revision']==expected+1
        assert (await ac.get(PATH+'/'+old_id,headers=headers)).json()['state']=='ERASED'
        assert (await ac.post(PATH,json={**payload,'operation_id':old_id},headers=headers)).status_code==410
        assert old_receipt['expires_at_ms']-old_receipt['created_at_ms']==TTL_MS


@pytest.mark.asyncio
async def test_explicit_privacy_erase_does_not_launder_corrupt_selection_into_valid_empty(client):
    ac,app,device=client;headers=_base_headers(device);payload,receipt=await publish(client)
    key=_key(FAMILY,'owner',payload['family_id']);corrupt={'revision':999,'draft_id':None}
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps(corrupt),key))
    deleted=await ac.request('DELETE',PATH+'/'+payload['operation_id'],json={'expected_digest':receipt['body_digest']},headers=headers)
    assert deleted.status_code==200 and deleted.json()['canonical_bodies_removed']==deleted.json()['projections_removed']==1
    stored=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,));assert json.loads(stored['value'])==corrupt
    record=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(_key(PREFIX,'owner',payload['operation_id']),))
    tomb=json.loads(record['value']);assert 'body' not in tomb and tomb['selection_witness']['erase_revision'] is None
    assert (await ac.get(PATH+'/'+payload['operation_id'],headers=headers)).json()['state']=='ERASED'
    assert (await ac.get(PATH+'/selections/'+payload['family_id'],headers=headers)).status_code==503
    assert (await ac.post(PATH,json=body(family_id=payload['family_id'],expected_revision=999),headers=headers)).status_code==503
    assert not await app.state.store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,))


@pytest.mark.asyncio
@pytest.mark.parametrize('damage',['missing-tomb','missing-witness','wrong-scope','wrong-digest','gap-rehashed','false-erase-rehashed','wrong-operation'])
async def test_empty_family_requires_its_exact_original_erase_witness(client,damage):
    from van_gateway.trading.account_application_drafts import digest
    ac,app,device=client;headers=_base_headers(device);payload,receipt=await publish(client);store=app.state.store
    erased=await ac.request('DELETE',PATH+'/'+payload['operation_id'],json={'expected_digest':receipt['body_digest']},headers=headers)
    assert erased.status_code==200
    key=_key(PREFIX,'owner',payload['operation_id']);stored=await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,));tomb=json.loads(stored['value'])
    if damage=='missing-tomb':await store.execute('DELETE FROM runtime_meta WHERE key=?',(key,))
    else:
        witness=tomb['selection_witness']
        if damage=='missing-witness':del tomb['selection_witness']
        elif damage=='wrong-scope':witness['family_scope']=_key(FAMILY,'owner',uuid.uuid4().hex)
        elif damage=='wrong-digest':witness['witness_hash']='0'*64
        elif damage=='gap-rehashed':
            witness['publication_revision']=99;witness['erase_revision']=100
        elif damage=='false-erase-rehashed':witness['erase_revision']=None
        else:witness['draft_id']='ad_'+'0'*64
        if damage in ('gap-rehashed','false-erase-rehashed'):
            witness['witness_hash']=digest({'owner_id':'owner','operation_id':payload['operation_id'],'body_digest':tomb['body_digest'],
                'selection':{k:v for k,v in witness.items() if k!='witness_hash'}})
        await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps(tomb),key))
    selection=await ac.get(PATH+'/selections/'+payload['family_id'],headers=headers)
    assert selection.status_code==503,selection.text
    result=await ac.post(PATH,json=body(family_id=payload['family_id'],expected_revision=2),headers=headers)
    assert result.status_code==503,result.text
    assert not await store.fetchall('SELECT artifact_id FROM owner_artifacts WHERE canonical_source_type=?',(SOURCE_TYPE,))
    if damage=='missing-witness':
        # Unsupported old receipt remains historical fact, not current lineage.
        assert (await ac.get(PATH+'/'+payload['operation_id'],headers=headers)).json()['state']=='ERASED'
