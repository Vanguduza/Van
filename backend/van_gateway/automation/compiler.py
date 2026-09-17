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

from van_gateway.automation.canonical import (
    COMPILER_VERSION,
    NODE_CATALOG_VERSION,
    digest,
)
from van_gateway.automation.models import Primitive, WorkflowIR, WorkflowIRStep
from van_gateway.automation.policy import AutomationPolicy, PolicyError, load_automation_policy

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

#: §28 — canonical sub-workflow macros the compiler may target.
VAN_SUBWORKFLOWS = {
    Primitive.VAN_CAPABILITY: "van.gateway.capability",
    Primitive.VAN_EVENT: "van.gateway.emit",
    Primitive.VAN_EVIDENCE: "van.evidence.seal",
    Primitive.DEDUPE: "van.event.normalise",
    Primitive.HASH: "van.document.hash",
    Primitive.STORE_TRANSIENT_FILE: "van.document.ingest",
    Primitive.DELETE_TRANSIENT_FILE: "van.document.release",
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


class AutomationCompiler:
    """Compiles a validated IR into a deployable, digest-stable n8n workflow."""

    def __init__(self, policy: AutomationPolicy | None = None) -> None:
        self.policy = policy or load_automation_policy()

    def compile(
        self,
        ir: WorkflowIR,
        *,
        credential_ids: dict[str, str] | None = None,
        workflow_name: str | None = None,
    ) -> CompiledWorkflow:
        credential_ids = credential_ids or {}
        node_names = self._assign_node_names(ir)

        nodes: list[dict[str, Any]] = []
        for step in ir.steps:
            node_type, type_version = self._resolve_node(step)
            self.policy.nodes.check(node_type)
            node: dict[str, Any] = {
                "name": node_names[step.step_id],
                "type": node_type,
                "typeVersion": type_version,
                "parameters": self._compile_parameters(step),
            }
            if step.credential_alias:
                # §46 — resolved to an n8n credential *identifier*, never a value.
                resolved = credential_ids.get(step.credential_alias)
                if resolved is None:
                    raise PolicyError(f"unresolved_credential_alias:{step.credential_alias}")
                node["credentials"] = {"vanConnector": {"id": resolved, "name": step.credential_alias}}
            nodes.append(node)

        nodes.sort(key=lambda n: n["name"])
        connections = self._compile_connections(ir, node_names)

        semantic_graph = {
            "van_semantic_version": 1,
            "family": ir.family,
            "semantic_goal": ir.semantic_goal,
            "version": ir.version,
            "action_class": ir.action_class.value,
            "nodes": nodes,
            "connections": connections,
            "settings": {
                "executionOrder": "v1",
                "saveManualExecutions": False,
                # §48 — n8n is not VAN's evidence archive.
                "saveDataSuccessExecution": "none",
                "saveDataErrorExecution": "all",
                "executionTimeout": self._workflow_timeout_seconds(ir),
            },
        }
        semantic_digest = digest(semantic_graph)

        # §150 — positions are added only now, so they cannot affect the digest.
        positioned = [dict(node) for node in nodes]
        for node in positioned:
            node["position"] = self._position(node["name"], ir, node_names)

        n8n_graph = {
            "name": workflow_name or f"van::{ir.family}::v{ir.version}",
            "nodes": positioned,
            "connections": connections,
            "settings": semantic_graph["settings"],
            "tags": ["van", f"van-family-{ir.family}"],
        }
        return CompiledWorkflow(
            semantic_graph=semantic_graph,
            n8n_graph=n8n_graph,
            semantic_digest=semantic_digest,
            full_digest=digest(n8n_graph),
            node_catalog_version=NODE_CATALOG_VERSION,
            compiler_version=COMPILER_VERSION,
            node_names=node_names,
        )

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

    def _compile_parameters(self, step: WorkflowIRStep) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if step.primitive is Primitive.HTTP_GET:
            params = {"method": "GET", "url": step.input_bindings.get("url", ""), "options": {}}
        elif step.primitive is Primitive.HTTP_REQUEST:
            method = str(step.input_bindings.get("method", "GET")).upper()
            if method not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"):
                raise PolicyError(f"http_method_not_permitted:{method}")
            params = {"method": method, "url": step.input_bindings.get("url", ""), "options": {}}
        elif step.primitive is Primitive.SCHEDULE_TRIGGER:
            params = {"rule": step.input_bindings.get("rule", {})}
        elif step.primitive in (Primitive.WEBHOOK_TRIGGER, Primitive.EVENT_TRIGGER):
            params = {
                "httpMethod": str(step.input_bindings.get("method", "POST")).upper(),
                "path": step.input_bindings.get("path", ""),
                # §208 — ingress is authenticated; never an open webhook.
                "authentication": "headerAuth",
            }
        elif step.primitive in VAN_SUBWORKFLOWS:
            params = {
                "workflowId": VAN_SUBWORKFLOWS[step.primitive],
                "mode": "each",
                "options": {},
                "vanOperation": step.operation,
                "vanInput": dict(sorted(step.input_bindings.items())),
            }
        else:
            params = {"vanOperation": step.operation, **dict(sorted(step.input_bindings.items()))}

        params["vanStepId"] = step.step_id
        params["vanTimeoutMs"] = step.timeout_ms
        params["vanRetryClass"] = step.retry_class.value
        params["vanMaxAttempts"] = step.max_attempts
        if step.idempotency_key_expr:
            params["vanIdempotencyKey"] = step.idempotency_key_expr
        return dict(sorted(params.items()))

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

    @staticmethod
    def _position(node_name: str, ir: WorkflowIR, names: dict[str, str]) -> list[int]:
        """§150 — readable canvas layout, excluded from the semantic digest."""
        reverse = {value: key for key, value in names.items()}
        step_id = reverse[node_name]
        depth = next((i for i, s in enumerate(ir.steps) if s.step_id == step_id), 0)
        branch = sum(1 for e in ir.edges if e.to_step == step_id and e.branch) % 4
        return [depth * 320, branch * 180]


__all__ = ["AutomationCompiler", "CompiledWorkflow", "NODE_MAP", "VAN_SUBWORKFLOWS"]
