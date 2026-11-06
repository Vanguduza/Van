"""Mission verification independently re-reads the exact A4-approved sent MIME."""
import base64

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from test_gmail_owner_send_approval import _clear_settings_cache, _no_scheduler, client, _owner, _command
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.google.mail import content_digest, encode_snapshot, message_snapshot
from van_gateway.models import PrincipalType
from van_gateway.mission.models import VerificationStatus


SNAPSHOT = {"from": "owner@example.invalid", "to": ["target@example.invalid"], "cc": ["cc@example.invalid"],
    "bcc": ["bcc@example.invalid"], "reply_to": [], "subject": "Owner reviewed send", "in_reply_to": "", "references": [], "body": "Exact approved text\n"}


async def _send(ac, app, monkeypatch):
    key = await _owner(ac, app)
    raw = encode_snapshot(SNAPSHOT)
    sent = {"id": "sent-1", "threadId": "thread-1", "labelIds": ["SENT"], "raw": raw}
    reads = []
    async def provider(method, *args, **kwargs):
        reads.append(method)
        if method == "gmail_draft_get":
            return {"id": "DraftCase_1", "message": {"threadId": "thread-1", "raw": raw}}
        if method == "gmail_message_send":
            assert content_digest(message_snapshot(args[0]), args[1]) == content_digest(SNAPSHOT, "thread-1")
            return {"id": "sent-1"}
        if method == "gmail_message_get":
            return dict(sent)
        raise AssertionError(method)
    monkeypatch.setattr(app.state.google, "_provider_call", provider)
    first = (await ac.post("/v1/commands", json=_command(app, "mission-challenge"))).json()
    assert first["status"] == "approval_required", first
    assert first["approval_preview"]["cc"] == SNAPSHOT["cc"] and first["approval_preview"]["bcc"] == SNAPSHOT["bcc"]
    proof = {"challenge_id": first["approval_challenge_id"], "signature_b64": base64.b64encode(
        key.sign(first["approval_challenge"].encode(), ec.ECDSA(hashes.SHA256()))).decode()}
    result = (await ac.post("/v1/commands", json=_command(app, "mission-approved", proof=proof))).json()
    assert result["status"] == "accepted", result
    authority = await CommandAuthorityService(app.state.store).get("gmail-mission-approved")
    params = authority.typed_parameter_constraints
    actions = app.state.owner_runtime.actions
    execution = await actions.begin(execution_id="gmail-owner-send", command_id=authority.command_id, turn_id=None,
        action_id="google.gmail.send", principal_type=PrincipalType.OWNER_DEVICE, requested_by="device:gmail-owner",
        idempotency_key="gmail-owner-send-key", parameters=params, snapshot_id=authority.snapshot_id, owner_approved=True)
    receipt = await app.state.google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=params)
    assert receipt["verification"]["status"] == "VERIFIED_SUCCESS"
    mission = await app.state.missions.get(result["mission_id"])
    return sent, reads, mission


@pytest.mark.asyncio
async def test_sent_mission_rechecks_provider_after_action_receipt_and_reaches_verified_success(client, monkeypatch):
    ac, app = client
    sent, reads, mission = await _send(ac, app, monkeypatch)
    count = reads.count("gmail_message_get")
    receipt = await app.state.missions.ingest_hermes_result(hermes_run_id="run-1", outcome="COMPLETED", summary="worker done")
    assert receipt["state"] == "VERIFIED_SUCCESS", receipt
    assert reads.count("gmail_message_get") > count
    fresh = await app.state.missions.get(mission.mission_id)
    assert fresh.verification_state is VerificationStatus.VERIFIED
    assert fresh.success_contract.postconditions["draft_content_sha256"] == content_digest(SNAPSHOT, "thread-1")


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["recipient", "thread", "label", "provider-unavailable", "missing-correlation"])
async def test_worker_and_old_verified_action_receipt_cannot_certify_changed_or_unreadable_sent_message(client, monkeypatch, change):
    ac, app = client
    sent, _, mission = await _send(ac, app, monkeypatch)
    if change == "recipient":
        sent["raw"] = encode_snapshot({**SNAPSHOT, "bcc": ["changed@example.invalid"]})
    elif change == "thread":
        sent["threadId"] = "unapproved-thread"
    elif change == "label":
        sent["labelIds"] = ["DRAFT"]
    elif change == "provider-unavailable":
        async def unavailable(message_id):
            raise OSError("test provider unreachable")
        monkeypatch.setattr(app.state.google, "gmail_message_get", unavailable)
    else:
        await app.state.store.execute("UPDATE action_executions SET correlation_json='{}' WHERE execution_id='gmail-owner-send'")
    receipt = await app.state.missions.ingest_hermes_result(hermes_run_id="run-1", outcome="COMPLETED", summary="worker says success")
    assert receipt["state"] != "VERIFIED_SUCCESS"
    fresh = await app.state.missions.get(mission.mission_id)
    assert fresh.verification_state in {VerificationStatus.FAILED, VerificationStatus.UNVERIFIABLE}
