"""The owner disables standing work through real signed command ingress and readback."""

from __future__ import annotations

import json

import pytest

from tests.conftest_automation import seed_snapshot, seed_standing_intent, seal_owner_command
from tests.test_local_typed_actions import client, _settings, _pair_for_test, _v1_command  # noqa: F401
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.command.standing import StandingAutomationAuthorityService
from van_gateway.command.success_contracts import contract_for
from van_gateway.models import ActionClass
from van_gateway.verification.observations import standing_intent_disable_readback

pytestmark = pytest.mark.asyncio


async def _standing(app, device_id="dev-standing", intent_id="intent-Case_1"):
    store = app.state.store
    await seed_standing_intent(store, intent_id=intent_id)
    command_id, snapshot_id = f"source-{intent_id}", f"snapshot-{intent_id}"
    await seed_snapshot(store, snapshot_id, command_id)
    authority = CommandAuthorityService(store)
    await seal_owner_command(authority, command_id=command_id, snapshot_id=snapshot_id,
                             device_id=device_id, effective=ActionClass.A3)
    return await StandingAutomationAuthorityService(store, authority).seal(
        standing_intent_id=intent_id, source_command_id=command_id,
        capability_id="wfcap_statements", artifact_id="artifact-statements", workflow_version=1,
        action_class_ceiling=ActionClass.A2, trigger={}, parameter_constraints={},
        allowed_effects=["READ"], allowed_domains=[], owner_authority_evidence_ref="test://owner-standing",
        policy_version="test-policy",
    )


async def test_signed_disable_exact_intent_revokes_roots_and_verifies_mission(client):
    ac, app, hermes_calls = client
    await _pair_for_test(ac, app, "dev-standing", "standing-secret")
    root = await _standing(app)
    other = await _standing(app, intent_id="other-intent")
    before = await ac.get("/v1/owner/automation")
    assert before.status_code == 200, before.text
    target = next(i for i in before.json()["standing_intents"] if i["intent_id"] == "intent-Case_1")
    assert target["disable_control"]["available"] is True
    body = _v1_command(app, device_id="dev-standing", text="disable standing intent intent-Case_1",
                       idempotency_key="standing-disable-1", command_id="disable-command-1", action_class="A3")
    response = await ac.post("/v1/commands", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "accepted", result
    assert result["resolved_action_id"] == "automation.standing_intent.disable"
    assert result["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert hermes_calls["create_run"] == 0
    intent = await app.state.store.fetchone("SELECT enabled FROM automation_standing_intents WHERE intent_id='intent-Case_1'")
    assert intent["enabled"] == 0
    roots = await app.state.store.fetchall("SELECT authority_id,revoked_at_ms FROM standing_automation_authorities")
    times = {r["authority_id"]: r["revoked_at_ms"] for r in roots}
    assert times[root.authority_id] is not None and times[other.authority_id] is None
    mission = await app.state.store.fetchone("SELECT state,verification_record_json FROM missions WHERE mission_id=?", (result["mission_id"],))
    assert mission["state"] == "VERIFIED_SUCCESS"
    record = json.loads(mission["verification_record_json"])
    assert record["status"] == "VERIFIED" and record["evidence_refs"]
    assert record["observed_postconditions"]["intent_id"] == "intent-Case_1"
    assert record["observed_postconditions"]["captured_authorities_revoked"] is True
    replay = await ac.post("/v1/commands", json=body)
    assert replay.json() == result
    after = (await ac.get("/v1/owner/automation")).json()
    target = next(i for i in after["standing_intents"] if i["intent_id"] == "intent-Case_1")
    assert target["enabled"] is False and target["active_authorities"] == 0
    assert target["executable_authority_present"] is False


async def test_different_device_cannot_disable_another_devices_standing_root(client):
    ac, app, _ = client
    await _pair_for_test(ac, app, "dev-standing", "standing-secret")
    root = await _standing(app)
    await _pair_for_test(ac, app, "dev-other", "other-secret")
    response = await ac.post("/v1/commands", json=_v1_command(
        app, device_id="dev-other", text="disable standing intent intent-Case_1",
        idempotency_key="not-owner-root", action_class="A3",
    ))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "denied"
    row = await app.state.store.fetchone("SELECT enabled FROM automation_standing_intents WHERE intent_id='intent-Case_1'")
    assert row["enabled"] == 1
    row = await app.state.store.fetchone("SELECT revoked_at_ms FROM standing_automation_authorities WHERE authority_id=?", (root.authority_id,))
    assert row["revoked_at_ms"] is None


async def test_invalid_signature_cannot_disable_and_unknown_intent_is_named_refusal(client):
    ac, app, _ = client
    await _pair_for_test(ac, app, "dev-standing", "standing-secret")
    root = await _standing(app)
    body = _v1_command(app, device_id="dev-standing", text="disable standing intent intent-Case_1",
                       idempotency_key="bad-signature", action_class="A3")
    body["signature"] = "wrong"
    response = await ac.post("/v1/commands", json=body)
    assert response.status_code in {401, 403} or response.json()["status"] == "denied"
    assert (await app.state.store.fetchone("SELECT revoked_at_ms FROM standing_automation_authorities WHERE authority_id=?", (root.authority_id,)))["revoked_at_ms"] is None
    response = await ac.post("/v1/commands", json=_v1_command(
        app, device_id="dev-standing", text="disable standing intent unknown-intent",
        idempotency_key="unknown-standing", action_class="A3",
    ))
    assert response.json()["status"] == "denied"
    execution = await app.state.store.fetchone("SELECT error_code FROM action_executions WHERE execution_id=?", (response.json()["execution_id"],))
    assert execution["error_code"] == "standing_intent_not_found"


async def test_readback_requires_same_intent_witness_and_fresh_actual_disabled_state(client):
    ac, app, _ = client
    await _pair_for_test(ac, app, "dev-standing", "standing-secret")
    root = await _standing(app)
    await ac.post("/v1/commands", json=_v1_command(
        app, device_id="dev-standing", text="disable standing intent intent-Case_1",
        idempotency_key="disable-readback", command_id="disable-readback-command", action_class="A3",
    ))
    observed = await standing_intent_disable_readback(app.state.store, "intent-Case_1", "disable-readback-command")
    assert observed["captured_authorities_revoked"] is True
    await app.state.store.execute("UPDATE standing_automation_authorities SET revoked_at_ms=NULL WHERE authority_id=?", (root.authority_id,))
    observed = await standing_intent_disable_readback(app.state.store, "intent-Case_1", "disable-readback-command")
    assert observed["active_authorities"] == 1 and observed["captured_authorities_revoked"] is False
    assert "evidence_refs" not in observed
    missing = await standing_intent_disable_readback(app.state.store, "intent-Case_1", "fabricated-command")
    assert missing["owner_command_bound"] is False and "evidence_refs" not in missing


async def test_exact_resolver_preserves_identifier_and_contract_names_effect():
    resolver = TypedCommandResolver()
    resolution = resolver.resolve("Disable standing intent intent-Case_1")
    assert resolution.parameters == {"intent_id": "intent-Case_1"}
    assert resolution.canonical_action_class is ActionClass.A3
    contract = contract_for(resolution)
    assert contract.postconditions == {"intent_id": "intent-Case_1", "enabled": False,
        "active_authorities": 0, "captured_authorities_revoked": True, "owner_command_bound": True}
    for text in ("disable standing intent ../other", "disable standing intent id and send payment", "please disable standing intent id"):
        assert resolver.resolve(text).mode is ResolutionMode.HERMES_INTERPRETATION_REQUIRED


async def test_untrusted_content_cannot_disable_standing_work(client):
    ac, app, _ = client
    await _pair_for_test(ac, app, "dev-standing", "standing-secret")
    root = await _standing(app)
    body = _v1_command(app, device_id="dev-standing", text="disable standing intent intent-Case_1",
                       idempotency_key="untrusted-standing", action_class="A3")
    body["context_trust"] = "UNTRUSTED"
    result = await ac.post("/v1/commands", json=body)
    assert result.json()["status"] == "rejected_untrusted"
    assert (await app.state.store.fetchone("SELECT revoked_at_ms FROM standing_automation_authorities WHERE authority_id=?", (root.authority_id,)))["revoked_at_ms"] is None


async def test_owner_projections_are_mounted_without_runtime_credentials_or_provider_calls(client, monkeypatch):
    ac, app, _ = client
    await _pair_for_test(ac, app, "dev-standing", "standing-secret")

    async def remote_call_forbidden(*args, **kwargs):
        pytest.fail("owner local-state GET attempted a provider operation")

    runtime = app.state.owner_runtime
    monkeypatch.setattr(runtime.research, "search", remote_call_forbidden)
    monkeypatch.setattr(runtime.knowledge, "query_vekl", remote_call_forbidden)
    monkeypatch.setattr(runtime.knowledge, "query_obsidian", remote_call_forbidden)
    monkeypatch.setattr(runtime.knowledge.notebook_enterprise, "_request", remote_call_forbidden)
    monkeypatch.setattr(app.state.automation_health.n8n, "_request", remote_call_forbidden)
    for path in ("knowledge", "research", "automation", "diagnostics"):
        response = await ac.get("/v1/owner/" + path)
        assert response.status_code == 200, response.text
        assert response.json()["schema_version"] == 1
        assert response.headers["cache-control"] == "no-store"
    saved = ac.headers.pop("X-Van-Device-Token")
    try:
        response = await ac.get("/v1/owner/diagnostics", headers={"X-Van-Internal-Token": "local-actions-internal-token"})
        assert response.status_code == 401
    finally:
        ac.headers["X-Van-Device-Token"] = saved


async def test_historical_roots_allow_stop_cleanup_but_not_execution_and_unsupported_ids_are_disabled(client):
    ac, app, _ = client
    await _pair_for_test(ac, app, "dev-standing", "standing-secret")
    root = await _standing(app)
    await _standing(app, intent_id="legacy/unsupported")
    await app.state.store.execute("UPDATE standing_automation_authorities SET revoked_at_ms=1 WHERE authority_id=?", (root.authority_id,))
    response = (await ac.get("/v1/owner/automation")).json()
    target = next(i for i in response["standing_intents"] if i["intent_id"] == "intent-Case_1")
    assert target["current_device_authority_roots"] == 1
    assert target["current_device_authorities"] == 0 and target["active_authorities"] == 0
    assert target["executable_authority_present"] is False and target["disable_control"]["available"] is True
    legacy = next(i for i in response["standing_intents"] if i["intent_id"] == "legacy/unsupported")
    assert legacy["disable_control"]["available"] is False
    assert legacy["disable_control"]["unavailable_reason"] == "UNSUPPORTED_INTENT_IDENTIFIER"
