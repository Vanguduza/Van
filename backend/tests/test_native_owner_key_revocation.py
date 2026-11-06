"""Gateway device revocation reaches native key checks and survives lost delivery."""
import json

import pytest
from fastapi import HTTPException

from test_runtime_recovery_gateway import client, _env, session_control, prepare, BASE
from test_trading_api import HDR, DEVICE_PEM, DEVICE_KEY
from van_gateway.trading.strategies import owner_authority_key_id
from van_gateway.auth.service import AuthError
from vati.authority import load_owner_keys, sign_token, OwnerAuthorityError
from vati.risk.contracts import KillSwitchTrigger


@pytest.mark.asyncio
async def test_revoking_phone_key_prevents_a_queued_native_recovery_effect(client, session_control):
    ac, app = client; service, _, _ = session_control
    body = await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).json()['phase']=='REQUESTED'
    response = await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    assert owner_authority_key_id(DEVICE_PEM) not in load_owner_keys(service.cfg.owner_authority_keys)
    assert response.json()['native_authority_revocation']['phase']=='APPLIED'
    service.step_once()
    from vati.app.runtime_control_journal import RuntimeControlJournal
    final = RuntimeControlJournal(service._ledger).status(body['approval_proof']['challenge_id'],'test-device')
    assert final.phase=='REFUSED' and final.result['reason_code']=='OWNER_KEY_UNREGISTERED'
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active


@pytest.mark.asyncio
async def test_native_outage_keeps_local_device_revoked_and_durable_native_work_pending(client, session_control, monkeypatch):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    run = transport.run
    def unavailable(name,args):
        if name=='owner_authority_revoke':raise HTTPException(503,'fixture native revocation outage')
        return run(name,args)
    with monkeypatch.context() as scoped:
        scoped.setattr(transport,'run',unavailable)
        response = await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    assert response.json()['revoked'] is True
    assert response.json()['native_authority_revocation']['phase']=='PENDING'
    with pytest.raises(AuthError):await app.state.auth.require_device('test-device')
    dispatcher = app.state.native_owner_revocations
    cold = type(dispatcher)(store=app.state.store,promotions=app.state.strategy_promotions)
    assert (await cold.reconcile_once())['applied']==1
    assert owner_authority_key_id(DEVICE_PEM) not in load_owner_keys(service.cfg.owner_authority_keys)
    service.step_once()
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active


@pytest.mark.asyncio
async def test_revoked_native_key_cannot_be_reenrolled_by_a_stale_gateway_request(client, session_control):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    response = await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    with pytest.raises(HTTPException) as denied:
        transport.run('owner_authority_enroll',{'device_id':'test-device',
            'key_id':owner_authority_key_id(DEVICE_PEM),'public_key_pem':DEVICE_PEM})
    assert denied.value.status_code==409
    assert owner_authority_key_id(DEVICE_PEM) not in load_owner_keys(service.cfg.owner_authority_keys)


@pytest.mark.asyncio
async def test_native_key_cache_cannot_outlive_a_revocation_from_another_process(client, session_control):
    ac, app = client; service, _, _ = session_control
    body = await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    from commander.app import CommanderSettings
    other = CommanderSettings(owner_authority_keys=service.cfg.owner_authority_keys).owner_authority()
    kid = owner_authority_key_id(DEVICE_PEM)
    token = sign_token(DEVICE_KEY,act='owner-halt',subject='native-revocation-test',key_id=kid)
    assert other.verify(token,act='owner-halt',subject='native-revocation-test',single_use=False)
    response = await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    with pytest.raises(OwnerAuthorityError):
        other.verify(token,act='owner-halt',subject='native-revocation-test',single_use=False)


@pytest.mark.asyncio
async def test_native_commit_ack_loss_retries_same_tombstone_without_reenrollment(client, session_control, monkeypatch):
    ac, app = client; service, _, _ = session_control
    body = await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    import vati.authority_registry as registry
    write=registry._write
    def lose_ack(path,payload):
        write(path,payload)
        raise OSError('fixture lost native revocation commit acknowledgement')
    with monkeypatch.context() as scoped:
        scoped.setattr(registry,'_write',lose_ack)
        response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    saved=response.json()['native_authority_revocation']
    assert saved['phase']=='PENDING'
    assert owner_authority_key_id(DEVICE_PEM) not in load_owner_keys(service.cfg.owner_authority_keys)
    result=await app.state.native_owner_revocations.reconcile_operation(saved['operation_id'])
    assert result['phase']=='APPLIED' and result['operation_id']==saved['operation_id']
    assert len(registry.read_registry(service.cfg.owner_authority_keys)['revocations'])==1


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['active','quoted_revoked','foreign_key','bad_reference','bad_registry'])
async def test_native_acknowledgement_must_prove_the_exact_inactive_key(client,session_control,monkeypatch,bad):
    ac, app=client;service,transport,_=session_control
    body=await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    run=transport.run
    def weakened(name,args):
        result=run(name,args)
        if name=='owner_authority_revoke':
            result=dict(result)
            key,value={'active':('key_active',True),'quoted_revoked':('revoked','true'),
                'foreign_key':('key_id','device-'+'a'*24),'bad_reference':('revocation_ref','b'*64),
                'bad_registry':('registry_ref','not-evidence')}[bad]
            result[key]=value
        return result
    with monkeypatch.context() as scoped:
        scoped.setattr(transport,'run',weakened)
        response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    state=response.json()['native_authority_revocation']
    assert state['phase']=='PENDING' and state['native_result'] is None
    assert (await app.state.native_owner_revocations.reconcile_operation(state['operation_id']))['phase']=='APPLIED'


@pytest.mark.asyncio
async def test_cached_native_revocation_receipt_is_revalidated(client,session_control):
    ac,app=client;service,_,_=session_control
    body=await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    state=response.json()['native_authority_revocation'];key='native_owner_revocation:'+state['operation_id']
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
    damaged=json.loads(row['value']);damaged['native_result']['key_active']=True
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps(damaged),key))
    with pytest.raises(ValueError,match='receipt is unreadable'):
        await app.state.native_owner_revocations.reconcile_operation(state['operation_id'])


@pytest.mark.asyncio
async def test_device_revocation_and_native_pending_receipt_roll_back_together(client,monkeypatch):
    from contextlib import asynccontextmanager
    _,app=client;store=app.state.store;connect=store.connection
    @asynccontextmanager
    async def failed_connection():
        async with connect() as db:
            execute=db.execute
            async def failure(sql,args=()):
                result=await execute(sql,args)
                if sql.startswith('INSERT OR IGNORE INTO runtime_meta') and args[0].startswith('native_owner_revocation:'):
                    raise OSError('fixture failed native revocation receipt write')
                return result
            db.execute=failure
            yield db
    with monkeypatch.context() as scoped:
        scoped.setattr(store,'connection',failed_connection)
        with pytest.raises(OSError,match='receipt write'):
            await app.state.auth.revoke('test-device')
    assert (await app.state.auth.require_device('test-device')).revoked_at_unix is None
    assert not await store.fetchall("SELECT key FROM runtime_meta WHERE key GLOB 'native_owner_revocation:*'")


@pytest.mark.asyncio
async def test_native_revocation_background_worker_is_started_and_awaited(client,monkeypatch):
    import asyncio
    _,app=client;runner=app.state.native_owner_revocations
    started,stopped=asyncio.Event(),asyncio.Event()
    async def worker():
        started.set()
        try:await asyncio.Event().wait()
        finally:stopped.set()
    monkeypatch.setattr(runner,'run',worker)
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(),2)
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_one_bad_pending_record_cannot_starve_native_revocation(client,session_control,monkeypatch):
    ac,app=client;service,transport,_=session_control
    body=await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    run=transport.run
    def unavailable(name,args):
        if name=='owner_authority_revoke':raise HTTPException(503,'fixture native outage')
        return run(name,args)
    with monkeypatch.context() as scoped:
        scoped.setattr(transport,'run',unavailable)
        response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.json()['native_authority_revocation']['phase']=='PENDING'
    await app.state.store.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
        ('native_owner_revocation:'+'0'*64,json.dumps({'phase':'PENDING'}),0))
    cls=type(app.state.native_owner_revocations)
    runner=cls(store=app.state.store,promotions=app.state.strategy_promotions)
    assert (await runner.reconcile_once(limit=1))['pending']==1
    assert (await runner.reconcile_once(limit=1))['applied']==1
    assert owner_authority_key_id(DEVICE_PEM) not in load_owner_keys(service.cfg.owner_authority_keys)


@pytest.mark.asyncio
async def test_local_action_revocation_precedes_any_potentially_slow_native_delivery(client,session_control,monkeypatch):
    ac,app=client;service,transport,_=session_control
    body=await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    events=[];actions=app.state.owner_runtime.actions;local=actions.revoke_privileged_for_device;run=transport.run
    async def revoke_actions(identity):
        events.append('local_actions')
        return await local(identity)
    def native(name,args):
        if name=='owner_authority_revoke':events.append('native_transport')
        return run(name,args)
    monkeypatch.setattr(actions,'revoke_privileged_for_device',revoke_actions)
    monkeypatch.setattr(transport,'run',native)
    response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    assert events.index('local_actions') < events.index('native_transport')


@pytest.mark.asyncio
async def test_switching_actor_to_a_different_owner_key_registry_cannot_keep_old_recovery_authority(client,session_control):
    from pathlib import Path
    ac,app=client;service,_,_=session_control
    body=await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).json()['phase']=='REQUESTED'
    original=Path(service.cfg.owner_authority_keys);other=original.with_name('different-native-owner.json')
    other.write_bytes(original.read_bytes());service.cfg.owner_authority_keys=str(other)
    response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    service.step_once()
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active
    from vati.app.runtime_control_journal import RuntimeControlJournal
    final=RuntimeControlJournal(service._ledger).status(body['approval_proof']['challenge_id'],'test-device')
    assert final.phase=='REFUSED' and final.result['reason_code']=='STATE_CHANGED'


@pytest.mark.asyncio
async def test_mismatched_commander_and_actor_key_registry_refuses_new_owner_review(client,session_control):
    from pathlib import Path
    ac,app=client;service,_,_=session_control
    app.state.strategy_promotions.ensure_owner_authority(device_id='test-device',public_key_pem=DEVICE_PEM)
    original=Path(service.cfg.owner_authority_keys);other=original.with_name('different-native-owner.json')
    other.write_bytes(original.read_bytes());service.cfg.owner_authority_keys=str(other)
    service._heartbeat('RUNNING')
    response=await ac.get(BASE+'/state',params={'account_alias':service.cfg.account_alias,
        'session_id':service.runner.cycle.cfg.session_id})
    assert response.status_code==409,response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['key','public_key_type','operation','device','extra'])
async def test_private_revocation_refuses_a_changed_or_malformed_target_without_registry_effect(client,session_control,bad):
    from pathlib import Path
    from vati.authority_registry import revocation_record
    _,app=client;service,transport,_=session_control
    app.state.strategy_promotions.ensure_owner_authority(device_id='test-device',public_key_pem=DEVICE_PEM)
    kid=owner_authority_key_id(DEVICE_PEM)
    target={'device_id':'test-device','key_id':kid,'public_key_pem':DEVICE_PEM,
        'operation_id':revocation_record('test-device',kid)['operation_id']}
    if bad=='key':target['key_id']='device-'+'a'*24
    elif bad=='public_key_type':target['public_key_pem']=True
    elif bad=='operation':target['operation_id']='b'*64
    elif bad=='device':target['device_id']='owner|foreign'
    else:target['unbound']='ignored'
    path=Path(service.cfg.owner_authority_keys);before=path.read_bytes()
    with pytest.raises(HTTPException) as error:transport.run('owner_authority_revoke',target)
    assert error.value.status_code==422
    assert path.read_bytes()==before


@pytest.mark.asyncio
@pytest.mark.parametrize('broken',[[],{'runtime_recovery':[]},{'runtime_recovery':{'state':[]}}])
async def test_unrelated_corrupt_heartbeat_cannot_break_a_valid_native_owner_review(client,session_control,broken):
    from pathlib import Path
    ac,_=client;service,_,_=session_control
    (Path(service.cfg.heartbeat_path).parent/'unrelated-malformed.json').write_text(json.dumps(broken))
    response=await ac.get(BASE+'/state',params={'account_alias':service.cfg.account_alias,
        'session_id':service.runner.cycle.cfg.session_id})
    assert response.status_code==200,response.text


@pytest.mark.asyncio
async def test_known_native_success_survives_a_failed_gateway_marker_write(client,session_control,monkeypatch):
    ac,app=client;service,_,_=session_control
    body=await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    execute=app.state.store.execute
    async def lost_marker(sql,args=()):
        if sql.startswith('UPDATE runtime_meta SET value=') and args[-1].startswith('native_owner_revocation:'):
            raise OSError('fixture gateway revocation marker unavailable')
        return await execute(sql,args)
    with monkeypatch.context() as scoped:
        scoped.setattr(app.state.store,'execute',lost_marker)
        response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    assert response.status_code==200,response.text
    known=response.json()['native_authority_revocation']
    assert known['phase']=='APPLIED' and known['native_result']['key_active'] is False
    key='native_owner_revocation:'+known['operation_id']
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
    assert json.loads(row['value'])['phase']=='PENDING'  # original work remains durable
    assert (await app.state.native_owner_revocations.reconcile_once())['applied']==1
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
    assert json.loads(row['value'])['phase']=='APPLIED'
    assert owner_authority_key_id(DEVICE_PEM) not in load_owner_keys(service.cfg.owner_authority_keys)


async def admin_read(app,path,*,authorized=True):
    from httpx import AsyncClient,ASGITransport
    headers={'X-Van-Ingress-Token':'test-ingress-token-0123456789abcdef0123456789'}
    if authorized:headers.update(HDR)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test',headers=headers) as admin:
        return await admin.get(path)


@pytest.mark.asyncio
async def test_original_revocation_get_observes_pending_and_applied_without_dispatching(client,session_control,monkeypatch):
    ac,app=client;service,transport,_=session_control
    body=await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    # Pause only the unrelated periodic scheduler so the GET's own effect can
    # be judged independently. Explicit delivery below uses the real handler.
    async def idle(**kwargs):return {'examined':0,'applied':0,'pending':0}
    monkeypatch.setattr(app.state.native_owner_revocations,'reconcile_once',idle)
    run=transport.run
    def unavailable(name,args):
        if name=='owner_authority_revoke':raise HTTPException(503,'fixture native outage')
        return run(name,args)
    with monkeypatch.context() as scoped:
        scoped.setattr(transport,'run',unavailable)
        response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    state=response.json()['native_authority_revocation'];op=state['operation_id']
    path='/v1/devices/test-device/revocations/'+op
    calls=list(transport.calls)
    read=await admin_read(app,path)
    assert read.status_code==200 and read.json()['phase']=='PENDING',read.text
    assert transport.calls==calls
    assert (await app.state.native_owner_revocations.reconcile_operation(op))['phase']=='APPLIED'
    calls=list(transport.calls)
    read=await admin_read(app,path)
    assert read.status_code==200 and read.json()['phase']=='APPLIED',read.text
    assert transport.calls==calls and 'public_key_pem' not in read.text
    wrong=await admin_read(app,'/v1/devices/foreign-device/revocations/'+op)
    assert wrong.status_code==404


@pytest.mark.asyncio
async def test_original_revocation_get_refuses_missing_invalid_and_unprivileged_reads(client):
    _,app=client
    path='/v1/devices/test-device/revocations/'
    assert (await admin_read(app,path+'a'*64)).status_code==404
    assert (await admin_read(app,path+'not-an-original-id')).status_code==422
    assert (await admin_read(app,path+'a'*64,authorized=False)).status_code in {401,403}


@pytest.mark.asyncio
async def test_original_revocation_get_reports_corrupt_outcome_unavailable(client,session_control):
    ac,app=client;service,_,_=session_control
    body=await prepare(ac,service)
    assert (await ac.post(BASE+'/request',json=body)).status_code==200
    response=await ac.post('/v1/devices/test-device/revoke',headers=HDR)
    op=response.json()['native_authority_revocation']['operation_id']
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',('not-json','native_owner_revocation:'+op))
    read=await admin_read(app,'/v1/devices/test-device/revocations/'+op)
    assert read.status_code==503,read.text


@pytest.mark.asyncio
async def test_revocation_read_requires_enrolment_scope_instead_of_the_shared_runtime_token(client,monkeypatch):
    from httpx import AsyncClient,ASGITransport
    from van_gateway.config import get_settings
    from van_gateway.app import create_app
    _,_=client
    dedicated='dedicated-enrolment-read-token-0123456789abcdef'
    monkeypatch.setenv('VAN_DEVICE_ENROLMENT_TOKEN',dedicated)
    get_settings.cache_clear();app=create_app()
    path='/v1/devices/test-device/revocations/'+'a'*64
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as admin:
        shared=await admin.get(path,headers=HDR)
        assert shared.status_code==403,shared.text
        allowed=await admin.get(path,headers={'X-Van-Internal-Token':dedicated})
        assert allowed.status_code==404,allowed.text
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_agent_cannot_revoke_owner_authority_or_discover_the_hidden_command(client,session_control):
    from commander.auth import sign_headers
    from test_runtime_recovery_gateway import HERMES_TOKEN
    _,app=client;service,_,native=session_control
    app.state.strategy_promotions.ensure_owner_authority(device_id='test-device',public_key_pem=DEVICE_PEM)
    path='/v1/cmd/owner_authority_revoke';body=b'{"args":{}}'
    response=native.post(path,content=body,headers=sign_headers(HERMES_TOKEN,'POST',path,body))
    assert response.status_code==403
    tools=native.get('/v1/tools',headers=sign_headers(HERMES_TOKEN,'GET','/v1/tools',b''))
    assert not any(row['name']=='owner_authority_revoke' for row in tools.json()['tools'])
    assert owner_authority_key_id(DEVICE_PEM) in load_owner_keys(service.cfg.owner_authority_keys)
