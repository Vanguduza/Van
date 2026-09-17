"""Rev 1.3 §§145-151, 155, 263-264 — validator, compiler determinism and lineage.

The properties under test are the ones that make workflow generation safe to
repeat: the same IR always compiles to the same semantic graph, an unsafe graph
never reaches the compiler at all, and an admitted artifact is immutable so a
repair has to become a new version.
"""

from __future__ import annotations

import pytest

from conftest_automation import (
    make_store,
    policy_with_domains,
    sample_artifact,
    sample_capability,
    sample_ir,
)
from van_gateway.automation.canonical import canonical_json, digest, new_id
from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.models import (
    Primitive,
    RetryClass,
    WorkflowIREdge,
    WorkflowIRStep,
    WorkflowLifecycle,
    WorkflowStepEffect,
    strongest_class,
)
from van_gateway.automation.policy import PolicyError
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex, RegistryError
from van_gateway.automation.validator import WorkflowValidator
from van_gateway.models import ActionClass

DOMAIN = "reports.example.com"
CREDS = {"connector://broker/primary": "cred_17"}


def _policy():
    return policy_with_domains(DOMAIN)


# ------------------------------------------------------------------ canonical


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_canonical_json_rejects_non_finite_floats():
    with pytest.raises(ValueError):
        canonical_json({"x": float("inf")})


def test_decimal_serialises_losslessly():
    from decimal import Decimal

    assert b"0.1" in canonical_json({"x": Decimal("0.1")})


def test_identifiers_are_prefixed():
    assert new_id("run").startswith("wfrun_")
    assert new_id("artifact").startswith("wfart_")
    assert new_id("browser_task").startswith("btask_")


# ------------------------------------------------------------------ validator


def test_valid_workflow_passes():
    report = WorkflowValidator(_policy()).validate(sample_ir(domain=DOMAIN))
    assert report.ok, report.errors
    assert report.topological_order == ["s_trig01", "s_http02", "s_evid03"]
    assert report.report_digest.startswith("sha256:")


def test_action_class_is_derived_not_trusted():
    """§146 — a caller cannot under-declare the workflow's consequence."""
    ir = sample_ir(domain=DOMAIN).model_copy(update={"action_class": ActionClass.A1})
    report = WorkflowValidator(_policy()).validate(ir)
    assert not report.ok
    assert report.derived_action_class == "A3"
    assert any("ACTION_CLASS_UNDERDECLARED" in e for e in report.errors)


def test_strongest_class_picks_max():
    ir = sample_ir(domain=DOMAIN)
    assert strongest_class(ir.steps) is ActionClass.A3


def test_cycle_is_rejected():
    """§145 — no cycles without a bounded loop primitive."""
    ir = sample_ir(domain=DOMAIN)
    ir = ir.model_copy(
        update={"edges": [*ir.edges, WorkflowIREdge(from_step="s_evid03", to_step="s_http02")]}
    )
    report = WorkflowValidator(_policy()).validate(ir)
    assert not report.ok
    assert "WORKFLOW_GRAPH_CYCLE" in report.errors


def test_orphaned_step_is_rejected():
    ir = sample_ir(domain=DOMAIN)
    orphan = WorkflowIRStep(
        step_id="s_orph99", primitive=Primitive.MAP_FIELDS, operation="noop",
        effects=[WorkflowStepEffect.READ], action_class=ActionClass.A1, timeout_ms=1000,
        retry_class=RetryClass.IDEMPOTENT, max_attempts=1,
    )
    report = WorkflowValidator(_policy()).validate(
        ir.model_copy(update={"steps": [*ir.steps, orphan]})
    )
    assert not report.ok
    assert any("ORPHANED_STEP" in e for e in report.errors)


def test_duplicate_step_ids_rejected():
    ir = sample_ir(domain=DOMAIN)
    report = WorkflowValidator(_policy()).validate(
        ir.model_copy(update={"steps": [*ir.steps, ir.steps[1]]})
    )
    assert not report.ok
    assert any("DUPLICATE_STEP_ID" in e for e in report.errors)


def test_unbound_variable_rejected():
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[2] = steps[2].model_copy(update={"input_bindings": {"payload": "$never_defined"}})
    report = WorkflowValidator(_policy()).validate(ir.model_copy(update={"steps": steps}))
    assert not report.ok
    assert any("UNBOUND_VARIABLE" in e for e in report.errors)


def test_financial_effect_is_prohibited():
    """§145 — FINANCIAL and AUTHORITY writes never compile. VATI owns those."""
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[2] = steps[2].model_copy(update={"effects": [WorkflowStepEffect.FINANCIAL]})
    report = WorkflowValidator(_policy()).validate(ir.model_copy(update={"steps": steps}))
    assert not report.ok
    assert any("PROHIBITED_EFFECT" in e for e in report.errors)


def test_authority_effect_is_prohibited():
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[2] = steps[2].model_copy(update={"effects": [WorkflowStepEffect.AUTHORITY]})
    report = WorkflowValidator(_policy()).validate(ir.model_copy(update={"steps": steps}))
    assert not report.ok
    assert any("PROHIBITED_EFFECT" in e for e in report.errors)


def test_a5_step_makes_workflow_prohibited():
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[2] = steps[2].model_copy(update={"action_class": ActionClass.A5})
    report = WorkflowValidator(_policy()).validate(ir.model_copy(update={"steps": steps}))
    assert not report.ok
    assert "PROHIBITED_WORKFLOW" in report.errors or any(
        "PROHIBITED_WORKFLOW" in e for e in report.errors
    )


def test_mutation_without_verifier_rejected():
    """§40 — a consequential operation with no postcondition cannot be admitted."""
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[2] = steps[2].model_copy(update={"postcondition": None})
    report = WorkflowValidator(_policy()).validate(ir.model_copy(update={"steps": steps}))
    assert not report.ok
    assert any("CONSEQUENTIAL_STEP_WITHOUT_VERIFIER" in e for e in report.errors)


def test_non_idempotent_step_may_not_retry():
    """§79 — retry discipline."""
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[2] = steps[2].model_copy(
        update={"retry_class": RetryClass.NON_IDEMPOTENT, "max_attempts": 3}
    )
    report = WorkflowValidator(_policy()).validate(ir.model_copy(update={"steps": steps}))
    assert not report.ok
    assert any("NON_IDEMPOTENT_STEP_RETRIED" in e for e in report.errors)


def test_mutation_marked_blindly_idempotent_rejected():
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[2] = steps[2].model_copy(
        update={"retry_class": RetryClass.IDEMPOTENT, "idempotency_key_expr": None}
    )
    report = WorkflowValidator(_policy()).validate(ir.model_copy(update={"steps": steps}))
    assert not report.ok
    assert any("MUTATION_MARKED_BLINDLY_IDEMPOTENT" in e for e in report.errors)


def test_undeclared_credential_rejected():
    ir = sample_ir(domain=DOMAIN).model_copy(update={"credential_requirements": []})
    report = WorkflowValidator(_policy()).validate(ir)
    assert not report.ok
    assert any("UNDECLARED_CREDENTIAL" in e for e in report.errors)


def test_workflow_exceeding_step_limit_rejected():
    """config/automation/policy.yaml: max_steps = 40."""
    ir = sample_ir(domain=DOMAIN)
    extra = [
        ir.steps[0].model_copy(update={"step_id": f"s_pad{i:03d}", "primitive": Primitive.MAP_FIELDS})
        for i in range(45)
    ]
    report = WorkflowValidator(_policy()).validate(ir.model_copy(update={"steps": extra}))
    assert not report.ok
    assert any("WORKFLOW_TOO_LARGE" in e for e in report.errors)


def test_validate_or_raise_raises():
    with pytest.raises(PolicyError):
        WorkflowValidator(policy_with_domains()).validate_or_raise(sample_ir(domain=DOMAIN))


# ------------------------------------------------------------------- compiler


def test_same_ir_compiles_to_same_semantic_digest():
    """§263 — determinism is what makes drift detectable."""
    compiler = AutomationCompiler(_policy())
    first = compiler.compile(sample_ir(domain=DOMAIN), credential_ids=CREDS)
    second = compiler.compile(sample_ir(domain=DOMAIN), credential_ids=CREDS)
    assert first.semantic_digest == second.semantic_digest


def test_canvas_position_does_not_affect_semantic_digest():
    """§150 — moving a node in the editor is not logic drift."""
    compiler = AutomationCompiler(_policy())
    compiled = compiler.compile(sample_ir(domain=DOMAIN), credential_ids=CREDS)
    assert all("position" not in node for node in compiled.semantic_graph["nodes"])
    assert all("position" in node for node in compiled.n8n_graph["nodes"])
    mutated = {**compiled.n8n_graph}
    mutated["nodes"] = [{**n, "position": [999, 999]} for n in compiled.n8n_graph["nodes"]]
    assert digest(compiled.semantic_graph) == compiled.semantic_digest
    assert digest(mutated) != compiled.full_digest


def test_node_names_are_stable_and_ordinal():
    """§149 — <ordinal:03d>_<primitive>_<suffix>."""
    compiled = AutomationCompiler(_policy()).compile(sample_ir(domain=DOMAIN), credential_ids=CREDS)
    names = [node["name"] for node in compiled.n8n_graph["nodes"]]
    assert names == ["010_SCHEDULE_TRIGGER_ig01", "020_HTTP_GET_tp02", "030_VAN_EVIDENCE_id03"]


def test_credentials_compile_to_identifier_never_value():
    """§46 — the graph carries an n8n credential id, not a secret."""
    compiled = AutomationCompiler(_policy()).compile(sample_ir(domain=DOMAIN), credential_ids=CREDS)
    http_node = next(n for n in compiled.n8n_graph["nodes"] if n["name"].startswith("020_"))
    assert http_node["credentials"]["vanConnector"]["id"] == "cred_17"
    assert "secret" not in canonical_json(compiled.n8n_graph).decode().lower()


def test_unresolved_credential_alias_refuses_to_compile():
    with pytest.raises(PolicyError, match="unresolved_credential_alias"):
        AutomationCompiler(_policy()).compile(sample_ir(domain=DOMAIN), credential_ids={})


def test_execution_history_is_not_van_evidence_archive():
    """§48 — n8n keeps no successful execution payloads."""
    compiled = AutomationCompiler(_policy()).compile(sample_ir(domain=DOMAIN), credential_ids=CREDS)
    assert compiled.n8n_graph["settings"]["saveDataSuccessExecution"] == "none"


def test_workflow_timeout_is_always_set():
    """§40 — a missing timeout is a rejection; the compiler always emits one."""
    compiled = AutomationCompiler(_policy()).compile(sample_ir(domain=DOMAIN), credential_ids=CREDS)
    assert compiled.n8n_graph["settings"]["executionTimeout"] > 0


def test_webhook_trigger_compiles_with_authentication():
    """§208 — never an open webhook."""
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[0] = steps[0].model_copy(
        update={"primitive": Primitive.WEBHOOK_TRIGGER, "input_bindings": {"path": "van/x"}}
    )
    compiled = AutomationCompiler(_policy()).compile(
        ir.model_copy(update={"steps": steps}), credential_ids=CREDS
    )
    node = next(n for n in compiled.n8n_graph["nodes"] if n["name"].startswith("010_"))
    assert node["parameters"]["authentication"] == "headerAuth"


def test_disallowed_http_method_refused():
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[1] = steps[1].model_copy(
        update={
            "primitive": Primitive.HTTP_REQUEST,
            "input_bindings": {"url": f"https://{DOMAIN}/x", "method": "TRACE"},
        }
    )
    with pytest.raises(PolicyError, match="http_method_not_permitted"):
        AutomationCompiler(_policy()).compile(
            ir.model_copy(update={"steps": steps}), credential_ids=CREDS
        )


# ------------------------------------------------------------------- registry


async def test_admitted_artifact_is_immutable(tmp_path):
    """§151 — never overwrite an admitted artifact row; a repair is a new version."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability())
    artifact = await registry.record_artifact(sample_artifact())
    with pytest.raises(RegistryError, match="immutable"):
        await registry.record_artifact(
            artifact.model_copy(update={"compiled_semantic_digest": "sha256:tampered"})
        )


async def test_lifecycle_cannot_skip_validation(tmp_path):
    """§155 — PROPOSED may not jump straight to ADMITTED."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(
        sample_capability(lifecycle=WorkflowLifecycle.PROPOSED)
    )
    await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.PROPOSED, n8n_workflow_id=None)
    )
    with pytest.raises(RegistryError, match="illegal_transition"):
        await registry.transition(
            "wfart_wfcap_statements_1",
            expected=WorkflowLifecycle.PROPOSED,
            target=WorkflowLifecycle.ADMITTED,
        )


async def test_full_admission_path(tmp_path):
    """§155 — PROPOSED → QUARANTINED → VALIDATED → ADMITTED → HOT."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability(lifecycle=WorkflowLifecycle.PROPOSED))
    await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.PROPOSED, n8n_workflow_id=None)
    )
    aid = "wfart_wfcap_statements_1"
    for expected, target in (
        (WorkflowLifecycle.PROPOSED, WorkflowLifecycle.QUARANTINED),
        (WorkflowLifecycle.QUARANTINED, WorkflowLifecycle.VALIDATED),
        (WorkflowLifecycle.VALIDATED, WorkflowLifecycle.ADMITTED),
        (WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT),
    ):
        artifact = await registry.transition(aid, expected=expected, target=target)
        assert artifact.lifecycle_state is target
    assert artifact.admitted_at_ms is not None


async def test_transition_precondition_is_enforced(tmp_path):
    """§154 — no partial admission; the guard is the expected current state."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability(lifecycle=WorkflowLifecycle.PROPOSED))
    await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.PROPOSED, n8n_workflow_id=None)
    )
    with pytest.raises(RegistryError, match="precondition_failed"):
        await registry.transition(
            "wfart_wfcap_statements_1",
            expected=WorkflowLifecycle.VALIDATED,
            target=WorkflowLifecycle.ADMITTED,
        )


async def test_repair_creates_a_new_version(tmp_path):
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability())
    await registry.record_artifact(sample_artifact(version=1))
    assert await registry.next_version("wfcap_statements") == 2
    await registry.record_artifact(
        sample_artifact(version=2, lifecycle=WorkflowLifecycle.PROPOSED, n8n_workflow_id=None)
    )
    assert await registry.next_version("wfcap_statements") == 3


# ------------------------------------------------------------------ hot index


def test_hot_index_lookup_is_wording_independent():
    """§§26, 170 — natural phrasing maps to one capability."""
    from van_gateway.automation.models import IntentSignature

    index = HotWorkflowIndex()
    signature = IntentSignature(
        goal_class="BROKER_STATEMENT_COLLECTION", source_class="EMAIL",
        destination_class="VATI", mutation_class=ActionClass.A2,
    )
    index.publish(signature, "wfcap_statements", 3, "n8n-42")
    looser = IntentSignature(
        goal_class="broker statement collection", source_class="email",
        destination_class="vati", mutation_class=ActionClass.A2,
    )
    assert index.lookup(looser) == ("wfcap_statements", 3, "n8n-42")


def test_hot_index_withdraw_removes_capability():
    """§77 — a degraded capability stops being HOT."""
    from van_gateway.automation.models import IntentSignature

    index = HotWorkflowIndex()
    signature = IntentSignature(
        goal_class="G", source_class="S", destination_class="D", mutation_class=ActionClass.A1
    )
    index.publish(signature, "cap", 1, "ref")
    index.withdraw("cap")
    assert index.lookup(signature) is None
    assert index.size == 0


async def test_hot_index_rebuilds_from_durable_state(tmp_path):
    """§273 — startup reconciliation."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability(lifecycle=WorkflowLifecycle.HOT))
    await registry.record_artifact(sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED))
    index = HotWorkflowIndex()
    assert await index.rebuild(store) == 1
