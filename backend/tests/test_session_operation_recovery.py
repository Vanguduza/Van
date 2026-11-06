"""A transport retry cannot become a second owner operation or a false receipt."""
import asyncio

import pytest

from conftest_automation import make_store
from test_session_transport_api import _device, _headers, _mission, _open, _settings, client
from test_van_hermes_session import DEVICE, _envelope, _path
from van_gateway.session.models import CommandAdmission, ResumeRequest, SessionEnvelope
from van_gateway.session.router import REJECT_RESULT_PENDING, SessionDelegates, SessionRouter
from van_gateway.session.service import SessionError, VanHermesSessionService
from van_gateway.storage.db import Store


@pytest.fixture(autouse=True)
def _no_scheduler(monkeypatch):
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")


async def _service(tmp_path):
    service = VanHermesSessionService(await make_store(tmp_path))
    session, epoch = await service.open(device_id=DEVICE, path=_path())
    return service, session, epoch


@pytest.mark.asyncio
async def test_concurrent_same_key_admission_has_one_execution_and_no_null_success(tmp_path):
    service, session, epoch = await _service(tmp_path)
    started, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def submit(payload, device_id):
        calls.append(payload)
        started.set()
        await release.wait()
        return {"status": "accepted", "command_id": "first-command"}
    router = SessionRouter(service, SessionDelegates(submit_command=submit))
    first = asyncio.create_task(router.route(_envelope(session, epoch, idempotency_key="one-key")))
    await asyncio.wait_for(started.wait(), 2)
    duplicates = await asyncio.gather(*(router.route(_envelope(
        session, epoch, idempotency_key="one-key", message_id=f"retry-{i}",
    )) for i in range(10)))
    assert len(calls) == 1
    assert all(not result.accepted and result.refusal == REJECT_RESULT_PENDING for result in duplicates)
    release.set()
    assert (await first).accepted
    recovered = await router.route(_envelope(session, epoch, idempotency_key="one-key", message_id="lost-ack"))
    assert recovered.accepted and recovered.result == {"status": "accepted", "command_id": "first-command"}
    assert len(calls) == 1
    assert len(await service.store.fetchall("SELECT * FROM van_session_messages")) == 1


@pytest.mark.asyncio
async def test_same_message_id_without_key_reuses_receipt_and_changed_payload_refuses(tmp_path):
    service, session, epoch = await _service(tmp_path)
    calls = []
    async def submit(payload, device_id):
        calls.append(payload)
        return {"status": "accepted"}
    router = SessionRouter(service, SessionDelegates(submit_command=submit))
    envelope = _envelope(session, epoch)
    assert (await router.route(envelope)).accepted
    same = await router.route(envelope)
    assert same.accepted and same.admission is CommandAdmission.ALREADY_KNOWN
    changed = await router.route(envelope.model_copy(update={"payload": {"text": "different command"}}))
    assert not changed.accepted and changed.refusal == "session_idempotency_conflict"
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"kind": "mission.cancel"}, {"command_id": "different"},
                                     {"idempotency_key": "different"}])
async def test_message_identity_cannot_be_reused_for_different_operation(tmp_path, changes):
    service, session, epoch = await _service(tmp_path)
    first = _envelope(session, epoch, idempotency_key="first", command_id="original")
    assert (await service.admit(first))[0] is CommandAdmission.ADMITTED
    await service.record_result(first, {"owner_result": "private"})
    assert await service.admit(first.model_copy(update=changes)) == (CommandAdmission.CONFLICT, None)


@pytest.mark.asyncio
async def test_global_message_id_collision_does_not_leak_other_sessions_receipt(tmp_path):
    service, first, epoch = await _service(tmp_path)
    original = _envelope(first, epoch)
    await service.admit(original)
    await service.record_result(original, {"private": "other session result"})
    other, other_epoch = await service.open(device_id=DEVICE, path=_path())
    attempted = _envelope(other, other_epoch)
    assert await service.admit(attempted) == (CommandAdmission.CONFLICT, None)
    await service.forget_message(attempted)
    await service.record_result(attempted, {"forged": "replacement"})
    assert (await service.admit(original))[1] == {"private": "other session result"}


@pytest.mark.asyncio
async def test_non_command_delegate_failure_keeps_ambiguous_effect_from_repeating_after_restart(tmp_path):
    service, session, epoch = await _service(tmp_path)
    calls = []
    async def message(payload, device_id):
        calls.append("owner note durably written")
        raise RuntimeError("acknowledgment failed after effect")
    router = SessionRouter(service, SessionDelegates(submit_command=message, message_mission=message))
    envelope = _envelope(session, epoch, kind="mission.message", idempotency_key="owner-note")
    with pytest.raises(RuntimeError):
        await router.route(envelope)
    restarted = SessionRouter(VanHermesSessionService(Store(service.store.path)),
                              SessionDelegates(submit_command=message, message_mission=message))
    retry = await restarted.route(envelope)
    assert retry.refusal == REJECT_RESULT_PENDING and not retry.accepted
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_new_epoch_is_rechecked_when_envelope_admission_was_delayed(tmp_path):
    service, session, epoch = await _service(tmp_path)
    envelope = _envelope(session, epoch, idempotency_key="delayed")
    await service.accept_upstream(envelope)
    await service.resume(ResumeRequest(van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE))
    with pytest.raises(SessionError) as refused:
        await service.admit(envelope)
    assert refused.value.reason == "session_path_epoch_stale"
    assert not await service.store.fetchall("SELECT * FROM van_session_messages")


@pytest.mark.asyncio
async def test_concurrent_resumes_grant_distinct_epochs_and_keep_matching_paths(tmp_path):
    service, session, epoch = await _service(tmp_path)
    request = ResumeRequest(van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE)
    results = await asyncio.gather(*(service.resume(request, path=_path(path_id=f"path-{i}")) for i in range(10)))
    assert sorted(result.new_path_epoch for result in results) == list(range(epoch + 1, epoch + 11))
    assert (await service.get(session.van_session_id)).authoritative_path_epoch == epoch + 10
    rows = await service.store.fetchall("SELECT * FROM van_session_paths WHERE van_session_id=?", (session.van_session_id,))
    assert len(rows) == 11 and len({row["path_epoch"] for row in rows}) == 11


@pytest.mark.asyncio
async def test_failed_resume_path_persistence_does_not_grant_or_retire_epoch(tmp_path, monkeypatch):
    service, session, epoch = await _service(tmp_path)
    async def unavailable(*args, **kwargs):
        raise RuntimeError("path persistence interrupted")
    monkeypatch.setattr(service, "_record_path", unavailable)
    with pytest.raises(RuntimeError):
        await service.resume(ResumeRequest(van_session_id=session.van_session_id, session_epoch=1, device_id=DEVICE), path=_path())
    assert (await service.get(session.van_session_id)).authoritative_path_epoch == epoch
    assert len(await service.store.fetchall("SELECT * FROM van_session_paths")) == 1


@pytest.mark.asyncio
async def test_http_pending_result_is_retryable_and_resume_does_not_settle_outbox(client):
    ac, app = client
    device = await _device(app)
    opened = await _open(ac, device)
    body = {"message_id": "pending-note", "van_session_id": opened["van_session_id"],
            "session_epoch": opened["session_epoch"], "path_epoch": opened["path_epoch"],
            "kind": "mission.message", "created_at_ms": 1000, "idempotency_key": "pending-note-key",
            "payload": {"mission_id": "known-mission", "text": "owner note"}}
    await app.state.van_sessions.admit(SessionEnvelope(**body, device_id="owner-phone", direction="UPSTREAM"))
    app.state.session_router.delegates.recover_result = None
    response = await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    assert response.status_code == 503 and response.json()["detail"] == REJECT_RESULT_PENDING
    resumed = await ac.post("/v1/session/resume", headers=_headers(device), json={
        "van_session_id": opened["van_session_id"], "session_epoch": opened["session_epoch"],
        "pending_command_ids": ["pending-note"],
    })
    assert resumed.status_code == 200
    assert resumed.json()["command_states"]["pending-note"] == "RESULT_PENDING"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["mission.cancel", "mission.message", "decision.answer"])
async def test_local_control_recovers_interrupted_ack_without_duplicate_effect(client, monkeypatch, kind):
    from van_gateway.decisions.service import DecisionCreate
    ac, app = client
    device = await _device(app)
    opened = await _open(ac, device)
    mission_id = await _mission(ac)
    decision = await app.state.decisions.escalate(DecisionCreate(title="Owner judgment", body="Approve?"))
    payload = ({"decision_id": decision.id, "approved": False} if kind == "decision.answer" else
               {"mission_id": mission_id, "text": "single owner note"})
    body = {"message_id": "interrupted-control", "van_session_id": opened["van_session_id"],
            "session_epoch": opened["session_epoch"], "path_epoch": opened["path_epoch"],
            "kind": kind, "idempotency_key": "interrupted-control-key", "payload": payload}
    original = app.state.van_sessions.record_result
    async def interrupted(*args, **kwargs):
        raise RuntimeError("acknowledgment persistence interrupted after local effect")
    monkeypatch.setattr(app.state.van_sessions, "record_result", interrupted)
    with pytest.raises(RuntimeError):
        await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    monkeypatch.setattr(app.state.van_sessions, "record_result", original)
    body["message_id"] = "control-retry-on-another-carrier"
    recovered = await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    assert recovered.status_code == 200 and recovered.json()["accepted"] is True
    stable = await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    assert stable.json() == recovered.json()
    if kind == "mission.message":
        notes = await app.state.store.fetchall("SELECT event_id FROM mission_events WHERE mission_id=? AND summary=?",
                                               (mission_id, "single owner note"))
        assert len(notes) == 1 and recovered.json()["result"]["event_id"] == notes[0]["event_id"]
        row = await app.state.store.fetchone("SELECT event_type FROM mission_events WHERE event_id=?", (notes[0]["event_id"],))
        assert row["event_type"] == "mission.message"
    elif kind == "mission.cancel":
        assert recovered.json()["result"]["state"] == "CANCELLED"
        assert len(await app.state.store.fetchall("SELECT event_id FROM mission_events WHERE mission_id=? AND event_type='mission.cancelled'",
                                                 (mission_id,))) == 1
    else:
        assert recovered.json()["result"]["status"] == "REJECTED"
    rows = await app.state.store.fetchall("SELECT result_json FROM van_session_messages WHERE idempotency_key=?",
                                         ("interrupted-control-key",))
    assert len(rows) == 1 and rows[0]["result_json"] is not None


@pytest.mark.asyncio
async def test_idempotent_owner_note_identity_refuses_changed_event_content(client):
    from van_gateway.mission.models import MissionEventType
    from van_gateway.mission.service import MissionError
    from van_gateway.models import PrincipalType
    ac, app = client
    await _device(app)
    mission_id = await _mission(ac)
    args = {"mission_id": mission_id, "event_type": MissionEventType.MISSION_CREATED,
            "actor": PrincipalType.OWNER_DEVICE, "summary": "original", "idempotency_key": "exact-note"}
    first = await app.state.missions.record_event(**args)
    assert await app.state.missions.record_event(**args) == first
    with pytest.raises(MissionError, match="MISSION_EVENT_IDEMPOTENCY_CONFLICT"):
        await app.state.missions.record_event(**{**args, "summary": "different"})


@pytest.mark.asyncio
@pytest.mark.parametrize("ambiguous", [False, True])
async def test_session_command_retry_uses_original_authority_and_never_redelivers_unknown_handoff(client, monkeypatch, ambiguous):
    from test_command_recovery import _request
    from van_gateway.hermes.bridge import HermesBridgeError
    ac, app = client
    device = await _device(app)
    opened = await _open(ac, device)
    command = await _request(app, "owner-phone")
    calls = []
    async def healthy():
        return {"ok": True}
    async def initially_unavailable(text, metadata=None):
        calls.append(metadata)
        raise HermesBridgeError("hermes_offline", "test handoff failed", retry_safe=not ambiguous)
    monkeypatch.setattr(app.state.orchestrator.hermes, "health", healthy)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", initially_unavailable)
    body = {"message_id": "session-command", "van_session_id": opened["van_session_id"],
            "session_epoch": opened["session_epoch"], "path_epoch": opened["path_epoch"],
            "kind": "command.submit", "command_id": command["command_id"],
            "idempotency_key": "outer-session-command-key", "payload": command}
    first = await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    assert first.status_code == 200
    assert first.json()["result"]["status"] == ("outcome_unknown" if ambiguous else "degraded")
    original_authority = await app.state.owner_runtime.authority.get(command["command_id"])
    async def accepted(text, metadata=None):
        calls.append(metadata)
        return {"id": "safely-retried-run"}
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", accepted)
    body["message_id"] = "command-retry-carrier"
    second = await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    assert second.status_code == 200
    assert second.json()["result"]["status"] == ("outcome_unknown" if ambiguous else "accepted")
    assert second.json()["result"]["mission_id"] == first.json()["result"]["mission_id"]
    assert await app.state.owner_runtime.authority.get(command["command_id"]) == original_authority
    assert len(calls) == (1 if ambiguous else 2)
    if not ambiguous:
        assert calls[0] == calls[1]
    stable = await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    assert stable.json() == second.json()


@pytest.mark.asyncio
async def test_cancellation_state_and_owner_timeline_commit_together(client, monkeypatch):
    from van_gateway.mission.models import MissionEventType
    ac, app = client
    device = await _device(app)
    mission_id = await _mission(ac)
    original = app.state.missions._persist_event
    async def unavailable(db, event):
        if event.event_type is MissionEventType.MISSION_CANCELLED:
            raise RuntimeError("timeline persistence interrupted")
        return await original(db, event)
    monkeypatch.setattr(app.state.missions, "_persist_event", unavailable)
    with pytest.raises(RuntimeError):
        await ac.post(f"/v1/missions/{mission_id}/cancel", headers=_headers(device))
    assert (await app.state.missions.get(mission_id)).state.value == "CAPTURED"
    assert not await app.state.store.fetchall("SELECT event_id FROM mission_events WHERE mission_id=? AND event_type='mission.cancelled'", (mission_id,))
    monkeypatch.setattr(app.state.missions, "_persist_event", original)
    first = await ac.post(f"/v1/missions/{mission_id}/cancel", headers=_headers(device))
    second = await ac.post(f"/v1/missions/{mission_id}/cancel", headers=_headers(device))
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    assert len(await app.state.store.fetchall("SELECT event_id FROM mission_events WHERE mission_id=? AND event_type='mission.cancelled'", (mission_id,))) == 1
    downstream = await app.state.missions.bus.replay("owner-phone", 0)
    assert any(event["event_type"] == "mission.cancelled" for event in downstream["events"])
