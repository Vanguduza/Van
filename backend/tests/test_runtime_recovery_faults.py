"""Owner boundaries and atomic consumed-approval/public-receipt crash recovery."""
from contextlib import asynccontextmanager
import json

import pytest

from test_runtime_recovery_gateway import client, _env, session_control, prepare, BASE
from test_trading_api import HDR, DEVICE_PEM


@pytest.mark.asyncio
async def test_another_paired_device_cannot_read_or_retarget_the_original_recovery(client, session_control):
    ac, _ = client; service, _, _ = session_control
    body = await prepare(ac, service)
    accepted = await ac.post(BASE+'/request', json=body)
    assert accepted.status_code==200, accepted.text
    ticket = await ac.post('/v1/devices/pairing-ticket', json={'label':'other','ttl_seconds':600}, headers=HDR)
    paired = await ac.post('/v1/devices/pair', json={'pairing_token':ticket.json()['pairing_token'],
        'device_id':'other-owner-device','device_secret':'other-owner-secret','public_key_pem':DEVICE_PEM,'label':'other'})
    assert paired.status_code==200, paired.text
    headers = {'X-Van-Ingress-Token':paired.json()['ingress_token'], 'X-Van-Device-Token':paired.json()['device_access_token']}
    foreign = await ac.get(BASE+'/operations/'+body['approval_proof']['challenge_id'], headers=headers)
    assert foreign.status_code==404, foreign.text
    changed = await ac.post(BASE+'/request', json=body, headers=headers)
    assert changed.status_code==403, changed.text


@pytest.mark.asyncio
async def test_expiry_is_part_of_the_actual_cryptographic_statement_not_a_client_override(client, session_control):
    ac, _ = client; service, _, _ = session_control
    body = await prepare(ac, service)
    original = body['approval_proof']['expires_at_unix']
    body['approval_proof']['expires_at_unix'] = original+1
    assert (await ac.post(BASE+'/request', json=body)).status_code==403
    body['approval_proof']['expires_at_unix'] = original
    assert (await ac.post(BASE+'/request', json=body)).status_code==200


@pytest.mark.asyncio
async def test_failure_before_approval_commit_restores_both_challenge_and_dispatch_receipt(client, session_control, monkeypatch):
    ac, app = client; service, _, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    store = app.state.store; connect = store.connection
    @asynccontextmanager
    async def fail_receipt_write():
        async with connect() as db:
            execute = db.execute
            async def failed(sql, parameters=()):
                result = await execute(sql, parameters)
                if sql.startswith('INSERT INTO runtime_meta') and parameters[0]=='owner_approval_receipt:'+op:
                    raise OSError('fixture crash before shared approval/receipt commit')
                return result
            db.execute = failed
            yield db
    from vati.app.runtime_control_protocol import RecoveryIntent
    intent = RecoveryIntent.from_mapping(body['intent'])
    with monkeypatch.context() as scoped:
        scoped.setattr(store, 'connection', fail_receipt_write)
        with pytest.raises(OSError, match='before shared approval/receipt commit'):
            await app.state.orchestrator.approvals.verify_and_consume(challenge_id=op,
                source_command_id='runtime:'+intent.action, device_id=intent.device_id, turn_id=None,
                action_id=intent.action_id, text=intent.approval_text, project_id=None,
                signature_b64=body['approval_proof']['signature_b64'], durable_receipt={'intent':intent.body()})
    assert await store.fetchone('SELECT value FROM runtime_meta WHERE key=?', ('owner_approval:'+op,))
    assert await store.fetchone('SELECT value FROM runtime_meta WHERE key=?', ('owner_approval_receipt:'+op,)) is None
    retried = await ac.post(BASE+'/request', json=body)
    assert retried.status_code==200 and retried.json()['phase']=='REQUESTED', retried.text
