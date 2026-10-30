"""Cold gateway dispatch from durable exact owner receipts, never renewed consent."""
import json

import pytest

from test_runtime_recovery_gateway import client, _env, session_control, prepare, BASE
from vati.core import EventKind
from vati.risk.contracts import KillSwitchTrigger


def dispatcher(app):
    value = getattr(app.state, 'runtime_recovery_dispatcher', None)
    assert value is not None, 'The gateway needs a durable recovery dispatcher, not another phone POST'
    # A new instance must recover solely from the durable store after process death.
    return type(value)(store=app.state.store, auth=app.state.auth,
                       promotions=app.state.strategy_promotions)


@pytest.mark.asyncio
async def test_cold_gateway_recovers_original_without_phone_resubmission(client, session_control):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    transport.fail_before_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    assert (await ac.get(BASE+'/operations/'+op)).json()['phase'] == 'PENDING_DISPATCH'
    assert transport.calls.count('runtime_recovery_request') == 1  # GET did not dispatch.
    report = await dispatcher(app).reconcile_once()
    assert report['delivered'] == 1 and report['deferred'] == 0
    assert (await ac.get(BASE+'/operations/'+op)).json()['phase'] == 'REQUESTED'
    service.step_once()
    final = (await ac.get(BASE+'/operations/'+op)).json()
    assert final['phase'] == 'APPLIED' and final['operation_id'] == op
    assert not service.runner.cycle.kill.halted
    await dispatcher(app).reconcile_once()
    assert transport.calls.count('runtime_recovery_request') == 2
    assert len([e for e in service._ledger.iter(EventKind.KILL_SWITCH) if e.payload.get('cleared')]) == 1
    assert service._ledger.count(EventKind.ORDER_COMMAND) == 0


@pytest.mark.asyncio
async def test_expired_never_delivered_original_gets_native_no_effect_receipt(client, session_control, monkeypatch):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    transport.fail_before_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    import commander.runtime_controls as native
    from vati.app.runtime_control_journal import RuntimeControlJournal
    monkeypatch.setattr(native, 'RuntimeControlJournal',
        lambda ledger: RuntimeControlJournal(ledger, clock=lambda:body['approval_proof']['expires_at_unix']+1))
    report = await dispatcher(app).reconcile_once()
    assert report['delivered'] == 1 and report['deferred'] == 0
    final = (await ac.get(BASE+'/operations/'+op)).json()
    assert final['phase'] == 'REFUSED' and final['result']['reason_code'] == 'APPROVAL_EXPIRED'
    assert final['result']['effect_refs'] == [] and final['result']['entry_authority_granted'] is False
    # No actor/current-market observation occurred: unknown current state must stay unknown.
    assert final['result']['remaining_kill'] is None and final['result']['state_ref'] is None
    assert len(final['native_event_ref']) == 64
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active
    assert not any(e.payload.get('cleared') for e in service._ledger.iter(EventKind.KILL_SWITCH))
    assert service._ledger.count(EventKind.ORDER_COMMAND) == 0


@pytest.mark.asyncio
async def test_lost_native_ack_is_read_back_not_dispatched_again(client, session_control):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    transport.lose_after_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    assert (await dispatcher(app).reconcile_once())['delivered'] == 1
    assert transport.calls.count('runtime_recovery_request') == 1
    service.step_once()
    assert (await ac.get(BASE+'/operations/'+op)).json()['phase'] == 'APPLIED'
    await dispatcher(app).reconcile_once()
    assert transport.calls.count('runtime_recovery_request') == 1


@pytest.mark.asyncio
async def test_revoked_device_receipt_is_retained_without_native_dispatch(client, session_control):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    transport.fail_before_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    await app.state.auth.revoke(body['intent']['device_id'])
    report = await dispatcher(app).reconcile_once()
    assert report['delivered'] == 0 and report['deferred'] == 1
    assert transport.calls.count('runtime_recovery_request') == 1
    row = await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?', ('owner_approval_receipt:'+op,))
    assert json.loads(row['value'])['context']['intent'] == body['intent']
    assert service._ledger.count(EventKind.ORDER_COMMAND) == 0


@pytest.mark.asyncio
async def test_one_corrupt_old_receipt_cannot_starve_original_dispatch(client, session_control):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    transport.fail_before_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    # Sorts ahead of every real base64-url operation ID.
    bad = 'owner_approval_receipt:!corrupt'
    await app.state.store.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)', (bad,'not-json',0))
    runner = dispatcher(app)
    first = await runner.reconcile_once(limit=1)
    assert first['deferred'] == 1 and first['delivered'] == 0
    assert (await runner.reconcile_once(limit=1))['delivered'] == 1
    assert (await ac.get(BASE+'/operations/'+op)).json()['phase'] == 'REQUESTED'
    assert (await runner.reconcile_once(limit=1))['deferred'] == 1  # wraps fairly, retains bad receipt


@pytest.mark.asyncio
async def test_delivery_marker_failure_recovers_native_original_instead_of_resending(client, session_control, monkeypatch):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    transport.fail_before_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    execute = app.state.store.execute
    async def fail_marker(sql, args=()):
        if args and args[0] == 'runtime_recovery_delivered:'+op:
            raise OSError('fixture lost gateway delivery marker commit')
        return await execute(sql,args)
    with monkeypatch.context() as scoped:
        scoped.setattr(app.state.store,'execute',fail_marker)
        assert (await dispatcher(app).reconcile_once())['deferred'] == 1
    assert (await dispatcher(app).reconcile_once())['delivered'] == 1
    assert transport.calls.count('runtime_recovery_request') == 2  # initial lost-before + one real dispatch
    service.step_once()
    assert (await ac.get(BASE+'/operations/'+op)).json()['phase'] == 'APPLIED'


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['device_id','expires_at_unix','intent_digest','operation_id','other_valid_digest'])
async def test_corrupt_receipt_metadata_never_dispatches(client, session_control, field):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    transport.fail_before_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    row = await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('owner_approval_receipt:'+op,))
    saved = json.loads(row['value'])
    if field=='other_valid_digest':
        from vati.app.runtime_control_protocol import RecoveryIntent
        intent=RecoveryIntent.from_mapping(saved['context']['intent'])
        assert saved['intent_digest']==intent.structured_intent_digest
        saved['intent_digest']=intent.intent_digest
    else:
        saved[field] = saved[field]+1 if field=='expires_at_unix' else 'foreign'
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps(saved),'owner_approval_receipt:'+op))
    assert (await dispatcher(app).reconcile_once())['deferred'] == 1
    assert transport.calls.count('runtime_recovery_request') == 1
    assert service._ledger.count(EventKind.ORDER_COMMAND) == 0


@pytest.mark.asyncio
async def test_recovery_dispatch_background_worker_is_started_and_awaited_on_shutdown(client, monkeypatch):
    import asyncio
    _, app = client
    runner = getattr(app.state,'runtime_recovery_dispatcher',None)
    assert runner is not None
    started, stopped = asyncio.Event(), asyncio.Event()
    async def worker():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    monkeypatch.setattr(runner,'run',worker)
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(),2)
        assert not stopped.is_set()
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_invalid_archived_signature_is_not_forwarded_to_native(client, session_control):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    transport.fail_before_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    row = await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('owner_approval_receipt:'+op,))
    saved = json.loads(row['value']); saved['context']['proof']['signature_b64']='AAAA'
    await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps(saved),'owner_approval_receipt:'+op))
    assert (await dispatcher(app).reconcile_once())['deferred'] == 1
    assert transport.calls.count('runtime_recovery_request') == 1


@pytest.mark.asyncio
async def test_owner_key_change_during_enrollment_prevents_dispatch(client, session_control, monkeypatch):
    import asyncio
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service)
    transport.fail_before_enqueue = True
    assert (await ac.post(BASE+'/request', json=body)).status_code == 503
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    enroll = app.state.strategy_promotions.ensure_owner_authority
    def change_owner(**kwargs):
        result = enroll(**kwargs)
        asyncio.run(app.state.store.execute('UPDATE devices SET public_key_pem=? WHERE device_id=?',
            (pem,body['intent']['device_id'])))
        return result
    monkeypatch.setattr(app.state.strategy_promotions,'ensure_owner_authority',change_owner)
    assert (await dispatcher(app).reconcile_once())['deferred'] == 1
    assert transport.calls.count('runtime_recovery_request') == 1
