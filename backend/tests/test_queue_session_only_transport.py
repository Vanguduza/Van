"""LAC234 SOURCE: same-envelope transport recovery through existing idempotent owners."""
import time
import pytest
from test_session_transport_api import client, _settings, _device, _headers, _open, _mission
from van_gateway.decisions.service import DecisionCreate
from van_gateway.ops.retention import POLICIES, RETENTION_DAYS


@pytest.fixture(autouse=True)
def no_scheduler(monkeypatch):
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["mission.message", "mission.cancel", "decision.answer"])
@pytest.mark.parametrize("interrupted_after_effect", [False, True])
async def test_original_session_only_transport_identity_has_one_owned_effect(client, monkeypatch, kind, interrupted_after_effect):
    ac, app = client
    device = await _device(app)
    opened = await _open(ac, device)
    mission = await _mission(ac)
    decision = await app.state.decisions.escalate(DecisionCreate(title="SOURCE decision", body="Owner judgment"))
    payload = ({"decision_id": decision.id, "approved": False} if kind == "decision.answer"
               else {"mission_id": mission, "text": "SOURCE single original note"})
    now = int(time.time() * 1000)
    body = dict(message_id="SOURCE-original-message", van_session_id=opened["van_session_id"],
                session_epoch=opened["session_epoch"], path_epoch=opened["path_epoch"], kind=kind,
                idempotency_key="SOURCE-original-outer-key", created_at_ms=now,
                expires_at_ms=now + 4 * 60 * 60 * 1000, payload=payload)
    original_record = app.state.van_sessions.record_result
    if interrupted_after_effect:
        async def fail_after_effect(*args, **kwargs):
            raise RuntimeError("SOURCE lost original result write after local effect")
        monkeypatch.setattr(app.state.van_sessions, "record_result", fail_after_effect)
        with pytest.raises(RuntimeError):
            await ac.post("/v1/session/messages", headers=_headers(device), json=body)
        monkeypatch.setattr(app.state.van_sessions, "record_result", original_record)
    resumed = await ac.post("/v1/session/resume", headers=_headers(device), json=dict(
        van_session_id=opened["van_session_id"], session_epoch=opened["session_epoch"],
        pending_command_ids=[body["message_id"]]))
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["command_states"][body["message_id"]] == ("RESULT_PENDING" if interrupted_after_effect else "UNKNOWN")
    # Only the replaceable carrier epoch changes. This is the same operation, not
    # a new key/body/lease and not a statement that the original effect was absent.
    recovered_body = {**body, "path_epoch": resumed.json()["new_path_epoch"]}
    recovered = await ac.post("/v1/session/messages", headers=_headers(device), json=recovered_body)
    assert recovered.status_code == 200, recovered.text
    replay = await ac.post("/v1/session/messages", headers=_headers(device), json=recovered_body)
    assert replay.status_code == 200
    assert replay.json()["result"] == recovered.json()["result"]
    assert replay.json()["admission"] == "ALREADY_KNOWN"
    assert recovered.json()["admission"] == ("ALREADY_KNOWN" if interrupted_after_effect else "ADMITTED")
    rows = await app.state.store.fetchall("SELECT * FROM van_session_messages WHERE idempotency_key=?", (body["idempotency_key"],))
    assert len(rows) == 1 and rows[0]["message_id"] == body["message_id"] and rows[0]["result_json"] is not None
    if kind == "mission.message":
        notes = await app.state.store.fetchall("SELECT * FROM mission_events WHERE mission_id=? AND summary=?", (mission, payload["text"]))
        assert len(notes) == 1 and recovered.json()["result"]["event_id"] == notes[0]["event_id"]
    elif kind == "mission.cancel":
        assert recovered.json()["result"]["state"] == "CANCELLED"
        assert len(await app.state.store.fetchall("SELECT * FROM mission_events WHERE mission_id=? AND event_type='mission.cancelled'", (mission,))) == 1
    else:
        assert recovered.json()["result"]["status"] == "REJECTED"
    policy = next(p for p in POLICIES if p.table == "van_session_messages")
    assert RETENTION_DAYS[policy.retention] == 365
    assert body["expires_at_ms"] - body["created_at_ms"] < 365 * 24 * 60 * 60 * 1000
