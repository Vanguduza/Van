"""A supported operation cannot lower its real consequence by declaring metadata."""
import pytest

from conftest_automation import policy_with_domains
from van_gateway.automation.models import Primitive, WorkflowIR, WorkflowIRStep
from van_gateway.automation.primitive_policy import (
    SUPPORTED_OPERATIONS, PrimitiveSemanticError, assert_primitive_semantics, primitive_semantics,
)
from van_gateway.automation.validator import WorkflowValidator
from van_gateway.models import ActionClass


WRITES = [
    (Primitive.VAN_EVENT, "emit_attention", "NOTIFY"),
    (Primitive.VAN_EVENT, "emit_external_event", "NOTIFY"),
    (Primitive.VAN_EVENT, "emit_event", "NOTIFY"),
    (Primitive.VAN_EVIDENCE, "seal_artifact", "WRITE"),
    (Primitive.VAN_EVIDENCE, "seal_evidence", "WRITE"),
    (Primitive.STORE_TRANSIENT_FILE, "ingest", "WRITE"),
    (Primitive.STORE_TRANSIENT_FILE, "store_transient_file", "WRITE"),
    (Primitive.DELETE_TRANSIENT_FILE, "release", "DELETE"),
    (Primitive.DELETE_TRANSIENT_FILE, "delete_transient_file", "DELETE"),
]
NETWORK = [
    (primitive, operation)
    for primitive in (Primitive.HTTP_GET, Primitive.HTTP_REQUEST)
    for operation in sorted(SUPPORTED_OPERATIONS[primitive])
    if operation not in {"write_json", "delete_resource"}
]
LOCAL = [
    (primitive, operation)
    for primitive in (Primitive.HASH, Primitive.DEDUPE, Primitive.FILTER, Primitive.MAP_FIELDS)
    for operation in sorted(SUPPORTED_OPERATIONS[primitive])
]


def step(primitive, operation, *, action_class="A1", effects=None, postcondition=None, **extra):
    predicate = {"op": "EQ", "left": {"kind": "LITERAL", "value": 1}, "right": {"kind": "LITERAL", "value": 1}}
    bindings = ({"payload": {}, "predicate": predicate} if operation == "evaluate_predicate" else
                {"payload": {}, "fields": {"fixed": {"kind": "LITERAL", "value": 1}}} if operation == "map_fields" else {})
    return WorkflowIRStep(
        step_id="target", primitive=primitive, operation=operation,
        input_bindings=bindings, effects=effects or ["READ"], action_class=action_class,
        external_domain="reports.example.com" if primitive in (Primitive.HTTP_GET, Primitive.HTTP_REQUEST) else None,
        timeout_ms=1000, retry_class="NEVER_RETRY", max_attempts=1,
        postcondition=postcondition, **extra,
    )


def validate(target):
    domains = [target.external_domain] if target.external_domain else []
    ir = WorkflowIR(
        ir_id="semantic-authority-test", family="test", semantic_goal="Bounded operation",
        version=1, trigger={"kind": "INVOKE"}, steps=[target], external_domains=domains,
        action_class=target.action_class, policy_version="test", compiler_version="test",
        verifier={"kind": "READ_BACK"} if target.mutates else {},
    )
    return WorkflowValidator(policy_with_domains(*domains)).validate(ir)


@pytest.mark.parametrize("primitive,operation,effect", WRITES)
@pytest.mark.parametrize("declared_class", ["A1", "A2"])
def test_declared_read_class_cannot_authorize_real_write(primitive, operation, effect, declared_class):
    target = step(primitive, operation, action_class=declared_class)
    with pytest.raises(PrimitiveSemanticError, match="ACTION_CLASS_UNDERDECLARED"):
        assert_primitive_semantics(target)
    report = validate(target)
    assert not report.ok
    assert report.derived_action_class == "A3"
    assert any("PRIMITIVE_ACTION_CLASS_UNDERDECLARED" in error for error in report.errors)


@pytest.mark.parametrize("primitive,operation", NETWORK)
def test_external_read_cannot_be_classified_as_deterministic_local(primitive, operation):
    target = step(primitive, operation)
    report = validate(target)
    assert not report.ok
    assert report.derived_action_class == "A2"
    assert any("required=A2" in error for error in report.errors)


@pytest.mark.parametrize("primitive,operation,effect", WRITES)
def test_consequential_class_alone_cannot_hide_effect_or_omit_readback(primitive, operation, effect):
    target = step(primitive, operation, action_class="A3")
    with pytest.raises(PrimitiveSemanticError, match=f"EFFECT_UNDERDECLARED.*required={effect}"):
        assert_primitive_semantics(target)
    target = target.model_copy(update={"effects": [effect]})
    with pytest.raises(PrimitiveSemanticError, match="MUTATION_POSTCONDITION_REQUIRED"):
        assert_primitive_semantics(target)


@pytest.mark.parametrize("postcondition", [
    {}, {"kind": "UNKNOWN"}, {"kind": "READ_BACK", "expected": True},
    {"kind": "STATE_PREDICATE", "predicate": {"arbitrary": True}},
    {"kind": "READ_BACK", "field": ""}, {"kind": "READ_BACK", "field": False},
])
def test_missing_or_unsupported_mutation_readback_fails_closed(postcondition):
    target = step(Primitive.STORE_TRANSIENT_FILE, "ingest", action_class="A3",
                  effects=["WRITE"], postcondition=postcondition)
    with pytest.raises(PrimitiveSemanticError, match="MUTATION_POSTCONDITION"):
        assert_primitive_semantics(target)


@pytest.mark.parametrize("primitive,operation,effect", WRITES)
def test_admitted_mutation_metadata_remains_valid(primitive, operation, effect):
    target = step(primitive, operation, action_class="A3", effects=[effect],
                  postcondition={"kind": "READ_BACK", "field": "receipt"})
    semantics = assert_primitive_semantics(target)
    assert semantics.minimum_action_class == ActionClass.A3
    assert semantics.required_effect.value == effect
    assert validate(target).ok


@pytest.mark.parametrize("primitive,operation", NETWORK)
def test_network_authority_requires_declared_network_effect(primitive, operation):
    target = step(primitive, operation, action_class="A2")
    with pytest.raises(PrimitiveSemanticError, match="EFFECT_UNDERDECLARED.*NETWORK_READ"):
        assert_primitive_semantics(target)
    target = target.model_copy(update={"effects": ["NETWORK_READ"]})
    assert validate(target).ok


@pytest.mark.parametrize("primitive,operation", LOCAL)
def test_local_deterministic_operations_keep_read_authority(primitive, operation):
    target = step(primitive, operation)
    assert assert_primitive_semantics(target).minimum_action_class == ActionClass.A1
    if operation == "evaluate_predicate":
        assert "BRANCH_OUTPUT_UNCONNECTED:target" in validate(target).errors
    else:
        assert validate(target).ok


def test_helper_does_not_silently_ignore_declared_guard_or_downgrade_class():
    target = step(Primitive.STORE_TRANSIENT_FILE, "ingest", action_class="A4", effects=["WRITE"],
                  postcondition={"kind": "READ_BACK"})
    assert assert_primitive_semantics(target).minimum_action_class == ActionClass.A3
    assert target.action_class == ActionClass.A4
    with pytest.raises(PrimitiveSemanticError, match="DSL_PREDICATE_INVALID"):
        assert_primitive_semantics(target.model_copy(update={"precondition": {"authorized": True}}))


def test_unknown_operation_remains_candidate_and_never_becomes_supported_effect():
    target = step(Primitive.WAIT, "wait")
    assert primitive_semantics(target) is None
    assert validate(target).ok
    with pytest.raises(PrimitiveSemanticError, match="OPERATION_UNSUPPORTED"):
        assert_primitive_semantics(target)
