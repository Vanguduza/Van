"""Owner authority survives safe retry and stops at terminal or unknown work."""
import asyncio
import time

import pytest

from test_ingress_trust_boundary import _settings, client, TestGatewayEnforcement as _Signer
from van_gateway.auth.service import AuthService
from van_gateway.hermes.bridge import HermesBridgeError
from van_gateway.idempotency.service import IdempotencyInFlight, IdempotencyService
from van_gateway.models import OriginChannel

async def _pair(ac, app):
    ticket = await app.state.auth.create_pairing_ticket('recovery-device')
    paired = await app.state.auth.pair_device(ticket.token, 'recovery-device', 'test-only-secret', 'PEM', 'recovery')
    ac.headers.update({'X-Van-Device-Token':paired.access_token})
    return 'recovery-device'

async def _request(app, device, *, action_class='A1', nonce=None):
    body = await _Signer()._signed(app, device, 'unused', text='help organize my work',
                                  action_class=action_class, channel=OriginChannel.TEXT)
    if nonce is not None:
        body['nonce'] = nonce
        canonical = AuthService.canonical_command_v2(
            command_id=body['command_id'],idempotency_key=body['idempotency_key'],device_id=device,
            issued_at_unix=body['issued_at_unix'],text=body['text'],action_class=action_class,
            project_id=None,turn_id=None,origin_channel=body['origin_channel'],principal_type='OWNER_DEVICE',
            requested_by=body['requested_by'],expires_at_unix=None,nonce=nonce,
            context_capsule_revision=None,context_capsule_hash=None,speech_evidence_ref=None,
            no_stale_replay=False,context_trust=body['context_trust'],
        )
        body['signature'] = app.state.auth.sign(device,canonical)
    return body

@pytest.mark.asyncio
async def test_definitive_failure_retries_same_signed_request_with_immutable_context(client,monkeypatch):
    ac,app=client
    device=await _pair(ac,app)
    calls=[]
    async def reject(text,metadata=None):
        calls.append(metadata)
        raise HermesBridgeError('hermes_reject','definitive test rejection',retry_safe=True)
    monkeypatch.setattr(app.state.orchestrator.hermes,'create_run',reject)
    body=await _request(app,device,nonce='original-nonce')
    first=(await ac.post('/v1/commands',json=body)).json()
    original=await app.state.owner_runtime.authority.get(body['command_id'])
    async def recover(text,metadata=None):
        calls.append(metadata)
        return {'id':'recovered-run','status':'accepted'}
    monkeypatch.setattr(app.state.orchestrator.hermes,'create_run',recover)
    second=(await ac.post('/v1/commands',json=body)).json()
    assert first['status']=='degraded' and second['status']=='accepted'
    assert second['mission_id']==first['mission_id']
    assert second['context_snapshot_id']==first['context_snapshot_id']
    assert await app.state.owner_runtime.authority.get(body['command_id'])==original
    assert calls[0]==calls[1]
    assert len(await app.state.store.fetchall('SELECT snapshot_id FROM context_snapshots'))==1
    assert len(await app.state.store.fetchall('SELECT nonce FROM command_nonces'))==1


@pytest.mark.asyncio
async def test_crash_after_seal_before_authorization_recovers_proven_no_send_gap(client, monkeypatch):
    ac, app = client
    device = await _pair(ac, app)
    body = await _request(app, device, nonce='pre-dispatch-seal-nonce')
    calls = []
    async def create_run(text, metadata=None):
        calls.append(metadata)
        return {'id': 'after-seal-recovery'}
    monkeypatch.setattr(app.state.orchestrator.hermes, 'create_run', create_run)
    original = app.state.orchestrator.missions.authorized
    async def interrupted(*args, **kwargs):
        raise RuntimeError('process interrupted after sealed authority before mission authorization')
    monkeypatch.setattr(app.state.orchestrator.missions, 'authorized', interrupted)
    with pytest.raises(RuntimeError):
        await ac.post('/v1/commands', json=body)
    mission = await app.state.orchestrator.missions.existing_for_command(body['command_id'])
    record = await app.state.owner_runtime.authority.get(body['command_id'])
    assert mission.state.value == 'PLANNED' and record is not None and calls == []
    assert not await app.state.store.fetchone('SELECT key FROM runtime_meta WHERE key=?',
                                              (f"command_dispatch:{body['command_id']}",))
    monkeypatch.setattr(app.state.orchestrator.missions, 'authorized', original)
    await app.state.store.execute('UPDATE idempotency SET updated_at_unix=? WHERE idempotency_key=?',
                                  (int(time.time()) - 1000, body['idempotency_key']))
    recovered = (await ac.post('/v1/commands', json=body)).json()
    assert recovered['status'] == 'accepted' and recovered['hermes_run_id'] == 'after-seal-recovery'
    assert recovered['mission_id'] == mission.mission_id and len(calls) == 1
    assert await app.state.owner_runtime.authority.get(body['command_id']) == record
    assert len(await app.state.store.fetchall('SELECT nonce FROM command_nonces')) == 1
    assert len(await app.state.store.fetchall('SELECT snapshot_id FROM context_snapshots')) == 1

@pytest.mark.asyncio
async def test_ambiguous_failure_is_unknown_and_exact_retry_does_not_dispatch(client,monkeypatch):
    ac,app=client
    device=await _pair(ac,app)
    calls=[]
    async def ambiguous(text,metadata=None):
        calls.append(metadata)
        raise HermesBridgeError('hermes_offline','read timeout after possible acceptance')
    monkeypatch.setattr(app.state.orchestrator.hermes,'create_run',ambiguous)
    body=await _request(app,device)
    first=(await ac.post('/v1/commands',json=body)).json()
    second=(await ac.post('/v1/commands',json=body)).json()
    assert first==second and first['status']=='outcome_unknown' and len(calls)==1
    mission=await app.state.missions.get(first['mission_id'])
    assert mission.state.value=='WAITING_EXTERNAL' and mission.deadline_ms is not None
    assert 'Reconcile' in first['message']

@pytest.mark.asyncio
async def test_abandoned_dispatch_marker_does_not_allow_blind_redelivery(client,monkeypatch):
    ac,app=client
    device=await _pair(ac,app)
    calls=[]
    async def reject(text,metadata=None):
        calls.append(metadata)
        raise HermesBridgeError('hermes_reject','definitive test rejection',retry_safe=True)
    monkeypatch.setattr(app.state.orchestrator.hermes,'create_run',reject)
    body=await _request(app,device)
    first=(await ac.post('/v1/commands',json=body)).json()
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',
                                 ('IN_FLIGHT',f"command_dispatch:{body['command_id']}"))
    await app.state.store.execute('UPDATE idempotency SET status=?,updated_at_unix=? WHERE idempotency_key=?',
                                 ('IN_FLIGHT',int(time.time())-1000,body['idempotency_key']))
    second=(await ac.post('/v1/commands',json=body)).json()
    assert second['status']=='outcome_unknown' and len(calls)==1
    assert second['mission_id']==first['mission_id']

@pytest.mark.asyncio
async def test_conflicting_or_altered_signature_attempt_preserves_completed_receipt(client):
    ac,app=client
    device=await _pair(ac,app)
    body=await _request(app,device)
    first=(await ac.post('/v1/commands',json=body)).json()
    for changed in (dict(body,text='changed text'),dict(body,signature='forged')):
        assert (await ac.post('/v1/commands',json=changed)).json()['status']=='conflict'
    assert (await ac.post('/v1/commands',json=body)).json()==first
    claim=await app.state.store.fetchone('SELECT status FROM idempotency WHERE idempotency_key=?',(body['idempotency_key'],))
    assert claim['status']=='COMPLETED'

@pytest.mark.asyncio
@pytest.mark.parametrize('cancel',[False,True])
async def test_observed_run_receipt_recovers_after_gateway_ack_failure_without_redelivery(client,monkeypatch,cancel):
    ac,app=client
    device=await _pair(ac,app)
    body=await _request(app,device)
    calls=[]
    async def create_run(text,metadata=None):
        calls.append(metadata)
        return {'id':'observed-before-gateway-ack'}
    monkeypatch.setattr(app.state.orchestrator.hermes,'create_run',create_run)
    original_audit=app.state.orchestrator.audit.record
    async def interrupted_ack(**kwargs):
        if kwargs['result']=='accepted':
            raise RuntimeError('gateway acknowledgment interrupted after run receipt')
        return await original_audit(**kwargs)
    monkeypatch.setattr(app.state.orchestrator.audit,'record',interrupted_ack)
    with pytest.raises(RuntimeError):
        await ac.post('/v1/commands',json=body)
    mission=await app.state.orchestrator.missions.existing_for_command(body['command_id'])
    if cancel:
        assert (await ac.post(f'/v1/missions/{mission.mission_id}/cancel')).status_code==200
    await app.state.store.execute('UPDATE idempotency SET updated_at_unix=? WHERE idempotency_key=?',
                                 (int(time.time())-1000,body['idempotency_key']))
    monkeypatch.setattr(app.state.orchestrator.audit,'record',original_audit)
    recovered=(await ac.post('/v1/commands',json=body)).json()
    assert recovered['status']=='accepted' and recovered['hermes_run_id']=='observed-before-gateway-ack'
    assert recovered['mission_id']==mission.mission_id and len(calls)==1
    assert (await app.state.missions.get(mission.mission_id)).state.value==('CANCELLED' if cancel else 'RUNNING')
    assert len(await app.state.store.fetchall('SELECT snapshot_id FROM context_snapshots'))==1

@pytest.mark.asyncio
@pytest.mark.parametrize('terminal',['CANCELLED','FAILED','EXPIRED'])
async def test_terminal_mission_refuses_subsequent_runtime_action(client,terminal):
    ac,app=client
    device=await _pair(ac,app)
    body=await _request(app,device,action_class='A3')
    result=(await ac.post('/v1/commands',json=body)).json()
    if terminal=='CANCELLED':
        assert (await ac.post(f"/v1/missions/{result['mission_id']}/cancel")).status_code==200
    else:
        from van_gateway.mission.models import MissionState
        await app.state.missions.transition(result['mission_id'],target=MissionState(terminal))
    response=await ac.post('/v1/runtime/actions/begin',headers={'X-Van-Internal-Token':'trust-internal-token'},json={
        'execution_id':'exec-after-terminal','command_id':body['command_id'],'action_id':'memory.remember',
        'principal_type':'OWNER_DEVICE','requested_by':body['requested_by'],'idempotency_key':'action-after-terminal',
        'snapshot_id':result['context_snapshot_id'],'parameters':{'predicate':'accountant','value':'Mallory'},
    })
    assert response.status_code==403 and response.json()['detail']=='command_mission_terminal'
    assert await app.state.owner_runtime.actions.get_execution('exec-after-terminal') is None

@pytest.mark.asyncio
async def test_failed_idempotency_claim_has_exactly_one_concurrent_retry_winner(tmp_path):
    from van_gateway.storage.db import Store
    store=Store(str(tmp_path/'claim.sqlite3'))
    await store.migrate()
    service=IdempotencyService(store)
    payload={'command_id':'original'}
    await service.begin('original',payload)
    await service.fail('original',{'status':'degraded'})
    async def retry():
        try:
            await service.begin('original',payload)
            return 'winner'
        except IdempotencyInFlight:
            return 'in_flight'
    outcomes=await asyncio.gather(*(retry() for _ in range(10)))
    assert outcomes.count('winner')==1 and outcomes.count('in_flight')==9

@pytest.mark.asyncio
async def test_generic_hermes_verification_cannot_claim_independent_observer(client):
    ac,app=client
    device=await _pair(ac,app)
    body=await _request(app,device,action_class='A3')
    result=(await ac.post('/v1/commands',json=body)).json()
    headers={'X-Van-Internal-Token':'trust-internal-token'}
    execution=await ac.post('/v1/runtime/actions/begin',headers=headers,json={
        'execution_id':'exec-generic','command_id':body['command_id'],'action_id':'memory.remember',
        'principal_type':'OWNER_DEVICE','requested_by':body['requested_by'],'idempotency_key':'generic-action',
        'snapshot_id':result['context_snapshot_id'],'parameters':{'subject':'OWNER','predicate':'fake','value':'fake'},
    })
    assert execution.status_code==200
    await ac.post('/v1/runtime/actions/exec-generic/submitted',headers=headers,json={'correlation':{'fact_id':'fake'}})
    receipt=await ac.post('/v1/runtime/actions/verify',headers=headers,json={
        'execution_id':'exec-generic','success':True,'correlation':{'fact_id':'fake'},
        'observed_postcondition':{'exists':True},'evidence_pointer':'model://claimed',
        'independent_observer':True,
    })
    assert receipt.status_code==200 and receipt.json()['status']=='UNVERIFIABLE'
    assert await app.state.store.fetchall('SELECT fact_id FROM owner_facts')==[]

@pytest.mark.asyncio
async def test_action_authorized_before_mission_cancel_cannot_start_afterwards(client):
    from van_gateway.action.service import ActionPolicyError
    ac,app=client
    device=await _pair(ac,app)
    body=await _request(app,device,action_class='A3')
    result=(await ac.post('/v1/commands',json=body)).json()
    execution=await ac.post('/v1/runtime/actions/begin',headers={'X-Van-Internal-Token':'trust-internal-token'},json={
        'execution_id':'exec-before-cancel','command_id':body['command_id'],'action_id':'memory.remember',
        'principal_type':'OWNER_DEVICE','requested_by':body['requested_by'],'idempotency_key':'before-cancel',
        'snapshot_id':result['context_snapshot_id'],'parameters':{'subject':'OWNER','predicate':'fake','value':'fake'},
    })
    assert execution.json()['status']=='AUTHORIZED'
    await ac.post(f"/v1/missions/{result['mission_id']}/cancel")
    with pytest.raises(ActionPolicyError,match='command_mission_terminal'):
        await app.state.owner_runtime.actions.mark_executing('exec-before-cancel')
    assert (await app.state.owner_runtime.actions.get_execution('exec-before-cancel')).status.value=='AUTHORIZED'
