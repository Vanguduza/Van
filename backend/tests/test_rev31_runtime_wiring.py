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
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def runtime_client(monkeypatch):
    app = create_app()
    observed: dict[str, object] = {}

    async def fake_health():
        return {"ok": True, "profile": "van"}

    async def fake_create_run(text, metadata=None):
        observed["text"] = text
        observed["metadata"] = metadata or {}
        return {"id": "run-rev31", "status": "accepted", "input": text, "metadata": metadata or {}}

    app.state.test_hermes_observed = observed
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


async def pair_owner_device(
    client: AsyncClient,
    *,
    device_id: str,
    secret: str,
    label: str | None = None,
) -> str:
    ticket = await client.post(
        "/v1/devices/pairing-ticket",
        json={"label": label, "ttl_seconds": 600},
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert ticket.status_code == 200
    paired = await client.post(
        "/v1/devices/pair",
        json={
            "pairing_token": ticket.json()["pairing_token"],
            "device_id": device_id,
            "device_secret": secret,
            "public_key_pem": "PEM",
            "label": label,
        },
    )
    assert paired.status_code == 200
    return paired.json()["device_access_token"]


@pytest.mark.asyncio
async def test_runtime_routes_require_hermes_internal_control(runtime_client):
    client, _app = runtime_client

    denied_outer = await client.get("/v1/runtime/status")
    assert denied_outer.status_code == 403
    assert denied_outer.json()["required_scope"] == "runtime"

    token = await pair_owner_device(client, device_id="dev-runtime", secret="runtime-secret")
    denied_internal = await client.get(
        "/v1/runtime/status",
        headers={"X-Van-Device-Token": token},
    )
    assert denied_internal.status_code == 403
    assert denied_internal.json()["detail"] == "internal_control_unauthorized"

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
async def test_v2_signature_binds_voice_provenance_and_canonical_context(runtime_client):
    client, app = runtime_client
    device_id = "dev-voice"
    secret = "voice-secret"
    device_token = await pair_owner_device(client, device_id=device_id, secret=secret, label="S24")

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
    accepted = await client.post(
        "/v1/commands",
        json=body,
        headers={"X-Van-Device-Token": device_token},
    )
    assert accepted.status_code == 200
    result = accepted.json()
    assert result["status"] == "accepted"
    snapshot_id = result["context_snapshot_id"]
    assert snapshot_id

    row = await app.state.store.fetchone(
        "SELECT command_id, kernel_revision, digest FROM context_snapshots WHERE snapshot_id = ?",
        (snapshot_id,),
    )
    assert row is not None
    assert row["command_id"] == "voice-c1"

    metadata = app.state.test_hermes_observed["metadata"]
    assert isinstance(metadata, dict)
    sealed = metadata["canonical_context"]
    assert sealed["snapshot_id"] == snapshot_id
    assert sealed["digest"] == row["digest"]
    assert sealed["kernel_revision"] == row["kernel_revision"]
    assert sealed["policy_refs"] == [
        "security-policy:A1-A5",
        "action-class:signed:A1",
        "action-class:effective:A1",
        "principal:OWNER_DEVICE",
        "resolver:rev3.1.1",
        # A legacy v2 voice command cannot carry signed speaker evidence. The gateway
        # records that absence explicitly so later mission/audit readers cannot mistake
        # "not measured" for "owner voice matched".
        "speaker-evidence:UNAVAILABLE",
    ]
    assert metadata["client_context_authoritative"] is False
    assert metadata["context_capsule_revision"] == 7
    assert metadata["context_capsule_hash"] == "capsule-hash"
    assert metadata["turn_id"] == "voice-turn-1"
    assert metadata["speech_evidence_ref"] == "speech://turn-1"

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
    denied = await client.post(
        "/v1/commands",
        json=tampered,
        headers={"X-Van-Device-Token": device_token},
    )
    assert denied.status_code == 200
    assert denied.json()["status"] == "denied"
    assert "signature" in denied.json()["message"].lower()


@pytest.mark.asyncio
async def test_project_command_snapshot_binds_current_truth_and_repo_head(runtime_client):
    client, app = runtime_client
    device_id = "dev-project"
    secret = "project-secret"
    device_token = await pair_owner_device(client, device_id=device_id, secret=secret)
    await app.state.projects.cache_truth(
        "van",
        {"project_id": "van", "status": "active"},
        "truth-sha-123",
        "repo-sha-456",
    )

    issued = int(time.time())
    canonical = AuthService.canonical_command_v2(
        command_id="project-c1",
        idempotency_key="project-turn-1:mutate",
        device_id=device_id,
        issued_at_unix=issued,
        text="Update VAN implementation",
        action_class="A3",
        project_id="van",
        turn_id="project-turn-1",
        origin_channel="TEXT",
        principal_type="OWNER_DEVICE",
        requested_by=f"device:{device_id}",
        expires_at_unix=issued + 120,
        nonce="project-nonce-1",
        context_capsule_revision=None,
        context_capsule_hash=None,
        speech_evidence_ref=None,
        no_stale_replay=False,
        context_trust="CONVERSATION",
    )
    body = {
        "command_id": "project-c1",
        "idempotency_key": "project-turn-1:mutate",
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": app.state.auth.sign(device_id, canonical),
        "signature_version": 2,
        "text": "Update VAN implementation",
        "action_class": "A3",
        "project_id": "van",
        "turn_id": "project-turn-1",
        "origin_channel": "TEXT",
        "principal_type": "OWNER_DEVICE",
        "requested_by": f"device:{device_id}",
        "expires_at_unix": issued + 120,
        "nonce": "project-nonce-1",
        "context_trust": "CONVERSATION",
    }
    response = await client.post(
        "/v1/commands",
        json=body,
        headers={"X-Van-Device-Token": device_token},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    metadata = app.state.test_hermes_observed["metadata"]
    sealed = metadata["canonical_context"]
    assert "project-truth:van:truth-sha-123" in sealed["live_state_refs"]
    assert "repo-head:van:repo-sha-456" in sealed["live_state_refs"]


@pytest.mark.asyncio
async def test_context_seal_failure_blocks_hermes_dispatch(runtime_client, monkeypatch):
    client, app = runtime_client
    device_id = "dev-context-fail"
    secret = "context-secret"
    device_token = await pair_owner_device(client, device_id=device_id, secret=secret)

    async def fail_compile(*args, **kwargs):
        raise RuntimeError("context-store-unavailable")

    monkeypatch.setattr(app.state.owner_runtime.context, "compile_snapshot", fail_compile)
    issued = int(time.time())
    canonical = AuthService.canonical_command_v2(
        command_id="context-fail-c1",
        idempotency_key="context-fail-turn:read",
        device_id=device_id,
        issued_at_unix=issued,
        text="Show VAN status",
        action_class="A1",
        project_id=None,
        turn_id="context-fail-turn",
        origin_channel="TEXT",
        principal_type="OWNER_DEVICE",
        requested_by=f"device:{device_id}",
        expires_at_unix=issued + 120,
        nonce="context-fail-nonce",
        context_capsule_revision=None,
        context_capsule_hash=None,
        speech_evidence_ref=None,
        no_stale_replay=False,
        context_trust="CONVERSATION",
    )
    body = {
        "command_id": "context-fail-c1",
        "idempotency_key": "context-fail-turn:read",
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": app.state.auth.sign(device_id, canonical),
        "signature_version": 2,
        "text": "Show VAN status",
        "action_class": "A1",
        "turn_id": "context-fail-turn",
        "origin_channel": "TEXT",
        "principal_type": "OWNER_DEVICE",
        "requested_by": f"device:{device_id}",
        "expires_at_unix": issued + 120,
        "nonce": "context-fail-nonce",
        "context_trust": "CONVERSATION",
    }
    response = await client.post(
        "/v1/commands",
        json=body,
        headers={"X-Van-Device-Token": device_token},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "degraded"
    assert result["degraded"] == ["OWNER_CONTEXT_UNAVAILABLE"]
    assert app.state.test_hermes_observed == {}


@pytest.mark.asyncio
async def test_device_revocation_revokes_nonterminal_privileged_execution(runtime_client):
    client, app = runtime_client
    device_id = "dev-revoke"
    secret = "revoke-secret"
    await pair_owner_device(client, device_id=device_id, secret=secret)

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

    revoked = await client.post(
        f"/v1/devices/{device_id}/revoke",
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_privileged_executions"] == 1

    after = await app.state.owner_runtime.actions.get_execution("exec-revoke")
    assert after is not None
    assert after.status.value == "REVOKED"
    assert after.error_code == "DEVICE_OR_GRANT_REVOKED"


@pytest.mark.asyncio
async def test_knowledge_runtime_routes_are_internal_only_and_fail_closed_when_unconfigured(runtime_client):
    client, _app = runtime_client
    token = await pair_owner_device(client, device_id="dev-knowledge", secret="knowledge-secret")

    denied = await client.get(
        "/v1/runtime/knowledge/status",
        headers={"X-Van-Device-Token": token},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "internal_control_unauthorized"

    status = await client.get(
        "/v1/runtime/knowledge/status",
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert status.status_code == 200
    body = status.json()
    assert body["canonical_truth_writes_exposed"] is False
    assert body["secret_content_admitted"] is False
    states = {item["provider"]: item["state"] for item in body["providers"]}
    assert states == {
        "VEKL": "DISABLED",
        "OBSIDIAN": "DISABLED",
        "NOTEBOOK_ENTERPRISE": "DISABLED",
        "NOTEBOOK_CONSUMER": "DISABLED",
    }

    obsidian = await client.post(
        "/v1/runtime/knowledge/obsidian/query",
        json={"query": "VAN architecture"},
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert obsidian.status_code == 503
    assert obsidian.json()["detail"] == "obsidian_disabled"

    no_execution = await client.post(
        "/v1/runtime/knowledge/actions/execute",
        json={"execution_id": "missing-exec", "parameters": {}},
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert no_execution.status_code == 404
    assert no_execution.json()["detail"] == "unknown_execution"