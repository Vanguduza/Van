"""Speaker consent uses both actual gateway-enrolled public identities."""
import hashlib

from cryptography.hazmat.primitives import serialization

from test_device_proof_enforcement import client, _settings, _base_headers, _bind  # noqa: F401
from test_owner_device_binding import _keypair


async def test_binding_status_reports_approval_identity_separately_from_hardware_identity(client):
    ac, app = client
    approval_pem, approval_key = _keypair()
    ticket = await app.state.auth.create_pairing_ticket("speaker-test")
    paired = await app.state.auth.pair_device(ticket.token, "speaker-test", "s" * 32, approval_pem, "speaker-test")
    hardware_key = await _bind(app, paired.device.device_id)
    response = await ac.get("/v1/device-binding/status", headers=_base_headers(paired))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["device_id"] == paired.device.device_id and result["status"] == "ACTIVE"
    assert result["binding_id"] and result["owner_principal_id"]
    fingerprint = lambda key: hashlib.sha256(key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
    assert result["owner_approval_key_fingerprint"] == fingerprint(approval_key)
    assert result["device_key_fingerprint"] == fingerprint(hardware_key)
    assert result["owner_approval_key_fingerprint"] != result["device_key_fingerprint"]
    # This fixture has no actual attestation chain. A public identity alone may
    # not make the Android enrollment policy treat it as attested owner consent.
    assert result["attestation_chain_verified"] is False


async def test_unbound_or_revoked_pairing_never_supplies_enrollment_binding(client):
    ac, app = client
    pem, _ = _keypair()
    ticket = await app.state.auth.create_pairing_ticket("speaker-unbound")
    paired = await app.state.auth.pair_device(ticket.token, "speaker-unbound", "s" * 32, pem, "speaker-unbound")
    unbound = await ac.get("/v1/device-binding/status", headers=_base_headers(paired))
    assert unbound.status_code == 200 and unbound.json()["bound"] is False
    assert "owner_approval_key_fingerprint" not in unbound.json()
    await app.state.auth.revoke(paired.device.device_id)
    revoked = await ac.get("/v1/device-binding/status", headers=_base_headers(paired))
    assert revoked.status_code in {401, 403}
