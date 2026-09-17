from __future__ import annotations

import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.auth.service import AuthService
from van_gateway.config import get_settings
from van_gateway.models import PrincipalType


INGRESS = "test-ingress-token-0123456789abcdef"
INTERNAL = "rev31-hermes-internal-control"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "rev31.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def runtime_client(monkeypatch):
    app = create_app()

    async def fake_health():
        return {"ok": True, "profile": "van"}

    async def fake_create_run(text, metadata=None):
        return {"id": "run-rev31", "status": "accepted", "input": text, "metadata": metadata or {}}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", fake_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", fake_create_run)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Van-Ingress-Token": INGRESS},
    ) as client:
        async with app.router.lifespan_context(app):
            yield client, app


@pytest.mark.asyncio
async def test_runtime_routes_require_hermes_internal_control(runtime_client):
    client, _app = runtime_client

    denied = await client.get("/v1/runtime/status")
    assert denied.status_code == 403
    assert denied.json()["detail"] == "internal_control_unauthorized"

    allowed = await client.get(
        "/v1/runtime/status",
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["hermes_is_sole_agent_runtime"] is True
    assert body["enabled_actions"] >= 4
    assert body["research"]["credential_locus"] == "gateway"


@pytest.mark.asyncio
async def test_v2_signature_binds_voice_provenance_and_replay_fields(runtime_client):
    client, app = runtime_client
    device_id = "dev-voice"
    secret = "voice-secret"
    enrolled = await client.post(
        "/v1/devices/enroll",
        json={"device_id": device_id, "device_secret": secret, "public_key_pem": "PEM", "label": "S24"},
    )
    assert enrolled.status_code == 200
    app.state.auth.remember_secret(device_id, secret)

    issued = int(time.time())
    expires = issued + 30
    text = "Open VAN"
    canonical = AuthService.canonical_command_v2(
        command_id="voice-c1",
        idempotency_key="voice-turn-1:open",
        device_id=device_id,
        issued_at_unix=issued,
        text=text,
        action_class="A1",
        project_id=None,
        turn_id="voice-turn-1",
        origin_channel="VOICE",
        principal_type="OWNER_DEVICE",
        requested_by=f"device:{device_id}",
        expires_at_unix=expires,
        nonce="nonce-1",
        context_capsule_revision=7,
        context_capsule_hash="capsule-hash",
        speech_evidence_ref="speech://turn-1",
        no_stale_replay=True,
        context_trust="CONVERSATION",
    )
    signature = app.state.auth.sign(device_id, canonical)
    body = {
        "command_id": "voice-c1",
        "idempotency_key": "voice-turn-1:open",
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": signature,
        "signature_version": 2,
        "text": text,
        "action_class": "A1",
        "turn_id": "voice-turn-1",
        "origin_channel": "VOICE",
        "principal_type": "OWNER_DEVICE",
        "requested_by": f"device:{device_id}",
        "expires_at_unix": expires,
        "nonce": "nonce-1",
        "context_capsule_revision": 7,
        "context_capsule_hash": "capsule-hash",
        "speech_evidence_ref": "speech://turn-1",
        "no_stale_replay": True,
        "context_trust": "CONVERSATION",
    }
    accepted = await client.post("/v1/commands", json=body)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    tampered_canonical = AuthService.canonical_command_v2(
        command_id="voice-c2",
        idempotency_key="voice-turn-2:open",
        device_id=device_id,
        issued_at_unix=issued,
        text=text,
        action_class="A1",
        project_id=None,
        turn_id="voice-turn-2",
        origin_channel="UI",
        principal_type="OWNER_DEVICE",
        requested_by=f"device:{device_id}",
        expires_at_unix=expires,
        nonce="nonce-2",
        context_capsule_revision=None,
        context_capsule_hash=None,
        speech_evidence_ref=None,
        no_stale_replay=False,
        context_trust="CONVERSATION",
    )
    tampered = {
        "command_id": "voice-c2",
        "idempotency_key": "voice-turn-2:open",
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": app.state.auth.sign(device_id, tampered_canonical),
        "signature_version": 2,
        "text": text,
        "action_class": "A1",
        "turn_id": "voice-turn-2",
        "origin_channel": "VOICE",
        "principal_type": "OWNER_DEVICE",
        "requested_by": f"device:{device_id}",
        "expires_at_unix": expires,
        "nonce": "nonce-2",
        "context_trust": "CONVERSATION",
    }
    denied = await client.post("/v1/commands", json=tampered)
    assert denied.status_code == 200
    assert denied.json()["status"] == "denied"
    assert "signature" in denied.json()["message"].lower()


@pytest.mark.asyncio
async def test_device_revocation_revokes_nonterminal_privileged_execution(runtime_client):
    client, app = runtime_client
    device_id = "dev-revoke"
    secret = "revoke-secret"
    assert (await client.post(
        "/v1/devices/enroll",
        json={"device_id": device_id, "device_secret": secret, "public_key_pem": "PEM"},
    )).status_code == 200
    app.state.auth.remember_secret(device_id, secret)

    execution = await app.state.owner_runtime.actions.begin(
        execution_id="exec-revoke",
        command_id="cmd-revoke",
        turn_id="turn-revoke",
        action_id="google.notebook.note.create",
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by=f"device:{device_id}",
        idempotency_key="turn-revoke:google.notebook.note.create",
        parameters={"title": "Dial Health"},
        snapshot_id=None,
        owner_approved=True,
    )
    assert execution.status.value == "AUTHORIZED"

    revoked = await client.post(f"/v1/devices/{device_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_privileged_executions"] == 1

    after = await app.state.owner_runtime.actions.get_execution("exec-revoke")
    assert after is not None
    assert after.status.value == "REVOKED"
    assert after.error_code == "DEVICE_OR_GRANT_REVOKED"
