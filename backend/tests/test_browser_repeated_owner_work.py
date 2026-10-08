"""Durable parent reconciliation and new signed preparation, without effect replay.

Only the CDP page transport is controlled. Real owner signatures, A4 biometric
challenge, mounted HTTP routes, authoritative task/Mission bindings and stored
verification receipts are exercised; this does not qualify a physical device.
"""
import json
import time

import pytest

from test_browser_owner_command_e2e import client, _settings, browser_config, setup_plan, approve  # noqa: F401
from tests.test_owner_memory_erasure import _command
from van_gateway.browser.action_plans import PlanError


async def verified_plan(ac, app):
    key, plan, page, native, parent = await setup_plan(ac, app)
    body = await approve(ac, app, key, plan)
    response = await ac.post("/v1/commands", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "accepted", result
    assert result["local_execution"]["parent_reconciliation"]["reconciliation_complete"] is True
    assert len(native.calls) == 4
    return plan, native, parent, result


async def prepare_again(ac, app, plan):
    response = await ac.post(f"/v1/browser/interactive-sessions/{plan['session_id']}/take-control")
    assert response.status_code == 200, response.text
    assert response.json()["holder"] == "OWNER"
    parameters = {"session_id": plan["session_id"], "target_domain": "example.org", "goal": "Review a second independently approved task"}
    body = _command(app, text="prepare browser task " + json.dumps(parameters), idem="prepare-second",
                    expires=int(time.time())+20, no_stale=True)
    return await ac.post("/v1/commands", json=body)


@pytest.mark.asyncio
async def test_verified_plan_completes_task_without_claiming_freeform_goal_and_allows_fresh_owner_work(client):
    ac, app, calls = client
    plan, native, parent, result = await verified_plan(ac, app)
    completion = result["local_execution"]["parent_reconciliation"]
    assert completion["approved_effects_verified"] is True
    assert completion["freeform_goal_independently_verified"] is False
    assert completion["parent_state"] == "UNVERIFIABLE"
    task = await app.state.store.fetchone("SELECT * FROM browser_tasks WHERE task_id=?", (plan["task_id"],))
    assert task["status"] == "COMPLETED"
    original_activities = await app.state.store.fetchall("SELECT * FROM mission_activities WHERE mission_id=?", (parent.mission_id,))
    original_event_count = len(await app.state.store.fetchall("SELECT * FROM mission_events WHERE mission_id=?", (parent.mission_id,)))
    assert await app.state.browser_preparation.complete_after_verified_plan(result["command_id"]) == completion
    assert len(await app.state.store.fetchall("SELECT * FROM mission_events WHERE mission_id=?", (parent.mission_id,))) == original_event_count
    response = await prepare_again(ac, app, plan)
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["status"] == "accepted", second
    assert second["local_execution"]["mission_pending"] is True
    assert second["mission_id"] != parent.mission_id
    assert (await app.state.missions.get(second["mission_id"])).state.value == "RUNNING"
    assert (await app.state.interactive_sessions.get(plan["session_id"])).mission_id == second["mission_id"]
    assert await app.state.store.fetchall("SELECT * FROM mission_activities WHERE mission_id=?", (parent.mission_id,)) == original_activities
    catalog = (await ac.get(f"/v1/browser/interactive-sessions/{plan['session_id']}/action-plans")).json()
    assert len(catalog["task_candidates"]) == 1
    assert catalog["task_candidates"][0]["task_id"] != plan["task_id"]
    assert catalog["plan_contract"]["profile_mutation_permitted"] is True
    assert catalog["preparation_contract"]["observed_target_domain"] == "example.org"
    assert catalog["preparation_contract"]["freshness_seconds"] == 30
    assert len(native.calls) == 4 and calls["create_run"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["plan_sha256", "native_predicate", "source_authority"])
async def test_completion_rechecks_exact_independent_receipt_and_owner_source_even_with_existing_marker(client, tamper):
    ac, app, _ = client
    plan, native, parent, result = await verified_plan(ac, app)
    execution = await app.state.store.fetchone("SELECT execution_id FROM action_executions WHERE command_id=?", (result["command_id"],))
    receipt = await app.state.store.fetchone("SELECT * FROM action_receipts WHERE execution_id=? AND status='VERIFIED_SUCCESS'", (execution["execution_id"],))
    if tamper == "source_authority":
        await app.state.store.execute("UPDATE runtime_meta SET value=json_set(value,'$.authority_source','STANDING_AUTOMATION') WHERE key=?", ("command_authority:"+result["command_id"],))
    else:
        observed = json.loads(receipt["observed_postcondition_json"])
        if tamper == "plan_sha256":
            observed["plan_sha256"] = "0"*64
        else:
            observed["independent_readbacks"][0]["postcondition_matched"] = False
        await app.state.store.execute("UPDATE action_receipts SET observed_postcondition_json=? WHERE receipt_id=?", (json.dumps(observed), receipt["receipt_id"]))
    with pytest.raises((PlanError, ValueError)):
        await app.state.browser_preparation.complete_after_verified_plan(result["command_id"])
    assert len(native.calls) == 4
    assert (await app.state.missions.get(parent.mission_id)).state.value == "UNVERIFIABLE"


@pytest.mark.asyncio
async def test_new_signed_prepare_recovers_interrupted_metadata_completion_without_reactuation(client):
    ac, app, _ = client
    plan, native, parent, result = await verified_plan(ac, app)
    # Model the crash after the durable task/verified-plan marker but before the
    # final parent transition. All canonical effect receipts remain unchanged.
    await app.state.store.execute("UPDATE missions SET state='RUNNING' WHERE mission_id=?", (parent.mission_id,))
    response = await prepare_again(ac, app, plan)
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["status"] == "accepted", second
    assert second["mission_id"] != parent.mission_id
    assert (await app.state.missions.get(parent.mission_id)).state.value == "UNVERIFIABLE"
    assert (await app.state.missions.get(second["mission_id"])).state.value == "RUNNING"
    assert len(native.calls) == 4


@pytest.mark.asyncio
async def test_plan_command_mission_pause_during_native_focus_fences_remaining_input(client):
    ac, app, _ = client
    key, plan, page, native, parent = await setup_plan(ac, app)
    body = await approve(ac, app, key, plan)
    async def pause(method):
        if method != "DOM.focus":
            return
        row = await app.state.store.fetchone("SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?", (body["command_id"],))
        assert row is not None and row["mission_id"] != parent.mission_id
        response = await ac.post(f"/v1/missions/{row['mission_id']}/pause", json={"request_id":"pause-plan-during-focus","expected_generation":0})
        assert response.status_code == 200, response.text
    page.hook = pause
    response = await ac.post("/v1/commands", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "degraded", result
    assert page.value == "before" and len(native.calls) == 1
    assert not any(method == "Input.insertText" for method,_ in page.calls)
    assert (await ac.post("/v1/commands", json=body)).json() == result
    assert len(native.calls) == 1
