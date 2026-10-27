"""Stored fields cannot rebind an authentic signature to another approval."""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from test_owner_approval_parameters import _approval
from test_gateway import _clear_settings_cache, _pair_for_test, client
from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService
from van_gateway.auth.service import AuthService


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', ['action', 'turn', 'command', 'parameters', 'unbound', 'expiry', 'challenge'])
async def test_corrupt_record_cannot_repurpose_original_signed_canonical(tmp_path, changed):
    original_parameters = {'account': 'Demo', 'scope': 'autonomous'}
    service, challenge, identity, proof = await _approval(tmp_path, original_parameters)
    key = service.PREFIX + challenge.challenge_id
    row = await service.store.fetchone('SELECT value FROM runtime_meta WHERE key=?', (key,))
    original = row['value']
    record = json.loads(original)
    requested = dict(identity)
    parameters = dict(original_parameters)
    now = 1001
    if changed == 'action':
        requested['action_id'] = record['action_id'] = 'trading.owner_halt'
    elif changed == 'turn':
        requested['turn_id'] = record['turn_id'] = 'another-turn'
    elif changed == 'command':
        requested['source_command_id'] = record['source_command_id'] = 'another-command'
    elif changed == 'parameters':
        parameters = {'account': 'Live', 'scope': 'all'}
        record['parameters'] = parameters
    elif changed == 'unbound':
        parameters = None
        record['parameters_bound'] = False
        record['parameters'] = None
    elif changed == 'expiry':
        now = challenge.expires_at_unix + 1
        record['expires_at_unix'] += 60
    elif changed == 'challenge':
        record['challenge_id'] = 'another-challenge'
    record['intent_digest'] = service.intent_digest(
        device_id=requested['device_id'], action_id=requested['action_id'], text=requested['text'],
        project_id=requested['project_id'], parameters=parameters)
    # Original canonical and genuine test-key signature remain byte-identical.
    assert record['canonical'] == challenge.canonical
    await service.store.execute('UPDATE runtime_meta SET value=? WHERE key=?', (json.dumps(record), key))
    with pytest.raises(OwnerApprovalError, match='approval_challenge_binding_corrupt'):
        await service.verify_and_consume(
            **requested, parameters=parameters, challenge_id=challenge.challenge_id,
            signature_b64=proof, now_unix=now, durable_receipt={'request_id': 'original-recovery-request'})
    assert await service.store.fetchone('SELECT key FROM runtime_meta WHERE key=?', (key,))
    assert not await service.store.fetchone('SELECT key FROM runtime_meta WHERE key=?',
                                            ('owner_approval_receipt:' + challenge.challenge_id,))
    if changed != 'expiry':
        await service.store.execute('UPDATE runtime_meta SET value=? WHERE key=?', (original, key))
        verified = await service.verify_and_consume(
            **identity, parameters=original_parameters, challenge_id=challenge.challenge_id,
            signature_b64=proof, now_unix=now)
        assert verified['operation_id'] == challenge.challenge_id


@pytest.mark.parametrize('left,right', [
    ({'project_id': 'project|text', 'text': 'tail'}, {'project_id': 'project', 'text': 'text|tail'}),
    ({'text': 'pay|{"x":1}', 'parameters': None}, {'text': 'pay', 'parameters': {'x': 1}}),
    ({'device_id': 'device|action', 'action_id': 'id'}, {'device_id': 'device', 'action_id': 'action|id'}),
])
def test_structured_intents_distinguish_real_legacy_delimiter_collisions(left, right):
    original = dict(device_id='owner', action_id='trading.halt', text='halt trading', project_id=None,
                    parameters=None)
    a, b = original | left, original | right
    assert OwnerApprovalService._legacy_intent_digest(**a) == OwnerApprovalService._legacy_intent_digest(**b)
    assert OwnerApprovalService.intent_digest(**a) != OwnerApprovalService.intent_digest(**b)


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['halt trading', 'halt | trading'])
async def test_actual_signed_legacy_challenge_uses_original_unambiguous_encoding(tmp_path, text):
    parameters = {'account': 'Demo', 'scope': 'autonomous'}
    service, challenge, identity, _ = await _approval(tmp_path, parameters)
    identity['text'] = text
    row = await service.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',
                                     (service.PREFIX + challenge.challenge_id,))
    record = json.loads(row['value'])
    record.pop('intent_digest_schema')
    record['intent_digest'] = service._legacy_intent_digest(
        device_id=identity['device_id'], action_id=identity['action_id'], text=text,
        project_id=None, parameters=parameters)
    record['canonical'] = service._canonical_challenge(
        challenge_id=challenge.challenge_id, device_id=identity['device_id'],
        source_command_id=identity['source_command_id'], turn_id=identity['turn_id'],
        action_id=identity['action_id'], intent_digest=record['intent_digest'],
        expires_at_unix=record['expires_at_unix'])
    signer = ec.generate_private_key(ec.SECP256R1())
    public = signer.public_key().public_bytes(serialization.Encoding.PEM,
                                              serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    await service.store.execute('UPDATE devices SET public_key_pem=? WHERE device_id=?',
                                (public, identity['device_id']))
    await service.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',
                                (json.dumps(record), service.PREFIX + challenge.challenge_id))
    proof = base64.b64encode(signer.sign(record['canonical'].encode(), ec.ECDSA(hashes.SHA256()))).decode()
    arguments = dict(**identity, parameters=parameters, challenge_id=challenge.challenge_id,
                     signature_b64=proof, now_unix=1001)
    if '|' in text:
        with pytest.raises(OwnerApprovalError, match='approval_challenge_binding_corrupt'):
            await service.verify_and_consume(**arguments)
        assert await service.store.fetchone('SELECT key FROM runtime_meta WHERE key=?',
                                             (service.PREFIX + challenge.challenge_id,))
    else:
        receipt = await service.verify_and_consume(**arguments)
        assert receipt['operation_id'] == challenge.challenge_id


@pytest.mark.asyncio
async def test_new_structured_challenge_keeps_pipe_text_and_one_use_signature(tmp_path):
    service, _, identity, _ = await _approval(tmp_path, None)
    identity['text'] = 'halt | trading'
    challenge = await service.issue(**identity, now_unix=1000)
    assert challenge.canonical.startswith('van-a4-approval-v2|')
    row = await service.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',
                                     (service.PREFIX + challenge.challenge_id,))
    assert json.loads(row['value'])['intent_digest_schema'] == service.INTENT_SCHEMA
    signer = ec.generate_private_key(ec.SECP256R1())
    public = signer.public_key().public_bytes(serialization.Encoding.PEM,
                                              serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    await service.store.execute('UPDATE devices SET public_key_pem=? WHERE device_id=?',
                                (public, identity['device_id']))
    proof = base64.b64encode(signer.sign(challenge.canonical.encode(), ec.ECDSA(hashes.SHA256()))).decode()
    arguments = dict(**identity, challenge_id=challenge.challenge_id, signature_b64=proof, now_unix=1001)
    assert (await service.verify_and_consume(**arguments))['operation_id'] == challenge.challenge_id
    with pytest.raises(OwnerApprovalError, match='approval_challenge_unknown_or_consumed'):
        await service.verify_and_consume(**arguments)


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['device_id', 'source_command_id', 'turn_id', 'action_id'])
async def test_unescaped_challenge_envelope_fields_refuse_before_issue(tmp_path, field):
    service, _, identity, _ = await _approval(tmp_path, None)
    identity[field] = 'ambiguous|field'
    before = await service.store.fetchone('SELECT COUNT(*) AS n FROM runtime_meta WHERE key LIKE ?',
                                         (service.PREFIX + '%',))
    with pytest.raises(OwnerApprovalError, match='approval_challenge_binding_corrupt'):
        await service.issue(**identity, now_unix=1000)
    after = await service.store.fetchone('SELECT COUNT(*) AS n FROM runtime_meta WHERE key LIKE ?',
                                        (service.PREFIX + '%',))
    assert after['n'] == before['n']


@pytest.mark.asyncio
@pytest.mark.parametrize('command_id,turn_id', [('ambiguous|command', None), ('original-command', 'ambiguous|turn')])
async def test_gateway_refuses_ambiguous_approval_lineage_without_issuing_or_dispatching(client, command_id, turn_id):
    ac, app = client
    await _pair_for_test(ac, app, 'binding-owner', 'test-binding-secret')
    issued, text = int(time.time()), 'delete notebook enterprise notebook id DemoCase_1'
    canonical = AuthService.canonical_command(command_id, 'binding-request', 'binding-owner', issued, text, 'A1', None)
    response = await ac.post('/v1/commands', json={
        'command_id': command_id, 'idempotency_key': 'binding-request', 'device_id': 'binding-owner',
        'issued_at_unix': issued, 'signature': app.state.auth.sign('binding-owner', canonical),
        'text': text, 'action_class': 'A1', 'turn_id': turn_id})
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'denied'
    assert not result.get('approval_challenge_id')
    assert not result.get('requires_approval')
    row = await app.state.store.fetchone('SELECT COUNT(*) AS n FROM runtime_meta WHERE key LIKE ?',
                                         (OwnerApprovalService.PREFIX + '%',))
    assert row['n'] == 0
    # The same native command readback retains the original refusal.
    replay = await ac.post('/v1/commands', json={
        'command_id': command_id, 'idempotency_key': 'binding-request', 'device_id': 'binding-owner',
        'issued_at_unix': issued, 'signature': app.state.auth.sign('binding-owner', canonical),
        'text': text, 'action_class': 'A1', 'turn_id': turn_id})
    assert replay.json()['status'] == 'denied'
