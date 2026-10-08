"""Actual sealed worker effects, branch decisions and independent target reads."""
import json
import time
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from tests.test_automation_worker_runtime import admitted, build, step
from van_gateway.automation.canonical import digest
from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.grants import GrantDenied
from van_gateway.automation.models import Primitive, WorkflowIREdge
from van_gateway.automation.primitive_policy import PrimitiveSemanticError, assert_primitive_semantics
from van_gateway.automation.source_credentials import SourceCredentialStore
from van_gateway.automation.worker_runtime import GatewayDocumentFetcher, WorkerDenied, WorkerWorkflowObserver
from van_gateway.models import ActionClass
from conftest_automation import policy_with_domains


def predicate(path="payload.ready", expected=True):
    return {"op": "EQ", "left": {"kind": "PATH", "path": path}, "right": {"kind": "LITERAL", "value": expected}}


async def test_pause_committed_before_step_writer_admission_refuses_actual_effect_and_spends_no_new_authority(tmp_path):
    native = step("remind", Primitive.VAN_CAPABILITY, "reminder.create", {"text": "Review", "due_at_unix": int(time.time()) + 60}, action_class=ActionClass.A3)
    native.postcondition = {"kind": "READ_BACK", "field": "verified", "expected": True}
    worker, store, factory = await build(tmp_path, steps=[native], inputs={})
    await admitted(worker, factory)
    run = await store.fetchone("SELECT command_id FROM automation_runs WHERE run_id='run'")
    await store.execute("INSERT INTO missions(mission_id,owner_principal_id,origin,origin_channel,title,goal,state,authority_envelope_json,created_at_ms,updated_at_ms) VALUES('mission','device:dev-owner-1','OWNER_UI','UI','Review','Review','RUNNING',?,1,1)",
                        (json.dumps({"source_command_id":run["command_id"]}),))
    body = await server_body(factory, "remind")
    redeemed, release = asyncio.Event(), asyncio.Event()
    original = worker.grants.redeem
    async def redeem_then_wait(**kwargs):
        await original(**kwargs)
        redeemed.set()
        await release.wait()
    worker.grants.redeem = redeem_then_wait
    pending = asyncio.create_task(worker.execute(body))
    await asyncio.wait_for(redeemed.wait(), 2)
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("INSERT INTO mission_execution_controls(mission_id,generation,desired_execution,updated_at_ms) VALUES('mission',1,'PAUSED',1)")
        release.set()
        done, _ = await asyncio.wait({pending}, timeout=0.02)
        assert not done
        await db.commit()
    with pytest.raises(WorkerDenied, match="MISSION_DISPATCH_PAUSED"):
        await pending
    assert (await store.fetchone("SELECT count(*) AS n FROM reminders"))["n"] == 0
    assert await store.fetchone("SELECT state FROM automation_worker_steps WHERE step_id='remind'") is None
    worker.grants.redeem = original
    await store.execute("UPDATE mission_execution_controls SET desired_execution='RUNNING',generation=2 WHERE mission_id='mission'")
    with pytest.raises(GrantDenied, match="GRANT_REPLAYED"):
        await worker.execute(body)
    # Resume needs a fresh admission, never resurrection of the spent grant.
    assert (await worker.execute(await server_body(factory, "remind")))["result"]["verified"] is True


async def server_body(factory, name):
    return (await factory(name)).model_copy(update={"resolve_bindings": True})


@pytest.mark.parametrize("ready", [True, False])
async def test_delivery_baseline_advances_after_actual_selected_sink_and_verified_final_skip(tmp_path, ready):
    change = step("change", Primitive.DEDUPE, "change_detect", {"payload":"$input.document"})
    choose = step("choose", Primitive.FILTER, "evaluate_predicate", {"payload":"$steps.change.payload", "predicate":predicate()})
    yes = step("yes", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload":{"selected":"yes"}}, action_class=ActionClass.A3)
    no = step("no", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload":{"selected":"no"}}, action_class=ActionClass.A3)
    edges = [WorkflowIREdge(from_step="change",to_step="choose"),
             WorkflowIREdge(from_step="choose",to_step="yes",branch="true"), WorkflowIREdge(from_step="choose",to_step="no",branch="false")]
    worker, store, factory = await build(tmp_path, steps=[change, choose, yes, no], inputs={"document":{"ready":ready}}, edges=edges,
        declared_verifier={"kind":"READ_BACK","field":"evidence_pointer"})
    await admitted(worker, factory)
    await worker.execute(await server_body(factory,"change"))
    await worker.execute(await server_body(factory,"choose"))
    selected, skipped = ("yes","no") if ready else ("no","yes")
    await worker.execute(await server_body(factory,selected))
    assert await store.fetchone("SELECT * FROM automation_worker_dedupe") is None
    skipped_body = await server_body(factory,skipped)
    receipt = await worker.execute(skipped_body)
    assert receipt["status"] == "SKIPPED"
    baseline = await store.fetchone("SELECT generation,content_digest FROM automation_worker_dedupe WHERE step_id='change'")
    assert baseline["generation"] == 1 and baseline["content_digest"] == digest({"ready":ready})
    assert (await store.fetchone("SELECT count(*) AS n FROM automation_worker_evidence"))["n"] == 1
    assert (await WorkerWorkflowObserver(worker).observe(None,{"run_id":"run","inputs":{"document":{"ready":ready}}}))["exists"] is True
    await worker.execute(skipped_body)
    assert (await store.fetchone("SELECT generation FROM automation_worker_dedupe"))["generation"] == 1


@pytest.mark.parametrize("ready", [True, False])
async def test_real_selected_branch_effects_and_optional_join_have_durable_independent_evidence(tmp_path, ready):
    select = step("choose", Primitive.FILTER, "evaluate_predicate", {"payload": "$input.document", "predicate": predicate()})
    branches = [step("yes", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload": {"selected": "yes"}}, action_class=ActionClass.A3),
                step("no", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload": {"selected": "no"}}, action_class=ActionClass.A3)]
    join = step("join", Primitive.MERGE, "merge_objects", {"sources": [
        {"kind": "STEP_RESULT", "step_id": name, "path": "", "optional": True} for name in ("yes", "no")]})
    seal = step("seal", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload": "$steps.join.payload"}, action_class=ActionClass.A3)
    edges = [WorkflowIREdge(from_step="choose", to_step="yes", branch="true"), WorkflowIREdge(from_step="choose", to_step="no", branch="false"),
             WorkflowIREdge(from_step="yes", to_step="join"), WorkflowIREdge(from_step="no", to_step="join"), WorkflowIREdge(from_step="join", to_step="seal")]
    worker, store, factory = await build(tmp_path, steps=[select, *branches, join, seal], inputs={"document": {"ready": ready}}, edges=edges)
    await admitted(worker, factory)
    await worker.execute(await server_body(factory, "choose"))
    with pytest.raises(WorkerDenied, match="PARENT_UNSETTLED"):
        await worker.execute(await server_body(factory, "join"))
    receipts = {name: await worker.execute(await server_body(factory, name)) for name in ("yes", "no")}
    selected, skipped = ("yes", "no") if ready else ("no", "yes")
    assert receipts[selected]["status"] == "COMPLETED"
    assert receipts[skipped]["status"] == "SKIPPED"
    assert (await store.fetchone("SELECT count(*) AS n FROM automation_worker_evidence"))["n"] == 1
    await worker.execute(await server_body(factory, "join"))
    await worker.execute(await server_body(factory, "seal"))
    observer = WorkerWorkflowObserver(worker)
    observed = await observer.observe(None, {"run_id": "run", "inputs": {"document": {"ready": ready}}})
    assert observed["exists"] is True
    assert next(s for s in observed["steps"] if s["step_id"] == skipped)["status"] == "SKIPPED"
    # Even a self-consistently rehashed receipt cannot invent a different selection.
    forged = {**receipts[skipped]["result"], "branch_proof": []}
    await store.execute("UPDATE automation_worker_steps SET result_json=?,result_digest=? WHERE run_id='run' AND step_id=?", (json.dumps(forged), digest(forged), skipped))
    assert (await observer.observe(None, {"run_id": "run", "inputs": {"document": {"ready": ready}}}))["exists"] is False


async def test_false_precondition_refuses_actual_native_effect_and_never_replays(tmp_path):
    native = step("remind", Primitive.VAN_CAPABILITY, "reminder.create", {"text": "Review", "due_at_unix": int(time.time()) + 60}, action_class=ActionClass.A3)
    native = native.model_copy(update={"postcondition": {"kind": "READ_BACK", "field": "verified", "expected": True},
                                     "precondition": predicate("text", "Different")})
    worker, store, factory = await build(tmp_path, steps=[native], inputs={})
    await admitted(worker, factory)
    body = await server_body(factory, "remind")
    with pytest.raises(WorkerDenied, match="PRECONDITION_FALSE"):
        await worker.execute(body)
    assert (await store.fetchone("SELECT state FROM automation_worker_steps WHERE step_id='remind'"))["state"] == "REFUSED"
    assert (await store.fetchone("SELECT count(*) AS n FROM reminders"))["n"] == 0
    with pytest.raises(WorkerDenied, match="RESULT_PENDING"):
        await worker.execute(body)


async def test_native_reminder_is_actual_service_write_exact_replay_and_readback_detects_change(tmp_path):
    native = step("remind", Primitive.VAN_CAPABILITY, "reminder.create", {"text": "Review", "due_at_unix": int(time.time()) + 60}, action_class=ActionClass.A3)
    native.postcondition = {"kind": "READ_BACK", "field": "verified", "expected": True}
    worker, store, factory = await build(tmp_path, steps=[native], inputs={})
    await admitted(worker, factory)
    body = await server_body(factory, "remind")
    receipt = await worker.execute(body)
    assert receipt["result"]["verified"] is True
    assert (await worker.execute(body))["replayed"] is True
    assert (await store.fetchone("SELECT count(*) AS n FROM reminders"))["n"] == 1
    observer = WorkerWorkflowObserver(worker)
    assert (await observer.observe(None, {"run_id": "run", "inputs": {}}))["exists"] is True
    await store.execute("UPDATE reminders SET text='Changed'")
    assert (await observer.observe(None, {"run_id": "run", "inputs": {}}))["exists"] is False


def write_step(method="POST"):
    target = step("write", Primitive.HTTP_REQUEST, "delete_resource" if method == "DELETE" else "write_json", {}, domain="api.example.com")
    return type(target).model_validate({**target.model_dump(), "action_class": ActionClass.A4, "effects": ["DELETE" if method == "DELETE" else "WRITE"],
        "credential_alias": "connector://example", "retry_class": "NEVER_RETRY", "postcondition": {"kind": "READ_BACK", "field": "verified", "expected": True},
        "input_bindings": {"url": "https://api.example.com/resource", "method": method,
            **({"body": {"status": "ready"}} if method != "DELETE" else {}),
            "readback": {"url": "https://api.example.com/resource/status", "predicate": predicate("payload.status", "ready")}}})


def source_credentials(tmp_path, methods):
    token = tmp_path / "provider-token"
    token.write_text("test-provider-secret")
    token.chmod(0o600)
    config = tmp_path / "source-credentials.json"
    config.write_text(json.dumps({"schema_version": 1, "aliases": {"connector://example": {
        "credential_class": "C4_LOW_RISK_INTEGRATION", "admitted": True, "allowed_domains": ["api.example.com"],
        "header_name": "Authorization", "value_prefix": "Bearer ", "token_file": str(token), "allowed_methods": methods}}}))
    config.chmod(0o600)
    return SourceCredentialStore(str(config))


async def external_worker(tmp_path, *, method="POST", timeout=False, mismatch=False, methods=None):
    worker, store, factory = await build(tmp_path, steps=[write_step(method)], inputs={}, authority_class=ActionClass.A4)
    calls, state = [], {"status": "old"}
    def handler(request):
        calls.append(request.method)
        assert request.url.host == "8.8.8.8" and request.headers["host"] == "api.example.com"
        assert request.extensions["sni_hostname"] == "api.example.com"
        if request.method != "GET":
            assert request.headers["idempotency-key"].startswith("van-automation-")
            state["status"] = "ready"
            if timeout:
                raise httpx.ReadTimeout("response lost", request=request)
            return httpx.Response(202, json={"accepted": True})
        return httpx.Response(200, json={"status": "old"} if mismatch else state)
    async def resolver(host):
        return ["8.8.8.8"]
    worker.fetcher = GatewayDocumentFetcher(policy_with_domains("api.example.com"), transport=httpx.MockTransport(handler),
                                            resolver=resolver, credentials=source_credentials(tmp_path, methods or ["GET", method]))
    await admitted(worker, factory)
    return worker, store, factory, calls, state


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_actual_external_method_one_attempt_verified_only_after_independent_get(tmp_path, method):
    worker, store, factory, calls, state = await external_worker(tmp_path, method=method)
    body = await server_body(factory, "write")
    result = await worker.execute(body)
    assert result["result"]["verified"] is True and calls == [method, "GET"]
    assert (await worker.execute(body))["replayed"] is True and calls == [method, "GET"]
    observer = WorkerWorkflowObserver(worker)
    assert (await observer.observe(None, {"run_id": "run", "inputs": body.input}))["exists"] is True
    assert calls == [method, "GET", "GET"]
    state["status"] = "changed"
    assert (await observer.observe(None, {"run_id": "run", "inputs": body.input}))["exists"] is False
    assert calls.count(method) == 1


@pytest.mark.parametrize("failure", ["timeout", "mismatch", "method_unbound"])
async def test_external_unknown_or_unverified_effect_never_retried_or_reported_success(tmp_path, failure):
    worker, store, factory, calls, state = await external_worker(tmp_path, timeout=failure == "timeout", mismatch=failure == "mismatch",
        methods=["GET"] if failure == "method_unbound" else None)
    body = await server_body(factory, "write")
    with pytest.raises((WorkerDenied, httpx.ReadTimeout, ValueError)):
        await worker.execute(body)
    with pytest.raises(WorkerDenied, match="RESULT_PENDING"):
        await worker.execute(body)
    assert calls.count("POST") == (0 if failure == "method_unbound" else 1)
    row = await store.fetchone("SELECT state FROM automation_worker_steps WHERE step_id='write'")
    assert row["state"] == "IN_PROGRESS"
    assert (await WorkerWorkflowObserver(worker).observe(None, {"run_id": "run", "inputs": body.input}))["exists"] is False


@pytest.mark.parametrize("change", [{"owner_approved": False}, {"principal_type": "AUTOMATION"}, {"typed_action_id": None},
                                   {"typed_parameter_constraints": {"extra": 1}}, {"issued_at_unix": 1}])
async def test_a4_requires_exact_fresh_owner_scope_not_untyped_or_standing_authority(tmp_path, change):
    worker, store, factory, calls, state = await external_worker(tmp_path)
    row = await store.fetchone("SELECT key,value FROM runtime_meta WHERE key LIKE 'command_authority:%'")
    value = {**json.loads(row["value"]), **change}
    await store.execute("UPDATE runtime_meta SET value=? WHERE key=?", (json.dumps(value), row["key"]))
    with pytest.raises(GrantDenied, match="ACTION_CLASS_PROHIBITED"):
        await factory("write")
    assert calls == []


def test_external_readback_must_observe_provider_target_and_cannot_be_constant_true():
    target = write_step()
    target.input_bindings["readback"]["predicate"] = {"op": "EQ", "left": {"kind": "LITERAL", "value": True}, "right": {"kind": "LITERAL", "value": True}}
    with pytest.raises(PrimitiveSemanticError, match="READBACK_NOT_OBSERVABLE"):
        assert_primitive_semantics(target)


async def test_pause_committed_under_writer_lock_fences_next_actual_worker_effect(tmp_path):
    target = step("seal", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload": {"sealed": True}}, action_class=ActionClass.A3)
    worker, store, factory = await build(tmp_path, steps=[target], inputs={})
    await admitted(worker, factory)
    await store.execute("INSERT INTO missions(mission_id,owner_principal_id,origin,origin_channel,title,goal,state,authority_envelope_json,created_at_ms,updated_at_ms) VALUES('mission','owner','OWNER_UI','UI','Test','Bound automation','RUNNING',?,1,1)",
                        (json.dumps({"max_action_class":"A3", "source_command_id":"cmd-owner-1"}),))
    body = await server_body(factory, "seal")
    entered = asyncio.Event()
    original = worker.grants.redeem
    async def redeem(**kwargs):
        entered.set()
        return await original(**kwargs)
    worker.grants.redeem = redeem
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("INSERT INTO mission_execution_controls(mission_id,generation,desired_execution,updated_at_ms) VALUES('mission',1,'PAUSED',1)")
        task = asyncio.create_task(worker.execute(body))
        await asyncio.wait_for(entered.wait(), 2)
        await db.commit()
    with pytest.raises(WorkerDenied, match="MISSION_DISPATCH_PAUSED"):
        await task
    assert (await store.fetchone("SELECT count(*) AS n FROM automation_worker_evidence"))["n"] == 0
    assert await store.fetchone("SELECT state FROM automation_worker_steps WHERE step_id='seal'") is None


async def test_branched_delivery_checkpoint_advances_only_selected_durable_effects(tmp_path):
    detect = step("detect", Primitive.DEDUPE, "change_detect", {"payload":"$input.document"})
    choose = step("choose", Primitive.FILTER, "evaluate_predicate", {"payload":"$steps.detect.payload", "predicate":predicate()})
    emit = step("emit", Primitive.VAN_EVENT, "emit_external_event", {"payload":"$steps.detect", "event_type":"source.changed"}, action_class=ActionClass.A3)
    seal = step("seal", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload":{"selected":"false"}}, action_class=ActionClass.A3)
    final = step("final", Primitive.HASH, "hash", {"payload":{"settled":True}})
    edges = [WorkflowIREdge(from_step="detect",to_step="choose"), WorkflowIREdge(from_step="choose",to_step="emit",branch="true"),
             WorkflowIREdge(from_step="choose",to_step="seal",branch="false"), WorkflowIREdge(from_step="emit",to_step="final"),
             WorkflowIREdge(from_step="seal",to_step="final")]
    inputs = {"document":{"ready":True}}
    worker, store, factory = await build(tmp_path, steps=[detect,choose,emit,seal,final], inputs=inputs, edges=edges)
    await admitted(worker,factory)
    for name in ("detect","choose","emit"):
        await worker.execute(await server_body(factory,name))
    assert await store.fetchone("SELECT * FROM automation_worker_dedupe") is None
    skipped = await worker.execute(await server_body(factory,"seal"))
    assert skipped["status"] == "SKIPPED"
    await worker.execute(await server_body(factory,"final"))
    checkpoint = await store.fetchone("SELECT * FROM automation_worker_dedupe")
    assert checkpoint["generation"] == 1 and checkpoint["content_digest"] == digest(inputs["document"])
    assert (await store.fetchone("SELECT count(*) AS n FROM events WHERE event_type='automation.external_event'"))["n"] == 1
    assert (await WorkerWorkflowObserver(worker).observe(None,{"run_id":"run","inputs":inputs}))["exists"] is True
