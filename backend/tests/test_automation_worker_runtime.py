from __future__ import annotations

import asyncio
import base64
import json
import time

import httpx
import pytest
from fastapi import FastAPI

from conftest_automation import (
    enroll_device, make_action_runtime, make_store, policy_with_domains,
    sample_artifact, sample_capability, seal_owner_command, seed_snapshot,
)
from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.automation.canonical import digest
from van_gateway.automation.grants import GrantDenied, GrantKind, RunGrantService
from van_gateway.automation.models import Primitive, WorkflowIR, WorkflowIRStep, WorkflowIREdge, strongest_class
from van_gateway.automation.registry import AutomationRegistry
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.automation.worker_runtime import (
    AutomationWorkerRuntime, GatewayDocumentFetcher, WorkerDenied, WorkerStepBody, WorkerWorkflowObserver,
)
from van_gateway.automation.verifier import PostconditionSpec, VerificationOutcome, WorkflowVerifier
from van_gateway.command.authority import CommandAuthorityError, CommandAuthorityService
from van_gateway.config import Settings
from van_gateway.models import ActionClass, PrincipalType


def step(step_id, primitive, operation, bindings, *, action_class=ActionClass.A1, domain=None):
    postcondition = None
    if action_class == ActionClass.A3:
        postcondition = {"kind": "READ_BACK", "field": ("evidence_pointer" if primitive == Primitive.VAN_EVIDENCE
                                                       else "event_id" if primitive == Primitive.VAN_EVENT else "file_id")}
    effects = (["NOTIFY"] if primitive == Primitive.VAN_EVENT else ["DELETE"] if primitive == Primitive.DELETE_TRANSIENT_FILE
               else ["WRITE"] if action_class == ActionClass.A3 else ["NETWORK_READ"] if domain else ["READ"])
    return WorkflowIRStep(step_id=step_id, primitive=primitive, operation=operation,
                          input_bindings=bindings, effects=effects,
                          action_class=action_class, timeout_ms=1000, retry_class="IDEMPOTENT_WITH_KEY",
                          max_attempts=1, external_domain=domain, postcondition=postcondition)


async def build(tmp_path, *, steps=None, inputs=None, settings=None, declared_verifier=None, edges=None, authority_class=ActionClass.A3):
    store = await make_store(tmp_path)
    await enroll_device(store)
    authority = CommandAuthorityService(store)
    inputs = {"document": {"amount": "12.34", "currency": "USD"}} if inputs is None else inputs
    steps = steps or [
        step("hash", Primitive.HASH, "digest_documents", {"payload": "$input.document"}),
        step("seal", Primitive.VAN_EVIDENCE, "seal_artifact", {"payload": "$input.document", "digests": "$steps.hash"}, action_class=ActionClass.A3),
    ]
    ir = WorkflowIR(ir_id="ir-test", family="test", semantic_goal="bounded test", version=1,
                    trigger={"kind": "INVOKE"}, steps=steps,
                    edges=edges if edges is not None else [WorkflowIREdge(from_step=a.step_id, to_step=b.step_id) for a, b in zip(steps, steps[1:])],
                    action_class=strongest_class(steps), policy_version="policy-test", compiler_version="compiler-test",
                    verifier={"kind": "READ_BACK"} if declared_verifier is None else declared_verifier)
    registry = AutomationRegistry(store)
    cap = sample_capability(action_class=ir.action_class, mutates=any(s.mutates for s in steps))
    if authority_class is ActionClass.A4:
        inputs = {**inputs, "_automation_artifact_id": sample_artifact().artifact_id}
    action_id = "automation.workflow." + cap.capability_id if authority_class is ActionClass.A4 else "automation.test"
    sealed = await seal_owner_command(authority, effective=authority_class, owner_approved=authority_class is ActionClass.A4,
        typed_action_id=action_id if authority_class is ActionClass.A4 else None,
        typed_parameters=inputs if authority_class is ActionClass.A4 else None)
    await seed_snapshot(store, sealed.snapshot_id, sealed.command_id)
    await store.execute("UPDATE context_snapshots SET digest=? WHERE snapshot_id=?", (sealed.context_digest, sealed.snapshot_id))
    await registry.upsert_capability(cap)
    semantic, runtime_graph = {"ir": ir.semantic_payload()}, {"nodes": [{"name": "real-worker-callback"}]}
    artifact = sample_artifact().model_copy(update={
        "workflow_ir_digest": digest(ir.semantic_payload()), "compiled_semantic_digest": digest(semantic),
        "compiled_full_digest": digest(runtime_graph),
    })
    await registry.record_artifact(artifact)
    bindings = RuntimeBindingStore(store)
    await bindings.record(artifact_id=artifact.artifact_id, ir=ir.model_dump(mode="json"),
                          semantic_graph=semantic, runtime_graph=runtime_graph, readiness_errors=[])
    await bindings.mark_deployed(artifact.artifact_id, artifact.n8n_workflow_id)
    actions = await make_action_runtime(store)
    await actions.register(ActionDefinition(action_id=action_id, action_class=ir.action_class,
                                            mutates_state=cap.mutates_state, verifier_type=VerifierType.READ_BACK))
    execution = await actions.begin(execution_id="exec-run", command_id=sealed.command_id,
                                     turn_id=sealed.turn_id, action_id=action_id, principal_type=PrincipalType.OWNER_DEVICE,
                                     requested_by=sealed.requested_by, idempotency_key="run-test", parameters=inputs,
                                     snapshot_id=sealed.snapshot_id, owner_approved=True)
    await actions.mark_executing(execution.execution_id)
    now = int(time.time() * 1000)
    await store.execute("""INSERT INTO automation_runs(run_id,capability_id,artifact_id,command_id,turn_id,execution_id,
        status,action_class,input_digest,started_at_ms,updated_at_ms) VALUES('run',?,?,?,?,?,'PENDING',?,?,?,?)""",
                        (cap.capability_id, artifact.artifact_id, sealed.command_id, sealed.turn_id, execution.execution_id,
                         cap.action_class.value, digest(inputs), now, now))
    grants = RunGrantService(store, signing_key="worker-test-signing-key")
    worker = AutomationWorkerRuntime(store, grants=grants, actions=actions, authority=authority,
                                      registry=registry, enabled=True, settings=settings)

    async def body(step_id, value=None):
        selected = next((s for s in steps if s.step_id == step_id), None)
        minted = await grants.mint(run_id="run", command_id=sealed.command_id, capability_id=cap.capability_id,
                                    artifact_id=artifact.artifact_id, artifact_version=artifact.version,
                                    context_snapshot_id=sealed.snapshot_id, input_digest=digest(inputs),
                                    action_class_ceiling=selected.action_class if selected else cap.action_class,
                                    allowed_gateway_operations=[f"step:{step_id}" if selected else "admit_run"],
                                    allowed_external_domains=[selected.external_domain] if selected and selected.external_domain else [],
                                    grant_kind=GrantKind.SINGLE_USE_MUTATION)
        return WorkerStepBody(capability_grant=minted.token, grant=minted.grant, run_id="run",
                              step_id=step_id, input=inputs, value=value or {})
    return worker, store, body


async def admitted(worker, body):
    receipt = await worker.execute(await body("__admit__"))
    assert receipt["admitted"] is True


async def new_run(worker, store, steps, run_id, inputs):
    """Admit a fresh canonical owner run against the same immutable artifact."""
    original = await store.fetchone("SELECT * FROM automation_runs WHERE run_id='run'")
    sealed = await seal_owner_command(worker.authority, command_id=f"cmd-{run_id}",
                                      snapshot_id=f"ctx-{run_id}", turn_id=f"turn-{run_id}", effective=ActionClass.A3)
    await seed_snapshot(store, sealed.snapshot_id, sealed.command_id)
    await store.execute("UPDATE context_snapshots SET digest=? WHERE snapshot_id=?", (sealed.context_digest, sealed.snapshot_id))
    execution = await worker.actions.begin(execution_id=f"exec-{run_id}", command_id=sealed.command_id,
        turn_id=sealed.turn_id, action_id="automation.test", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by=sealed.requested_by, idempotency_key=run_id, parameters=inputs,
        snapshot_id=sealed.snapshot_id, owner_approved=True)
    await worker.actions.mark_executing(execution.execution_id)
    now = int(time.time() * 1000)
    await store.execute("""INSERT INTO automation_runs(run_id,capability_id,artifact_id,command_id,turn_id,execution_id,
        status,action_class,input_digest,started_at_ms,updated_at_ms) VALUES(?,?,?,?,?,?,'PENDING',?,?,?,?)""",
        (run_id, original["capability_id"], original["artifact_id"], sealed.command_id, sealed.turn_id,
         execution.execution_id, original["action_class"], digest(inputs), now, now))
    artifact = await worker.registry.get_artifact(original["artifact_id"])

    async def body(step_id, value=None):
        selected = next((s for s in steps if s.step_id == step_id), None)
        minted = await worker.grants.mint(run_id=run_id, command_id=sealed.command_id,
            capability_id=original["capability_id"], artifact_id=artifact.artifact_id, artifact_version=artifact.version,
            context_snapshot_id=sealed.snapshot_id, input_digest=digest(inputs),
            action_class_ceiling=selected.action_class if selected else strongest_class(steps),
            allowed_gateway_operations=[f"step:{step_id}" if selected else "admit_run"],
            allowed_external_domains=[selected.external_domain] if selected and selected.external_domain else [],
            grant_kind=GrantKind.SINGLE_USE_MUTATION)
        return WorkerStepBody(capability_grant=minted.token, grant=minted.grant, run_id=run_id,
                              step_id=step_id, input=inputs, value=value or {})
    return body


@pytest.mark.parametrize("input_ref,step_ref", [
    ("{{ input.document }}", "{{ steps.hash }}"),
    ("{{input.document}}", "{{steps.hash}}"),
    ("$input.document", "$steps.hash"),
])
async def test_compiler_binding_vocabulary_reaches_actual_bound_callback_effect(tmp_path, input_ref, step_ref):
    from van_gateway.automation.compiler import AutomationCompiler
    steps = [step("hash", Primitive.HASH, "hash", {"payload": input_ref}),
             step("seal", Primitive.VAN_EVIDENCE, "seal_artifact", {"payload": input_ref, "digests": step_ref}, action_class=ActionClass.A3)]
    expression = AutomationCompiler._binding_expression(input_ref, {}, {s.step_id: s for s in steps}, {"hash": "001_hash"}, "root")
    assert expression == 'root.input["document"]'
    worker, store, body = await build(tmp_path, steps=steps)
    await admitted(worker, body)
    payload = {"amount": "12.34", "currency": "USD"}
    hashed = await worker.execute(await body("hash", {"payload": payload}))
    await worker.execute(await body("seal", {"payload": payload, "digests": hashed["result"]}))
    assert (await store.fetchone("SELECT content_digest FROM automation_worker_evidence"))["content_digest"] == digest(payload)
    tampered = await body("seal", {"payload": payload, "digests": {"primary": "changed"}})
    with pytest.raises(WorkerDenied, match="BINDING_MISMATCH"):
        await worker.execute(tampered)
    assert (await store.fetchone("SELECT use_count FROM automation_run_nonces WHERE grant_id=?", (tampered.grant.grant_id,)))["use_count"] == 0


@pytest.mark.parametrize("reference", ["{{ input.document + 1 }}", "{{ input.document", "$input..document", "{{ steps.hash[0] }}"])
async def test_binding_expressions_cannot_execute_arbitrary_n8n_syntax(tmp_path, reference):
    worker, store, body = await build(tmp_path, steps=[step("hash", Primitive.HASH, "hash", {"payload": reference})])
    await admitted(worker, body)
    with pytest.raises(WorkerDenied, match="EXPRESSION_UNSUPPORTED"):
        await worker.execute(await body("hash", {"payload": {}}))


def monitor_steps():
    return [step("detect", Primitive.DEDUPE, "change_detect", {"payload": "$input.document"}),
            step("emit", Primitive.VAN_EVENT, "emit_external_event", {"payload": "$steps.detect", "event_type": "source.changed"}, action_class=ActionClass.A3)]


async def test_interrupted_monitor_observation_remains_deliverable_in_next_canonical_run(tmp_path):
    steps, inputs = monitor_steps(), {"document": {"version": "A"}}
    worker, store, body = await build(tmp_path, steps=steps, inputs=inputs)
    await admitted(worker, body)
    staged = await worker.execute(await body("detect", {"payload": inputs["document"]}))
    assert staged["result"]["changed"] is True
    assert await store.fetchone("SELECT * FROM automation_worker_dedupe") is None
    # First run stops before required owner delivery. Fresh authority can continue
    # the observation without repeating the original consumed callback.
    following = await new_run(worker, store, steps, "following", inputs)
    await admitted(worker, following)
    retry = await worker.execute(await following("detect", {"payload": inputs["document"]}))
    assert retry["result"]["changed"] is True
    assert retry["result"]["delivery_key"] == staged["result"]["delivery_key"]
    emitted = await worker.execute(await following("emit", {"payload": retry["result"], "event_type": "source.changed"}))
    assert emitted["result"]["emitted"] is True
    assert (await store.fetchone("SELECT generation FROM automation_worker_dedupe"))["generation"] == 1
    later = await new_run(worker, store, steps, "later", inputs)
    await admitted(worker, later)
    unchanged = await worker.execute(await later("detect", {"payload": inputs["document"]}))
    assert unchanged["result"]["changed"] is False
    assert (await worker.execute(await later("emit", {"payload": unchanged["result"], "event_type": "source.changed"})))["result"]["emitted"] is False
    assert len(await store.fetchall("SELECT * FROM events WHERE event_type='automation.external_event'")) == 1


async def test_delivery_before_lost_completion_recovers_without_duplicate_notification(tmp_path, monkeypatch):
    steps, inputs = monitor_steps(), {"document": {"version": "A"}}
    worker, store, body = await build(tmp_path, steps=steps, inputs=inputs)
    await admitted(worker, body)
    staged = await worker.execute(await body("detect", {"payload": inputs["document"]}))
    complete = worker._complete
    async def interrupted(request, *args):
        if request.step_id == "emit":
            raise WorkerDenied("completion_interrupted")
        await complete(request, *args)
    monkeypatch.setattr(worker, "_complete", interrupted)
    pending = await body("emit", {"payload": staged["result"], "event_type": "source.changed"})
    with pytest.raises(WorkerDenied, match="completion_interrupted"):
        await worker.execute(pending)
    monkeypatch.setattr(worker, "_complete", complete)
    with pytest.raises(WorkerDenied, match="RESULT_PENDING"):
        await worker.execute(pending)
    assert await store.fetchone("SELECT * FROM automation_worker_dedupe") is None
    following = await new_run(worker, store, steps, "following", inputs)
    await admitted(worker, following)
    retry = await worker.execute(await following("detect", {"payload": inputs["document"]}))
    recovered = await worker.execute(await following("emit", {"payload": retry["result"], "event_type": "source.changed"}))
    events = await store.fetchall("SELECT * FROM events WHERE event_type='automation.external_event'")
    assert len(events) == 1 and recovered["result"]["event_id"] == events[0]["event_id"]
    assert recovered["result"]["command_id"] == pending.grant.command_id
    assert (await store.fetchone("SELECT generation FROM automation_worker_dedupe"))["generation"] == 1


async def test_attention_delivery_recovery_preserves_owner_acknowledgement(tmp_path, monkeypatch):
    steps = [step("detect", Primitive.DEDUPE, "change_detect", {"payload": "$input.document"}),
             step("emit", Primitive.VAN_EVENT, "emit_attention",
                  {"change": "$steps.detect", "severity": "FOLLOW_UP", "title": "Report changed"}, action_class=ActionClass.A3)]
    inputs = {"document": {"version": "A"}}
    worker, store, body = await build(tmp_path, steps=steps, inputs=inputs)
    await admitted(worker, body)
    staged = await worker.execute(await body("detect", {"payload": inputs["document"]}))
    complete = worker._complete
    async def interrupted(request, *args):
        if request.step_id == "emit":
            raise WorkerDenied("completion_interrupted")
        await complete(request, *args)
    monkeypatch.setattr(worker, "_complete", interrupted)
    with pytest.raises(WorkerDenied, match="completion_interrupted"):
        await worker.execute(await body("emit", {"change": staged["result"], "severity": "FOLLOW_UP", "title": "Report changed"}))
    attention = await store.fetchone("SELECT * FROM attention")
    await store.execute("UPDATE attention SET state='ACKNOWLEDGED' WHERE id=?", (attention["id"],))
    monkeypatch.setattr(worker, "_complete", complete)
    following = await new_run(worker, store, steps, "following", inputs)
    await admitted(worker, following)
    retry = await worker.execute(await following("detect", {"payload": inputs["document"]}))
    recovered = await worker.execute(await following("emit", {"change": retry["result"], "severity": "FOLLOW_UP", "title": "Report changed"}))
    assert recovered["result"]["attention_id"] == attention["id"]
    assert len(await store.fetchall("SELECT * FROM attention")) == 1
    assert (await store.fetchone("SELECT state FROM attention"))["state"] == "ACKNOWLEDGED"
    assert len(await store.fetchall("SELECT * FROM events WHERE event_type='attention.upserted'")) == 1
    assert (await store.fetchone("SELECT generation FROM automation_worker_dedupe"))["generation"] == 1


async def test_monitor_repeated_A_B_A_B_transitions_have_distinct_delivery_revisions(tmp_path):
    steps, inputs = monitor_steps(), {"document": {"version": "A"}}
    worker, store, body = await build(tmp_path, steps=steps, inputs=inputs)
    identities = []
    for index, value in enumerate("ABAB"):
        current = {"document": {"version": value}}
        active = body if index == 0 else await new_run(worker, store, steps, f"transition-{index}", current)
        await admitted(worker, active)
        observed = await worker.execute(await active("detect", {"payload": current["document"]}))
        assert observed["result"]["changed"] is True
        delivered = await worker.execute(await active("emit", {"payload": observed["result"], "event_type": "source.changed"}))
        identities.append(delivered["result"]["event_id"])
    assert len(set(identities)) == 4
    assert (await store.fetchone("SELECT generation FROM automation_worker_dedupe"))["generation"] == 4


async def test_all_required_notification_and_evidence_targets_precede_delivery_checkpoint(tmp_path):
    steps = monitor_steps() + [step("seal", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload": "$input.document"}, action_class=ActionClass.A3)]
    inputs = {"document": {"version": "A"}}
    worker, store, body = await build(tmp_path, steps=steps, inputs=inputs)
    await admitted(worker, body)
    observed = await worker.execute(await body("detect", {"payload": inputs["document"]}))
    await worker.execute(await body("emit", {"payload": observed["result"], "event_type": "source.changed"}))
    assert await store.fetchone("SELECT * FROM automation_worker_dedupe") is None
    await worker.execute(await body("seal", {"payload": inputs["document"]}))
    assert (await store.fetchone("SELECT generation FROM automation_worker_dedupe"))["generation"] == 1


@pytest.mark.parametrize("operation", ["emit_external_event", "emit_attention"])
async def test_concurrent_canonical_runs_share_one_durable_staged_notification(tmp_path, operation):
    steps, inputs = monitor_steps(), {"document": {"version": "A"}}
    if operation == "emit_attention":
        steps[1] = step("emit", Primitive.VAN_EVENT, operation,
            {"change": "$steps.detect", "severity": "FOLLOW_UP", "title": "Changed"}, action_class=ActionClass.A3)
    worker, store, body = await build(tmp_path, steps=steps, inputs=inputs)
    following = await new_run(worker, store, steps, "following", inputs)
    await admitted(worker, body)
    await admitted(worker, following)
    requests = []
    for active in (body, following):
        staged = await worker.execute(await active("detect", {"payload": inputs["document"]}))
        value = ({"change": staged["result"], "severity": "FOLLOW_UP", "title": "Changed"}
                 if operation == "emit_attention" else {"payload": staged["result"], "event_type": "source.changed"})
        requests.append(await active("emit", value))
    receipts = await asyncio.gather(*(worker.execute(request) for request in requests))
    assert receipts[0]["result"]["event_id"] == receipts[1]["result"]["event_id"]
    event_type = "attention.upserted" if operation == "emit_attention" else "automation.external_event"
    assert len(await store.fetchall("SELECT * FROM events WHERE event_type=?", (event_type,))) == 1
    if operation == "emit_attention":
        assert len(await store.fetchall("SELECT * FROM attention")) == 1
    assert (await store.fetchone("SELECT generation FROM automation_worker_dedupe"))["generation"] == 1


async def test_owner_verifier_uses_actual_graph_sink_for_out_of_order_ir_storage(tmp_path):
    steps = [step("seal", Primitive.VAN_EVIDENCE, "seal_evidence", {"payload": "$input.document", "digests": "{{ steps.hash }}"}, action_class=ActionClass.A3),
             step("hash", Primitive.HASH, "hash", {"payload": "{{ input.document }}"})]
    worker, store, body = await build(tmp_path, steps=steps, edges=[WorkflowIREdge(from_step="hash", to_step="seal")],
        declared_verifier={"kind": "READ_BACK", "field": "evidence_pointer"})
    await admitted(worker, body)
    payload = {"amount": "12.34", "currency": "USD"}
    hashed = await worker.execute(await body("hash", {"payload": payload}))
    sealed = await worker.execute(await body("seal", {"payload": payload, "digests": hashed["result"]}))
    observed = await verified_result(worker, {"document": payload})
    assert observed.outcome == VerificationOutcome.VERIFIED
    assert observed.observed["evidence_pointer"] == sealed["result"]["evidence_pointer"]


async def test_legacy_underdeclared_file_macro_refuses_before_nonce_or_real_byte_effect(tmp_path):
    content = base64.b64encode(b"must not store").decode()
    steps = [step("store", Primitive.STORE_TRANSIENT_FILE, "ingest", {"content_base64": "$input.content"})]
    worker, store, body = await build(tmp_path, steps=steps, inputs={"content": content})
    await admitted(worker, body)
    request = await body("store", {"content_base64": content})
    with pytest.raises(ValueError, match="primitive_.*|PRIMITIVE_.*"):
        await worker.execute(request)
    assert await store.fetchone("SELECT * FROM automation_worker_files") is None
    assert (await store.fetchone("SELECT use_count FROM automation_run_nonces WHERE grant_id=?", (request.grant.grant_id,)))["use_count"] == 0


async def test_real_admission_hash_and_seal_have_durable_independent_records(tmp_path):
    worker, store, body = await build(tmp_path)
    await admitted(worker, body)
    payload = {"amount": "12.34", "currency": "USD"}
    hashed = await worker.execute(await body("hash", {"payload": payload}))
    sealed = await worker.execute(await body("seal", {"payload": payload, "digests": hashed["result"]}))
    evidence = await store.fetchone("SELECT * FROM automation_worker_evidence")
    assert evidence["content_digest"] == digest(payload)
    assert json.loads(evidence["payload_json"]) == payload
    assert sealed["result"]["provider_correctness_verified"] is False
    assert sealed["result"]["evidence_pointer"].endswith(evidence["evidence_id"])


async def test_step_cannot_execute_before_run_admission(tmp_path):
    worker, store, body = await build(tmp_path)
    with pytest.raises(WorkerDenied, match="RUN_NOT_ADMITTED"):
        await worker.execute(await body("hash", {"payload": {}}))
    assert await store.fetchone("SELECT * FROM automation_worker_steps") is None


async def test_lost_reply_replays_only_exact_completed_receipt_without_another_effect(tmp_path):
    worker, store, body = await build(tmp_path)
    await admitted(worker, body)
    request = await body("hash", {"payload": {"amount": "12.34", "currency": "USD"}})
    first = await worker.execute(request)
    repeated = await worker.execute(request)
    assert repeated["result_digest"] == first["result_digest"]
    assert repeated["replayed"] is True
    assert (await store.fetchone("SELECT use_count FROM automation_run_nonces WHERE grant_id=?", (request.grant.grant_id,)))["use_count"] == 1


async def test_binding_tampering_is_refused_before_nonce_consumption(tmp_path):
    worker, store, body = await build(tmp_path)
    await admitted(worker, body)
    request = await body("hash", {"payload": {"amount": "999"}})
    with pytest.raises(WorkerDenied, match="BINDING_MISMATCH"):
        await worker.execute(request)
    assert (await store.fetchone("SELECT use_count FROM automation_run_nonces WHERE grant_id=?", (request.grant.grant_id,)))["use_count"] == 0


@pytest.mark.parametrize("change,expected", [
    ("cancel", "RUN_NOT_ACTIVE"), ("device", "revoked"), ("snapshot", "SNAPSHOT_MISMATCH"),
    ("artifact", "ARTIFACT_DIGEST_MISMATCH"), ("input", "RUN_BINDING_MISMATCH"),
    ("action", "ACTION_BINDING_MISMATCH"),
])
async def test_current_run_authority_and_immutable_bindings_are_rechecked(tmp_path, change, expected):
    worker, store, body = await build(tmp_path)
    await admitted(worker, body)
    request = await body("hash", {"payload": {"amount": "12.34", "currency": "USD"}})
    if change == "cancel":
        await store.execute("UPDATE automation_runs SET status='CANCELLED'")
    elif change == "device":
        await store.execute("UPDATE devices SET revoked_at_unix=1")
    elif change == "snapshot":
        await store.execute("UPDATE context_snapshots SET digest='changed'")
    elif change == "artifact":
        row = await worker.bindings.get(request.grant.artifact_id)
        await store.execute("UPDATE automation_runtime_bindings SET ir_json=?", (json.dumps({**row["ir"], "semantic_goal": "changed"}),))
    elif change == "input":
        request = request.model_copy(update={"input": {"document": "changed"}})
    else:
        await store.execute("UPDATE action_executions SET parameters_digest='changed'")
    with pytest.raises((WorkerDenied, CommandAuthorityError), match=expected):
        await worker.execute(request)


async def test_bad_mac_never_admits_a_run(tmp_path):
    worker, store, body = await build(tmp_path)
    request = await body("__admit__")
    with pytest.raises(GrantDenied, match="SIGNATURE_INVALID"):
        await worker.execute(request.model_copy(update={"capability_grant": request.capability_grant + "bad"}))
    assert await store.fetchone("SELECT * FROM automation_worker_steps") is None


async def test_interrupted_effect_remains_pending_and_cannot_be_repeated(tmp_path, monkeypatch):
    worker, store, body = await build(tmp_path)
    await admitted(worker, body)
    calls = []
    async def uncertain(*_):
        calls.append(True)
        raise WorkerDenied("producer_failed_after_admission")
    monkeypatch.setattr(worker, "_produce", uncertain)
    request = await body("hash", {"payload": {"amount": "12.34", "currency": "USD"}})
    with pytest.raises(WorkerDenied, match="producer_failed"):
        await worker.execute(request)
    with pytest.raises(WorkerDenied, match="RESULT_PENDING"):
        await worker.execute(request)
    assert len(calls) == 1


async def test_file_bytes_are_stored_deleted_and_receipt_replay_does_not_repeat_delete(tmp_path):
    steps = [step("store", Primitive.STORE_TRANSIENT_FILE, "ingest", {"content_base64": "$input.content", "filename": "statement.txt"}, action_class=ActionClass.A3),
             step("delete", Primitive.DELETE_TRANSIENT_FILE, "release", {"file_id": "$steps.store.file_id"}, action_class=ActionClass.A3)]
    content = base64.b64encode(b"actual document bytes").decode()
    worker, store, body = await build(tmp_path, steps=steps, inputs={"content": content})
    await admitted(worker, body)
    saved = await worker.execute(await body("store", {"content_base64": content, "filename": "statement.txt"}))
    row = await store.fetchone("SELECT * FROM automation_worker_files")
    assert row["content"] == b"actual document bytes"
    request = await body("delete", {"file_id": saved["result"]["file_id"]})
    assert (await worker.execute(request))["result"]["deleted"] is True
    assert (await worker.execute(request))["replayed"] is True
    assert (await store.fetchone("SELECT content FROM automation_worker_files"))["content"] is None


async def test_retention_erases_expired_bytes_and_preserves_replay_and_receipt_records(tmp_path):
    steps = [step("store", Primitive.STORE_TRANSIENT_FILE, "ingest", {"content_base64": "$input.content"}, action_class=ActionClass.A3)]
    content = base64.b64encode(b"private bytes").decode()
    worker, store, body = await build(tmp_path, steps=steps, inputs={"content": content})
    await admitted(worker, body)
    saved = await worker.execute(await body("store", {"content_base64": content}))
    future = int(time.time() * 1000) + 90_000_000
    assert await worker.cleanup_transient_bytes(now_ms=future) == 1
    row = await store.fetchone("SELECT * FROM automation_worker_files")
    assert row["content"] is None and row["state"] == "RETIRED"
    receipt = await store.fetchone("SELECT * FROM automation_worker_steps WHERE step_id='store'")
    assert receipt["result_digest"] == saved["result_digest"]
    assert receipt["state"] == "COMPLETED"


async def test_http_source_is_fetched_by_gateway_with_pinned_address_and_normal_tls_contract():
    observed = []
    def handle(request):
        observed.append(request)
        return httpx.Response(200, json={"statement": "observed"})
    async def resolver(_):
        return ["1.1.1.1"]
    fetcher = GatewayDocumentFetcher(policy_with_domains("reports.example.com"), transport=httpx.MockTransport(handle), resolver=resolver)
    result = await fetcher.fetch("https://reports.example.com/statement", timeout_ms=1000)
    assert observed[0].url.host == "1.1.1.1"
    assert observed[0].headers["host"] == "reports.example.com"
    assert observed[0].extensions["sni_hostname"] == "reports.example.com"
    assert result["payload"] == {"statement": "observed"}
    assert result["source_trust"] == "UNTRUSTED_EXTERNAL"


async def test_slow_continuous_source_stream_has_total_deadline_and_closes_transport():
    class SlowStream(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield b" "
        async def aclose(self):
            self.closed = True
    stream = SlowStream()
    async def resolver(_):
        return ["1.1.1.1"]
    fetcher = GatewayDocumentFetcher(policy_with_domains("reports.example.com"),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)), resolver=resolver)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await fetcher.fetch("https://reports.example.com/stream", timeout_ms=35)
    assert time.monotonic() - started < 0.5
    assert stream.closed is True


async def test_callback_total_deadline_preserves_uncertain_nonce_without_false_completion(tmp_path, monkeypatch):
    steps = [step("hash", Primitive.HASH, "hash", {"payload": "$input.document"}).model_copy(update={"timeout_ms": 30})]
    worker, store, body = await build(tmp_path, steps=steps)
    await admitted(worker, body)
    calls = []
    async def slow(*_):
        calls.append(True)
        await asyncio.sleep(1)
        return {"primary": "never-completed"}
    monkeypatch.setattr(worker, "_produce", slow)
    request = await body("hash", {"payload": {"amount": "12.34", "currency": "USD"}})
    with pytest.raises(TimeoutError):
        await worker.execute(request)
    with pytest.raises(WorkerDenied, match="RESULT_PENDING"):
        await worker.execute(request)
    record = await store.fetchone("SELECT * FROM automation_worker_steps WHERE step_id='hash'")
    assert record["state"] == "IN_PROGRESS" and record["result_digest"] is None
    assert len(calls) == 1


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
async def test_dns_private_addresses_are_refused_before_any_request(address):
    observed = []
    async def resolver(_):
        return [address]
    fetcher = GatewayDocumentFetcher(policy_with_domains("reports.example.com"),
                                     transport=httpx.MockTransport(lambda r: observed.append(r)), resolver=resolver)
    with pytest.raises(WorkerDenied, match="ADDRESS_DENIED"):
        await fetcher.fetch("https://reports.example.com/statement", timeout_ms=1000)
    assert not observed


async def test_callback_route_requires_dedicated_machine_scope_and_https_host(tmp_path):
    token, broad = "w" * 40, "a" * 40
    settings = Settings(internal_control_scoped_tokens=f"automation_worker:{token};automation:{broad}",
                        automation_worker_endpoint="https://worker.private/v1/automation/worker/step")
    worker, store, body = await build(tmp_path, settings=settings)
    app = FastAPI()
    app.include_router(worker.router)
    request = (await body("__admit__")).model_dump(mode="json")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://worker.private") as client:
        rejected = await client.post("/v1/automation/worker/step", json=request, headers={"X-Van-Internal-Token": broad})
        assert rejected.status_code == 403
        accepted = await client.post("/v1/automation/worker/step", json=request, headers={"X-Van-Internal-Token": token})
        assert accepted.status_code == 200 and accepted.json()["admitted"] is True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://worker.private") as client:
        rejected = await client.post("/v1/automation/worker/step", json=request, headers={"X-Van-Internal-Token": token})
        assert rejected.status_code == 403


async def test_concurrent_duplicate_callbacks_produce_one_effect(tmp_path, monkeypatch):
    worker, store, body = await build(tmp_path)
    await admitted(worker, body)
    original, calls = worker._produce, []
    async def counted(*args):
        calls.append(True)
        await asyncio.sleep(0.02)
        return await original(*args)
    monkeypatch.setattr(worker, "_produce", counted)
    request = await body("hash", {"payload": {"amount": "12.34", "currency": "USD"}})
    outcomes = await asyncio.gather(*(worker.execute(request) for _ in range(5)), return_exceptions=True)
    assert len(calls) == 1
    assert any(isinstance(outcome, dict) for outcome in outcomes)
    assert all(isinstance(outcome, (dict, GrantDenied, WorkerDenied)) for outcome in outcomes)


async def verified_result(worker, inputs):
    verifier = WorkflowVerifier({"AUTOMATION_WORKER_READ_BACK": WorkerWorkflowObserver(worker)})
    return await verifier.verify(spec=PostconditionSpec(kind="AUTOMATION_WORKER_READ_BACK"),
                                  verifier_type=VerifierType.READ_BACK, engine_reported_success=True,
                                  context={"run_id": "run", "inputs": inputs})


async def test_independent_observer_requires_actual_exact_effect_not_engine_success(tmp_path):
    worker, store, body = await build(tmp_path)
    await admitted(worker, body)
    payload = {"amount": "12.34", "currency": "USD"}
    inputs = {"document": payload}
    hashed = await worker.execute(await body("hash", {"payload": payload}))
    assert (await verified_result(worker, inputs)).outcome == VerificationOutcome.FAILED
    await worker.execute(await body("seal", {"payload": payload, "digests": hashed["result"]}))
    observed = await verified_result(worker, inputs)
    assert observed.outcome == VerificationOutcome.VERIFIED
    assert observed.observed["provider_correctness_verified"] is False
    await store.execute("UPDATE automation_worker_evidence SET payload_json='{}'")
    assert (await verified_result(worker, inputs)).outcome == VerificationOutcome.FAILED


async def test_missing_declared_owner_goal_is_unverifiable_even_with_all_steps_completed(tmp_path):
    steps = [step("hash", Primitive.HASH, "hash", {"payload": "$input.document"})]
    worker, store, body = await build(tmp_path, steps=steps, declared_verifier={})
    await admitted(worker, body)
    payload = {"amount": "12.34", "currency": "USD"}
    await worker.execute(await body("hash", {"payload": payload}))
    assert (await verified_result(worker, {"document": payload})).outcome == VerificationOutcome.UNVERIFIABLE


async def test_source_observer_reads_provider_again_and_refuses_changed_content(tmp_path):
    steps = [step("fetch", Primitive.HTTP_GET, "fetch_resource", {"url": "https://reports.example.com/item"},
                  action_class=ActionClass.A2, domain="reports.example.com")]
    worker, store, body = await build(tmp_path, steps=steps, inputs={})
    state = {"value": "first"}
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=state)
    async def resolver(_):
        return ["1.1.1.1"]
    worker.fetcher = GatewayDocumentFetcher(policy_with_domains("reports.example.com"),
                                            transport=httpx.MockTransport(handle), resolver=resolver)
    await admitted(worker, body)
    await worker.execute(await body("fetch", {"url": "https://reports.example.com/item"}))
    assert (await verified_result(worker, {})).outcome == VerificationOutcome.VERIFIED
    assert len(requests) == 2
    state["value"] = "changed"
    assert (await verified_result(worker, {})).outcome == VerificationOutcome.FAILED
    assert len(requests) == 3


async def test_scoped_source_credential_reaches_only_the_pinned_request_and_is_never_returned():
    credential = "synthetic-source-token-for-test"
    class Credentials:
        async def headers(self, alias, url):
            assert alias == "connector://reports/primary"
            assert url == "https://reports.example.com/item"
            return {"Authorization": "Bearer " + credential}
    observed = []
    def handle(request):
        observed.append(request)
        return httpx.Response(200, json={"report": "owner record"})
    async def resolver(_):
        return ["1.1.1.1"]
    fetcher = GatewayDocumentFetcher(policy_with_domains("reports.example.com"),
                                     transport=httpx.MockTransport(handle), resolver=resolver, credentials=Credentials())
    result = await fetcher.fetch("https://reports.example.com/item", timeout_ms=1000,
                                credential_alias="connector://reports/primary")
    assert observed[0].headers["authorization"] == "Bearer " + credential
    assert credential not in json.dumps(result)


@pytest.mark.parametrize("credential,json_encoded", [
    ("synthetic-source-token-for-test", False), ("abc", False), ("a\"b", True), ("a b", True),
])
async def test_provider_echoing_a_scoped_source_secret_is_refused_before_persistence(credential, json_encoded):
    class Credentials:
        async def headers(self, alias, url):
            return {"Authorization": "Bearer " + credential}
    async def resolver(_):
        return ["1.1.1.1"]
    fetcher = GatewayDocumentFetcher(policy_with_domains("reports.example.com"),
                                     transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"nested": {"echo": credential}})
                                                                  if json_encoded else httpx.Response(200, text=credential)),
                                     resolver=resolver, credentials=Credentials())
    with pytest.raises(WorkerDenied, match="RESPONSE_CONTAINS_CREDENTIAL"):
        await fetcher.fetch("https://reports.example.com/item", timeout_ms=1000, credential_alias="connector://reports/primary")
