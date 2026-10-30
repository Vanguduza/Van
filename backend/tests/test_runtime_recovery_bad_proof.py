"""Malformed private proof identities fail before ledger lookup or execution."""
from dataclasses import replace
import json

import pytest
from fastapi.testclient import TestClient

from test_runtime_recovery_protocol import owner_proof, NOW
from commander.app import CommanderSettings, create_app
from commander.auth import sign_headers
from vati.app.runtime_control_protocol import RecoveryProof, RuntimeControlError
from vati.app.runtime_control_journal import RuntimeControlJournal
from vati.core import Ledger


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('operation_id', []), ('operation_id', {}),
    ('operation_id', False), ('operation_id', ''), ('operation_id', 'not an operation'),
    ('expires_at_unix', True), ('expires_at_unix', '1800000060'), ('expires_at_unix', -1)])
async def test_closed_proof_contract_rejects_bad_original_identity_and_expiry(owner_proof, field, value):
    _, proof, _ = await owner_proof(); body = proof.public_record(); body[field] = value
    with pytest.raises(RuntimeControlError): RecoveryProof.from_mapping(body)


@pytest.mark.asyncio
async def test_direct_dataclass_cannot_bypass_native_journal_identity_gate(tmp_path, owner_proof):
    intent, proof, keys = await owner_proof(); ledger = Ledger(tmp_path/'bad-proof.sqlite')
    try:
        journal = RuntimeControlJournal(ledger, clock=lambda: NOW)
        with pytest.raises(RuntimeControlError): journal.enqueue(intent, replace(proof, operation_id=[]), keys)
        assert ledger.count()==0
        assert journal.status([], intent.device_id) is None
    finally: ledger.close()


@pytest.mark.asyncio
async def test_authenticated_native_http_reports_a_shape_refusal_instead_of_internal_error(tmp_path, owner_proof):
    intent, proof, _ = await owner_proof(); bad = proof.public_record(); bad['operation_id'] = []
    token = 'source-native-gateway-token-'+'x'*20
    settings = CommanderSettings(tokens={'van-gateway':token}, ledger=str(tmp_path/'native.sqlite'),
        owner_authority_keys=str(tmp_path/'keys.json'), log_dir=str(tmp_path/'logs'),
        accounts_registry=str(tmp_path/'accounts.json'), secrets_dir=str(tmp_path/'secrets'))
    path = '/v1/cmd/runtime_recovery_request'
    body = json.dumps({'args':{'intent':intent.body(),'proof':bad}}).encode()
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.post(path, content=body, headers=sign_headers(token,'POST',path,body))
    assert response.status_code==403, response.text
    assert 'original operation identity is invalid' in response.json()['detail']
    ledger = Ledger(settings.ledger)
    try: assert ledger.count()==0
    finally: ledger.close()
