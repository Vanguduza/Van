from __future__ import annotations

import hashlib
import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.auth.service import AuthService
from van_gateway.config import get_settings

INGRESS = "test-ingress-token-0123456789abcdef"
INTERNAL = "test-internal-token"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "pairing.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

@pytest_asyncio.fixture
async def app_client(monkeypatch):
    app = create_app()

    async def ok():
        return {"ok": True, "profile": "van"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", ok)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


def device_payload(device_id: str, secret: str, pairing_token: str | None = None) -> dict:
    body = {
        "device_id": device_id,
        "device_secret": secret,
        "public_key_pem": "PEM",
        "label": "owner-phone",
    }
    if pairing_token is not None:
        body["pairing_token"] = pairing_token
    return body


async def issue_ticket(ac: AsyncClient) -> dict:
    response = await ac.post(
        "/v1/devices/pairing-ticket",
        headers={"X-Van-Internal-Token": INTERNAL},
        json={"label": "owner-phone", "ttl_seconds": 600},
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    return response.json()

@pytest.mark.asyncio
async def test_pairing_ticket_is_hashed_and_single_use(app_client):
    ac, app = app_client
    ticket = await issue_ticket(ac)
    token = ticket["pairing_token"]
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = await app.state.store.fetchone(
        "SELECT ticket_hash, used_at_unix FROM pairing_tickets WHERE ticket_hash = ?",
        (digest,),
    )
    assert row is not None
    assert row["ticket_hash"] == digest
    assert row["ticket_hash"] != token
    assert row["used_at_unix"] is None

    paired = await ac.post(
        "/v1/devices/pair",
        json=device_payload("paired-1", "secret-1", token),
    )
    assert paired.status_code == 200
    assert paired.headers.get("cache-control") == "no-store"
    assert paired.json()["ingress_token"] == INGRESS
    device_access = paired.json()["device_access_token"]
    assert len(device_access) >= 32
    device_row = await app.state.store.fetchone(
        "SELECT access_token_hash FROM devices WHERE device_id = ?",
        ("paired-1",),
    )
    assert device_row is not None
    assert device_row["access_token_hash"] == hashlib.sha256(device_access.encode()).hexdigest()
    assert device_row["access_token_hash"] != device_access

    reused = await ac.post(
        "/v1/devices/pair",
        json=device_payload("paired-2", "secret-2", token),
    )
    assert reused.status_code == 400

@pytest.mark.asyncio
async def test_bearer_cannot_create_or_revoke_device_authority(app_client):
    ac, _app = app_client
    bearer = {"X-Van-Ingress-Token": INGRESS}
    direct = await ac.post(
        "/v1/devices/enroll",
        headers=bearer,
        json=device_payload("direct-1", "secret-direct"),
    )
    # P0-SEC-001 — an owner ingress bearer is authenticated but is not authority for
    # device enrolment, and the refusal names the scope rather than pretending the caller
    # is unauthenticated. Before, this route fell through to device authentication.
    assert direct.status_code == 403
    assert direct.json()["detail"] == "internal_control_unauthorized"
    assert direct.json()["required_scope"] == "device_enrolment"

    ticket = await issue_ticket(ac)
    paired = await ac.post(
        "/v1/devices/pair",
        json=device_payload("paired-revoke", "secret-r", ticket["pairing_token"]),
    )
    assert paired.status_code == 200

    denied_revoke = await ac.post(
        "/v1/devices/paired-revoke/revoke",
        headers=bearer,
    )
    assert denied_revoke.status_code == 403
    assert denied_revoke.json()["required_scope"] == "device_enrolment"

    allowed_revoke = await ac.post(
        "/v1/devices/paired-revoke/revoke",
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert allowed_revoke.status_code == 200

@pytest.mark.asyncio
async def test_device_access_token_required_and_revoked_with_device(app_client):
    ac, _app = app_client
    ticket = await issue_ticket(ac)
    paired = await ac.post(
        "/v1/devices/pair",
        json=device_payload("paired-access", "secret-a", ticket["pairing_token"]),
    )
    assert paired.status_code == 200
    device_token = paired.json()["device_access_token"]

    bearer_only = await ac.get(
        "/v1/projects",
        headers={"X-Van-Ingress-Token": INGRESS},
    )
    assert bearer_only.status_code == 401
    assert bearer_only.json()["detail"] == "device_access_denied"

    client_headers = {
        "X-Van-Ingress-Token": INGRESS,
        "X-Van-Device-Token": device_token,
    }
    allowed = await ac.get("/v1/projects", headers=client_headers)
    assert allowed.status_code == 200

    revoked = await ac.post(
        "/v1/devices/paired-access/revoke",
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert revoked.status_code == 200

    denied_after_revoke = await ac.get("/v1/projects", headers=client_headers)
    assert denied_after_revoke.status_code == 401
    assert denied_after_revoke.json()["detail"] == "device_access_denied"


@pytest.mark.asyncio
async def test_pairing_ticket_expiry_fails_closed(app_client):
    ac, app = app_client
    ticket = await issue_ticket(ac)
    token = ticket["pairing_token"]
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    await app.state.store.execute(
        "UPDATE pairing_tickets SET expires_at_unix = ? WHERE ticket_hash = ?",
        (int(time.time()) - 1, digest),
    )
    expired = await ac.post(
        "/v1/devices/pair",
        json=device_payload("expired-1", "secret-e", token),
    )
    assert expired.status_code == 400
    assert expired.json()["detail"] == "Pairing ticket invalid or expired"


@pytest.mark.asyncio
async def test_pairing_ticket_issue_requires_internal_control(app_client):
    ac, _app = app_client
    bootstrap = await issue_ticket(ac)
    paired = await ac.post(
        "/v1/devices/pair",
        json=device_payload("paired-no-control", "secret-nc", bootstrap["pairing_token"]),
    )
    assert paired.status_code == 200
    denied = await ac.post(
        "/v1/devices/pairing-ticket",
        headers={
            "X-Van-Ingress-Token": INGRESS,
            "X-Van-Device-Token": paired.json()["device_access_token"],
        },
        json={"ttl_seconds": 600},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_new_ticket_supersedes_prior_ticket_for_same_label(app_client):
    ac, _app = app_client
    first = await issue_ticket(ac)
    second = await issue_ticket(ac)
    superseded = await ac.post(
        "/v1/devices/pair",
        json=device_payload("superseded-1", "secret-old", first["pairing_token"]),
    )
    assert superseded.status_code == 400
    current = await ac.post(
        "/v1/devices/pair",
        json=device_payload("current-1", "secret-new", second["pairing_token"]),
    )
    assert current.status_code == 200


@pytest.mark.asyncio
async def test_device_token_cannot_authorize_another_device_identity(app_client):
    ac, app = app_client
    first_ticket = await issue_ticket(ac)
    first = await ac.post(
        "/v1/devices/pair",
        json=device_payload("device-a", "secret-a", first_ticket["pairing_token"]),
    )
    assert first.status_code == 200
    token_a = first.json()["device_access_token"]

    second_ticket = await issue_ticket(ac)
    second = await ac.post(
        "/v1/devices/pair",
        json=device_payload("device-b", "secret-b", second_ticket["pairing_token"]),
    )
    assert second.status_code == 200

    issued = int(time.time())
    canonical = AuthService.canonical_command("cross-1", "cross-key", "device-b", issued, "noop", "A1", None)
    signature = app.state.auth.sign("device-b", canonical)

    headers = {
        "X-Van-Ingress-Token": INGRESS,
        "X-Van-Device-Token": token_a,
    }
    command = await ac.post(
        "/v1/commands",
        headers=headers,
        json={
            "command_id": "cross-1",
            "idempotency_key": "cross-key",
            "device_id": "device-b",
            "issued_at_unix": issued,
            "signature": signature,
            "text": "noop",
            "action_class": "A1",
        },
    )
    assert command.status_code == 403
    assert command.json()["detail"] == "device_identity_mismatch"

    events = await ac.get("/v1/events?device_id=device-b&after_seq=0", headers=headers)
    assert events.status_code == 403
    assert events.json()["detail"] == "device_identity_mismatch"
