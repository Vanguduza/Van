"""A lost pairing reply is recoverable only by the original bound hardware key.

These exercise the public HTTP handler with real P-256 request signatures. The
binding helper supplies a policy-accepted test attestation; no live device or
provider is contacted.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sqlite3
import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from httpx import ASGITransport, AsyncClient

from test_device_proof_enforcement import _bind
from test_owner_device_binding import PACKAGE, SIGNING_CERT, _keypair
from van_gateway.app import create_app
from van_gateway.auth.device_proof import request_signing_input
from van_gateway.auth.service import AuthError
from van_gateway.config import get_settings

PAIR = "/v1/devices/pair"
INGRESS = "pairing-recovery-test-ingress-0123456789"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "pairing-recovery.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "pairing-recovery-test-internal")
    monkeypatch.setenv("VAN_OWNER_DEVICE_PACKAGE", PACKAGE)
    monkeypatch.setenv("VAN_OWNER_DEVICE_SIGNING_CERT_SHA256", SIGNING_CERT)
    monkeypatch.setenv("VAN_REQUIRE_DEVICE_BINDING", "true")
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _offline_health():
    return {"ok": True, "profile": "van"}


@pytest_asyncio.fixture
async def client(monkeypatch):
    app = create_app()
    monkeypatch.setattr(app.state.orchestrator.hermes, "health", _offline_health)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac, app


def _body(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class Proofs:
    def __init__(self):
        self.last_issued = 0

    def headers(self, key, raw_body, *, device_id="recovery-phone", method="POST", path=PAIR, issued=None):
        if issued is None:
            issued = max(int(time.time() * 1000), self.last_issued + 1)
            self.last_issued = issued
        signing_input = request_signing_input(
            method=method, path=path, device_id=device_id, issued_at_ms=issued,
            body_sha256=hashlib.sha256(raw_body).hexdigest(),
        )
        der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(der)
        return {
            "Content-Type": "application/json",
            "X-Van-Device-Proof": base64.b64encode(r.to_bytes(32, "big") + s.to_bytes(32, "big")).decode(),
            "X-Van-Device-Proof-Issued-At": str(issued),
        }


@pytest.fixture
def proofs():
    return Proofs()


async def _pending(app):
    ticket = await app.state.auth.create_pairing_ticket("owner-phone")
    hardware_key = await _bind(app, "recovery-phone")
    # The public signed-chain bootstrap is tested separately. This fixture explicitly
    # establishes its trusted admission so this suite isolates pairing and proof recovery.
    await app.state.store.execute(
        "UPDATE owner_device_bindings SET attestation_chain_verified = 1 WHERE device_id = ?",
        ("recovery-phone",),
    )
    # Approval and hardware-identity keys are distinct Android Keystore aliases.
    approval_pem, _ = _keypair()
    payload = {
        "pairing_token": ticket.token,
        "device_id": "recovery-phone",
        "device_secret": "pairing-recovery-test-secret-0123456789",
        "public_key_pem": approval_pem,
        "label": "owner-phone",
        "device_access_token": "client-known-pairing-test-token-0123456789",
    }
    return payload, hardware_key


async def _post(ac, payload, key, proofs, *, raw=None):
    raw = _body(payload) if raw is None else raw
    return await ac.post(PAIR, content=raw, headers=proofs.headers(key, raw, device_id=payload["device_id"]))


async def _counts(app):
    return tuple([
        (await app.state.store.fetchone(f"SELECT COUNT(*) AS n FROM {table}"))["n"]
        for table in ("devices", "capability_grants", "pairing_attempts")
    ])


def _service_args(payload, raw):
    return {
        "pairing_token": payload["pairing_token"], "device_id": payload["device_id"],
        "device_secret": payload["device_secret"], "public_key_pem": payload["public_key_pem"],
        "label": payload["label"], "device_access_token": payload["device_access_token"],
        "request_hash": hashlib.sha256(raw).hexdigest(),
    }


@pytest.mark.asyncio
async def test_lost_first_reply_recovers_the_same_credentials_with_fresh_proof(client, proofs):
    ac, app = client
    payload, key = await _pending(app)
    first = await _post(ac, payload, key, proofs)
    assert first.status_code == 200, first.text
    recovered = await _post(ac, payload, key, proofs)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == first.json()
    assert recovered.json()["device_access_token"] == payload["device_access_token"]
    assert recovered.json()["ingress_token"] == INGRESS
    assert recovered.headers["cache-control"] == "no-store"
    assert await _counts(app) == (1, 1, 1)
    attempt = await app.state.store.fetchone("SELECT * FROM pairing_attempts")
    assert set(attempt.keys()) == {"pairing_ticket_hash", "device_id", "request_hash", "access_token_hash", "created_at_unix"}
    assert attempt["pairing_ticket_hash"] == hashlib.sha256(payload["pairing_token"].encode()).hexdigest()
    assert attempt["request_hash"] == hashlib.sha256(_body(payload)).hexdigest()
    assert attempt["access_token_hash"] == hashlib.sha256(payload["device_access_token"].encode()).hexdigest()
    assert payload["device_access_token"] not in tuple(attempt)
    assert payload["device_secret"] not in tuple(attempt)
    device = await app.state.auth.require_access_token(payload["device_access_token"])
    assert device.public_key_pem == payload["public_key_pem"]


@pytest.mark.asyncio
async def test_recovery_survives_new_app_and_expired_spent_ticket(client, proofs, monkeypatch):
    ac, app = client
    payload, key = await _pending(app)
    raw = _body(payload)
    original_headers = proofs.headers(key, raw)
    first = await ac.post(PAIR, content=raw, headers=original_headers)
    assert first.status_code == 200
    await app.state.store.execute("UPDATE pairing_tickets SET expires_at_unix = 1")
    restarted = create_app()
    monkeypatch.setattr(restarted.state.orchestrator.hermes, "health", _offline_health)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(transport=ASGITransport(app=restarted), base_url="http://test") as other:
            replayed = await other.post(PAIR, content=raw, headers=original_headers)
            assert replayed.status_code == 401
            assert replayed.json()["detail"] == "device_proof_replayed"
            recovered = await _post(other, payload, key, proofs)
            assert recovered.status_code == 200, recovered.text
            assert recovered.json() == first.json()
            assert await _counts(restarted) == (1, 1, 1)
            restarted.state.auth.verify_signature(
                payload["device_id"], "restart-test",
                app.state.auth.sign(payload["device_id"], "restart-test"),
            )


@pytest.mark.asyncio
async def test_reusing_pairing_proof_is_refused_before_recovery(client, proofs):
    ac, app = client
    payload, key = await _pending(app)
    raw = _body(payload)
    headers = proofs.headers(key, raw)
    assert (await ac.post(PAIR, content=raw, headers=headers)).status_code == 200
    replay = await ac.post(PAIR, content=raw, headers=headers)
    assert replay.status_code == 401
    assert replay.json()["detail"] == "device_proof_replayed"
    assert await _counts(app) == (1, 1, 1)


@pytest.mark.asyncio
async def test_caller_hardware_proved_flag_cannot_replace_real_proof(client):
    ac, app = client
    payload, _ = await _pending(app)
    response = await ac.post(PAIR, json={**payload, "hardware_proved": True})
    assert response.status_code == 401
    assert response.json()["detail"] == "device_proof_required"
    assert await _counts(app) == (0, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong", ["method", "path", "body", "key", "stale", "malformed"])
async def test_invalid_pairing_proof_never_consumes_ticket(client, proofs, wrong):
    ac, app = client
    payload, key = await _pending(app)
    raw = _body(payload)
    kwargs = {}
    signing_body = raw
    if wrong == "method":
        kwargs["method"] = "GET"
    elif wrong == "path":
        kwargs["path"] = "/v1/session/open"
    elif wrong == "body":
        signing_body = raw + b" "
    elif wrong == "key":
        key = ec.generate_private_key(ec.SECP256R1())
    elif wrong == "stale":
        kwargs["issued"] = int(time.time() * 1000) - 3600000
    headers = proofs.headers(key, signing_body, **kwargs)
    if wrong == "malformed":
        headers["X-Van-Device-Proof"] = "not-base64!"
    response = await ac.post(PAIR, content=raw, headers=headers)
    assert response.status_code == 401, response.text
    assert await _counts(app) == (0, 0, 0)
    assert (await app.state.store.fetchone("SELECT used_at_unix FROM pairing_tickets"))["used_at_unix"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["label", "device_secret", "public_key_pem", "device_access_token", "serialization"])
async def test_fresh_proof_cannot_change_original_pairing_request(client, proofs, changed):
    ac, app = client
    payload, key = await _pending(app)
    assert (await _post(ac, payload, key, proofs)).status_code == 200
    altered = dict(payload)
    raw = None
    if changed == "serialization":
        raw = json.dumps(payload, sort_keys=True, indent=2).encode()
    else:
        altered[changed] += "changed"
    refused = await _post(ac, altered, key, proofs, raw=raw)
    assert refused.status_code == 409, refused.text
    assert await _counts(app) == (1, 1, 1)
    assert (await _post(ac, payload, key, proofs)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke", ["device", "binding", "access_token"])
async def test_revocation_or_token_rotation_blocks_recovery(client, proofs, revoke):
    ac, app = client
    payload, key = await _pending(app)
    assert (await _post(ac, payload, key, proofs)).status_code == 200
    if revoke == "device":
        await app.state.auth.revoke(payload["device_id"])
    elif revoke == "binding":
        await app.state.owner_device_bindings.revoke(reason="test revocation")
    else:
        await app.state.store.execute(
            "UPDATE devices SET access_token_hash = ? WHERE device_id = ?",
            (hashlib.sha256(b"rotated-test-token").hexdigest(), payload["device_id"]),
        )
    refused = await _post(ac, payload, key, proofs)
    assert refused.status_code == (403 if revoke == "binding" else 409), refused.text
    assert await _counts(app) == (1, 1, 1)


@pytest.mark.asyncio
async def test_spent_ticket_without_receipt_has_no_recovery(client, proofs):
    ac, app = client
    payload, key = await _pending(app)
    assert (await _post(ac, payload, key, proofs)).status_code == 200
    await app.state.store.execute("DELETE FROM pairing_attempts")
    refused = await _post(ac, payload, key, proofs)
    assert refused.status_code == 400
    assert await _counts(app) == (1, 1, 0)


@pytest.mark.asyncio
async def test_legacy_server_generated_token_remains_one_return(client, proofs):
    ac, app = client
    payload, key = await _pending(app)
    del payload["device_access_token"]
    first = await _post(ac, payload, key, proofs)
    assert first.status_code == 200, first.text
    assert len(first.json()["device_access_token"]) >= 32
    assert await _counts(app) == (1, 1, 0)
    assert (await _post(ac, payload, key, proofs)).status_code == 400


@pytest.mark.asyncio
async def test_optional_binding_policy_does_not_allow_unbound_recovery(client, proofs, monkeypatch):
    ac, app = client
    monkeypatch.setenv("VAN_REQUIRE_DEVICE_BINDING", "false")
    get_settings.cache_clear()
    optional = create_app()
    monkeypatch.setattr(optional.state.orchestrator.hermes, "health", _offline_health)
    ticket = await app.state.auth.create_pairing_ticket("unbound")
    _, key = _keypair()
    payload = {
        "pairing_token": ticket.token, "device_id": "unbound", "device_secret": "test-secret",
        "public_key_pem": "PEM", "device_access_token": "client-known-unbound-test-token-0123456789",
    }
    async with optional.router.lifespan_context(optional):
        async with AsyncClient(transport=ASGITransport(app=optional), base_url="http://test") as other:
            response = await _post(other, payload, key, proofs)
            assert response.status_code == 403
            assert response.json()["detail"] == "device_not_bound"
    assert await _counts(app) == (0, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("client_token", [True, False])
async def test_strict_unconfigured_binding_refuses_pairing(client, client_token):
    ac, app = client
    payload, _ = await _pending(app)
    if not client_token:
        del payload["device_access_token"]
    app.state.owner_device_bindings = None
    response = await ac.post(PAIR, json=payload)
    assert response.status_code == 503
    assert response.json()["detail"] == "owner_device_binding_unconfigured"
    assert await _counts(app) == (0, 0, 0)


@pytest.mark.asyncio
async def test_client_token_length_is_validated_before_pairing(client):
    ac, app = client
    payload, _ = await _pending(app)
    response = await ac.post(PAIR, json={**payload, "device_access_token": "short"})
    assert response.status_code == 422
    assert await _counts(app) == (0, 0, 0)


@pytest.mark.asyncio
async def test_service_does_not_trust_a_boolean_without_live_binding(client):
    _, app = client
    payload, _ = await _pending(app)
    args = _service_args(payload, _body(payload))
    with pytest.raises(AuthError) as denied:
        await app.state.auth.pair_device(**args)
    assert denied.value.code == "pairing_hardware_proof_required"
    await app.state.owner_device_bindings.revoke(reason="test revocation")
    with pytest.raises(AuthError) as denied:
        await app.state.auth.pair_device(**args, hardware_proved=True)
    assert denied.value.code == "pairing_binding_inactive"
    assert await _counts(app) == (0, 0, 0)


@pytest.mark.asyncio
async def test_legacy_unverified_binding_cannot_enable_recovery(client, proofs):
    ac, app = client
    payload, key = await _pending(app)
    await app.state.store.execute("UPDATE owner_device_bindings SET attestation_chain_verified = 0")
    response = await _post(ac, payload, key, proofs)
    assert response.status_code == 403
    assert response.json()["detail"] == "device_attestation_chain_unverified"
    with pytest.raises(AuthError) as denied:
        await app.state.auth.pair_device(**_service_args(payload, _body(payload)), hardware_proved=True)
    assert denied.value.code == "pairing_binding_unverified"
    assert await _counts(app) == (0, 0, 0)


@pytest.mark.asyncio
async def test_strict_legacy_pairing_rechecks_binding_at_enrollment_commit(client):
    _, app = client
    payload, _ = await _pending(app)
    await app.state.owner_device_bindings.revoke(reason="revoked after HTTP proof")
    with pytest.raises(AuthError) as denied:
        await app.state.auth.pair_device(
            payload["pairing_token"], payload["device_id"], payload["device_secret"],
            payload["public_key_pem"], payload["label"], hardware_proved=True,
        )
    assert denied.value.code == "pairing_binding_inactive"
    assert await _counts(app) == (0, 0, 0)


@pytest.mark.asyncio
async def test_concurrent_fresh_proofs_create_one_enrollment_and_receipt(client, proofs):
    ac, app = client
    payload, key = await _pending(app)
    responses = await asyncio.gather(*(_post(ac, payload, key, proofs) for _ in range(8)))
    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    assert all(response.json() == responses[0].json() for response in responses)
    assert await _counts(app) == (1, 1, 1)


@pytest.mark.asyncio
async def test_receipt_failure_rolls_back_enrollment_grant_and_ticket(client):
    _, app = client
    payload, _ = await _pending(app)
    proved_binding_id = (await app.state.owner_device_bindings.active()).binding_id
    await app.state.store.execute(
        "CREATE TRIGGER refuse_test_receipt BEFORE INSERT ON pairing_attempts "
        "BEGIN SELECT RAISE(ABORT, 'test receipt failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        await app.state.auth.pair_device(**_service_args(payload, _body(payload)), hardware_proved=True,
                                         proved_binding_id=proved_binding_id)
    assert await _counts(app) == (0, 0, 0)
    assert (await app.state.store.fetchone("SELECT used_at_unix FROM pairing_tickets"))["used_at_unix"] is None
    await app.state.store.execute("DROP TRIGGER refuse_test_receipt")
    result = await app.state.auth.pair_device(**_service_args(payload, _body(payload)), hardware_proved=True,
                                             proved_binding_id=proved_binding_id)
    assert result.access_token == payload["device_access_token"]
    assert await _counts(app) == (1, 1, 1)


@pytest.mark.asyncio
async def test_binding_replaced_between_proof_and_pair_commit_cannot_use_old_key_authority(client):
    _, app = client
    payload, _ = await _pending(app)
    proved_binding_id = (await app.state.owner_device_bindings.active()).binding_id
    # Model a completed administrative rebind after the HTTP signature was checked:
    # the device ID still exists, but its active binding identity is different.
    await app.state.store.execute('UPDATE owner_device_bindings SET binding_id=? WHERE binding_id=?',
                                 ('replacement-binding',proved_binding_id))
    with pytest.raises(AuthError) as denied:
        await app.state.auth.pair_device(**_service_args(payload,_body(payload)),hardware_proved=True,
                                         proved_binding_id=proved_binding_id)
    assert denied.value.code=='pairing_binding_changed'
    assert await _counts(app)==(0,0,0)
