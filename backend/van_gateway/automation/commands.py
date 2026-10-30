"""Exact owner command resolution and native automation execution.

All classes, inputs and artifact pins are derived from sealed plans before an
A4 challenge. No recognized automation command falls back to free-form dispatch.
"""
from __future__ import annotations

import json
import math
import re
import time

from fastapi import HTTPException

from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.automation.api import AdmitBody
from van_gateway.automation.canonical import canonical_json, digest
from van_gateway.automation.dsl import bounded_json
from van_gateway.automation.models import WorkflowIR, WorkflowLifecycle
from van_gateway.automation.provisioner import graph_matches, verify_runtime_dependencies
from van_gateway.automation.provisioner import ProvisioningError
from van_gateway.automation.n8n_client import N8nClientError
from van_gateway.automation.dispatch import DispatchError
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.command.local_executors import LocalExecutionError, LocalExecutionResult
from van_gateway.command.resolver import CommandResolution, ResolutionMode
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.automation.input_bindings import ARTIFACT_PIN, workflow_inputs


class AutomationCommandDenied(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AutomationCommandDenied("AUTOMATION_INPUT_DUPLICATE_KEY")
        result[key] = value
    return result


def _validate_schema(schema, depth=0):
    """Validate every declared assertion, including currently unused properties."""
    if depth > 12 or not isinstance(schema, dict):
        raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    if set(schema) - {"type", "properties", "required", "additionalProperties", "items", "enum", "const",
                      "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "description", "title", "default"}:
        raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    expected = schema.get("type", "object" if "properties" in schema or not schema else None)
    kinds = expected if isinstance(expected, list) else [expected]
    if (not kinds or len(kinds) > 7 or any(not isinstance(kind, str) or kind not in
            {"object", "array", "string", "integer", "number", "boolean", "null"} for kind in kinds)
            or len(set(kinds)) != len(kinds)):
        raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    for low, high in (("minLength", "maxLength"), ("minItems", "maxItems")):
        if any(key in schema and (type(schema[key]) is not int or schema[key] < 0) for key in (low, high)):
            raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
        if low in schema and high in schema and schema[low] > schema[high]:
            raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    for key in ("minimum", "maximum"):
        if key in schema and (type(schema[key]) not in (int, float)
                              or type(schema[key]) is float and not math.isfinite(schema[key])):
            raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    if "minimum" in schema and "maximum" in schema and schema["minimum"] > schema["maximum"]:
        raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not 1 <= len(schema["enum"]) <= 256):
        raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    if "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
        raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    properties, required = schema.get("properties", {}), schema.get("required", [])
    if (not isinstance(properties, dict) or len(properties) > 64 or not isinstance(required, list)
            or len(required) > 64 or any(not isinstance(key, str) or key not in properties for key in required)
            or len(set(required)) != len(required)):
        raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
    for key, child in properties.items():
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or key == ARTIFACT_PIN:
            raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
        _validate_schema(child, depth + 1)
    if "items" in schema:
        _validate_schema(schema["items"], depth + 1)
    for keys, allowed in (({"properties", "required", "additionalProperties"}, {"object"}),
                          ({"items", "minItems", "maxItems"}, {"array"}),
                          ({"minLength", "maxLength"}, {"string"}),
                          ({"minimum", "maximum"}, {"integer", "number"})):
        if set(schema) & keys and not set(kinds) & allowed:
            raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")


def validate_inputs(value, schema, depth=0):
    """Bounded supported schema subset; unknown assertions refuse, never disappear."""
    if depth == 0:
        try:
            bounded_json(value)
            bounded_json(schema)
            _validate_schema(schema)
        except (ValueError, TypeError, OverflowError) as exc:
            raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED") from exc
    expected = schema.get("type", "object" if "properties" in schema or not schema else None)
    checks = {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
              "integer": type(value) is int, "number": type(value) in (int, float), "boolean": type(value) is bool, "null": value is None}
    kinds = expected if isinstance(expected, list) else [expected]
    if not kinds or any(not isinstance(kind, str) or kind not in checks for kind in kinds) or not any(checks[kind] for kind in kinds):
        raise AutomationCommandDenied("AUTOMATION_INPUT_TYPE_INVALID")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not any(canonical_json(value) == canonical_json(item) for item in schema["enum"])):
        raise AutomationCommandDenied("AUTOMATION_INPUT_ENUM_INVALID")
    if "const" in schema and canonical_json(value) != canonical_json(schema["const"]):
        raise AutomationCommandDenied("AUTOMATION_INPUT_CONST_INVALID")
    if isinstance(value, dict):
        properties, required = schema.get("properties", {}), schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list) or any(not isinstance(key, str) or key not in properties for key in required):
            raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
        if not set(required) <= set(value) or set(value) - set(properties):
            # Every input is declared, even if a broad schema asked for extras.
            raise AutomationCommandDenied("AUTOMATION_INPUT_FIELDS_INVALID")
        for key, child in value.items():
            validate_inputs(child, properties[key], depth + 1)
    elif isinstance(value, list):
        if "items" not in schema:
            raise AutomationCommandDenied("AUTOMATION_INPUT_SCHEMA_UNSUPPORTED")
        if not schema.get("minItems", 0) <= len(value) <= min(schema.get("maxItems", 256), 256):
            raise AutomationCommandDenied("AUTOMATION_INPUT_BOUND_INVALID")
        for child in value:
            validate_inputs(child, schema["items"], depth + 1)
    elif isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= min(schema.get("maxLength", 65536), 65536):
            raise AutomationCommandDenied("AUTOMATION_INPUT_BOUND_INVALID")
    elif type(value) in (int, float):
        if ("minimum" in schema and value < schema["minimum"]) or ("maximum" in schema and value > schema["maximum"]):
            raise AutomationCommandDenied("AUTOMATION_INPUT_BOUND_INVALID")


async def sealed_plan(api, artifact_id: str, *, admitted: bool):
    artifact = await api.registry.get_artifact(artifact_id)
    binding = await api.runtime_bindings.get(artifact_id)
    if artifact is None or binding is None:
        raise AutomationCommandDenied("AUTOMATION_PLAN_NOT_FOUND")
    ir = WorkflowIR.model_validate(binding["ir"])
    api.validator.validate_or_raise(ir)
    _validate_schema(ir.inputs_schema)
    if (digest(ir.semantic_payload()) != artifact.workflow_ir_digest
            or digest(binding["semantic_graph"]) != artifact.compiled_semantic_digest
            or binding["semantic_digest"] != artifact.compiled_semantic_digest):
        raise AutomationCommandDenied("AUTOMATION_PLAN_MANIFEST_MISMATCH")
    if admitted:
        current = await api.registry.admitted_artifact(artifact.capability_id)
        capability = await api.registry.get_capability(artifact.capability_id)
        if (current is None or current.artifact_id != artifact_id or capability is None
                or capability.action_class != ir.action_class or capability.lifecycle_state not in {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT}
                or artifact.lifecycle_state not in {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT}
                or binding["binding_state"] != "DEPLOYED" or binding["readiness_errors"]
                or not binding["runtime_graph"]
                or RuntimeBindingStore.dependency_ids(binding["runtime_graph"]) != set(binding["dependencies"])
                or RuntimeBindingStore.compute_full_digest(binding["runtime_graph"], binding["dependencies"]) != artifact.compiled_full_digest):
            raise AutomationCommandDenied("AUTOMATION_PLAN_NOT_ADMITTED_OR_DEPLOYED")
    return artifact, binding, ir


async def resolve_automation_command(api, text: str) -> CommandResolution | None:
    if not re.match(r"^automation(?:\s|$)", text.strip(), re.IGNORECASE):
        return None
    identifier = r"[A-Za-z0-9_-]{1,160}"
    execute = re.fullmatch(rf"automation\s+execute\s+({identifier})\s+artifact\s+({identifier})\s+with\s+(.+)", text.strip(), re.IGNORECASE | re.DOTALL)
    admission = re.fullmatch(rf"automation\s+admit\s+({identifier})", text.strip(), re.IGNORECASE)
    if execute:
        capability_id, artifact_id, raw = execute.groups()
        if len(raw.encode("utf-8")) > 1024 * 1024:
            raise AutomationCommandDenied("AUTOMATION_INPUT_TOO_LARGE")
        try:
            inputs = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
            bounded_json(inputs)
        except (ValueError, TypeError) as exc:
            raise AutomationCommandDenied("AUTOMATION_INPUT_JSON_INVALID") from exc
        artifact, binding, ir = await sealed_plan(api, artifact_id, admitted=True)
        if artifact.capability_id != capability_id or not isinstance(inputs, dict) or ARTIFACT_PIN in inputs:
            raise AutomationCommandDenied("AUTOMATION_PLAN_INPUT_BINDING_MISMATCH")
        validate_inputs(inputs, ir.inputs_schema)
        parameters = {**inputs, ARTIFACT_PIN: artifact_id}
        action_id, action_class = f"automation.workflow.{capability_id}", ir.action_class
        definition = await api.dispatcher.actions.get_definition(action_id) if api.dispatcher else None
        if definition is None or not definition.enabled or definition.action_class != action_class:
            raise AutomationCommandDenied("AUTOMATION_DYNAMIC_ACTION_UNAVAILABLE")
        intent = "automation.workflow.execute"
    elif admission:
        artifact_id = admission.group(1)
        artifact, binding, ir = await sealed_plan(api, artifact_id, admitted=False)
        if artifact.lifecycle_state not in {WorkflowLifecycle.PROPOSED, WorkflowLifecycle.QUARANTINED, WorkflowLifecycle.VALIDATED}:
            raise AutomationCommandDenied("AUTOMATION_PLAN_NOT_CANDIDATE")
        parameters = {"artifact_id": artifact_id, "workflow_ir_digest": artifact.workflow_ir_digest,
                      "semantic_digest": artifact.compiled_semantic_digest}
        action_id = f"automation.plan.admit.{artifact_id}"
        action_class = ActionClass.A4 if ir.action_class is ActionClass.A4 else ActionClass.A3
        actions = api.dispatcher.actions if api.dispatcher else None
        if actions is None:
            raise AutomationCommandDenied("AUTOMATION_DISPATCH_UNCONFIGURED")
        await actions.register(ActionDefinition(action_id=action_id, action_class=action_class, mutates_state=True,
            allowed_principals={PrincipalType.OWNER_DEVICE}, verifier_type=VerifierType.READ_BACK,
            parameter_schema={"type": "object", "required": sorted(parameters)},
            no_stale_replay=action_class is ActionClass.A4, max_age_seconds=5 if action_class is ActionClass.A4 else 300))
        intent = "automation.plan.admit"
    else:
        raise AutomationCommandDenied("AUTOMATION_EXACT_COMMAND_REQUIRED")
    return CommandResolution(mode=ResolutionMode.EXACT_ACTION, normalized_text=text.strip(), intent_id=intent,
        action_id=action_id, canonical_action_class=action_class, parameters=parameters,
        no_stale_replay=action_class is ActionClass.A4, max_age_seconds=5 if action_class is ActionClass.A4 else 300,
        verifier_type=VerifierType.READ_BACK, rule_id="automation-immutable-plan-v1")


async def admission_readback(api, parameters):
    artifact, binding, ir = await sealed_plan(api, parameters["artifact_id"], admitted=True)
    if artifact.workflow_ir_digest != parameters["workflow_ir_digest"] or artifact.compiled_semantic_digest != parameters["semantic_digest"]:
        raise AutomationCommandDenied("AUTOMATION_PLAN_MANIFEST_MISMATCH")
    await verify_runtime_dependencies(api.dispatcher.client, binding)
    observed = await api.dispatcher.client.get_workflow(binding["n8n_workflow_id"])
    if observed.get("active") is not True or not graph_matches(binding["runtime_graph"], observed):
        raise AutomationCommandDenied("AUTOMATION_PLAN_TARGET_READBACK_MISMATCH")
    return {"artifact_id": artifact.artifact_id, "admitted": True, "workflow_ir_digest": artifact.workflow_ir_digest,
            "semantic_digest": artifact.compiled_semantic_digest, "evidence_pointer": "automation-plan://" + artifact.artifact_id}


async def command_readback(api, command_id: str):
    """Fresh mission observation from the exact canonical command and actual targets."""
    authority = await api.dispatcher.authority.get(command_id) if api and api.dispatcher else None
    if authority is None or authority.principal_type is not PrincipalType.OWNER_DEVICE:
        raise AutomationCommandDenied("AUTOMATION_OWNER_AUTHORITY_REQUIRED")
    parameters = authority.typed_parameter_constraints
    if (authority.typed_action_id or "").startswith("automation.plan.admit."):
        result = await admission_readback(api, parameters)
    elif (authority.typed_action_id or "").startswith("automation.workflow."):
        artifact_id = parameters.get(ARTIFACT_PIN)
        artifact, binding, ir = await sealed_plan(api, artifact_id, admitted=True)
        if authority.typed_action_id != f"automation.workflow.{artifact.capability_id}":
            raise AutomationCommandDenied("AUTOMATION_TYPED_ACTION_MISMATCH")
        rows = await api.store.fetchall("SELECT * FROM automation_runs WHERE command_id=? AND artifact_id=?", (command_id, artifact_id))
        if len(rows) != 1 or rows[0]["status"] != "VERIFIED_SUCCESS" or rows[0]["verifier_status"] != "VERIFIED_SUCCESS" or rows[0]["input_digest"] != digest(parameters):
            raise AutomationCommandDenied("AUTOMATION_VERIFIED_UNIQUE_RUN_REQUIRED")
        from van_gateway.automation.worker_runtime import WorkerWorkflowObserver
        worker = getattr(api, "worker", None)
        if worker is None:
            raise AutomationCommandDenied("AUTOMATION_WORKER_OBSERVER_UNCONFIGURED")
        result = await WorkerWorkflowObserver(worker).observe(None, {"run_id": rows[0]["run_id"], "inputs": parameters})
        if result.get("exists") is not True:
            raise AutomationCommandDenied("AUTOMATION_TARGET_READBACK_MISMATCH")
        result = {"artifact_id": artifact_id, "run_id": rows[0]["run_id"], "verified": True,
                  "evidence_pointer": result["evidence_pointer"]}
    else:
        raise AutomationCommandDenied("AUTOMATION_TYPED_ACTION_MISMATCH")
    return {**result, "evidence_refs": [result["evidence_pointer"]]}


class AutomationPlanExecutor:
    def __init__(self, api):
        self.api = api

    async def execute(self, ctx):
        try:
            authority = await self.api.dispatcher.authority.get(ctx.command_id)
            definition = await self.api.dispatcher.actions.get_definition(authority.typed_action_id) if authority else None
            if not authority or not definition or authority.principal_type is not PrincipalType.OWNER_DEVICE:
                raise AutomationCommandDenied("AUTOMATION_OWNER_AUTHORITY_REQUIRED")
            await self.api.dispatcher.authority.authorize_action(command_id=ctx.command_id, action=definition,
                principal_type=authority.principal_type, requested_by=authority.requested_by, snapshot_id=authority.snapshot_id,
                turn_id=authority.turn_id, parameters=ctx.parameters)
            if definition.action_class is ActionClass.A4 and (not authority.owner_approved or int(time.time()) - authority.issued_at_unix > 5):
                raise AutomationCommandDenied("AUTOMATION_FRESH_A4_APPROVAL_REQUIRED")
            if authority.typed_action_id.startswith("automation.plan.admit."):
                artifact, binding, ir = await sealed_plan(self.api, ctx.parameters["artifact_id"], admitted=False)
                if artifact.workflow_ir_digest != ctx.parameters["workflow_ir_digest"] or artifact.compiled_semantic_digest != ctx.parameters["semantic_digest"]:
                    raise AutomationCommandDenied("AUTOMATION_PLAN_MANIFEST_MISMATCH")
                await self.api.provision_candidate(artifact.artifact_id)
                for expected, target in ((WorkflowLifecycle.PROPOSED, WorkflowLifecycle.QUARANTINED),
                                         (WorkflowLifecycle.QUARANTINED, WorkflowLifecycle.VALIDATED),
                                         (WorkflowLifecycle.VALIDATED, WorkflowLifecycle.ADMITTED)):
                    current = await self.api.registry.get_artifact(artifact.artifact_id)
                    if current.lifecycle_state is expected:
                        await self.api.dispatcher.authority.authorize_action(command_id=ctx.command_id, action=definition,
                            principal_type=authority.principal_type, requested_by=authority.requested_by, snapshot_id=authority.snapshot_id,
                            turn_id=authority.turn_id, parameters=ctx.parameters)
                        await self.api.transition_candidate(AdmitBody(artifact_id=artifact.artifact_id, expected=expected, target=target))
                observed = await admission_readback(self.api, ctx.parameters)
                return LocalExecutionResult("The exact automation plan was deployed and admitted after readback.",
                                            observed["evidence_pointer"], observed)
            artifact_id = ctx.parameters.get(ARTIFACT_PIN)
            artifact, binding, ir = await sealed_plan(self.api, artifact_id, admitted=True)
            if authority.typed_action_id != f"automation.workflow.{artifact.capability_id}":
                raise AutomationCommandDenied("AUTOMATION_TYPED_ACTION_MISMATCH")
            result = await self.api.dispatcher.dispatch(capability_id=artifact.capability_id,
                action_id=authority.typed_action_id, command_id=ctx.command_id, snapshot_id=authority.snapshot_id,
                principal_type=authority.principal_type, requested_by=authority.requested_by,
                turn_id=authority.turn_id, inputs=ctx.parameters, mission_id=ctx.mission_id)
            if not result.owner_success:
                raise LocalExecutionError(result.error_code or "AUTOMATION_OUTCOME_UNVERIFIED",
                    "Automation did not produce a verified outcome; inspect its durable run before another owner decision.", status="degraded")
            return LocalExecutionResult("The selected automation path passed independent target readback.", result.evidence_pointer,
                {"artifact_id": artifact_id, "run_id": result.run_id, "verified": True})
        except LocalExecutionError:
            raise
        except HTTPException as exc:
            raise LocalExecutionError("AUTOMATION_DEPLOYMENT_BLOCKED", str(exc.detail), status="degraded") from exc
        except (ProvisioningError, N8nClientError, DispatchError) as exc:
            raise LocalExecutionError("AUTOMATION_PROVIDER_OR_RUNTIME_BLOCKED", str(exc), status="degraded") from exc
        except ValueError as exc:
            raise LocalExecutionError("AUTOMATION_COMMAND_REFUSED", str(exc)) from exc
