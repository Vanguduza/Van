"""LAC234 SOURCE: original HTTP command recovery through the existing session reader."""
import asyncio
import time

import pytest
from test_session_transport_api import client, _settings, _device, _headers, _open
from van_gateway.auth.service import AuthService
from van_gateway.models import CommandRequest


@pytest.fixture(autouse=True)
def no_scheduler(monkeypatch):
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")


def signed(app, device_id, key="original-key"):
    body = dict(command_id="original-command", idempotency_key=key, device_id=device_id,
                issued_at_unix=int(time.time()), text="brief me", action_class="A1")
    body["signature"] = app.state.auth.sign(device_id, AuthService.canonical_command(
        **body, project_id=None))
    return body


def reference(opened, body):
    return dict(van_session_id=opened["van_session_id"], message_id="original-outer-message",
                command_id=body["command_id"], device_id=body["device_id"],
                profile_id="SOURCE-captured-profile", idempotency_key="original-outer-key", command_request=body)


async def resume(ac, enrolled, opened, body):
    return await ac.post("/v1/session/resume", headers=_headers(enrolled), json=dict(
        van_session_id=opened["van_session_id"], session_epoch=opened["session_epoch"],
        pending_command_ids=[body["command_id"]],
        original_command_references=[reference(opened, body)]))


@pytest.mark.asyncio
async def test_direct_http_reservation_is_pending_in_new_session_envelope(client, monkeypatch):
    ac, app = client
    enrolled = await _device(app)
    opened = await _open(ac, enrolled)
    body = signed(app, "owner-phone")
    admitted = asyncio.Event()
    release = asyncio.Event()
    original = app.state.orchestrator.idempotency.begin

    async def interrupted(*args, **kwargs):
        result = await original(*args, **kwargs)
        admitted.set()
        await release.wait()
        return result

    monkeypatch.setattr(app.state.orchestrator.idempotency, "begin", interrupted)
    direct = asyncio.create_task(ac.post("/v1/commands", headers=_headers(enrolled), json=body))
    try:
        await asyncio.wait_for(admitted.wait(), 5)
        response = await resume(ac, enrolled, opened, body)
        assert response.status_code == 200, response.text
        assert response.json()["command_states"][body["command_id"]] == "RESULT_PENDING"
    finally:
        release.set()
        await direct


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "digest", "signature", "device", "outer_session", "legacy"])
async def test_unverifiable_or_missing_original_is_held_without_state_change(client, change):
    ac, app = client
    enrolled = await _device(app)
    opened = await _open(ac, enrolled)
    body = signed(app, "owner-phone")
    if change != "missing":
        await app.state.orchestrator.idempotency.begin(body["idempotency_key"], CommandRequest(**body).model_dump())
    ref = reference(opened, dict(body))
    if change == "digest":
        ref["command_request"]["client_context"] = {"changed": True}
    if change == "signature":
        ref["command_request"]["signature"] = "0" * 64
    if change == "device":
        ref["device_id"] = "foreign-device"
    if change == "outer_session":
        ref["van_session_id"] = "foreign-session"
    if change == "legacy":
        del ref["command_request"]["signature"]
    before = await app.state.store.fetchall("SELECT * FROM idempotency")
    response = await ac.post("/v1/session/resume", headers=_headers(enrolled), json=dict(
        van_session_id=opened["van_session_id"], session_epoch=opened["session_epoch"],
        pending_command_ids=[body["command_id"]], original_command_references=[ref]))
    assert response.status_code == 200, response.text
    assert response.json()["command_states"][body["command_id"]] == "ORIGINAL_UNRESOLVED"
    assert [dict(r) for r in await app.state.store.fetchall("SELECT * FROM idempotency")] == [dict(r) for r in before]
    assert await app.state.store.fetchall("SELECT * FROM van_session_messages") == []


@pytest.mark.asyncio
async def test_completed_original_can_be_read_repeatedly_after_restart_without_old_nonce_use(client):
    ac, app = client
    enrolled = await _device(app)
    opened = await _open(ac, enrolled)
    body = signed(app, "owner-phone")
    body.update(signature_version=3, issued_at_unix=1, expires_at_unix=2, nonce="original-already-used-nonce",
                requested_by="device:owner-phone")
    body["signature"] = app.state.auth.sign("owner-phone", app.state.orchestrator.original_command_canonical(CommandRequest(**body)))
    idem = app.state.orchestrator.idempotency
    await idem.begin(body["idempotency_key"], CommandRequest(**body).model_dump())
    result = dict(status="denied", command_id=body["command_id"], idempotency_key=body["idempotency_key"], message="Original refusal")
    await idem.complete(body["idempotency_key"], result)
    from van_gateway.command.nonce import CommandNonceService
    await CommandNonceService(app.state.store).consume(device_id="owner-phone", nonce=body["nonce"], command_id=body["command_id"])
    original_nonces = [dict(r) for r in await app.state.store.fetchall("SELECT * FROM command_nonces")]
    # Reload original protected secret through its existing restart owner, not a new key.
    await app.state.auth.load_persisted_secrets()
    original = [dict(r) for r in await app.state.store.fetchall("SELECT * FROM idempotency")]
    for _ in range(2):
        response = await resume(ac, enrolled, opened, body)
        assert response.status_code == 200, response.text
        assert response.json()["command_states"][body["command_id"]] == "ORIGINAL_COMPLETED"
    assert [dict(r) for r in await app.state.store.fetchall("SELECT * FROM idempotency")] == original
    assert await app.state.store.fetchall("SELECT * FROM van_session_messages") == []
    assert [dict(r) for r in await app.state.store.fetchall("SELECT * FROM command_nonces")] == original_nonces


@pytest.mark.asyncio
async def test_foreign_current_device_cannot_recover_original_result(client):
    ac, app = client
    original_device = await _device(app)
    original_session = await _open(ac, original_device)
    body = signed(app, "owner-phone")
    other = await _device(app, "other-phone")
    other_session = await _open(ac, other)
    await app.state.orchestrator.idempotency.begin(body["idempotency_key"], CommandRequest(**body).model_dump())
    await app.state.orchestrator.idempotency.complete(body["idempotency_key"], dict(
        status="accepted", command_id=body["command_id"], idempotency_key=body["idempotency_key"], message="Private original"))
    ref = reference(original_session, body)
    ref["van_session_id"] = other_session["van_session_id"]
    ref["device_id"] = "other-phone"
    response = await ac.post("/v1/session/resume", headers=_headers(other), json=dict(
        van_session_id=other_session["van_session_id"], session_epoch=other_session["session_epoch"],
        pending_command_ids=[body["command_id"]], original_command_references=[ref]))
    assert response.status_code == 200, response.text
    assert response.json()["command_states"][body["command_id"]] == "ORIGINAL_UNRESOLVED"
    assert "Private original" not in response.text


@pytest.mark.asyncio
async def test_http_then_original_same_id_session_handoff_has_one_downstream_run(client, monkeypatch):
    from test_session_transport_api import _envelope
    ac, app = client
    enrolled = await _device(app)
    calls = []

    async def source_health():
        return {"ok": True, "profile": "SOURCE-hermes"}

    async def source_run(text, metadata=None):
        calls.append((text, metadata))
        return {"id": "SOURCE-original-run", "status": "accepted"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", source_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", source_run)
    body = signed(app, "owner-phone")
    first = await ac.post("/v1/commands", headers=_headers(enrolled), json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "accepted", first.text
    assert len(calls) == 1
    opened = await _open(ac, enrolled)
    recovered = await resume(ac, enrolled, opened, body)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["command_states"][body["command_id"]] == "ORIGINAL_COMPLETED"
    original_result = recovered.json()["original_command_results"][body["command_id"]]
    assert original_result["history_owner"] == "command_mission"
    assert original_result["result"]["status"] == "accepted"
    assert original_result["result"]["mission_id"] == first.json()["mission_id"]
    assert original_result["result"]["hermes_run_id"] == "SOURCE-original-run"
    assert original_result["owner_result"]["mission_state"] == "RUNNING"
    assert not any(key.startswith("approval_") or key == "signature" for key in original_result["result"])
    handoff = await ac.post("/v1/session/messages", headers=_headers(enrolled), json=_envelope(
        opened, recovered.json()["new_path_epoch"], message_id="original-outer-message",
        idempotency_key="original-outer-key", command_id=body["command_id"], kind="command.submit", payload=body))
    assert handoff.status_code == 200, handoff.text
    assert len(calls) == 1
    reread = await resume(ac, enrolled, opened, body)
    assert reread.status_code == 200, reread.text
    assert reread.json()["command_states"][body["command_id"]] == "ORIGINAL_COMPLETED"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_unconfigured_binding_policy_preserves_legacy_but_refuses_strict_currentness(client, monkeypatch):
    from van_gateway.config import get_settings
    ac, app = client
    enrolled = await _device(app)
    assert app.state.owner_device_bindings is None
    legacy = await ac.get("/v1/device-binding/status", headers=_headers(enrolled))
    assert legacy.status_code == 200 and legacy.json()["owner_mutation_policy"]["eligible"]
    monkeypatch.setattr(get_settings(), "require_device_binding", True)
    strict = await ac.get("/v1/device-binding/status", headers=_headers(enrolled))
    assert strict.status_code == 200 and not strict.json()["owner_mutation_policy"]["eligible"]
    assert strict.json()["owner_mutation_policy"]["reason"] == "owner_device_binding_unconfigured"
    mutation = await ac.post("/v1/session/open", json={}, headers=_headers(enrolled))
    assert mutation.status_code == 503 and mutation.json()["detail"] == "owner_device_binding_unconfigured"
    assert await app.state.store.fetchall("SELECT * FROM command_nonces") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["missing_mission", "foreign_mission", "unbound_run"])
async def test_original_accepted_result_without_proved_native_history_transfer_remains_unresolved(client, monkeypatch, corruption):
    import json
    ac, app = client
    enrolled = await _device(app)
    async def source_health(): return {"ok": True, "profile": "SOURCE"}
    async def source_run(text, metadata=None): return {"id": "SOURCE-bound-run", "status": "accepted"}
    monkeypatch.setattr(app.state.orchestrator.hermes, "health", source_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", source_run)
    body = signed(app, "owner-phone")
    accepted = await ac.post("/v1/commands", headers=_headers(enrolled), json=body)
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    damaged = accepted.json()
    if corruption == "missing_mission": damaged["mission_id"] = None
    if corruption == "foreign_mission": damaged["mission_id"] = "SOURCE-other-mission"
    if corruption == "unbound_run": damaged["hermes_run_id"] = "SOURCE-unbound-run"
    await app.state.store.execute("UPDATE idempotency SET response_json=? WHERE idempotency_key=?", (json.dumps(damaged), body["idempotency_key"]))
    before = [dict(r) for r in await app.state.store.fetchall("SELECT * FROM idempotency")]
    opened = await _open(ac, enrolled)
    response = await resume(ac, enrolled, opened, body)
    assert response.status_code == 200, response.text
    assert response.json()["command_states"][body["command_id"]] == "ORIGINAL_UNRESOLVED"
    assert body["command_id"] not in response.json()["original_command_results"]
    assert [dict(r) for r in await app.state.store.fetchall("SELECT * FROM idempotency")] == before
