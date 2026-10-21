"""Actual paired-owner HTTP ingress for immutable proposals and read-only recovery."""
import json

import pytest

from tests.test_device_proof_enforcement import (_settings, client, _paired, _bind, _proof_headers, _base_headers, INGRESS, INTERNAL)
from van_gateway.automation.canonical import digest
from van_gateway.config import get_settings
from van_gateway.automation.models import WorkflowIR
from van_gateway.automation.owner_api import OwnerPlanBody


@pytest.fixture(autouse=True)
def automation_enabled(_settings, monkeypatch):
    monkeypatch.setenv("VAN_AUTOMATION_ENABLED", "1")
    get_settings.cache_clear()


def plan_body(key="owner-plan-request-1"):
    return {"idempotency_key": key, "semantic_name": "Owner bounded hash", "workflow_ir": {
        "ir_id": "owner-ir-1", "family": "bounded-hash", "semantic_goal": "Hash the sealed owner data", "version": 1,
        "trigger": {"kind": "INVOKE"}, "steps": [{"step_id": "hash", "primitive": "HASH", "operation": "hash",
            "input_bindings": {"payload": {"sealed": True}}, "effects": ["READ"], "action_class": "A1", "timeout_ms": 1000,
            "retry_class": "NEVER_RETRY", "max_attempts": 1}], "action_class": "A1", "verifier": {"kind": "READ_BACK"},
        "policy_version": "owner-proposal", "compiler_version": "owner-proposal"}}


async def signed_post(ac, app, enrolled, private, body):
    raw = json.dumps(body, separators=(",", ":")).encode()
    path = "/v1/owner/automation/plans"
    headers = {**_base_headers(enrolled), "Content-Type": "application/json", **_proof_headers(private,
        method="POST", path=path, device_id=enrolled.device.device_id, body=raw)}
    return await ac.post(path, headers=headers, content=raw)


async def test_actual_owner_proof_gate_catalog_proposal_immutable_read_and_fresh_signature_idempotency(client):
    ac, app = client
    enrolled = await _paired(app)
    private = await _bind(app, enrolled.device.device_id)
    catalog = await ac.get("/v1/owner/automation/contracts", headers=_base_headers(enrolled))
    assert catalog.status_code == 200 and catalog.headers["cache-control"] == "no-store"
    assert catalog.json()["candidate_grants_execution"] is False
    assert "write_json" in catalog.json()["operations"]["HTTP_REQUEST"]
    denied = await ac.post("/v1/owner/automation/plans", json=plan_body(), headers=_base_headers(enrolled))
    assert denied.status_code == 401 and denied.json()["detail"] == "device_proof_required"
    proposed = await signed_post(ac, app, enrolled, private, plan_body())
    assert proposed.status_code == 201, proposed.text
    result = proposed.json()
    assert result["lifecycle_state"] == "PROPOSED" and result["candidate_only"] is True and result["owner_success"] is False
    assert result["deployable"] is False and result["runtime_readiness_errors"]
    repeated = await signed_post(ac, app, enrolled, private, plan_body())
    assert repeated.status_code == 201 and repeated.json()["artifact_id"] == result["artifact_id"] and repeated.json()["replayed"] is True
    read = await ac.get("/v1/owner/automation/plans/" + result["artifact_id"], headers=_base_headers(enrolled))
    assert read.status_code == 200 and read.json()["workflow_ir"]["steps"][0]["input_bindings"]["payload"] == {"sealed": True}
    assert read.json()["workflow_ir_digest"] == digest(WorkflowIR.model_validate(plan_body()["workflow_ir"]).semantic_payload())
    recovery = await ac.get("/v1/owner/automation/requests/owner-plan-request-1", headers=_base_headers(enrolled))
    assert recovery.json()["state"] == "COMPLETED" and recovery.json()["result"]["artifact_id"] == result["artifact_id"]
    assert recovery.json()["recovery_read_only"] is True and recovery.json()["replay_permitted"] is False
    assert (await app.state.store.fetchone("SELECT count(*) AS n FROM automation_runs"))["n"] == 0
    assert (await app.state.store.fetchone("SELECT count(*) AS n FROM automation_artifacts"))["n"] == 1


async def test_owner_proposal_conflict_pending_and_cross_device_read_recovery_are_exact(client):
    ac, app = client
    enrolled = await _paired(app)
    private = await _bind(app, enrolled.device.device_id)
    first = await signed_post(ac, app, enrolled, private, plan_body())
    assert first.status_code == 201
    altered = plan_body()
    altered["semantic_name"] = "Changed"
    conflict = await signed_post(ac, app, enrolled, private, altered)
    assert conflict.status_code == 409 and conflict.json()["detail"] == "AUTOMATION_PLAN_IDEMPOTENCY_CONFLICT"
    pending_body = plan_body("owner-pending-request")
    await app.state.store.execute("INSERT INTO automation_owner_plans VALUES(?,?,?,'IN_PROGRESS',NULL,1,NULL)",
                                  (enrolled.device.device_id, pending_body["idempotency_key"], digest(OwnerPlanBody.model_validate(pending_body).model_dump(mode="json"))))
    pending = await signed_post(ac, app, enrolled, private, pending_body)
    assert pending.status_code == 409 and pending.json()["detail"] == "AUTOMATION_PLAN_OUTCOME_PENDING"
    recovery = await ac.get("/v1/owner/automation/requests/owner-pending-request", headers=_base_headers(enrolled))
    assert recovery.json()["state"] == "IN_PROGRESS" and recovery.json()["result"] is None
    other = await _paired(app, "second-device")
    assert (await ac.get("/v1/owner/automation/requests/owner-plan-request-1", headers=_base_headers(other))).status_code == 404
    missing_owner = await ac.get("/v1/owner/automation/contracts", headers={"X-Van-Ingress-Token": INGRESS, "X-Van-Internal-Token": INTERNAL})
    assert missing_owner.status_code in {401, 403}


async def test_bad_typed_graph_is_refused_without_artifact_or_execution_and_recorded_as_refused(client):
    ac, app = client
    enrolled = await _paired(app)
    private = await _bind(app, enrolled.device.device_id)
    body = plan_body()
    body["workflow_ir"]["steps"][0]["precondition"] = {"op": [], "args": []}
    result = await signed_post(ac, app, enrolled, private, body)
    assert result.status_code == 422
    recovery = await ac.get("/v1/owner/automation/requests/owner-plan-request-1", headers=_base_headers(enrolled))
    assert recovery.json()["state"] == "REFUSED"
    assert (await app.state.store.fetchone("SELECT count(*) AS n FROM automation_artifacts"))["n"] == 0


async def test_owner_cannot_revision_an_unowned_capability_or_weaken_effect_floor(client):
    ac, app = client
    enrolled = await _paired(app)
    private = await _bind(app, enrolled.device.device_id)
    body = plan_body()
    body["capability_id"] = "unowned-capability"
    result = await signed_post(ac, app, enrolled, private, body)
    assert result.status_code == 403 and result.json()["detail"] == "AUTOMATION_PLAN_REVISION_NOT_OWNED"
    body = plan_body("owner-write-underdeclared")
    body["workflow_ir"]["steps"][0].update({"primitive":"VAN_CAPABILITY","operation":"reminder.create"})
    result = await signed_post(ac, app, enrolled, private, body)
    assert result.status_code == 422 and "ACTION_CLASS_UNDERDECLARED" in result.text
