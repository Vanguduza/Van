"""Typed automation evaluates bounded data and rejects malformed graph contracts."""
from __future__ import annotations

import math

import pytest

from van_gateway.automation.dsl import (
    DslError, bounded_json, branches, evaluate, map_fields, pure_result,
    select_branch, validate_predicate, validate_value, value_of,
)
from van_gateway.automation.models import WorkflowIR, WorkflowIREdge, WorkflowIRStep
from van_gateway.automation.primitive_policy import (
    PrimitiveSemanticError, assert_primitive_semantics, validate_branch_graph,
)
from van_gateway.automation.validator import WorkflowValidator


def literal(value):
    return {"kind": "LITERAL", "value": value}


def path(value):
    return {"kind": "PATH", "path": value}


def compare(op, left, right):
    return {"op": op, "left": literal(left), "right": literal(right)}


def ready_predicate():
    return {"op": "EQ", "left": path("payload.status"), "right": literal("ready")}


def step(identifier, primitive="HASH", operation="hash", bindings=None):
    return WorkflowIRStep(
        step_id=identifier, primitive=primitive, operation=operation,
        input_bindings=bindings if bindings is not None else {"payload": {}},
        effects=["READ"], action_class="A1", timeout_ms=1000,
        retry_class="NEVER_RETRY", max_attempts=1,
    )


def selector_ir(selector=None, edges=None):
    selector = selector or step("select", "FILTER", "evaluate_predicate", {
        "payload": {"status": "ready"}, "predicate": ready_predicate(),
    })
    return WorkflowIR(
        ir_id="typed-branch-test", family="test", semantic_goal="Inspect a bounded branch",
        version=1, trigger={"kind": "INVOKE"},
        steps=[selector, step("yes"), step("no"), step("joined")],
        edges=edges if edges is not None else [
            WorkflowIREdge(from_step="select", to_step="yes", branch="true"),
            WorkflowIREdge(from_step="select", to_step="no", branch="false"),
            WorkflowIREdge(from_step="yes", to_step="joined"),
            WorkflowIREdge(from_step="no", to_step="joined"),
        ],
        action_class="A1", policy_version="test", compiler_version="test",
        verifier={"kind": "READ_BACK", "field": "primary"},
    )


@pytest.mark.parametrize("op,left,right,expected", [
    ("EQ", True, 1, False), ("NE", True, 1, True),
    ("EQ", 1, 1.0, False), ("EQ", {"b": 2, "a": 1}, {"a": 1, "b": 2}, True),
    ("EQ", [1, 2], [2, 1], False),
    ("LT", 1, 2.0, True), ("LTE", 2.0, 2, True),
    ("GT", 2.0, 1, True), ("GTE", 2, 2.0, True),
    ("IN", True, [1], False), ("IN", True, [1, True], True),
    ("CONTAINS", [1], True, False), ("CONTAINS", [1, True], True, True),
    ("CONTAINS", "sealed callback", "callback", True),
])
def test_predicates_use_typed_data_comparisons(op, left, right, expected):
    assert evaluate(compare(op, left, right), {}) is expected


@pytest.mark.parametrize("op,left,right", [
    ("LT", True, 2), ("GT", "2", 1), ("LTE", None, 0),
    ("IN", 1, "123"), ("IN", 1, list(range(257))),
    ("CONTAINS", {}, "key"), ("CONTAINS", "123", 1),
    ("CONTAINS", list(range(257)), 1),
])
def test_invalid_comparison_types_refuse_instead_of_coercing(op, left, right):
    with pytest.raises(DslError, match="TYPE_INVALID"):
        evaluate(compare(op, left, right), {})


def test_exists_checks_presence_and_missing_operands_cannot_hide_in_short_circuit():
    assert evaluate({"op": "EXISTS", "value": path("payload.present")}, {"payload": {"present": None}})
    assert not evaluate({"op": "EXISTS", "value": path("payload.absent")}, {"payload": {}})
    for op, constant in [("ANY", True), ("ALL", False)]:
        predicate = {"op": op, "args": [compare("EQ", constant, True), ready_predicate()]}
        with pytest.raises(DslError, match="PATH_MISSING"):
            evaluate(predicate, {"payload": {}})


@pytest.mark.parametrize("spec", [
    None, "payload.status", {"kind": "EXPRESSION", "code": "return true"},
    {"kind": "PATH", "path": "payload.status", "fallback": True},
    {"kind": "LITERAL"}, {"kind": "LITERAL", "value": True, "path": "x"},
])
def test_value_specs_have_closed_shapes(spec):
    with pytest.raises(DslError, match="VALUE_INVALID"):
        validate_value(spec)


@pytest.mark.parametrize("reference", [
    "", "payload..status", "payload[0]", "payload['status']",
    "$payload.status", "{{ payload.status }}", "payload.status; process.exit()",
    "payload." + "a" * 257,
])
def test_path_specs_cannot_access_expressions_attributes_or_indices(reference):
    with pytest.raises(DslError, match="PATH_INVALID"):
        value_of(path(reference), {"payload": {"status": "ready"}})


def test_literal_code_and_attribute_names_remain_inert_dictionary_data():
    code = "$input.secret; __import__('os').system('false')"
    assert value_of(literal(code), {}) == code
    assert value_of(path("payload.__class__"), {"payload": {"__class__": code}}) == code
    with pytest.raises(DslError, match="PATH_MISSING"):
        value_of(path("payload.__class__"), {"payload": "text"})


@pytest.mark.parametrize("predicate", [
    None, [], {"op": "PYTHON", "code": "True"},
    {"op": []}, {"op": {}}, {"op": 1},
    {"op": "ALL", "args": []}, {"op": "ANY", "args": [compare("EQ", 1, 1)] * 17},
    {"op": "NOT", "arg": compare("EQ", 1, 1), "extra": True},
    {"op": "EXISTS", "value": literal(True)},
    {"op": "EQ", "left": literal(1)},
    {"op": "EQ", "left": literal(1), "right": literal(1), "extra": True},
])
def test_malformed_predicates_raise_typed_refusal(predicate):
    with pytest.raises(DslError):
        validate_predicate(predicate)


def test_predicate_depth_and_node_count_are_bounded_before_evaluation():
    predicate = compare("EQ", 1, 1)
    for _ in range(8):
        predicate = {"op": "NOT", "arg": predicate}
    validate_predicate(predicate)
    with pytest.raises(DslError, match="PREDICATE_LIMIT"):
        validate_predicate({"op": "NOT", "arg": predicate})
    too_many = {"op": "ALL", "args": [{"op": "ANY", "args": [compare("EQ", 1, 1)] * 16}] * 4}
    with pytest.raises(DslError, match="PREDICATE_LIMIT"):
        evaluate(too_many, {})


@pytest.mark.parametrize("value", [
    math.inf, math.nan, (1, 2), {1: "non-string key"}, {"a" * 129: True},
])
def test_data_rejects_non_json_nonfinite_or_unbounded_keys(value):
    with pytest.raises(DslError, match="DATA_"):
        bounded_json(value)


def test_data_depth_item_count_and_encoded_size_are_bounded():
    nested = None
    for _ in range(17):
        nested = [nested]
    for value in [nested, [None] * 8192, "é" * (1024 * 1024)]:
        with pytest.raises(DslError, match="DATA_LIMIT"):
            bounded_json(value)


def test_mapping_reads_declared_paths_and_preserves_literal_reference_text():
    result = map_fields({"invoice": {"amount": 10}}, {
        "amount": path("payload.invoice.amount"), "inert": literal("$steps.other.secret"),
    })
    assert result == {"amount": 10, "inert": "$steps.other.secret"}
    with pytest.raises(DslError, match="PATH_MISSING"):
        map_fields({}, {"amount": path("payload.invoice.amount")})


@pytest.mark.parametrize("fields", [
    {}, {"x" + str(index): literal(index) for index in range(65)},
    {"nested.target": literal(1)}, {"": literal(1)}, {"a" * 129: literal(1)},
])
def test_mapping_shape_and_field_names_are_bounded(fields):
    with pytest.raises(DslError, match="MAPPING_"):
        map_fields({}, fields)


def test_malformed_mapping_target_is_refused_before_admission():
    target = step("mapping", "MAP_FIELDS", "map_fields", {
        "payload": {}, "fields": {"nested.target": literal(1)},
    })
    with pytest.raises(PrimitiveSemanticError, match="MAPPING_TARGET_INVALID"):
        assert_primitive_semantics(target)


def test_switch_records_all_evaluated_cases_and_selects_first_match():
    value = {"payload": {"status": "ready"}, "cases": [
        {"branch": "first", "predicate": ready_predicate()},
        {"branch": "second", "predicate": compare("EQ", 1, 1)},
    ], "default_branch": "fallback"}
    result = select_branch(value)
    assert result["selected_branch"] == "first"
    assert result["matched_case"] == 0
    assert result["predicate_results"] == [True, True]
    value["payload"]["status"] = "pending"
    value["cases"][1]["predicate"] = compare("EQ", 1, 2)
    assert select_branch(value)["selected_branch"] == "fallback"
    assert select_branch(value)["matched_case"] is None


@pytest.mark.parametrize("cases,default", [
    ([], "fallback"), ([{"branch": "same", "predicate": ready_predicate()}], "same"),
    ([{"branch": "bad label", "predicate": ready_predicate()}], "fallback"),
    ([{"branch": "case", "predicate": ready_predicate(), "code": "True"}], "fallback"),
    ([{"branch": str(index), "predicate": ready_predicate()} for index in range(11)], "fallback"),
])
def test_switch_requires_unique_closed_bounded_case_labels(cases, default):
    with pytest.raises(DslError):
        branches({"payload": {}, "cases": cases, "default_branch": default})


def test_merge_handles_explicit_skipped_source_without_overwriting_fields():
    assert pure_result("MERGE", "merge_objects", {"sources": [None, {"one": 1}, {"two": 2}]})["payload"] == {"one": 1, "two": 2}
    with pytest.raises(DslError, match="MERGE_CONFLICT"):
        pure_result("MERGE", "merge_objects", {"sources": [{"same": 1}, {"same": 2}]})
    for sources in [[], [None] * 17, "expression"]:
        with pytest.raises(DslError, match="MERGE_INVALID"):
            pure_result("MERGE", "merge_objects", {"sources": sources})


def test_branch_graph_accepts_closed_selector_and_explicit_join():
    ir = selector_ir()
    validate_branch_graph(ir)
    report = WorkflowValidator().validate(ir)
    assert report.ok, report.errors


@pytest.mark.parametrize("changed,error", [
    ([WorkflowIREdge(from_step="select", to_step="yes", branch="wrong")], "BRANCH_LABEL_INVALID"),
    ([WorkflowIREdge(from_step="select", to_step="yes")], "BRANCH_LABEL_INVALID"),
    ([WorkflowIREdge(from_step="yes", to_step="joined", branch="true")], "BRANCH_SOURCE_NOT_SELECTOR"),
])
def test_branch_graph_rejects_unsealed_labels_and_nonselector_sources(changed, error):
    with pytest.raises(PrimitiveSemanticError, match=error):
        validate_branch_graph(selector_ir(edges=changed))


def test_branch_graph_rejects_duplicate_edges_and_unconnected_case():
    ir = selector_ir()
    with pytest.raises(PrimitiveSemanticError, match="DUPLICATE_GRAPH_EDGE"):
        validate_branch_graph(ir.model_copy(update={"edges": [*ir.edges, ir.edges[0]]}))
    with pytest.raises(PrimitiveSemanticError, match="BRANCH_OUTPUT_UNCONNECTED"):
        validate_branch_graph(ir.model_copy(update={"edges": [edge for edge in ir.edges if edge.branch != "false"]}))


def test_malformed_switch_operator_becomes_validation_refusal():
    selector = step("select", "SWITCH", "select_branch", {
        "payload": {}, "cases": [{"branch": "true", "predicate": {"op": []}}],
        "default_branch": "false",
    })
    report = WorkflowValidator().validate(selector_ir(selector))
    assert not report.ok
    assert any("DSL_PREDICATE" in error for error in report.errors)

