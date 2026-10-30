"""Existing gateway A4 CryptoObject statements bind exact native recovery."""
import base64
import hashlib
import json
from dataclasses import replace

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec

from van_gateway.approval.service import OwnerApprovalService
from van_gateway.storage.db import Store
from vati.app.runtime_control_protocol import RecoveryIntent,RecoveryProof,RuntimeControlError,approval_statement

NOW=1800000000


@pytest.mark.asyncio
async def test_current_gateway_signature_requires_its_actual_receipt_digest(owner_proof):
    intent,proof,keys=await owner_proof()
    reference=proof.verify(intent,keys,now_unix=NOW)
    assert proof.verify_signature(intent,keys,intent_digest=intent.structured_intent_digest)==reference
    with pytest.raises(RuntimeControlError,match='signature is invalid'):
        proof.verify_signature(intent,keys,intent_digest=intent.intent_digest)


@pytest.mark.asyncio
async def test_legacy_native_signature_keeps_original_reference_and_expiry(owner_proof):
    intent,current,_=await owner_proof()
    signer=ec.generate_private_key(ec.SECP256R1())
    public=signer.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    statement=approval_statement(intent,current.operation_id,current.expires_at_unix)
    signature=signer.sign(statement.encode(),ec.ECDSA(hashes.SHA256()))
    proof=replace(current,signature_b64=base64.b64encode(signature).decode())
    keys={proof.key_id:public}
    original='owner-runtime-control:'+hashlib.sha256(statement.encode()+b'\n'+signature).hexdigest()
    assert proof.verify(intent,keys,now_unix=NOW)==original
    assert proof.verify_signature(intent,keys,intent_digest=intent.intent_digest)==original
    with pytest.raises(RuntimeControlError,match='signature is invalid'):
        proof.verify_signature(intent,keys,intent_digest=intent.structured_intent_digest)
    with pytest.raises(RuntimeControlError,match='expired'):
        proof.verify(intent,keys,now_unix=proof.expires_at_unix)


@pytest.mark.asyncio
async def test_unconsumed_legacy_native_challenge_keeps_exact_fresh_one_use_authority(tmp_path,owner_proof):
    intent,_,_=await owner_proof()
    store=Store(str(tmp_path/'legacy-native-approval.sqlite'));await store.migrate()
    approvals=OwnerApprovalService(store)
    signer=ec.generate_private_key(ec.SECP256R1())
    public=signer.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    await store.execute('INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES(?,?,?)',
                        (intent.device_id,public,NOW))
    identity=dict(device_id=intent.device_id,source_command_id='runtime:'+intent.action,turn_id=None,
                  action_id=intent.action_id,text=intent.approval_text,project_id=None)
    challenge=await approvals.issue(**identity,now_unix=NOW)
    row=await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(approvals.PREFIX+challenge.challenge_id,))
    record=json.loads(row['value']);record.pop('intent_digest_schema')
    record['intent_digest']=intent.intent_digest
    record['canonical']=approval_statement(intent,challenge.challenge_id,challenge.expires_at_unix)
    await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',
                        (json.dumps(record),approvals.PREFIX+challenge.challenge_id))
    signature=base64.b64encode(signer.sign(record['canonical'].encode(),ec.ECDSA(hashes.SHA256()))).decode()
    proof=RecoveryProof(challenge.challenge_id,challenge.expires_at_unix,'legacy-fixture-key',signature)
    arguments=dict(**identity,challenge_id=challenge.challenge_id,signature_b64=signature,now_unix=NOW+1)
    context={'intent':intent.body(),'proof':proof.public_record()}
    await approvals.verify_and_consume(**arguments,durable_receipt=context)
    saved=json.loads((await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',
                     ('owner_approval_receipt:'+challenge.challenge_id,)))['value'])
    assert saved['intent_digest']==intent.intent_digest
    assert proof.verify_signature(intent,{proof.key_id:public},intent_digest=saved['intent_digest'])
    from van_gateway.approval.service import OwnerApprovalError
    with pytest.raises(OwnerApprovalError,match='unknown_or_consumed'):
        await approvals.verify_and_consume(**arguments)


@pytest_asyncio.fixture
async def owner_proof(tmp_path):
    store=Store(str(tmp_path/'native-owner-approval.sqlite'));await store.migrate()
    approvals=OwnerApprovalService(store)
    key=ec.generate_private_key(ec.SECP256R1())
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    async def issue(action='clear_kill_switch',args=None):
        if args is None:args={'trigger':'OWNER_HALT'}
        intent=RecoveryIntent.from_mapping({'schema':'vati.runtime-recovery/1','device_id':'owner-s24',
            'account_alias':'owner_demo','session_id':'owner_demo:EURUSD:original-instance',
            'action':action,'state_ref':'a'*64,'issued_at_unix':NOW,'args':args})
        challenge=await approvals.issue(device_id=intent.device_id,source_command_id='runtime:'+action,
            turn_id=None,action_id=intent.action_id,text=intent.approval_text,project_id=None,now_unix=NOW)
        signature=key.sign(challenge.canonical.encode(),ec.ECDSA(hashes.SHA256()))
        proof=RecoveryProof(challenge.challenge_id,challenge.expires_at_unix,'owner-device-key',base64.b64encode(signature).decode())
        return intent,proof,{'owner-device-key':public}
    return issue


@pytest.mark.asyncio
@pytest.mark.parametrize(('action','args'),[
    ('clear_kill_switch',{'trigger':'OWNER_HALT'}),
    ('reset_loss_streak',{'scope':'*ACCOUNT*'}),('resume_drawdown',{})])
async def test_real_gateway_a4_statement_proves_only_the_exact_recovery_intent(owner_proof,action,args):
    intent,proof,keys=await owner_proof(action,args)
    reference=proof.verify(intent,keys,now_unix=NOW)
    assert reference.startswith('owner-runtime-control:')
    assert proof.verify(RecoveryIntent.from_mapping(intent.body()),keys,now_unix=NOW+1)==reference


@pytest.mark.asyncio
@pytest.mark.parametrize('field',['device_id','account_alias','session_id','state_ref','issued_at_unix','args','action'])
async def test_a4_proof_cannot_move_to_another_device_session_state_or_recovery(owner_proof,field):
    intent,proof,keys=await owner_proof();body=intent.body()
    changes={'device_id':'other-owner','account_alias':'other_account','session_id':'owner_demo:EURUSD:new-instance',
        'state_ref':'b'*64,'issued_at_unix':NOW+1,'args':{'trigger':'VENUE_DISCONNECT'},'action':'reset_loss_streak'}
    body[field]=changes[field]
    if field=='action':body['args']={'scope':'*ACCOUNT*'}
    altered=RecoveryIntent.from_mapping(body)
    with pytest.raises(RuntimeControlError,match='signature is invalid'):proof.verify(altered,keys,now_unix=NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize('field',['operation_id','expires_at_unix'])
async def test_approval_cannot_be_rebound_to_a_new_operation_or_expiry(owner_proof,field):
    intent,proof,keys=await owner_proof()
    altered=replace(proof,**{field:'new-original-operation-identity' if field=='operation_id' else proof.expires_at_unix+1})
    with pytest.raises(RuntimeControlError,match='signature is invalid'):altered.verify(intent,keys,now_unix=NOW)


@pytest.mark.asyncio
async def test_expired_unregistered_and_malformed_proof_cannot_authorize_recovery(owner_proof):
    intent,proof,keys=await owner_proof()
    with pytest.raises(RuntimeControlError,match='expired'):proof.verify(intent,keys,now_unix=proof.expires_at_unix)
    with pytest.raises(RuntimeControlError,match='not currently registered'):proof.verify(intent,{},now_unix=NOW)
    with pytest.raises(RuntimeControlError,match='signature is invalid'):replace(proof,signature_b64='not-base64!').verify(intent,keys,now_unix=NOW)


@pytest.mark.asyncio
async def test_intent_copies_arguments_before_owner_confirmation(owner_proof):
    intent,proof,keys=await owner_proof();body=intent.body();copy=RecoveryIntent.from_mapping(body)
    body['args']['trigger']='VENUE_DISCONNECT'
    assert dict(copy.arguments)=={'trigger':'OWNER_HALT'}
    assert proof.verify(copy,keys,now_unix=NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize('field_value',[('unknown','secret'),('issued_at_unix',True),('args',{'trigger':'NOT_A_TRIGGER'}),('device_id','owner|other')])
async def test_closed_recovery_contract_refuses_ambiguous_fields(owner_proof,field_value):
    intent,_,_=await owner_proof();body=intent.body();field,value=field_value;body[field]=value
    with pytest.raises(RuntimeControlError):RecoveryIntent.from_mapping(body)
