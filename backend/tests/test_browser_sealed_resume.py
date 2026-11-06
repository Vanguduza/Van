"""Real owner HTTP approval -> same-task continuation; browser transport is a fixture."""
import asyncio
import base64
import json
import inspect
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from tests.test_local_typed_actions import client, _settings  # noqa: F401
from tests.test_owner_memory_erasure import _command, _pair
from test_browser_api import _ScriptedWorker, _Verdict
from van_gateway.browser.models import AutonomyTier, BrowserStrategy, BrowserTaskStatus
from van_gateway.browser.subagent import ProposedAction
from van_gateway.models import ActionClass
from van_gateway.auth.service import AuthService

DOMAIN = "docs.example.com"
NEXT = "reports.example.com"
INTERNAL = {"X-Van-Internal-Token": "local-actions-internal-token"}


@pytest.fixture(autouse=True)
def enabled(_settings, monkeypatch):
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "true")
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")


def configure_transport(browser, actions):
    browser.worker = _ScriptedWorker(actions)
    browser.verifier = _Verdict()

    async def release(**kwargs):
        return {"released": True}
    browser.broker.page_release_hook = release
    return browser.worker


async def waiting(ac, app):
    key = await _pair(ac, app)
    source = _command(app, text="Read the report from the browser", idem="resume-source")
    source["action_class"] = "A3"
    canonical = AuthService.canonical_command_v2(**{name: source.get(name)
        for name in inspect.signature(AuthService.canonical_command_v2).parameters})
    source["signature"] = app.state.auth.sign(source["device_id"], canonical)
    result = (await ac.post("/v1/commands", json=source)).json()
    assert result["status"] == "accepted", result
    task = await app.state.browser.tasks.create_task(profile_alias="public_research",
        strategy=BrowserStrategy.HARNESS, autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC,
        action_class=ActionClass.A2, target_domain=DOMAIN, goal="Read the exact report",
        mutating=False, command_id=source["command_id"])
    # Bind the prepared metadata through its actual local declaration. No native
    # provider readiness is invented; the worker transport below is a fixture.
    await app.state.browser.binder.bind_browser_task(mission_id=result["mission_id"], task_id=task.task_id,
        capability_id="browser.task.prepare")
    worker = configure_transport(app.state.browser, [ProposedAction(kind="extract", domain=NEXT, action_class=ActionClass.A1)])
    assignment = {"task_id": task.task_id, "command_id": source["command_id"], "turn_id": "resume-turn",
        "goal": task.goal, "allowed_domains": [DOMAIN], "action_class_ceiling": "A1",
        "autonomy_tier": "L1_HARNESS_DETERMINISTIC"}
    stopped = await ac.post("/v1/browser/assignments", headers=INTERNAL, json=assignment)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["stop_reason"] == "SCOPE_VIOLATION", stopped.json()
    assert worker.executed == 0
    contract = await ac.get(f"/v1/browser/tasks/{task.task_id}/resume-contract")
    assert contract.status_code == 200, contract.text
    assert contract.json()["grants_authority"] is False
    return key, task, assignment, contract.json()


async def approval_body(ac, app, key, contract, idem="resume-approved"):
    challenge = (await ac.post("/v1/commands", json=_command(app,
        text=contract["approval_command"], idem=idem+"-challenge"))).json()
    assert challenge["status"] == "approval_required", challenge
    assert challenge["resolved_action_id"] == "browser.task.resume"
    proof = {"challenge_id": challenge["approval_challenge_id"], "signature_b64": base64.b64encode(
        key.sign(challenge["approval_challenge"].encode(), ec.ECDSA(hashes.SHA256()))).decode()}
    return _command(app, text=contract["approval_command"], idem=idem, proof=proof,
                    expires=int(time.time())+25, no_stale=True)


async def approve(ac, app, key, contract):
    body = await approval_body(ac, app, key, contract)
    response = await ac.post("/v1/commands", json=body)
    result = response.json()
    assert result["status"] == "accepted", result
    assert result["local_execution"]["verification_state"] == "VERIFIED_SUCCESS", result
    assert (await app.state.missions.get(result["mission_id"])).state.value == "VERIFIED_SUCCESS"
    return body, result


async def test_signed_owner_command_survives_restart_and_continues_same_task_once(client):
    from van_gateway.app import create_app
    ac, app, _ = client
    key, task, assignment, contract = await waiting(ac, app)
    body, result = await approve(ac, app, key, contract)
    assert (await ac.post("/v1/commands", json=body)).json() == result
    assert (await app.state.store.fetchone("SELECT COUNT(*) n FROM browser_scope_authorizations"))["n"] == 1
    restarted = create_app()
    worker = configure_transport(restarted.state.browser,
        [ProposedAction(kind="extract", domain=NEXT, action_class=ActionClass.A1)])
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(transport=ASGITransport(app=restarted), base_url="http://test", headers=dict(ac.headers)) as resumed:
            response = await resumed.post("/v1/browser/assignments", headers=INTERNAL,
                json={**assignment, "allowed_domains": [DOMAIN, NEXT]})
            assert response.status_code == 200, response.text
            assert response.json()["task_id"] == task.task_id
            assert worker.executed == 1, response.json()
            again = await resumed.post("/v1/browser/assignments", headers=INTERNAL,
                json={**assignment, "allowed_domains": [DOMAIN, NEXT]})
            assert again.status_code == 409
    row = await app.state.store.fetchone("SELECT status,consumed_at_ms FROM browser_scope_authorizations WHERE task_id=?", (task.task_id,))
    assert row["status"] == "CONSUMED" and row["consumed_at_ms"] is not None
    assert (await app.state.store.fetchone("SELECT COUNT(*) n FROM browser_tasks"))["n"] == 1


async def test_advisory_yes_does_not_create_authority_or_resume(client):
    ac, app, _ = client
    _, task, assignment, contract = await waiting(ac, app)
    await app.state.store.execute("UPDATE decisions SET status='APPROVED' WHERE id=?", (contract["scope"]["decision_id"],))
    response = await ac.post("/v1/browser/assignments", headers=INTERNAL, json=assignment)
    assert response.status_code == 409
    assert not await app.state.store.fetchone("SELECT 1 FROM browser_scope_authorizations")
    assert (await app.state.browser._load_task(task.task_id)).status is BrowserTaskStatus.WAITING_FOR_OWNER


async def test_stale_advisory_sync_cannot_undo_a_new_sealed_resume(client):
    ac, app, _ = client
    key, task, _, contract = await waiting(ac, app)
    stale = await app.state.browser._load_task(task.task_id)
    await app.state.store.execute("UPDATE decisions SET status='APPROVED' WHERE id=?", (contract["scope"]["decision_id"],))
    await approve(ac, app, key, contract)
    assert await app.state.browser._sync_waiting_owner_decision(stale) is BrowserTaskStatus.RESUME_AUTHORIZED
    assert (await app.state.browser._load_task(task.task_id)).status is BrowserTaskStatus.RESUME_AUTHORIZED


@pytest.mark.parametrize("alteration", ["scope", "expired", "device_revoked", "witness", "source_seal", "class", "domains"])
async def test_changed_or_expired_authority_cannot_be_spent(client, alteration):
    ac, app, _ = client
    key, task, assignment, contract = await waiting(ac, app)
    await approve(ac, app, key, contract)
    store = app.state.store
    domains, ceiling = [DOMAIN, NEXT], ActionClass.A1
    if alteration == "scope":
        await store.execute("UPDATE browser_escalations SET requested_scope_delta_json=? WHERE task_id=?", (json.dumps({"allowed_domain": "changed.example.com"}), task.task_id))
    elif alteration == "expired":
        await store.execute("UPDATE browser_scope_authorizations SET expires_at_ms=1 WHERE task_id=?", (task.task_id,))
    elif alteration == "device_revoked":
        await store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='dev-erasure'")
    elif alteration == "witness":
        await store.execute("DELETE FROM runtime_meta WHERE key LIKE 'browser_resume_witness:%'")
    elif alteration == "source_seal":
        await store.execute("UPDATE runtime_meta SET value=json_set(value,'$.owner_approved',json('false')) WHERE key LIKE 'command_authority:%' AND json_extract(value,'$.typed_action_id')='browser.task.resume'")
    elif alteration == "class":
        ceiling = ActionClass.A3
    elif alteration == "domains":
        domains.append("outside.example.com")
    with pytest.raises(HTTPException) as refused:
        await app.state.browser.consume_resume_authorization(await app.state.browser._load_task(task.task_id),
            requested_domains=domains, requested_class=ceiling)
    assert refused.value.status_code == 409
    assert (await store.fetchone("SELECT status FROM browser_scope_authorizations WHERE task_id=?", (task.task_id,)))["status"] == "ACTIVE"


async def test_concurrent_consumers_spend_one_durable_grant(client):
    ac, app, _ = client
    key, task, _, contract = await waiting(ac, app)
    await approve(ac, app, key, contract)
    async def consume():
        loaded = await app.state.browser._load_task(task.task_id)
        return await app.state.browser.consume_resume_authorization(loaded, requested_domains=[DOMAIN, NEXT], requested_class=ActionClass.A1)
    outcomes = await asyncio.gather(consume(), consume(), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in outcomes) == 1, outcomes
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in outcomes) == 1, outcomes


async def test_failed_transition_rolls_back_grant_and_witness(client, monkeypatch):
    ac, app, _ = client
    key, task, _, contract = await waiting(ac, app)
    body = await approval_body(ac, app, key, contract)
    async def fail(**kwargs):
        raise ValueError("induced task transition failure")
    monkeypatch.setattr(app.state.browser.tasks, "set_working_status", fail)
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "degraded", result
    assert not await app.state.store.fetchone("SELECT 1 FROM browser_scope_authorizations")
    assert not await app.state.store.fetchone("SELECT 1 FROM runtime_meta WHERE key LIKE 'browser_resume_witness:%'")
    assert (await app.state.browser._load_task(task.task_id)).status is BrowserTaskStatus.WAITING_FOR_OWNER


async def test_actual_expiry_refuses_without_modifying_the_grant(client, monkeypatch):
    ac, app, _ = client
    key, task, _, contract = await waiting(ac, app)
    await approve(ac, app, key, contract)
    current = time.time()
    monkeypatch.setattr(time, "time", lambda: current+31)
    with pytest.raises(HTTPException) as refused:
        await app.state.browser.consume_resume_authorization(await app.state.browser._load_task(task.task_id))
    assert refused.value.status_code == 409


async def test_new_approval_cannot_override_paused_parent(client):
    ac, app, _ = client
    key, task, _, contract = await waiting(ac, app)
    body = await approval_body(ac, app, key, contract)
    mission = await app.state.store.fetchone("SELECT mission_id FROM mission_activities WHERE executor_ref=?", (task.task_id,))
    paused = await ac.post(f"/v1/missions/{mission['mission_id']}/pause",
        json={"request_id": "pause-original-task", "expected_generation": 0})
    assert paused.status_code == 200, paused.text
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "degraded", result
    assert not await app.state.store.fetchone("SELECT 1 FROM browser_scope_authorizations")


async def test_declared_local_readiness_tracks_configuration_and_keeps_owner_gate(client, monkeypatch):
    from van_gateway.capability.models import RoutingConstraints
    ac, app, _ = client
    registry = app.state.capability_registry
    denied = await registry.routability("browser.task.resume", constraints=RoutingConstraints(
        max_action_class=ActionClass.A3, owner_present=True))
    assert not denied.routable
    constraints = RoutingConstraints(max_action_class=ActionClass.A4, owner_present=True)
    assert (await registry.routability("browser.task.resume", constraints=constraints)).routable
    monkeypatch.setattr(app.state.browser.settings, "browser_enabled", False)
    disabled = await registry.routability("browser.task.resume", constraints=constraints)
    assert not disabled.routable and disabled.detail == "BROWSER_RESUME_DISABLED"
