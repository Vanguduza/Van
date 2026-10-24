"""Only an owner-reviewed immutable Gmail draft may reach the A4 handoff."""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from test_gateway import _clear_settings_cache, client
from van_gateway.auth.service import AuthService
from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.google.service import GoogleAuthError


@pytest.fixture(autouse=True)
def _no_scheduler(monkeypatch):
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")


async def _owner(ac, app):
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    ticket = await app.state.auth.create_pairing_ticket("gmail-owner")
    device = await app.state.auth.pair_device(ticket.token, "gmail-owner", "test-gmail-owner-secret", public, "Owner test phone")
    ac.headers.update({"X-Van-Device-Token": device.access_token})
    return key


def _command(app, suffix, *, proof=None, channel="UI", trust="CONVERSATION"):
    issued = int(time.time())
    body = {"command_id": f"gmail-{suffix}", "idempotency_key": f"gmail-{suffix}-key", "device_id": "gmail-owner",
            "issued_at_unix": issued, "text": "send gmail draft id DraftCase_1", "action_class": "A1", "signature_version": 2,
            "origin_channel": channel, "principal_type": "OWNER_DEVICE", "requested_by": "device:gmail-owner",
            "context_trust": trust, "expires_at_unix": issued + 20}
    canonical = AuthService.canonical_command_v2(
        command_id=body["command_id"], idempotency_key=body["idempotency_key"], device_id=body["device_id"],
        issued_at_unix=issued, text=body["text"], action_class="A1", project_id=None, turn_id=None,
        origin_channel=channel, principal_type="OWNER_DEVICE", requested_by="device:gmail-owner", expires_at_unix=issued + 20,
        nonce=None, context_capsule_revision=None, context_capsule_hash=None, speech_evidence_ref=None,
        no_stale_replay=False, context_trust=trust,
    )
    body["signature"] = app.state.auth.sign("gmail-owner", canonical)
    if proof is not None:
        body["approval_proof"] = proof
    return body


def _preview(digest="a" * 64, **changes):
    value = {"draft_id": "DraftCase_1", "draft_content_sha256": digest, "recipient": ["test@example.invalid"],
             "subject": "Private owner preview", "body_sha256": "b" * 64,
             "preview": {"body": "Canned owner-only message"}, "immutable_payload_send_supported": True}
    return {**value, **changes}


@pytest.mark.parametrize("text", ["send draft id DraftCase_1", "send gmail draft id DraftCase_1"])
def test_exact_send_draft_resolution_preserves_id_and_requires_a4(text):
    result = TypedCommandResolver().resolve(text)
    assert result.mode is ResolutionMode.EXACT_ACTION
    assert result.action_id == "google.gmail.send" and result.canonical_action_class.value == "A4"
    assert result.parameters == {"draft_id": "DraftCase_1"}


@pytest.mark.parametrize("text", ["send draft id x and delete notebook y", "please send draft id x", "send draft id ../x", "send draft id"])
def test_ambiguous_or_malformed_draft_commands_do_not_get_exact_send_authority(text):
    assert TypedCommandResolver().resolve(text).mode is not ResolutionMode.EXACT_ACTION


@pytest.mark.asyncio
async def test_owner_challenge_displays_and_binds_server_observed_content(client, monkeypatch):
    ac, app = client
    await _owner(ac, app)
    calls = []
    async def preview(draft_id):
        calls.append(draft_id)
        return _preview()
    monkeypatch.setattr(app.state.orchestrator.google, "gmail_draft_preview", preview)
    body = _command(app, "preview")
    # A model/device-supplied digest cannot replace the trusted provider read.
    body["client_context"] = {"draft_content_sha256": "c" * 64}
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "approval_required" and calls == ["DraftCase_1"]
    assert result["resolved_parameters"] == {"draft_id": "DraftCase_1", "draft_content_sha256": "a" * 64}
    assert result["approval_preview"]["recipient"] == ["test@example.invalid"]
    assert "preview" not in result["approval_preview"]
    assert result["approval_preview"]["source_draft_cleanup"] == "NOT_ATTEMPTED"
    record = await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",
                                           (f"owner_approval:{result['approval_challenge_id']}",))
    assert json.loads(record["value"])["parameters"] == result["resolved_parameters"]
    assert not await app.state.store.fetchall("SELECT key FROM runtime_meta WHERE key LIKE 'command_authority:%'")


@pytest.mark.asyncio
@pytest.mark.parametrize("preview_result", [None, _preview("invalid"), _preview(draft_id="Other"),
                                           _preview(immutable_payload_send_supported=False)])
async def test_unavailable_or_unqualified_preview_cannot_issue_send_approval(client, monkeypatch, preview_result):
    ac, app = client
    await _owner(ac, app)
    async def preview(draft_id):
        if preview_result is None:
            raise GoogleAuthError("test provider unavailable")
        return preview_result
    monkeypatch.setattr(app.state.orchestrator.google, "gmail_draft_preview", preview)
    result = (await ac.post("/v1/commands", json=_command(app, "unavailable"))).json()
    assert result["status"] == "degraded" and not result["requires_approval"]
    assert not await app.state.store.fetchall("SELECT key FROM runtime_meta WHERE key LIKE 'owner_approval:%'")
    assert not await app.state.store.fetchall("SELECT key FROM runtime_meta WHERE key LIKE 'command_authority:%'")


@pytest.mark.asyncio
@pytest.mark.parametrize("channel,trust", [("NOTIFICATION_EVENT", "CONVERSATION"), ("UI", "UNTRUSTED")])
async def test_external_content_cannot_read_or_receive_owner_mail_preview(client, monkeypatch, channel, trust):
    ac, app = client
    await _owner(ac, app)
    async def forbidden(draft_id):
        raise AssertionError("external-content command reached private mailbox preview")
    monkeypatch.setattr(app.state.orchestrator.google, "gmail_draft_preview", forbidden)
    result = (await ac.post("/v1/commands", json=_command(app, "external", channel=channel, trust=trust))).json()
    assert result["status"] == "denied" and result["approval_preview"] is None


@pytest.mark.asyncio
async def test_changed_draft_refuses_existing_biometric_proof_without_dispatch_or_forgery_lockout(client, monkeypatch):
    ac, app = client
    key = await _owner(ac, app)
    digest = ["a" * 64]
    async def preview(draft_id):
        return _preview(digest[0])
    monkeypatch.setattr(app.state.orchestrator.google, "gmail_draft_preview", preview)
    first = (await ac.post("/v1/commands", json=_command(app, "before-change"))).json()
    signature = base64.b64encode(key.sign(first["approval_challenge"].encode(), ec.ECDSA(hashes.SHA256()))).decode()
    proof = {"challenge_id": first["approval_challenge_id"], "source_command_id": "gmail-before-change", "signature_b64": signature}
    digest[0] = "d" * 64
    calls = []
    async def forbidden_send(text, metadata=None):
        calls.append(metadata)
        return {"id": "must-not-execute"}
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", forbidden_send)
    result = (await ac.post("/v1/commands", json=_command(app, "after-change", proof=proof))).json()
    assert result["status"] == "denied" and calls == []
    assert not await app.state.store.fetchall("SELECT key FROM runtime_meta WHERE key LIKE 'command_authority:%'")
    assert await app.state.store.fetchone("SELECT key FROM runtime_meta WHERE key=?", (f"owner_approval:{proof['challenge_id']}",))
    record = await app.state.store.fetchone("SELECT failure_reason FROM audit WHERE command_id=? ORDER BY rowid DESC LIMIT 1", ("gmail-after-change",))
    assert record["failure_reason"] == "approval_parameters_changed"
