"""Consequences of the closed gateway automation operation set.

IR metadata describes authority; it cannot change what a supported operation
actually does. The validator, compiler and callback share this policy so a
read declaration cannot acquire a write or an external-read capability.
"""
from __future__ import annotations

from dataclasses import dataclass

from van_gateway.automation.models import (
    MUTATING_EFFECTS, RANK, Primitive, WorkflowIRStep, WorkflowStepEffect,
)
from van_gateway.models import ActionClass
from van_gateway.automation.dsl import DslError, branches, validate_predicate, validate_mapping, validate_readback


SUPPORTED_OPERATIONS: dict[Primitive, frozenset[str]] = {
    Primitive.HTTP_GET: frozenset({"fetch_documents", "poll_source", "fetch_resource", "get"}),
    Primitive.HTTP_REQUEST: frozenset({"get", "write_json", "delete_resource"}),
    Primitive.HASH: frozenset({"digest_documents", "hash"}),
    Primitive.DEDUPE: frozenset({"change_detect", "dedupe"}),
    Primitive.FILTER: frozenset({"validate_and_dedupe", "evaluate_predicate"}),
    Primitive.SWITCH: frozenset({"select_branch"}),
    Primitive.MAP_FIELDS: frozenset({"to_van_schema", "map_fields"}),
    Primitive.MERGE: frozenset({"merge_objects"}),
    Primitive.WAIT: frozenset({"bounded_wait"}),
    Primitive.VAN_CAPABILITY: frozenset({"reminder.create"}),
    Primitive.VAN_EVENT: frozenset({"emit_attention", "emit_external_event", "emit_event"}),
    Primitive.VAN_EVIDENCE: frozenset({"seal_artifact", "seal_evidence"}),
    Primitive.STORE_TRANSIENT_FILE: frozenset({"store_transient_file", "ingest"}),
    Primitive.DELETE_TRANSIENT_FILE: frozenset({"delete_transient_file", "release"}),
}


@dataclass(frozen=True)
class PrimitiveSemantics:
    minimum_action_class: ActionClass
    required_effect: WorkflowStepEffect


_SEMANTICS = {
    Primitive.HTTP_GET: PrimitiveSemantics(ActionClass.A2, WorkflowStepEffect.NETWORK_READ),
    Primitive.HTTP_REQUEST: PrimitiveSemantics(ActionClass.A2, WorkflowStepEffect.NETWORK_READ),
    Primitive.HASH: PrimitiveSemantics(ActionClass.A1, WorkflowStepEffect.READ),
    Primitive.DEDUPE: PrimitiveSemantics(ActionClass.A1, WorkflowStepEffect.READ),
    Primitive.FILTER: PrimitiveSemantics(ActionClass.A1, WorkflowStepEffect.READ),
    Primitive.MAP_FIELDS: PrimitiveSemantics(ActionClass.A1, WorkflowStepEffect.READ),
    Primitive.SWITCH: PrimitiveSemantics(ActionClass.A1, WorkflowStepEffect.READ),
    Primitive.MERGE: PrimitiveSemantics(ActionClass.A1, WorkflowStepEffect.READ),
    Primitive.WAIT: PrimitiveSemantics(ActionClass.A1, WorkflowStepEffect.READ),
    Primitive.VAN_CAPABILITY: PrimitiveSemantics(ActionClass.A3, WorkflowStepEffect.WRITE),
    Primitive.VAN_EVENT: PrimitiveSemantics(ActionClass.A3, WorkflowStepEffect.NOTIFY),
    Primitive.VAN_EVIDENCE: PrimitiveSemantics(ActionClass.A3, WorkflowStepEffect.WRITE),
    Primitive.STORE_TRANSIENT_FILE: PrimitiveSemantics(ActionClass.A3, WorkflowStepEffect.WRITE),
    Primitive.DELETE_TRANSIENT_FILE: PrimitiveSemantics(ActionClass.A3, WorkflowStepEffect.DELETE),
}


class PrimitiveSemanticError(ValueError):
    pass


def primitive_semantics(step: WorkflowIRStep) -> PrimitiveSemantics | None:
    """Return known runtime semantics; broader IR operations remain candidates."""
    if step.operation not in SUPPORTED_OPERATIONS.get(step.primitive, frozenset()):
        return None
    if step.primitive is Primitive.HTTP_REQUEST and step.operation in {"write_json", "delete_resource"}:
        return PrimitiveSemantics(ActionClass.A4, WorkflowStepEffect.DELETE if step.operation == "delete_resource" else WorkflowStepEffect.WRITE)
    return _SEMANTICS[step.primitive]


def assert_primitive_semantics(step: WorkflowIRStep) -> PrimitiveSemantics:
    semantics = primitive_semantics(step)
    if semantics is None:
        raise PrimitiveSemanticError(
            f"PRIMITIVE_OPERATION_UNSUPPORTED:{step.step_id}:{step.primitive.value}:{step.operation}"
        )
    if RANK[step.action_class.value] < RANK[semantics.minimum_action_class.value]:
        raise PrimitiveSemanticError(
            f"PRIMITIVE_ACTION_CLASS_UNDERDECLARED:{step.step_id}:"
            f"required={semantics.minimum_action_class.value}:declared={step.action_class.value}"
        )
    if semantics.required_effect not in step.effects:
        raise PrimitiveSemanticError(
            f"PRIMITIVE_EFFECT_UNDERDECLARED:{step.step_id}:required={semantics.required_effect.value}"
        )
    try:
        if step.precondition is not None:
            validate_predicate(step.precondition)
        value = step.input_bindings
        if step.operation == "evaluate_predicate":
            if set(value) != {"payload", "predicate"}:
                raise DslError("DSL_FILTER_INVALID")
            validate_predicate(value["predicate"])
        if step.operation == "select_branch":
            branches(value)
        if step.operation == "map_fields":
            if set(value) != {"payload", "fields"} or not isinstance(value["fields"], dict) or not 1 <= len(value["fields"]) <= 64:
                raise DslError("DSL_MAPPING_INVALID")
            validate_mapping(value["fields"])
        if step.operation == "bounded_wait":
            if set(value) != {"delay_ms"} or type(value["delay_ms"]) is not int or not 0 <= value["delay_ms"] <= min(30_000, step.timeout_ms - 1):
                raise DslError("DSL_WAIT_INVALID")
        if step.primitive is Primitive.HTTP_REQUEST and step.operation in {"write_json", "delete_resource"}:
            method = value.get("method")
            if (method not in ({"DELETE"} if step.operation == "delete_resource" else {"POST", "PUT", "PATCH"})
                    or set(value) != ({"url", "method", "readback"} if method == "DELETE" else {"url", "method", "body", "readback"})
                    or not step.credential_alias or step.max_attempts != 1):
                raise DslError("EXTERNAL_WRITE_CONTRACT_INVALID")
            readback = value["readback"]
            if not isinstance(readback, dict) or set(readback) != {"url", "predicate"}:
                raise DslError("EXTERNAL_WRITE_READBACK_REQUIRED")
            validate_readback(readback["predicate"])
            if step.postcondition != {"kind": "READ_BACK", "field": "verified", "expected": True}:
                raise DslError("EXTERNAL_WRITE_READBACK_REQUIRED")
    except (DslError, KeyError, TypeError) as exc:
        raise PrimitiveSemanticError(f"PRIMITIVE_CONTRACT_INVALID:{step.step_id}:{exc}") from exc
    if semantics.required_effect in MUTATING_EFFECTS:
        postcondition = step.postcondition
        if not postcondition:
            raise PrimitiveSemanticError(f"PRIMITIVE_MUTATION_POSTCONDITION_REQUIRED:{step.step_id}")
        if (
            postcondition.get("kind") not in {"READ_BACK", "RECEIPT", "STATE_PREDICATE"}
            or set(postcondition) - {"kind", "field", "expected"}
            or ("expected" in postcondition and "field" not in postcondition)
            or ("field" in postcondition and (
                not isinstance(postcondition["field"], str)
                or not 1 <= len(postcondition["field"]) <= 128
            ))
        ):
            raise PrimitiveSemanticError(f"PRIMITIVE_MUTATION_POSTCONDITION_UNOBSERVABLE:{step.step_id}")
    return semantics


def validate_branch_graph(ir) -> None:
    """Every selector output is named; joins settle all parents then select any live edge."""
    by_id = {step.step_id: step for step in ir.steps}
    seen = set()
    for edge in ir.edges:
        if edge.from_step not in by_id or edge.to_step not in by_id:
            continue  # The graph validator reports unknown nodes.
        key = (edge.from_step, edge.to_step, edge.branch)
        if key in seen:
            raise PrimitiveSemanticError("DUPLICATE_GRAPH_EDGE")
        seen.add(key)
        source = by_id[edge.from_step]
        labels = branches(source.input_bindings) if source.operation == "select_branch" else ["true", "false"] if source.operation == "evaluate_predicate" else None
        if labels is None and edge.branch is not None:
            raise PrimitiveSemanticError(f"BRANCH_SOURCE_NOT_SELECTOR:{source.step_id}")
        if labels is not None and edge.branch not in labels:
            raise PrimitiveSemanticError(f"BRANCH_LABEL_INVALID:{source.step_id}")
    for step in ir.steps:
        if step.operation in {"select_branch", "evaluate_predicate"}:
            labels = branches(step.input_bindings) if step.operation == "select_branch" else ["true", "false"]
            if {edge.branch for edge in ir.edges if edge.from_step == step.step_id} != set(labels):
                raise PrimitiveSemanticError(f"BRANCH_OUTPUT_UNCONNECTED:{step.step_id}")
