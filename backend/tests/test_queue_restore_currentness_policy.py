"""LAC234 SOURCE currentness/proof facts are not a grant to discard local data."""
import pytest
from test_device_proof_enforcement import client, _settings, _paired, _bind, _proof_headers, _base_headers
from van_gateway.config import get_settings

STATUS = "/v1/device-binding/status"


@pytest.fixture(autouse=True)
def no_scheduler(monkeypatch):
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")


@pytest.mark.asyncio
async def test_unsigned_legacy_status_preserves_policy_without_issuing_authority(client):
    ac, app = client
    enrolled = await _paired(app)
    before = [dict(r) for r in await app.state.store.fetchall("SELECT * FROM capability_grants")]
    response = await ac.get(STATUS, headers=_base_headers(enrolled))
    assert response.status_code == 200, response.text
    assert response.json()["owner_mutation_policy"] == dict(binding_required=False, proof_required=False, eligible=True, reason=None)
    assert response.json()["current_request_proof_verified"] is False
    assert response.headers["cache-control"] == "no-store"
    assert [dict(r) for r in await app.state.store.fetchall("SELECT * FROM capability_grants")] == before
    assert await app.state.store.fetchall("SELECT * FROM command_nonces") == []
    assert await app.state.store.fetchall("SELECT * FROM idempotency") == []


@pytest.mark.asyncio
async def test_strict_absent_binding_read_fact_matches_actual_mutation_gate(client, monkeypatch):
    ac, app = client
    enrolled = await _paired(app)
    monkeypatch.setattr(get_settings(), "require_device_binding", True)
    response = await ac.get(STATUS, headers=_base_headers(enrolled))
    assert response.status_code == 200
    policy = response.json()["owner_mutation_policy"]
    assert policy["eligible"] is False and policy["binding_required"] is True
    mutation = await ac.post("/v1/session/open", json={}, headers=_base_headers(enrolled))
    assert mutation.status_code == 403
    assert mutation.json()["detail"] == policy["reason"] == "device_not_bound"


@pytest.mark.asyncio
async def test_current_bound_read_proof_is_exact_fresh_single_use_and_no_grant(client):
    ac, app = client
    enrolled = await _paired(app)
    device = enrolled.device.device_id
    key = await _bind(app, device)  # Existing SOURCE attestation fixture only.
    grants = [dict(r) for r in await app.state.store.fetchall("SELECT * FROM capability_grants")]
    unsigned = await ac.get(STATUS, headers=_base_headers(enrolled))
    assert unsigned.status_code == 200 and unsigned.json()["owner_mutation_policy"]["eligible"]
    assert unsigned.json()["owner_mutation_policy"]["proof_required"]
    assert not unsigned.json()["current_request_proof_verified"]
    assert await app.state.store.fetchall("SELECT * FROM command_nonces") == []
    proof = _proof_headers(key, method="GET", path=STATUS, device_id=device, body=b"")
    response = await ac.get(STATUS, headers={**_base_headers(enrolled), **proof})
    assert response.status_code == 200, response.text
    assert response.json()["current_request_proof_verified"] is True
    assert str(response.json()["current_request_proof_issued_at_ms"]) == proof["X-Van-Device-Proof-Issued-At"]
    assert response.headers["cache-control"] == "no-store"
    replayed = await ac.get(STATUS, headers={**_base_headers(enrolled), **proof})
    assert replayed.status_code == 401 and replayed.json()["detail"] == "device_proof_replayed"
    invalid = _proof_headers(key, method="GET", path="/v1/other", device_id=device, body=b"")
    refused = await ac.get(STATUS, headers={**_base_headers(enrolled), **invalid})
    assert refused.status_code == 401
    assert len(await app.state.store.fetchall("SELECT * FROM command_nonces")) == 1
    assert [dict(r) for r in await app.state.store.fetchall("SELECT * FROM capability_grants")] == grants
    assert await app.state.store.fetchall("SELECT * FROM idempotency") == []


@pytest.mark.asyncio
async def test_foreign_active_owner_fact_has_no_foreign_identity_and_matches_mutation(client):
    ac, app = client
    owner = await _paired(app, "SOURCE-primary-owner")
    await _bind(app, owner.device.device_id)
    other = await _paired(app, "SOURCE-other-owner")
    response = await ac.get(STATUS, headers=_base_headers(other))
    assert response.status_code == 200
    policy = response.json()["owner_mutation_policy"]
    assert not policy["eligible"] and policy["reason"] == "device_not_owner_device"
    assert owner.device.device_id not in response.text
    assert "device_key_fingerprint" not in response.json()
    mutation = await ac.post("/v1/session/open", json={}, headers=_base_headers(other))
    assert mutation.status_code == 403 and mutation.json()["detail"] == policy["reason"]


@pytest.mark.asyncio
async def test_retired_binding_cannot_fall_back_to_legacy_owner_policy(client):
    ac, app = client
    enrolled = await _paired(app)
    await _bind(app, enrolled.device.device_id)
    await app.state.owner_device_bindings.revoke(reason="SOURCE-retirement-before-paired-reconciliation")
    response = await ac.get(STATUS, headers=_base_headers(enrolled))
    assert response.status_code == 200
    assert response.json()["status"] == "REVOKED"
    policy = response.json()["owner_mutation_policy"]
    assert not policy["eligible"] and policy["reason"] == "device_binding_not_active"
    mutation = await ac.post("/v1/session/open", json={}, headers=_base_headers(enrolled))
    assert mutation.status_code == 403 and mutation.json()["detail"] == policy["reason"]
