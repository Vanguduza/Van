"""Real mounted owner and runtime boundaries for judgment and execution controls."""
from __future__ import annotations

import pytest

from test_session_transport_api import (
    INTERNAL, _device, _headers, _mission, _settings, client,
)


@pytest.fixture(autouse=True)
def no_scheduler(monkeypatch):
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")


async def bound(ac, app):
    device = await _device(app)
    mission = await _mission(ac)
    await app.state.store.execute("INSERT INTO hermes_run_bindings(hermes_run_id,mission_id,bound_at_ms) VALUES (?,?,?)", ("actual-run", mission, 1))
    return device, mission


def proposal(mission, **changes):
    body = dict(mission_id=mission, hermes_run_id="actual-run", request_id="runtime-decision-1",
                title="Choose a format", body="The owner must select a format.",
                choices=[{"id":"brief","label":"Brief"},{"id":"detailed","label":"Detailed"}])
    body.update(changes)
    return body


async def test_actual_bound_runtime_proposal_owner_answer_and_readback(client):
    ac, app = client
    device, mission = await bound(ac, app)
    created = await ac.post("/v1/runtime/decisions/escalate", headers={"X-Van-Internal-Token": INTERNAL}, json=proposal(mission))
    assert created.status_code == 200, created.text
    record = created.json()
    assert record["source"] == "hermes-runtime" and record["hermes_ref"] == "hermes-run:actual-run"
    assert record["status"] == "OPEN" and not record["grants_action_authority"]
    path = f"/v1/decisions/{record['id']}"
    assert (await ac.get(path, headers=_headers(device))).json() == record
    body = {"choice_id":"brief","expected_revision":1,"request_id":"owner-answer-1","note":"Exact note"}
    accepted = await ac.post(path + "/answer", headers=_headers(device), json=body)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["selected_choice_id"] == "brief" and accepted.json()["status"] == "ANSWERED"
    assert (await ac.post(path + "/answer", headers=_headers(device), json=body)).json() == accepted.json()
    assert (await ac.get(path, headers=_headers(device))).json() == accepted.json()
    assert (await app.state.store.fetchone("SELECT owner_choice FROM decision_fingerprints"))["owner_choice"] == "brief"
    seen = await ac.get(f"/v1/runtime/decisions/{record['id']}", params={"mission_id":mission,"hermes_run_id":"actual-run"}, headers={"X-Van-Internal-Token":INTERNAL})
    assert seen.status_code == 200 and seen.json() == accepted.json()


async def test_producer_refuses_wrong_run_and_caller_authority_claims(client):
    ac, app = client
    _, mission = await bound(ac, app)
    headers = {"X-Van-Internal-Token":INTERNAL}
    wrong = await ac.post("/v1/runtime/decisions/escalate", headers=headers, json=proposal(mission, hermes_run_id="made-up"))
    assert wrong.status_code == 409 and wrong.json()["detail"] == "decision_run_binding_mismatch"
    for changes in ({"source":"owner"},{"grants_action_authority":True},{"choices":[{"id":"one","label":"Only"}]}):
        refused = await ac.post("/v1/runtime/decisions/escalate", headers=headers, json=proposal(mission, **changes))
        assert refused.status_code == 422, refused.text
    assert await app.state.store.fetchone("SELECT 1 FROM decisions") is None


async def test_actual_pause_poll_checkpoint_direction_resume_are_distinct_receipts(client):
    ac, app = client
    device, mission = await bound(ac, app)
    owner = _headers(device)
    base = f"/v1/missions/{mission}"
    state = (await ac.get(base + "/control", headers=owner)).json()
    assert state["generation"] == 0 and state["dispatch_allowed"]
    body = {"request_id":"owner-pause-1","expected_generation":0,"reason":"Pause next dispatch"}
    paused = await ac.post(base + "/pause", headers=owner, json=body)
    assert paused.status_code == 200, paused.text
    receipt = paused.json()
    assert receipt["desired_execution"] == "PAUSED" and receipt["reason"] == body["reason"]
    assert (await ac.post(base + "/pause", headers=owner, json=body)).json() == receipt
    assert (await ac.get(base + "/control/requests/owner-pause-1", headers=owner)).json() == receipt
    control = {"mission_id":mission,"hermes_run_id":"actual-run"}
    runtime = {"X-Van-Internal-Token":INTERNAL}
    polled = await ac.post("/v1/runtime/missions/control/poll", headers=runtime, json=control)
    assert polled.status_code == 200, polled.text
    assert not polled.json()["dispatch_allowed"] and polled.json()["latest_worker_report"] is None
    ack = {**control,"control_id":receipt["control_id"],"generation":1,"payload_digest":receipt["payload_digest"],"checkpoint_ref":"checkpoint://actual-safe-boundary"}
    reported = await ac.post("/v1/runtime/missions/control/ack", headers=runtime, json=ack)
    assert reported.status_code == 200, reported.text
    assert reported.json()["status"] == "CHECKPOINT_RECORDED"
    assert not reported.json()["process_stopped_verified"] and not reported.json()["authority_granted"]
    direction = await ac.post(base + "/direction", headers=owner, json={"request_id":"owner-direction-1","expected_generation":1,"message":"Preserve existing effect authority."})
    assert direction.status_code == 200
    assert direction.json()["direction"] == "Preserve existing effect authority."
    polled = (await ac.post("/v1/runtime/missions/control/poll", headers=runtime, json=control)).json()
    pending = polled["pending_directions"][0]
    assert pending["direction"] == "Preserve existing effect authority."
    adopted = await ac.post("/v1/runtime/missions/control/ack", headers=runtime, json={**ack,"control_id":pending["control_id"],"generation":2,"payload_digest":pending["payload_digest"]})
    assert adopted.status_code == 200 and adopted.json()["status"] == "DIRECTION_ADOPTION_RECORDED"
    resumed = await ac.post(base + "/resume", headers=owner, json={"request_id":"owner-resume-1","expected_generation":2})
    assert resumed.status_code == 200 and resumed.json()["desired_execution"] == "RUNNING"
    assert (await ac.get(base + "/control", headers=owner)).json()["dispatch_allowed"]


async def test_owner_controls_refuse_missing_identity_stale_generation_and_wrong_runtime_run(client):
    ac, app = client
    device, mission = await bound(ac, app)
    base = f"/v1/missions/{mission}"
    body = {"request_id":"owner-pause-1","expected_generation":0}
    assert (await ac.post(base + "/pause", json=body)).status_code == 401
    assert (await ac.post(base + "/pause", headers={"X-Van-Internal-Token":INTERNAL}, json=body)).status_code in (401, 403)
    receipt = (await ac.post(base + "/pause", headers=_headers(device), json=body)).json()
    stale = await ac.post(base + "/resume", headers=_headers(device), json={**body,"request_id":"owner-resume-1"})
    assert stale.status_code == 409 and stale.json()["detail"] == "MISSION_CONTROL_GENERATION_CONFLICT"
    wrong = await ac.post("/v1/runtime/missions/control/ack", headers={"X-Van-Internal-Token":INTERNAL}, json={"mission_id":mission,"hermes_run_id":"not-actual","control_id":receipt["control_id"],"generation":1,"payload_digest":receipt["payload_digest"],"checkpoint_ref":"checkpoint://claim"})
    assert wrong.status_code == 409 and wrong.json()["detail"] == "MISSION_CONTROL_RUN_MISMATCH"
    assert (await ac.get(base + "/control", headers=_headers(device))).json()["latest_worker_report"] is None


async def test_strict_generation_and_metadata_schema_never_advertise_pause_verification(client):
    ac, app = client
    device, mission = await bound(ac, app)
    for generation in (True,"0",0.0):
        result = await ac.post(f"/v1/missions/{mission}/pause", headers=_headers(device), json={"request_id":"owner-pause-1","expected_generation":generation})
        assert result.status_code == 422
    schema = app.openapi()
    assert schema["components"]["schemas"]["MissionControlAcknowledgement"]["properties"]["process_stopped_verified"]["const"] is False
    assert schema["components"]["schemas"]["DecisionRecord"]["properties"]["grants_action_authority"]["const"] is False
