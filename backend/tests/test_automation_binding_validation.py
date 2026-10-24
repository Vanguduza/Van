"""Only declared inputs and observed ancestor outputs form runtime references."""
import json
from types import SimpleNamespace

import pytest

from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.models import Primitive, WorkflowIR, WorkflowIREdge, WorkflowIRStep
from van_gateway.automation.validator import WorkflowValidator
from van_gateway.automation.worker_runtime import AutomationWorkerRuntime
from van_gateway.automation.canonical import digest


def step(identifier, bindings, output=None):
    return WorkflowIRStep(
        step_id=identifier, primitive=Primitive.HASH, operation="hash", input_bindings=bindings,
        output_name=output, effects=["READ"], action_class="A1", timeout_ms=1000,
        retry_class="IDEMPOTENT", max_attempts=1,
    )


def workflow(bindings, *, reverse=False):
    first = step("first", {"payload": {"literal": 1}}, "raw")
    second = step("second", bindings, "hashed")
    return WorkflowIR(
        ir_id="binding-test", family="test", semantic_goal="Observe exact values", version=1,
        trigger={"kind": "INVOKE"}, inputs_schema={"properties": {"document": {"type": "object"}}},
        steps=[second, first] if reverse else [first, second],
        edges=[WorkflowIREdge(from_step="first", to_step="second")], action_class="A1",
        policy_version="test", compiler_version="test",
    )


@pytest.mark.parametrize("reference", [
    "$input", "$input.document", "$input.document.amount", "{{ input.document.amount }}",
    "$steps.first", "$steps.first.primary", "{{ steps.first.primary }}",
    "$raw", "$raw.primary", "{{ raw.primary }}",
])
@pytest.mark.parametrize("reverse", [False, True])
def test_runtime_namespaces_and_shorthand_follow_real_ancestor_edges(reference, reverse):
    ir = workflow({"payload": {"nested": [reference]}}, reverse=reverse)
    report = WorkflowValidator().validate(ir)
    assert report.ok, report.errors
    compiled = AutomationCompiler().compile(
        ir, subworkflow_ids={"HASH": "real_hash_1"}, worker_credential_id="real_worker_1",
        worker_endpoint="https://10.0.0.1/v1/automation/worker/step", run_path="van-run/binding-test",
    )
    assert compiled.deployable, compiled.readiness_errors


@pytest.mark.parametrize("reference,error", [
    ("$input.undeclared", "UNBOUND_INPUT_FIELD"),
    ("{{ input.undeclared }}", "UNBOUND_INPUT_FIELD"),
    ("$steps.absent.primary", "UNBOUND_STEP_REFERENCE"),
    ("$steps", "UNBOUND_STEP_REFERENCE"),
    ("$steps.second.primary", "BINDING_SOURCE_NOT_ANCESTOR"),
    ("$hashed.primary", "BINDING_SOURCE_NOT_ANCESTOR"),
    ("$never_defined", "UNBOUND_VARIABLE"),
    ("$input.document[0]", "UNSUPPORTED_BINDING_EXPRESSION"),
    ("$input.document + 1", "UNSUPPORTED_BINDING_EXPRESSION"),
    ("{{ input.document.toString() }}", "UNSUPPORTED_BINDING_EXPRESSION"),
    ("{{input.document", "UNSUPPORTED_BINDING_EXPRESSION"),
    ("$input..document", "UNSUPPORTED_BINDING_EXPRESSION"),
])
def test_nested_invalid_reference_never_reaches_admission(reference, error):
    report = WorkflowValidator().validate(workflow({"payload": [{"value": reference}]}))
    assert not report.ok
    assert any(error in item for item in report.errors), report.errors


def test_sibling_output_is_not_available_even_if_its_step_was_listed_first():
    ir = workflow({"payload": "$raw.primary"})
    root = step("root", {"payload": {}})
    ir = ir.model_copy(update={
        "steps": [root, *ir.steps],
        "edges": [WorkflowIREdge(from_step="root", to_step="first"),
                  WorkflowIREdge(from_step="root", to_step="second")],
    })
    report = WorkflowValidator().validate(ir)
    assert not report.ok
    assert "BINDING_SOURCE_NOT_ANCESTOR:second:first" in report.errors


def test_duplicate_output_alias_cannot_choose_a_different_source_by_list_order():
    ir = workflow({"payload": "$raw.primary"})
    ir = ir.model_copy(update={"steps": [ir.steps[0], ir.steps[1].model_copy(update={"output_name": "raw"})]})
    assert "DUPLICATE_OUTPUT_NAME:raw" in WorkflowValidator().validate(ir).errors


def test_declared_variable_is_not_an_arbitrary_expression_runtime():
    ir = workflow({"payload": "$custom"}).model_copy(update={"variables": {"custom": 42}})
    assert "UNBOUND_VARIABLE:second:custom" in WorkflowValidator().validate(ir).errors


@pytest.mark.asyncio
@pytest.mark.parametrize("reference,expected", [
    ("$input.document.amount", "12.34"),
    ("{{ input.document.amount }}", "12.34"),
    ("$steps.first.primary", "sha256:actual"),
    ("{{ steps.first.primary }}", "sha256:actual"),
    ("$raw.primary", "sha256:actual"),
])
async def test_validated_bindings_resolve_to_same_actual_callback_values(reference, expected):
    ir = workflow({"payload": reference}, reverse=True)
    assert WorkflowValidator().validate(ir).ok

    class RecordedOutputs:
        async def fetchone(self, query, parameters):
            assert parameters == ("run", "first")
            return {"result_json": json.dumps({"primary": "sha256:actual"}), "result_digest": digest({"primary": "sha256:actual"})}

    worker = AutomationWorkerRuntime.__new__(AutomationWorkerRuntime)
    worker.store = RecordedOutputs()
    resolved = await worker._resolve(
        {"payload": reference}, SimpleNamespace(run_id="run", input={"document": {"amount": "12.34"}}),
        ir, "second",
    )
    assert resolved == {"payload": expected}
