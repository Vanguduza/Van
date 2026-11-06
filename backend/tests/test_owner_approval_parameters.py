"""The values presented to the owner are part of the one-use A4 intent."""
import base64

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from conftest_automation import make_store
from test_gateway import _clear_settings_cache, _pair_for_test, client
from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService
from van_gateway.auth.service import AuthService


async def _approval(tmp_path, parameters):
    store = await make_store(tmp_path)
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    await store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES (?,?,?)", ("owner", public, 1000))
    service = OwnerApprovalService(store)
    identity = {"device_id": "owner", "source_command_id": "original-command", "turn_id": "owner-turn",
                "action_id": "trading.halt", "text": "halt trading", "project_id": None}
    challenge = await service.issue(**identity, parameters=parameters, now_unix=1000)
    proof = base64.b64encode(key.sign(challenge.canonical.encode(), ec.ECDSA(hashes.SHA256()))).decode()
    return service, challenge, identity, proof


@pytest.mark.asyncio
async def test_changed_resolution_values_refuse_without_consuming_original_approval(tmp_path):
    service, challenge, identity, proof = await _approval(tmp_path, {"scope": "autonomous", "account": "Demo"})
    for parameters in ({"scope": "all", "account": "Demo"}, {"scope": "autonomous", "account": "Live"}, None):
        with pytest.raises(OwnerApprovalError, match="approval_parameters_changed"):
            await service.verify_and_consume(**identity, challenge_id=challenge.challenge_id,
                                             signature_b64=proof, parameters=parameters, now_unix=1001)
        assert await service.store.fetchone("SELECT key FROM runtime_meta WHERE key=?", (service.PREFIX + challenge.challenge_id,))
    await service.verify_and_consume(**identity, challenge_id=challenge.challenge_id, signature_b64=proof,
                                    parameters={"account": "Demo", "scope": "autonomous"}, now_unix=1001)
    assert not await service.store.fetchone("SELECT key FROM runtime_meta WHERE key=?", (service.PREFIX + challenge.challenge_id,))


@pytest.mark.asyncio
async def test_old_text_only_challenge_cannot_authorize_new_parameter_bound_gateway_path(tmp_path):
    service, challenge, identity, proof = await _approval(tmp_path, None)
    with pytest.raises(OwnerApprovalError, match="approval_parameters_not_bound"):
        await service.verify_and_consume(**identity, challenge_id=challenge.challenge_id,
                                         signature_b64=proof, parameters={}, now_unix=1001)
    # An existing service caller whose contract is text-only retains its old semantics.
    await service.verify_and_consume(**identity, challenge_id=challenge.challenge_id, signature_b64=proof, now_unix=1001)


@pytest.mark.asyncio
async def test_gateway_exposes_exact_normalized_parameters_in_biometric_request(client):
    import time
    ac, app = client
    await _pair_for_test(ac, app, "parameter-owner", "test-parameter-secret")
    issued, text = int(time.time()), "delete notebook enterprise notebook id DemoCase_1"
    canonical = AuthService.canonical_command("parameter-command", "parameter-key", "parameter-owner", issued, text, "A1", None)
    response = await ac.post("/v1/commands", json={
        "command_id": "parameter-command", "idempotency_key": "parameter-key", "device_id": "parameter-owner",
        "issued_at_unix": issued, "signature": app.state.auth.sign("parameter-owner", canonical), "text": text, "action_class": "A1",
    })
    result = response.json()
    assert result["status"] == "approval_required"
    assert result["resolved_action_id"] == "google.notebook.enterprise.delete"
    assert result["resolved_parameters"] == {"notebook_id": "DemoCase_1"}
    record = await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",
                                           (OwnerApprovalService.PREFIX + result["approval_challenge_id"],))
    import json
    assert json.loads(record["value"])["parameters_bound"] is True
