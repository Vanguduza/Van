"""LAC-210 actual owner consent/revoker/effect/readback source recovery."""
import json
import pytest
from tests.test_local_typed_actions import client, _settings
from tests.test_owner_memory_erasure import _pair
from test_owner_permissions import _approved, _parameters, _begin
from van_gateway.capability import owner_permissions as permissions

pytestmark=pytest.mark.asyncio

async def grant(ac,app,*,idem='revocation-source'):
    key=await _pair(ac,app)
    params=_parameters(max_uses=3)
    command=await _approved(ac,app,key,params,idem)
    result=await ac.post('/v1/commands',json=command)
    assert result.json()['status']=='accepted',result.text
    witness=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(permissions.WITNESS_PREFIX+command['command_id'],))
    return json.loads(witness['value'])['grant_id'],params

async def test_lost_successful_revocation_reply_recovers_instead_of_conflicting(client):
    ac,app,_=client
    grant_id,_=await grant(ac,app)
    path='/v1/permissions/'+grant_id+'/revoke'
    first=await ac.post(path,json={})
    assert first.status_code==200,first.text
    retry=await ac.post(path,json={})
    assert retry.status_code==200,retry.text
    assert retry.json()==first.json()

async def explicit_request(ac,grant_id):
    detail=await ac.get('/v1/permissions/grants/'+grant_id)
    assert detail.status_code==200,detail.text
    data=detail.json()
    request=data['revocation_request']
    assert request['expected_revision']==data['source_revision'] and request['expected_source_digest']==data['source_digest']
    return request

async def test_exact_detail_ceiling_and_actual_http_revoke_fence_effect_and_original_readback(client):
    from van_gateway.action.service import ActionPolicyError
    from van_gateway.action.models import ExecutionStatus
    ac,app,_=client
    grant_id,params=await grant(ac,app)
    before=(await ac.get('/v1/permissions/grants/'+grant_id)).json()
    assert before['max_uses']==before['remaining_uses']==before['effective_remaining_uses']==3
    assert before['source_verified'] and before['grant_current'] and before['device_id']=='dev-erasure'
    await _begin(app,params,'queued-revocation-use')
    detail=(await ac.get('/v1/permissions/grants/'+grant_id)).json()
    assert detail['remaining_uses']==detail['effective_remaining_uses']==2
    request=await explicit_request(ac,grant_id)
    path='/v1/permissions/'+grant_id+'/revoke'
    first=await ac.post(path,json=request)
    assert first.status_code==200,first.text
    with pytest.raises(ActionPolicyError,match='revoked_or_expired'):
        await app.state.owner_runtime.actions.mark_executing('queued-revocation-use')
    assert (await app.state.owner_runtime.actions.get_execution('queued-revocation-use')).status is ExecutionStatus.AUTHORIZED
    original=await ac.get('/v1/permissions/'+grant_id+'/revocations/'+request['operation_id'])
    assert original.status_code==200 and original.json()==first.json()
    assert original.headers['cache-control']=='no-store'
    after=(await ac.get('/v1/permissions/grants/'+grant_id)).json()
    assert after['remaining_uses']==2 and after['effective_remaining_uses']==0 and not after['grant_current']
    assert (await ac.post(path,json=request)).json()==first.json()
    changed=await ac.post(path,json={**request,'expected_revision':'0'*64})
    assert changed.status_code==409 and changed.json()['detail']=='permission_revocation_operation_conflict'

async def test_admission_wins_then_same_generation_owner_revoke_preserves_budget_and_blocks_next_use(client):
    from van_gateway.action.service import ActionPolicyError
    ac,app,_=client
    grant_id,params=await grant(ac,app)
    before=(await ac.get('/v1/permissions/grants/'+grant_id)).json()
    request=before['revocation_request']
    await _begin(app,params,'charged-after-review')
    detail=(await ac.get('/v1/permissions/grants/'+grant_id)).json()
    assert detail['source_revision']==before['source_revision']
    assert detail['accounting_revision']!=before['accounting_revision'] and detail['use_count']==1
    response=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)
    assert response.status_code==200 and response.json()['state']=='APPLIED',response.text
    assert (await app.state.store.fetchone('SELECT use_count FROM permission_grants WHERE grant_id=?',(grant_id,)))[0]==1
    with pytest.raises(ActionPolicyError,match='revoked_or_expired'):
        await _begin(app,params,'next-admission-after-revoke')

async def test_wrong_device_tampered_receipt_and_reused_grant_identity_fail_closed(client):
    from van_gateway.capability.owner_permissions import REVOCATION_PREFIX
    ac,app,_=client
    grant_id,_=await grant(ac,app)
    request=await explicit_request(ac,grant_id)
    path='/v1/permissions/'+grant_id+'/revoke'
    original_headers=dict(ac.headers)
    await _pair(ac,app,device='other-phone')
    denied=await ac.post(path,json=request)
    assert denied.status_code==403,denied.text
    assert not await app.state.store.fetchone('SELECT key FROM runtime_meta WHERE key=?',(REVOCATION_PREFIX+request['operation_id'],))
    ac.headers.clear();ac.headers.update(original_headers)
    applied=await ac.post(path,json=request)
    assert applied.status_code==200,applied.text
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(REVOCATION_PREFIX+request['operation_id'],))
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',('corrupt',REVOCATION_PREFIX+request['operation_id']))
    unavailable=await ac.get('/v1/permissions/'+grant_id+'/revocations/'+request['operation_id'])
    assert unavailable.status_code==503,unavailable.text
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(row['value'],REVOCATION_PREFIX+request['operation_id']))
    await app.state.store.execute('UPDATE permission_grants SET revoked_at_ms=NULL WHERE grant_id=?',(grant_id,))
    retry=await ac.post(path,json=request)
    assert retry.status_code==409 and retry.json()['detail']=='permission_revocation_subject_changed'
    assert (await app.state.store.fetchone('SELECT revoked_at_ms FROM permission_grants WHERE grant_id=?',(grant_id,)))[0] is None

async def test_revocation_writer_wins_against_queued_actual_effect_without_rewriting_submitted_work(client,monkeypatch):
    import asyncio
    from van_gateway.action.service import ActionPolicyError
    ac,app,_=client
    grant_id,params=await grant(ac,app)
    await _begin(app,params,'submitted-original')
    await app.state.owner_runtime.actions.mark_executing('submitted-original')
    await app.state.owner_runtime.actions.mark_submitted('submitted-original',correlation={'original':'provider-command'})
    await _begin(app,params,'queued-after-original')
    request=await explicit_request(ac,grant_id)
    entered,release=asyncio.Event(),asyncio.Event()
    original=permissions.grant_detail_in_snapshot
    async def paused(*args,**kwargs):
        detail=await original(*args,**kwargs)
        entered.set();await release.wait()
        return detail
    monkeypatch.setattr(permissions,'grant_detail_in_snapshot',paused)
    revoke=asyncio.create_task(ac.post('/v1/permissions/'+grant_id+'/revoke',json=request))
    await asyncio.wait_for(entered.wait(),10)
    effect=asyncio.create_task(app.state.owner_runtime.actions.mark_executing('queued-after-original'))
    release.set()
    response=await revoke
    assert response.status_code==200,response.text
    with pytest.raises(ActionPolicyError,match='revoked_or_expired'):await effect
    assert (await app.state.owner_runtime.actions.get_execution('submitted-original')).status.value=='SUBMITTED'
    assert (await app.state.owner_runtime.actions.mark_verifying('submitted-original')).status.value=='VERIFYING'

async def test_registry_update_and_original_receipt_rollback_together_on_write_failure(client):
    ac,app,_=client
    grant_id,_=await grant(ac,app)
    request=await explicit_request(ac,grant_id)
    await app.state.store.execute("CREATE TRIGGER fail_permission_receipt BEFORE INSERT ON runtime_meta WHEN NEW.key GLOB 'owner_permission_revocation:*' BEGIN SELECT RAISE(ABORT,'original receipt failure'); END")
    from van_gateway.capability.permissions import PermissionRegistry
    with pytest.raises(Exception,match='original receipt failure'):
        await PermissionRegistry(app.state.store).revoke_original(grant_id=grant_id,device_id='dev-erasure',cipher=app.state.auth._cipher(),**request)
    assert (await app.state.store.fetchone('SELECT revoked_at_ms FROM permission_grants WHERE grant_id=?',(grant_id,)))[0] is None

async def test_remaining_ceiling_and_actual_guard_refuse_refunded_or_corrupt_use_count(client):
    from van_gateway.action.service import ActionPolicyError
    ac,app,_=client
    grant_id,params=await grant(ac,app)
    await _begin(app,params,'actual-charged-use')
    await app.state.store.execute('UPDATE permission_grants SET use_count=0 WHERE grant_id=?',(grant_id,))
    detail=await ac.get('/v1/permissions/grants/'+grant_id)
    assert detail.status_code==200 and detail.json()['authority_state']=='CORRUPT' and detail.json()['effective_remaining_uses']==0,detail.text
    with pytest.raises(ActionPolicyError,match='use_count_integrity_failed'):
        await app.state.owner_runtime.actions.mark_executing('actual-charged-use')

async def test_expired_request_is_refused_but_expired_target_and_legacy_cleanup_remain_available(client,monkeypatch):
    from van_gateway.capability.permissions import PermissionOrigin,PermissionRegistry
    ac,app,_=client
    grant_id,params=await grant(ac,app)
    request=await explicit_request(ac,grant_id)
    token=json.loads(app.state.auth._cipher().decrypt(request['request_token'].encode()))
    with monkeypatch.context() as scoped:
        scoped.setattr(permissions.time,'time',lambda:token['expires_at_ms']/1000+1)
        response=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)
    assert response.status_code==409 and response.json()['reason_code']=='permission_revocation_request_expired',response.text
    assert (await ac.get('/v1/permissions/'+grant_id+'/revocations/'+request['operation_id'])).json()==response.json()
    with monkeypatch.context() as scoped:
        scoped.setattr(permissions.time,'time',lambda:params['expires_at_ms']/1000+1)
        detail=(await ac.get('/v1/permissions/grants/'+grant_id)).json()
        assert detail['authority_state']=='EXPIRED' and detail['effective_remaining_uses']==0
        fresh=detail['revocation_request']
        applied=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=fresh)
    assert applied.status_code==200 and applied.json()['state']=='APPLIED',applied.text
    registry=PermissionRegistry(app.state.store)
    legacy=await registry.grant(permission='email.read',origin=PermissionOrigin.OAUTH_CONSENT,origin_evidence_ref='oauth://historical-consent')
    detail=(await ac.get('/v1/permissions/grants/'+legacy.grant_id)).json()
    assert detail['source_verified'] is False and detail['effective_remaining_uses']==0
    result=await ac.post('/v1/permissions/'+legacy.grant_id+'/revoke',json={})
    assert result.status_code==200 and result.json()['effect_scope']=='LOCAL_REGISTRY_ONLY_SOURCE_UNVERIFIED'
    assert result.json()['native_authority_issued'] is False

@pytest.mark.parametrize('crash',['before_commit','after_commit'])
async def test_actual_process_death_recovers_exact_original_operation(client,tmp_path,crash):
    import subprocess,sys,os
    ac,app,_=client
    grant_id,params=await grant(ac,app)
    request=await explicit_request(ac,grant_id)
    program=r'''
import asyncio,os,sys,json
import aiosqlite
from van_gateway.storage.db import Store
from van_gateway.auth.service import AuthService
from van_gateway.capability.permissions import PermissionRegistry
async def main():
    store=Store(sys.argv[1])
    request=json.loads(sys.argv[3])
    if sys.argv[4]=='before_commit':
        original=aiosqlite.Connection.execute
        async def execute(self,sql,*args,**kwargs):
            if sql.startswith('INSERT INTO runtime_meta') and args and str(args[0][0]).startswith('owner_permission_revocation:'):
                os._exit(27)
            return await original(self,sql,*args,**kwargs)
        aiosqlite.Connection.execute=execute
    await PermissionRegistry(store).revoke_original(grant_id=sys.argv[2],device_id='dev-erasure',
        cipher=AuthService(store,os.environ['VAN_DEVICE_SECRET_FERNET_KEY'])._cipher(),**request)
    os._exit(28)
asyncio.run(main())
'''
    result=subprocess.run([sys.executable,'-c',program,app.state.store.path,grant_id,json.dumps(request),crash],
        capture_output=True,timeout=30,env=dict(os.environ))
    (tmp_path/'child.stdout').write_bytes(result.stdout)
    (tmp_path/'child.stderr').write_bytes(result.stderr)
    assert result.returncode==(27 if crash=='before_commit' else 28),result.stderr.decode()
    original_path='/v1/permissions/'+grant_id+'/revocations/'+request['operation_id']
    observed=await ac.get(original_path)
    before=(await ac.get('/v1/permissions/grants/'+grant_id)).json()
    if crash=='before_commit':
        assert observed.status_code==404 and before['revoked_at_ms'] is None
    else:
        assert observed.status_code==200 and observed.json()['revoked_at_ms']==before['revoked_at_ms']
    response=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)
    assert response.status_code==200,response.text
    assert (await ac.get(original_path)).json()==response.json()
    assert len(await app.state.store.fetchall("SELECT key FROM runtime_meta WHERE key GLOB 'owner_permission_revocation:*'"))==1

async def test_legacy_rebound_subject_requires_explicit_identity_without_retargeting(client):
    from van_gateway.capability.permissions import PermissionOrigin,PermissionRegistry
    ac,app,_=client
    await _pair(ac,app)
    row=await PermissionRegistry(app.state.store).grant(permission='email.read',origin=PermissionOrigin.OAUTH_CONSENT,origin_evidence_ref='oauth://original')
    path='/v1/permissions/'+row.grant_id+'/revoke'
    assert (await ac.post(path,json={})).status_code==200
    await app.state.store.execute("UPDATE permission_grants SET scope='different-subject',granted_at_ms=granted_at_ms+1,revoked_at_ms=NULL WHERE grant_id=?",(row.grant_id,))
    response=await ac.post(path,json={})
    assert response.status_code==409,response.text
    assert (await app.state.store.fetchone('SELECT revoked_at_ms FROM permission_grants WHERE grant_id=?',(row.grant_id,)))[0] is None

async def test_restored_cached_scope_cannot_dispatch_after_actual_http_revocation(client):
    from van_gateway.action.service import ActionPolicyError
    ac,app,_=client
    grant_id,params=await grant(ac,app)
    await _begin(app,params,'retained-original-claim')
    key=permissions.scope_key(params['action_id'],params['parameters'])
    cached=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
    request=await explicit_request(ac,grant_id)
    assert (await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)).status_code==200
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(cached['value'],key))
    with pytest.raises(ActionPolicyError,match='revoked_or_expired'):
        await app.state.owner_runtime.actions.mark_executing('retained-original-claim')

async def test_current_owner_may_inspect_revoke_historical_other_device_grant(client):
    ac,app,_=client
    grant_id,_=await grant(ac,app)
    old_request=await explicit_request(ac,grant_id)
    await _pair(ac,app,device='replacement-owner-phone')
    # The current authenticated owner remains allowed to manage the old target.
    await app.state.auth.revoke('dev-erasure')
    detail=(await ac.get('/v1/permissions/grants/'+grant_id)).json()
    assert detail['grant_device_id']=='dev-erasure' and detail['caller_device_id']=='replacement-owner-phone'
    assert detail['source_verified'] and detail['authority_state']=='ISSUER_REVOKED' and detail['effective_remaining_uses']==0
    switched=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=old_request)
    assert switched.status_code==403,switched.text
    request=detail['revocation_request']
    result=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)
    assert result.status_code==200 and result.json()['caller_device_id']=='replacement-owner-phone'
    assert result.json()['grant_device_id']=='dev-erasure' and result.json()['changed'] is True
    again=(await ac.get('/v1/permissions/grants/'+grant_id)).json()['revocation_request']
    no_op=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=again)
    assert no_op.status_code==200 and no_op.json()['changed'] is False
    assert no_op.json()['revoked_at_ms']==result.json()['revoked_at_ms']

async def test_corrupt_target_source_remains_inspectable_and_defensively_revocable(client):
    from van_gateway.action.service import ActionPolicyError
    ac,app,_=client
    grant_id,params=await grant(ac,app)
    await _begin(app,params,'corrupt-source-queued')
    await app.state.store.execute("UPDATE runtime_meta SET value='malformed original witness' WHERE key GLOB 'owner_permission_witness:*'")
    detail=await ac.get('/v1/permissions/grants/'+grant_id)
    assert detail.status_code==200,detail.text
    body=detail.json()
    assert body['authority_state']=='CORRUPT' and not body['source_verified'] and body['effective_remaining_uses']==0
    assert body['grant_device_id'] is None
    with pytest.raises(ActionPolicyError,match='scope_integrity_failed'):
        await app.state.owner_runtime.actions.mark_executing('corrupt-source-queued')
    result=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=body['revocation_request'])
    assert result.status_code==200 and result.json()['effect_scope']=='LOCAL_REGISTRY_ONLY_CORRUPT_SOURCE',result.text
    assert result.json()['native_authority_issued'] is False

async def test_detail_proposals_are_inert_and_completed_original_survives_request_deadline(client,monkeypatch):
    ac,app,_=client
    grant_id,_=await grant(ac,app)
    before=dict(await app.state.store.fetchone('SELECT * FROM permission_grants WHERE grant_id=?',(grant_id,)))
    request=await explicit_request(ac,grant_id)
    other=await explicit_request(ac,grant_id)
    assert request['operation_id']!=other['operation_id']
    assert not await app.state.store.fetchall("SELECT key FROM runtime_meta WHERE key GLOB 'owner_permission_revocation:*'")
    assert dict(await app.state.store.fetchone('SELECT * FROM permission_grants WHERE grant_id=?',(grant_id,)))==before
    applied=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)
    assert applied.status_code==200,applied.text
    deadline=applied.json()['request_deadline_ms']
    with monkeypatch.context() as scoped:
        scoped.setattr(permissions.time,'time',lambda:deadline/1000+100)
        original=await ac.get('/v1/permissions/'+grant_id+'/revocations/'+request['operation_id'])
        replay=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)
    assert original.json()==replay.json()==applied.json()

async def test_changed_source_generation_or_tampered_proposal_cannot_retarget(client):
    ac,app,_=client
    grant_id,_=await grant(ac,app)
    request=await explicit_request(ac,grant_id)
    malformed=await ac.post('/v1/permissions/'+grant_id+'/revoke',json={**request,'request_token':'invalid'})
    assert malformed.status_code==409 and malformed.json()['detail']=='permission_revocation_request_invalid'
    wrong=await ac.post('/v1/permissions/'+grant_id+'/revoke',json={**request,'grant_device_id':'other-issuer'})
    assert wrong.status_code==409
    assert (await app.state.store.fetchone('SELECT revoked_at_ms FROM permission_grants WHERE grant_id=?',(grant_id,)))[0] is None
    await app.state.store.execute("UPDATE permission_grants SET scope='different-domain-target' WHERE grant_id=?",(grant_id,))
    changed=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)
    assert changed.status_code==409 and changed.json()['detail']=='permission_revocation_subject_changed'

async def test_pending_request_bound_to_caller_token_and_writer_rechecks_revocation(client):
    ac,app,_=client
    grant_id,_=await grant(ac,app)
    request=await explicit_request(ac,grant_id)
    # Token rotation keeps the device/owner lawful, but requires a new explicit intent.
    import hashlib
    fresh_token='fresh-current-owner-token-0123456789'
    await app.state.store.execute('UPDATE devices SET access_token_hash=? WHERE device_id=?',
        (hashlib.sha256(fresh_token.encode()).hexdigest(),'dev-erasure'))
    ac.headers['X-Van-Device-Token']=fresh_token
    result=await ac.post('/v1/permissions/'+grant_id+'/revoke',json=request)
    assert result.status_code==409 and result.json()['reason_code']=='permission_revocation_caller_changed',result.text
    assert result.json()['changed'] is False
    fresh=await explicit_request(ac,grant_id)
    assert (await ac.post('/v1/permissions/'+grant_id+'/revoke',json=fresh)).status_code==200

async def test_caller_retirement_after_http_authentication_is_rechecked_before_writer_effect(client,monkeypatch):
    import asyncio
    ac,app,_=client
    grant_id,_=await grant(ac,app)
    request=await explicit_request(ac,grant_id)
    entered,release=asyncio.Event(),asyncio.Event()
    original=permissions.revoke_permission_grant
    async def after_authentication(*args,**kwargs):
        entered.set();await release.wait()
        return await original(*args,**kwargs)
    monkeypatch.setattr(permissions,'revoke_permission_grant',after_authentication)
    task=asyncio.create_task(ac.post('/v1/permissions/'+grant_id+'/revoke',json=request))
    await asyncio.wait_for(entered.wait(),10)
    await app.state.auth.revoke('dev-erasure')
    release.set()
    response=await task
    assert response.status_code==403,response.text
    assert (await app.state.store.fetchone('SELECT revoked_at_ms FROM permission_grants WHERE grant_id=?',(grant_id,)))[0] is None
    assert not await app.state.store.fetchone('SELECT key FROM runtime_meta WHERE key=?',(permissions.REVOCATION_PREFIX+request['operation_id'],))
