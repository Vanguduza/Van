"""Rev 1.3 §§148-151 — deterministic WorkflowIR → n8n graph compiler.

Determinism is the whole point: the same IR must produce the same semantic
digest on every runtime, so drift can be detected (§274) and a repair can be
diffed against what was admitted (§396). Canvas positions are therefore assigned
*after* the semantic digest and excluded from it — moving a node in the editor is
not logic drift (§150).

No model participates. Hermes may help produce the IR; compilation is a pure
function of the IR plus the versioned node catalog.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any
import json
import re
import ipaddress
from urllib.parse import urlparse

from van_gateway.automation.canonical import (
    COMPILER_VERSION,
    NODE_CATALOG_VERSION,
    digest,
)
from van_gateway.automation.models import Primitive, WorkflowIR, WorkflowIRStep
from van_gateway.automation.policy import AutomationPolicy, PolicyError, load_automation_policy
from van_gateway.automation.primitive_policy import SUPPORTED_OPERATIONS, assert_primitive_semantics, PrimitiveSemanticError, validate_branch_graph

#: §148 — the versioned primitive → n8n node mapping. Changing this changes
#: ``NODE_CATALOG_VERSION`` and therefore every artifact's compiled digest.
NODE_MAP: dict[Primitive, tuple[str, int]] = {
    Primitive.HTTP_GET: ("n8n-nodes-base.httpRequest", 4),
    Primitive.HTTP_REQUEST: ("n8n-nodes-base.httpRequest", 4),
    Primitive.EVENT_TRIGGER: ("n8n-nodes-base.webhook", 2),
    Primitive.SCHEDULE_TRIGGER: ("n8n-nodes-base.scheduleTrigger", 1),
    Primitive.WEBHOOK_TRIGGER: ("n8n-nodes-base.webhook", 2),
    Primitive.FILTER: ("n8n-nodes-base.if", 2),
    Primitive.SWITCH: ("n8n-nodes-base.switch", 3),
    Primitive.MAP_FIELDS: ("n8n-nodes-base.set", 3),
    Primitive.MERGE: ("n8n-nodes-base.merge", 3),
    Primitive.DEDUPE: ("n8n-nodes-base.executeWorkflow", 1),
    Primitive.HASH: ("n8n-nodes-base.executeWorkflow", 1),
    Primitive.WAIT: ("n8n-nodes-base.wait", 1),
    Primitive.EXECUTE_SUBWORKFLOW: ("n8n-nodes-base.executeWorkflow", 1),
    # §§42-44 — the three private VAN nodes are compiled as sub-workflow calls
    # until the custom nodes ship, so no capability ever reaches a raw HTTP node.
    Primitive.VAN_CAPABILITY: ("n8n-nodes-base.executeWorkflow", 1),
    Primitive.VAN_EVENT: ("n8n-nodes-base.executeWorkflow", 1),
    Primitive.VAN_EVIDENCE: ("n8n-nodes-base.executeWorkflow", 1),
    Primitive.STORE_TRANSIENT_FILE: ("n8n-nodes-base.executeWorkflow", 1),
    Primitive.DELETE_TRANSIENT_FILE: ("n8n-nodes-base.executeWorkflow", 1),
}

@dataclass(frozen=True)
class CompiledWorkflow:
    """The compiler's output: semantic graph, deployable graph and both digests."""

    semantic_graph: dict[str, Any]
    n8n_graph: dict[str, Any]
    semantic_digest: str
    full_digest: str
    node_catalog_version: str
    compiler_version: str
    node_names: dict[str, str]
    deployable: bool = False
    readiness_errors: tuple[str, ...] = ()


class AutomationCompiler:
    """Compiles a validated IR into a deployable, digest-stable n8n workflow."""

    def __init__(self, policy: AutomationPolicy | None = None, source_credentials=None) -> None:
        self.policy = policy or load_automation_policy()
        self.source_credentials = source_credentials

    def compile(
        self, ir: WorkflowIR, *, credential_ids: dict[str, str] | None = None,
        workflow_name: str | None = None, subworkflow_ids: dict[str, str] | None = None,
        worker_endpoint: str = "", run_path: str = "", worker_credential_id: str = "",
    ) -> CompiledWorkflow:
        credential_ids = credential_ids or {}
        names = self._assign_node_names(ir)
        semantic_nodes = []
        errors = set()
        triggers = {Primitive.SCHEDULE_TRIGGER, Primitive.WEBHOOK_TRIGGER, Primitive.EVENT_TRIGGER}
        for step in ir.steps:
            node_type, version = self._resolve_node(step)
            self.policy.nodes.check(node_type)
            if step.credential_alias and step.credential_alias not in credential_ids:
                raise PolicyError(f"unresolved_credential_alias:{step.credential_alias}")
            if step.credential_alias and (self.source_credentials is None or not self.source_credentials.has(step.credential_alias, step.external_domain)):
                # A generic n8n handle does not supply a typed gateway credential
                # adapter. It cannot be passed to an imaginary vanConnector type.
                errors.add(f"gateway_credential_adapter_unavailable:{step.credential_alias}")
            if step.primitive is Primitive.HTTP_REQUEST:
                method = str(step.input_bindings.get("method", "GET")).upper()
                if method not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"):
                    raise PolicyError(f"http_method_not_permitted:{method}")
                if method != "GET" and step.operation not in {"write_json", "delete_resource"}:
                    errors.add(f"native_effect_requires_gateway_executor:{step.step_id}")
                if method != "GET" and step.operation in {"write_json", "delete_resource"} and (self.source_credentials is None or not self.source_credentials.has(step.credential_alias, step.external_domain, method)):
                    errors.add(f"gateway_write_method_unbound:{step.step_id}")
            if step.primitive not in triggers:
                if step.operation not in SUPPORTED_OPERATIONS.get(step.primitive, frozenset()):
                    errors.add(f"runtime_operation_unsupported:{step.primitive.value}:{step.operation}")
                else:
                    try:
                        assert_primitive_semantics(step)
                    except PrimitiveSemanticError as exc:
                        errors.add(str(exc))
                if not (subworkflow_ids or {}).get(step.primitive.value):
                    errors.add(f"runtime_helper_unprovisioned:{step.primitive.value}")
            semantic_nodes.append({"name": names[step.step_id], "primitive": step.primitive.value,
                                   "parameters": step.model_dump(mode="json")})
        settings = {"executionOrder": "v1", "saveManualExecutions": False,
                    "saveDataSuccessExecution": "none", "saveDataErrorExecution": "none",
                    "executionTimeout": self._workflow_timeout_seconds(ir)}
        semantic = {"van_semantic_version": 3, "family": ir.family, "semantic_goal": ir.semantic_goal,
                    "version": ir.version, "action_class": ir.action_class.value,
                    "nodes": semantic_nodes, "connections": self._compile_connections(ir, names),
                    "settings": settings, "node_catalog_version": NODE_CATALOG_VERSION}
        if not worker_endpoint:
            errors.add("private_worker_endpoint_unconfigured")
        else:
            self._check_worker_endpoint(worker_endpoint)
        if not run_path or re.fullmatch(r"van-run/[A-Za-z0-9_-]+", run_path) is None:
            errors.add("private_run_entry_unbound")
        if re.fullmatch(r"[A-Za-z0-9_-]+", worker_credential_id) is None:
            errors.add("private_worker_credential_unprovisioned")
        graph = {"name": workflow_name or f"van::{ir.family}::v{ir.version}",
                 "nodes": [], "connections": {}, "settings": settings}
        if not errors:
            try:
                graph = self._runtime_graph(ir, names, graph, subworkflow_ids or {}, worker_endpoint, run_path, worker_credential_id)
            except (PolicyError, PrimitiveSemanticError, ValueError) as exc:
                errors.add(str(exc))
        return CompiledWorkflow(semantic_graph=semantic, n8n_graph=graph,
            semantic_digest=digest(semantic), full_digest=digest(graph), node_catalog_version=NODE_CATALOG_VERSION,
            compiler_version=COMPILER_VERSION, node_names=names, deployable=not errors,
            readiness_errors=tuple(sorted(errors)))

    @staticmethod
    def _check_worker_endpoint(value: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise PolicyError("private_worker_endpoint_invalid")
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
        except ValueError:
            # Provisioning must bind a concrete private address, never resolve a
            # caller-controlled DNS name to an unexpected service at execution.
            raise PolicyError("private_worker_endpoint_requires_private_ip")
        if not (address.is_private and not address.is_unspecified and not address.is_multicast):
            raise PolicyError("private_worker_endpoint_not_private")
        if parsed.path != "/v1/automation/worker/step":
            raise PolicyError("private_worker_endpoint_path_invalid")

    def _runtime_graph(self, ir, names, graph, helpers, endpoint, path, worker_credential_id):
        triggers = {Primitive.SCHEDULE_TRIGGER, Primitive.WEBHOOK_TRIGGER, Primitive.EVENT_TRIGGER}
        work = [step for step in ir.steps if step.primitive not in triggers]
        if not work:
            raise PolicyError("workflow_has_no_runtime_operations")
        validate_branch_graph(ir)
        by_id = {step.step_id: step for step in ir.steps}
        remaining, ordered = set(by_id), []
        while remaining:
            frontier = sorted(key for key in remaining if not any(edge.to_step == key and edge.from_step in remaining for edge in ir.edges))
            if not frontier:
                raise PolicyError("runtime_graph_not_dag")
            ordered.extend(by_id[key] for key in frontier)
            remaining.difference_update(frontier)
        work = [step for step in ordered if step.primitive not in triggers]
        # All engine entry is one gateway-issued run request. An n8n timer or
        # external webhook cannot manufacture a canonical standing-run grant.
        root = "$('000_run_entry').first().json.body"
        nodes = [{"name": "000_run_entry", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
                  "parameters": {"httpMethod": "POST", "path": path, "authentication": "none",
                                 "responseMode": "lastNode", "options": {}}, "position": [0, 0]},
                 {"name": "001_run_admission", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4,
                  "parameters": self._http_callback_parameters(endpoint,
                      "={{ JSON.stringify({capability_grant:" + root + ".capability_grant,grant:" + root +
                      ".grant,run_id:" + root + ".run_id,step_id:'__admit__',input:" + root + ".input,value:{}}) }}", 15000),
                  "credentials": {"httpHeaderAuth": {"id": worker_credential_id, "name": "van-automation-worker"}},
                  "position": [320, 0]}]
        connections = {"000_run_entry": {"main": [[{"node": "001_run_admission", "type": "main", "index": 0}]]}}
        outputs = {step.output_name: step.step_id for step in ir.steps if step.output_name}
        payload_names = {}
        for index, step in enumerate(work):
            payload_name = names[step.step_id] + "_request"
            payload_names[step.step_id] = payload_name
            grant = root + ".step_grants[" + json.dumps(step.step_id) + "]"
            raw = "={{ JSON.stringify({capability_grant:" + grant + ".capability_grant,grant:" + grant
            raw += ".grant,run_id:" + root + ".run_id,step_id:" + json.dumps(step.step_id) + ",input:" + root + ".input,value:{},resolve_bindings:true}) }}"
            nodes.append({"name": payload_name, "type": "n8n-nodes-base.set", "typeVersion": 3,
                          "parameters": {"mode": "raw", "jsonOutput": raw, "includeOtherFields": False, "options": {}},
                          "position": [(index + 2) * 640, 0]})
            helper = helpers[step.primitive.value]
            if not isinstance(helper, str) or re.fullmatch(r"[A-Za-z0-9_-]+", helper) is None:
                raise PolicyError("runtime_helper_id_invalid")
            nodes.append({"name": names[step.step_id], "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2,
                          "parameters": {"source": "database", "workflowId": {"__rl": True, "value": helper, "mode": "id"},
                                         "mode": "each", "options": {"waitForSubWorkflow": True}},
                          "position": [(index + 2) * 640 + 320, 0]})
            connections[payload_name] = {"main": [[{"node": names[step.step_id], "type": "main", "index": 0}]]}
        # n8n schedules every sealed callback once. Branch selection and skipped
        # receipts are gateway decisions; no engine expression confers authority.
        previous = "001_run_admission"
        for step in work:
            connections[previous] = {"main": [[{"node": payload_names[step.step_id], "type": "main", "index": 0}]]}
            previous = names[step.step_id]
        final = "999_run_response"
        nodes.append({"name": final, "type": "n8n-nodes-base.set", "typeVersion": 3,
                      "parameters": {"mode": "raw", "includeOtherFields": False, "options": {},
                          "jsonOutput": "={{ JSON.stringify({success:true,executionId:$execution.id,run_id:" + root + ".run_id}) }}"},
                      "position": [(len(work) + 3) * 640, 0]})
        connections[names[work[-1].step_id]] = {"main": [[{"node": final, "type": "main", "index": 0}]]}
        for node in nodes:
            node["id"] = node["name"]
        return {**graph, "nodes": nodes, "connections": connections}

    @classmethod
    def _binding_expression(cls, value, outputs, by_id, names, root):
        if isinstance(value, dict):
            return "{" + ",".join(json.dumps(key) + ":" + cls._binding_expression(item, outputs, by_id, names, root)
                                  for key, item in sorted(value.items())) + "}"
        if isinstance(value, list):
            return "[" + ",".join(cls._binding_expression(item, outputs, by_id, names, root) for item in value) + "]"
        if not isinstance(value, str) or not (value.startswith("$") or value.startswith("{{")):
            return json.dumps(value, ensure_ascii=False, allow_nan=False)
        reference = value[1:] if value.startswith("$") else value[2:-2].strip() if value.endswith("}}") else ""
        parts = reference.split(".")
        if not parts or any(re.fullmatch(r"[A-Za-z0-9_-]+", part) is None for part in parts):
            raise PolicyError("runtime_binding_expression_unsupported")
        if parts[0] == "input":
            expression, tail = root + ".input", parts[1:]
        else:
            step_id = parts[1] if parts[0] == "steps" and len(parts) > 1 else outputs.get(parts[0])
            if step_id not in by_id:
                raise PolicyError("runtime_binding_source_unknown")
            if by_id[step_id].primitive in {Primitive.SCHEDULE_TRIGGER, Primitive.EVENT_TRIGGER, Primitive.WEBHOOK_TRIGGER}:
                expression = root + ".input"
            else:
                expression = "$(" + json.dumps(names[step_id]) + ").first().json.result"
            tail = parts[2:] if parts[0] == "steps" else parts[1:]
        return expression + "".join("[" + json.dumps(part) + "]" for part in tail)

    @staticmethod
    def _http_callback_parameters(endpoint, body, timeout_ms):
        return {"method": "POST", "url": endpoint, "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth", "sendBody": True, "specifyBody": "json",
                "jsonBody": body, "options": {"timeout": timeout_ms,
                  "redirect": {"redirect": {"followRedirects": False}}}}

    # ------------------------------------------------------------------ pieces

    @staticmethod
    def _assign_node_names(ir: WorkflowIR) -> dict[str, str]:
        """§149 — ``<ordinal:03d>_<primitive>_<step_id_suffix>``.

        Ordinals come from the IR's declared step order, which the validator has
        already proven has a deterministic topological ordering.
        """
        names: dict[str, str] = {}
        for index, step in enumerate(ir.steps, start=1):
            suffix = step.step_id[-4:] if len(step.step_id) >= 4 else step.step_id
            names[step.step_id] = f"{index * 10:03d}_{step.primitive.value}_{suffix}"
        return names

    @staticmethod
    def _resolve_node(step: WorkflowIRStep) -> tuple[str, int]:
        try:
            return NODE_MAP[step.primitive]
        except KeyError as exc:
            raise PolicyError(f"unknown_primitive:{step.primitive}") from exc

    @staticmethod
    def _compile_connections(ir: WorkflowIR, names: dict[str, str]) -> dict[str, Any]:
        connections: dict[str, dict[str, list[list[dict[str, Any]]]]] = {}
        grouped: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
        branch_index: dict[tuple[str, str | None], int] = {}
        for edge in sorted(ir.edges, key=lambda e: (e.from_step, e.branch or "", e.to_step)):
            key = (edge.from_step, edge.branch)
            if key not in branch_index:
                existing = {b for (f, b) in branch_index if f == edge.from_step}
                branch_index[key] = len(existing)
            grouped[edge.from_step][branch_index[key]].append(edge.to_step)

        for from_step, outputs in grouped.items():
            slots: list[list[dict[str, Any]]] = []
            for slot in range(max(outputs) + 1):
                slots.append(
                    [
                        {"node": names[target], "type": "main", "index": 0}
                        for target in sorted(outputs.get(slot, []))
                    ]
                )
            connections[names[from_step]] = {"main": slots}
        return dict(sorted(connections.items()))

    @staticmethod
    def _workflow_timeout_seconds(ir: WorkflowIR) -> int:
        """§249 — the workflow timeout bounds the sum of its steps."""
        total_ms = sum(step.timeout_ms * step.max_attempts for step in ir.steps)
        return max(30, min(3600, (total_ms // 1000) + 30))



__all__ = ["AutomationCompiler", "CompiledWorkflow", "NODE_MAP"]
