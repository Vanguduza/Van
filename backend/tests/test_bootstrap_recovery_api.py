"""Exercise recovery/certification through HTTP with synthetic signed attestation PKI.

These are real ASGI authorization and cryptographic checks, not physical Android
attestation or live service acceptance.
"""

from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import json
import time

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from cryptography.x509.oid import NameOID

from attestation_fixtures import signed_attestation_chain
from test_device_proof_enforcement import (
    _base_headers, _paired, _proof_headers, _settings, client,
)
from test_owner_device_binding import _attestation, _keypair
from van_gateway.auth.device_proof import PROOF_SKEW_MS, request_signing_input
from van_gateway.audit.service import AuditService
from van_gateway.config import get_settings
from van_gateway.mtls.pki import DeviceCA, init_ca


pytestmark = pytest.mark.asyncio
ATTEST = "/v1/devices/bootstrap/attest"
RECOVER = "/v1/devices/bootstrap/recover"
CERTIFY = "/v1/device-binding/certify"
STATUS = "/v1/devices/provisioning-status"
MUTATION = "/v1/reminders"
INSTALLER = "synthetic-installer-enrolment-scope-0123456789abcdef"


@pytest.fixture(autouse=True)
def _installer_settings(_settings, monkeypatch):
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INSTALLER)
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")
    get_settings.cache_clear()


def _encoded(payload):
    return json.dumps(payload, separators=(",", ":")).encode()


def _headers(key, path, device_id, body, *, authenticated=None, issued_at_ms=None):
    if issued_at_ms is None:
        proof = _proof_headers(key, method="POST", path=path, device_id=device_id, body=body)
    else:
        signing_input = request_signing_input(method="POST", path=path, device_id=device_id,
                                             issued_at_ms=issued_at_ms, body_sha256=hashlib.sha256(body).hexdigest())
        der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = asym_utils.decode_dss_signature(der)
        proof = {"X-Van-Device-Proof": base64.b64encode(r.to_bytes(32, "big") + s.to_bytes(32, "big")).decode(),
                 "X-Van-Device-Proof-Issued-At": str(issued_at_ms)}
    return {"Content-Type": "application/json", **(authenticated or {}), **proof}


async def _enrollment(app, *, device_id="owner-phone"):
    service = app.state.owner_device_bindings
    token, challenge = await service.create_bootstrap_token()
    pem, key = _keypair()
    extension = _attestation(challenge.encode())
    chain, root = signed_attestation_chain(pem, extension)
    service.policy = replace(service.policy, allowed_root_fingerprints=frozenset({root}))
    payload = {"token": token, "device_id": device_id, "public_key_pem": pem,
               "attestation_extension_b64": base64.b64encode(extension).decode(),
               "attestation_chain_b64": [base64.b64encode(item).decode() for item in chain],
               # This assertion supplied by a caller must not substitute for the chain.
               "attestation_root_fingerprint": "0" * 64}
    return payload, key, root


async def _attest(ac, payload, key):
    body = _encoded(payload)
    response = await ac.post(ATTEST, content=body,
                             headers=_headers(key, ATTEST, payload["device_id"], body))
    assert response.status_code == 200, response.text
    assert response.json()["attestation_chain_verified"] is True
    return response.json()


async def _bootstrap_row(app, token):
    return await app.state.store.fetchone("SELECT * FROM owner_device_bootstrap_tokens WHERE token_sha256 = ?",
                                          (hashlib.sha256(token.encode()).hexdigest(),))


async def test_unconsumed_exact_bootstrap_returns_404_without_consuming_or_binding(client):
    ac, app = client
    payload, key, _ = await _enrollment(app)
    body = _encoded({"token": payload["token"], "device_id": payload["device_id"]})
    response = await ac.post(RECOVER, content=body,
                             headers=_headers(key, RECOVER, payload["device_id"], body))
    assert response.status_code == 404
    assert response.json()["detail"] == "bootstrap_not_consumed"
    assert (await _bootstrap_row(app, payload["token"]))["consumed_at_ms"] is None
    assert await app.state.owner_device_bindings.active() is None


async def test_consumed_exact_device_and_fresh_key_recovers_without_pairing_credentials(client):
    ac, app = client
    payload, key, root = await _enrollment(app)
    bound = await _attest(ac, payload, key)
    body = _encoded({"token": payload["token"], "device_id": payload["device_id"]})
    response = await ac.post(RECOVER, content=body,
                             headers=_headers(key, RECOVER, payload["device_id"], body))
    assert response.status_code == 200, response.text
    recovered = response.json()
    assert recovered["binding_id"] == bound["binding_id"]
    assert recovered["device_id"] == bound["device_id"]
    assert recovered["device_key_fingerprint"] == bound["device_key_fingerprint"]
    assert recovered["attestation_chain_verified"] is True
    assert response.headers["Cache-Control"] == "no-store"
    assert not {"access_token", "ingress_token", "device_secret"} & recovered.keys()
    active = await app.state.owner_device_bindings.active()
    assert active.attestation_root_fingerprint == root


async def test_recovery_replays_are_refused_at_the_http_boundary(client):
    ac, app = client
    payload, key, _ = await _enrollment(app)
    await _attest(ac, payload, key)
    body = _encoded({"token": payload["token"], "device_id": payload["device_id"]})
    headers = _headers(key, RECOVER, payload["device_id"], body)
    assert (await ac.post(RECOVER, content=body, headers=headers)).status_code == 200
    replay = await ac.post(RECOVER, content=body, headers=headers)
    assert replay.status_code == 403
    assert replay.json()["detail"] == "device_proof_replayed"


@pytest.mark.parametrize("failure,detail", [
    ("wrong_device", "bootstrap_device_mismatch"),
    ("wrong_key", "device_proof_invalid"),
    ("stale_proof", "device_proof_stale"),
    ("expired_token", "bootstrap_token_expired"),
    ("revoked_token", "bootstrap_token_revoked"),
    ("revoked_binding", "device_binding_revoked"),
])
async def test_recovery_refuses_wrong_identity_freshness_or_revoked_authority(client, failure, detail):
    ac, app = client
    payload, key, _ = await _enrollment(app)
    await _attest(ac, payload, key)
    device_id = "different-phone" if failure == "wrong_device" else payload["device_id"]
    if failure == "wrong_key":
        key = _keypair()[1]
    if failure == "expired_token":
        await app.state.store.execute("UPDATE owner_device_bootstrap_tokens SET expires_at_ms = 1")
    if failure == "revoked_token":
        await app.state.store.execute("UPDATE owner_device_bootstrap_tokens SET revoked_at_ms = ?", (int(time.time() * 1000),))
    if failure == "revoked_binding":
        await app.state.owner_device_bindings.revoke(reason="synthetic recovery regression")
    body = _encoded({"token": payload["token"], "device_id": device_id})
    stamp = int(time.time() * 1000) - PROOF_SKEW_MS - 10_000 if failure == "stale_proof" else None
    response = await ac.post(RECOVER, content=body,
                             headers=_headers(key, RECOVER, device_id, body, issued_at_ms=stamp))
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == detail


@pytest.mark.parametrize("failure,status", [("missing_chain", 422), ("wrong_root", 403), ("wrong_leaf_key", 403)])
async def test_public_attestation_missing_or_wrong_chain_does_not_spend_bootstrap(client, failure, status):
    ac, app = client
    payload, key, root = await _enrollment(app)
    bad = dict(payload)
    if failure == "missing_chain":
        bad.pop("attestation_chain_b64")
    elif failure == "wrong_root":
        app.state.owner_device_bindings.policy = replace(app.state.owner_device_bindings.policy,
                                                        allowed_root_fingerprints=frozenset({"f" * 64}))
    else:
        other_chain, other_root = signed_attestation_chain(_keypair()[0], base64.b64decode(payload["attestation_extension_b64"]))
        bad["attestation_chain_b64"] = [base64.b64encode(item).decode() for item in other_chain]
        app.state.owner_device_bindings.policy = replace(app.state.owner_device_bindings.policy,
                                                        allowed_root_fingerprints=frozenset({other_root}))
    body = _encoded(bad)
    response = await ac.post(ATTEST, content=body,
                             headers=_headers(key, ATTEST, payload["device_id"], body))
    assert response.status_code == status, response.text
    assert (await _bootstrap_row(app, payload["token"]))["consumed_at_ms"] is None
    assert await app.state.owner_device_bindings.active() is None
    # The corrected chain can still enroll: the failure did not consume the token.
    app.state.owner_device_bindings.policy = replace(app.state.owner_device_bindings.policy,
                                                    allowed_root_fingerprints=frozenset({root}))
    await _attest(ac, payload, key)


async def _legacy_binding(app, device_id):
    service = app.state.owner_device_bindings
    token, challenge = await service.create_bootstrap_token()
    pem, key = _keypair()
    extension = _attestation(challenge.encode())
    bound = await service.bind(token=token, device_id=device_id, public_key_pem=pem,
                               attestation_extension=extension)
    assert bound.attestation_chain_verified is False
    # Existing bindings predate the challenge column. Certification must recover
    # the original accepted challenge from the persisted attestation event.
    await app.state.store.execute(
        "UPDATE owner_device_bindings SET attestation_challenge = NULL WHERE binding_id = ?",
        (bound.binding_id,),
    )
    chain, root = signed_attestation_chain(pem, extension)
    service.policy = replace(service.policy, allowed_root_fingerprints=frozenset({root}))
    return token, key, chain, bound


@pytest.mark.parametrize("strict", [False, True])
async def test_same_key_certification_preserves_binding_and_strict_migration_policy(client, monkeypatch, strict):
    ac, app = client
    paired = await _paired(app)
    _, key, chain, original = await _legacy_binding(app, paired.device.device_id)
    monkeypatch.setattr(get_settings(), "require_device_binding", strict)
    payload = {"text": "synthetic migration check", "due_at_unix": int(time.time()) + 3600,
               "idempotency_key": "synthetic-before-certification"}
    body = _encoded(payload)
    response = await ac.post(MUTATION, content=body,
                             headers=_headers(key, MUTATION, paired.device.device_id, body, authenticated=_base_headers(paired)))
    if strict:
        assert response.status_code == 403
        assert response.json()["detail"] == "device_attestation_recertification_required"
    else:
        assert response.status_code == 200, response.text
    certify_body = _encoded({"attestation_chain_b64": [base64.b64encode(item).decode() for item in chain]})
    certified = await ac.post(CERTIFY, content=certify_body,
                              headers=_headers(key, CERTIFY, paired.device.device_id, certify_body,
                                               authenticated=_base_headers(paired)))
    assert certified.status_code == 200, certified.text
    assert certified.json()["attestation_chain_verified"] is True
    current = await app.state.owner_device_bindings.active()
    assert current.binding_id == original.binding_id
    assert current.device_key_fingerprint == original.device_key_fingerprint
    assert current.public_key_pem == original.public_key_pem
    after_body = _encoded({**payload, "idempotency_key": "synthetic-after-certification"})
    after = await ac.post(MUTATION, content=after_body,
                          headers=_headers(key, MUTATION, paired.device.device_id, after_body, authenticated=_base_headers(paired)))
    assert after.status_code == 200, after.text


async def test_unverified_legacy_binding_cannot_recover_by_bootstrap_alone(client):
    ac, app = client
    paired = await _paired(app)
    token, key, _, _ = await _legacy_binding(app, paired.device.device_id)
    body = _encoded({"token": token, "device_id": paired.device.device_id})
    response = await ac.post(RECOVER, content=body,
                             headers=_headers(key, RECOVER, paired.device.device_id, body))
    assert response.status_code == 403
    assert response.json()["detail"] == "device_attestation_recertification_required"


async def _status(ac, token, *, credential=INSTALLER):
    return await ac.post(STATUS, json={"bootstrap_token": token},
                         headers={"X-Van-Internal-Token": credential})


async def test_provisioning_status_is_exact_scoped_and_read_only_for_an_unused_token(client):
    ac, app = client
    token, _ = await app.state.owner_device_bindings.create_bootstrap_token()
    before = dict(await _bootstrap_row(app, token))
    unknown = await _status(ac, "unknown-token-with-valid-length-0123456789")
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "bootstrap_token_unknown"
    forbidden = await _status(ac, token, credential="different-ungranted-installer-token-0123456789")
    assert forbidden.status_code == 403
    response = await _status(ac, token)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "NEEDS_BINDING"
    assert not any(body["steps"].values())
    assert body["transport_receipt"] is None
    assert body["owner_e2e_verified"] is False
    assert body["hermes_verified"] is False
    assert response.headers["Cache-Control"] == "no-store"
    assert token not in response.text
    assert dict(await _bootstrap_row(app, token)) == before


async def test_provisioning_status_names_legacy_certification_without_claiming_admission(client):
    ac, app = client
    paired = await _paired(app)
    token, _, _, _ = await _legacy_binding(app, paired.device.device_id)
    response = await _status(ac, token)
    assert response.status_code == 200
    assert response.json()["state"] == "NEEDS_CERTIFICATION"
    assert response.json()["transport_receipt"] is None
    assert response.json()["owner_e2e_verified"] is False


async def _provisioned(ac, app, tmp_path):
    payload, key, _ = await _enrollment(app)
    bound = await _attest(ac, payload, key)
    ticket = await app.state.auth.create_pairing_ticket(payload["device_id"])
    await app.state.auth.pair_device(ticket.token, payload["device_id"], "s" * 32,
                                     payload["public_key_pem"], payload["device_id"])
    directory = tmp_path / "synthetic-device-ca"
    init_ca(directory)
    ca = DeviceCA(directory)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, payload["device_id"])])
    ).sign(key, hashes.SHA256())
    issued = ca.issue_client(csr.public_bytes(serialization.Encoding.PEM).decode(), payload["device_id"])
    app.state.device_ca = ca
    session, _ = await app.state.van_sessions.open(device_id=payload["device_id"])
    return payload, bound, ca, issued, session


async def test_paired_bound_certified_and_opened_still_needs_observed_transport_admission(client, tmp_path):
    ac, app = client
    payload, _, ca, _, _ = await _provisioned(ac, app, tmp_path)
    pki_before = {name: (ca.dir / name).read_bytes() for name in ("ca.crt", "ca.key", "issued.json")}
    response = await _status(ac, payload["token"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "NEEDS_SESSION_ADMISSION"
    assert body["steps"] == {"binding": True, "pairing": True, "tls_certificate": True, "session_admitted": False}
    assert body["transport_receipt"] is None
    assert body["owner_e2e_verified"] is False
    assert body["hermes_verified"] is False
    assert {name: (ca.dir / name).read_bytes() for name in pki_before} == pki_before


@pytest.mark.parametrize("mismatch", ["binding", "matching_marker", "closed_session", "revoked_certificate"])
async def test_a_transport_receipt_cannot_survive_mismatched_binding_or_revoked_state(client, tmp_path, mismatch):
    ac, app = client
    payload, bound, ca, issued, session = await _provisioned(ac, app, tmp_path)
    # Fixture projection of a historical gateway observation, not a real WSS run.
    after = {"binding_id": bound["binding_id"], "certified_matching": True,
             "certificate_serial": issued.serial_hex, "van_session_id": session.van_session_id,
             "transport": "websocket", "synthetic_fixture": True}
    if mismatch == "binding":
        after["binding_id"] = "previous-other-binding"
    if mismatch == "matching_marker":
        after["certified_matching"] = False
    await AuditService(app.state.store).record(result="accepted", device_id=payload["device_id"],
                                              capability="session.transport.admitted", after=after)
    if mismatch == "closed_session":
        await app.state.van_sessions.close(session.van_session_id)
    if mismatch == "revoked_certificate":
        assert ca.revoke_device(payload["device_id"]) == 1
    response = await _status(ac, payload["token"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == ("NEEDS_TLS_CERTIFICATE" if mismatch == "revoked_certificate" else "NEEDS_SESSION_ADMISSION")
    assert body["transport_receipt"] is None
    assert body["steps"]["session_admitted"] is False
    assert body["owner_e2e_verified"] is False


async def test_recorded_admission_is_explicitly_historical_and_does_not_claim_live_owner_or_hermes(client, tmp_path):
    ac, app = client
    payload, bound, _, issued, session = await _provisioned(ac, app, tmp_path)
    audit_id = await AuditService(app.state.store).record(
        result="accepted", device_id=payload["device_id"], capability="session.transport.admitted",
        after={"binding_id": bound["binding_id"], "certified_matching": True,
               "certificate_serial": issued.serial_hex, "van_session_id": session.van_session_id,
               "transport": "websocket", "synthetic_fixture": True},
    )
    response = await _status(ac, payload["token"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "SESSION_ADMITTED"
    assert body["steps"]["session_admitted"] is True
    assert body["transport_receipt"]["audit_id"] == audit_id
    assert body["transport_receipt"]["currently_connected_verified"] is False
    assert body["owner_e2e_verified"] is False
    assert body["hermes_verified"] is False
