"""Provision real private n8n helpers; semantic names never masquerade as IDs."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from van_gateway.auth.control_scopes import ControlAuthority, ControlScope
from van_gateway.automation.canonical import digest
from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.models import WorkflowIR, WorkflowLifecycle
from van_gateway.automation.n8n_client import N8nClientError
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.automation.worker_runtime import SUPPORTED_OPERATIONS


class ProvisioningError(RuntimeError):
    pass


def graph_matches(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    """n8n may add display/identity defaults, but must preserve executable fields."""
    if expected.get("name") != observed.get("name") or expected.get("connections") != observed.get("connections"):
        return False
    nodes = observed.get("nodes")
    if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
        return False
    if len(nodes) != len(expected.get("nodes", [])) or len({node.get("name") for node in nodes}) != len(nodes):
        return False
    by_name = {node.get("name"): node for node in nodes}
    for node in expected.get("nodes", []):
        current = by_name.get(node["name"], {})
        for field in ("type", "typeVersion", "parameters", "credentials"):
            if current.get(field, {} if field == "credentials" else None) != node.get(field, {} if field == "credentials" else None):
                return False
        if any(current.get(field) for field in ("disabled", "continueOnFail", "alwaysOutputData", "retryOnFail")) or current.get("onError") not in (None, "stopWorkflow"):
            return False
    settings = observed.get("settings")
    return isinstance(settings, dict) and all(settings.get(key) == value for key, value in expected.get("settings", {}).items())


async def verify_runtime_dependencies(client, binding):
    dependencies = binding.get("dependencies", {})
    if RuntimeBindingStore.dependency_ids(binding["runtime_graph"]) != set(dependencies):
        raise ProvisioningError("N8N_RUNTIME_DEPENDENCIES_UNSEALED")
    for workflow_id, expected in sorted(dependencies.items()):
        if not graph_matches(expected, await client.get_workflow(workflow_id)):
            raise ProvisioningError("N8N_RUNTIME_HELPER_DRIFT")


class N8nProvisioner:
    def __init__(self, store, *, settings, client, registry, compiler):
        self.store, self.settings, self.client, self.registry, self.compiler = store, settings, client, registry, compiler
        self.bindings = RuntimeBindingStore(store)

    def worker_token(self) -> str:
        authority = ControlAuthority(legacy_token=self.settings.internal_control_token,
            scoped=self.settings.internal_control_scoped_tokens,
            device_enrolment_token=self.settings.device_enrolment_token,
            observability_token=self.settings.observability_token)
        tokens = {credential.token for credential in authority.credentials
                  if authority.granted_scopes(credential.token) == frozenset({ControlScope.AUTOMATION_WORKER})}
        if len(tokens) != 1:
            raise ProvisioningError("DEDICATED_AUTOMATION_WORKER_CREDENTIAL_REQUIRED")
        return tokens.pop()

    async def ensure(self) -> None:
        await self.bindings.ensure()
        await self.store.execute("""CREATE TABLE IF NOT EXISTS automation_n8n_resources(
            resource_key TEXT PRIMARY KEY, credential_id TEXT NOT NULL, workflow_id TEXT,
            graph_json TEXT, created_at_ms INTEGER NOT NULL)""")

    @staticmethod
    def helper_graph(primitive: str, endpoint: str, credential_id: str) -> dict[str, Any]:
        AutomationCompiler._check_worker_endpoint(endpoint)
        return {"name": f"van-worker::{primitive}::v2", "nodes": [
            {"id": "van-worker-input", "name": "Worker input", "type": "n8n-nodes-base.executeWorkflowTrigger",
             "typeVersion": 1.1, "parameters": {"inputSource": "passthrough"}, "position": [0, 0]},
            {"id": "van-worker-callback", "name": "Canonical step", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4,
             "parameters": AutomationCompiler._http_callback_parameters(endpoint, "={{ JSON.stringify($json) }}", 300000),
             "credentials": {"httpHeaderAuth": {"id": credential_id, "name": "van-automation-worker"}}, "position": [320, 0]},
        ], "connections": {"Worker input": {"main": [[{"node": "Canonical step", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1", "saveManualExecutions": False, "saveDataSuccessExecution": "none",
                     "saveDataErrorExecution": "none", "executionTimeout": 360}}

    async def provision_helpers(self, endpoint: str) -> tuple[dict[str, str], str]:
        AutomationCompiler._check_worker_endpoint(endpoint)
        await self.ensure()
        token = self.worker_token()
        key = digest({"endpoint": endpoint, "token_hash": hashlib.sha256(token.encode()).hexdigest()})
        credential = await self.store.fetchone("SELECT credential_id FROM automation_n8n_resources WHERE resource_key=?", (key,))
        if credential is None:
            credential_id = await self.client.create_worker_credential(token)
            await self.store.execute("INSERT INTO automation_n8n_resources(resource_key,credential_id,created_at_ms) VALUES (?,?,?)",
                                     (key, credential_id, int(time.time() * 1000)))
        else:
            credential_id = str(credential["credential_id"])
        helpers = {}
        for primitive in sorted(SUPPORTED_OPERATIONS, key=lambda item: item.value):
            graph = self.helper_graph(primitive.value, endpoint, credential_id)
            resource_key = digest(graph)
            prior = await self.store.fetchone("SELECT workflow_id FROM automation_n8n_resources WHERE resource_key=?", (resource_key,))
            if prior is None:
                workflow_id = await self.client.create_workflow(graph)
                observed = await self.client.get_workflow(workflow_id)
                if not graph_matches(graph, observed):
                    raise ProvisioningError("N8N_HELPER_READBACK_MISMATCH")
                await self.store.execute("INSERT INTO automation_n8n_resources(resource_key,credential_id,workflow_id,graph_json,created_at_ms) VALUES (?,?,?,?,?)",
                                         (resource_key, credential_id, workflow_id, json.dumps(graph), int(time.time() * 1000)))
            else:
                workflow_id = str(prior["workflow_id"])
                if not graph_matches(graph, await self.client.get_workflow(workflow_id)):
                    raise ProvisioningError("N8N_HELPER_DRIFT")
            helpers[primitive.value] = workflow_id
        return helpers, credential_id

    async def provision(self, artifact_id: str, endpoint: str) -> dict[str, Any]:
        artifact = await self.registry.get_artifact(artifact_id)
        binding = await self.bindings.get(artifact_id)
        if artifact is None or binding is None:
            raise ProvisioningError("WORKFLOW_CANDIDATE_NOT_FOUND")
        if artifact.lifecycle_state not in {WorkflowLifecycle.PROPOSED, WorkflowLifecycle.QUARANTINED, WorkflowLifecycle.VALIDATED}:
            raise ProvisioningError("WORKFLOW_PROVISION_REQUIRES_CANDIDATE")
        if binding["binding_state"] == "DEPLOYED":
            if not graph_matches(binding["runtime_graph"], await self.client.get_workflow(binding["n8n_workflow_id"])):
                raise ProvisioningError("N8N_RUNTIME_GRAPH_DRIFT")
            await verify_runtime_dependencies(self.client, binding)
            return binding
        ir = WorkflowIR.model_validate(binding["ir"])
        aliases = [step.credential_alias for step in ir.steps if step.credential_alias]
        if any(self.compiler.source_credentials is None or not self.compiler.source_credentials.has(step.credential_alias, step.external_domain)
               for step in ir.steps if step.credential_alias):
            raise ProvisioningError("GATEWAY_CREDENTIAL_ADAPTER_UNAVAILABLE")
        # Validate structure/operations/expressions before any management write.
        # Placeholder references are local preflight inputs, never deploy IDs.
        handles = self.compiler.source_credentials.admitted_handles(aliases) if aliases else {}
        preview = self.compiler.compile(ir, credential_ids=handles, worker_endpoint=endpoint,
            run_path=f"van-run/{artifact_id}", worker_credential_id="preflight-only",
            subworkflow_ids={primitive.value: "preflight-only" for primitive in SUPPORTED_OPERATIONS})
        if not preview.deployable:
            raise ProvisioningError("WORKFLOW_RUNTIME_UNSUPPORTED:" + ",".join(preview.readiness_errors))
        self.worker_token()
        helpers, credential_id = await self.provision_helpers(endpoint)
        compiled = self.compiler.compile(ir, credential_ids=handles, subworkflow_ids=helpers, worker_endpoint=endpoint,
                                         worker_credential_id=credential_id, run_path=f"van-run/{artifact_id}")
        if not compiled.deployable:
            raise ProvisioningError("WORKFLOW_RUNTIME_UNSUPPORTED:" + ",".join(compiled.readiness_errors))
        if compiled.semantic_digest != artifact.compiled_semantic_digest:
            raise ProvisioningError("WORKFLOW_SEMANTIC_BINDING_CHANGED")
        graph = compiled.n8n_graph
        dependencies = {}
        for workflow_id in RuntimeBindingStore.dependency_ids(graph):
            row = await self.store.fetchone("SELECT graph_json FROM automation_n8n_resources WHERE workflow_id=?", (workflow_id,))
            if row is None or not row["graph_json"]:
                raise ProvisioningError("N8N_RUNTIME_DEPENDENCIES_UNSEALED")
            dependencies[workflow_id] = json.loads(row["graph_json"])
        workflow_id = await self.client.create_workflow(graph)
        if not graph_matches(graph, await self.client.get_workflow(workflow_id)):
            raise ProvisioningError("N8N_RUNTIME_GRAPH_READBACK_MISMATCH")
        await self.bindings.record(artifact_id=artifact_id, ir=binding["ir"], semantic_graph=compiled.semantic_graph,
                                   runtime_graph=graph, readiness_errors=[], dependencies=dependencies)
        recorded = await self.bindings.get(artifact_id)
        await self.registry.record_artifact(artifact.model_copy(update={"compiled_full_digest": recorded["full_digest"],
                                                                      "n8n_workflow_id": workflow_id}))
        return await self.bindings.mark_deployed(artifact_id, workflow_id)
