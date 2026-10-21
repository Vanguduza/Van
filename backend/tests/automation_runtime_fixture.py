"""Canonical manifested test candidates and a stateful real-shaped n8n manager."""
from __future__ import annotations

import copy
import json

import httpx

from conftest_automation import sample_ir, policy_with_domains, sample_artifact, sample_capability
from van_gateway.automation.canonical import digest
from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.models import Primitive, WorkflowLifecycle
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.automation.provisioner import N8nProvisioner
from van_gateway.models import ActionClass

DOMAIN = "reports.example.com"
ENDPOINT = "https://127.0.0.1:8079/v1/automation/worker/step"
WORKER_TOKEN = "worker-test-token-0123456789abcdef"


def public_ir(*, read_only=False, verifier=None):
    ir = sample_ir(domain=DOMAIN)
    steps = list(ir.steps)
    steps[1] = steps[1].model_copy(update={"operation": "fetch_documents", "credential_alias": None, "max_attempts": 1})
    if read_only:
        steps = steps[:2]
    return ir.model_copy(update={"steps": steps, "edges": ir.edges[:len(steps)-1],
        "credential_requirements": [], "action_class": ActionClass.A2 if read_only else ActionClass.A3,
        "verifier": verifier if verifier is not None else ir.verifier})


def bound_compile(ir, *, artifact_id="wfart_wfcap_statements_1", helper_id="helper1"):
    compiler = AutomationCompiler(policy_with_domains(DOMAIN))
    return compiler.compile(ir, worker_endpoint=ENDPOINT,
        run_path=f"van-run/{artifact_id}", worker_credential_id="workerCredential1",
        subworkflow_ids={step.primitive.value: helper_id for step in ir.steps})


async def seed_runtime(store, registry, *, capability_id="wfcap_statements", read_only=True, verifier=None):
    ir = public_ir(read_only=read_only, verifier=verifier)
    artifact = sample_artifact(capability_id, lifecycle=WorkflowLifecycle.PROPOSED)
    compiled = bound_compile(ir, artifact_id=artifact.artifact_id)
    helper_graph = N8nProvisioner.helper_graph("HTTP_GET", ENDPOINT, "workerCredential1")
    dependencies = {"helper1": helper_graph}
    assert compiled.deployable, compiled.readiness_errors
    capability = sample_capability(capability_id, action_class=ir.action_class,
        mutates=any(step.mutates for step in ir.steps), lifecycle=WorkflowLifecycle.ADMITTED).model_copy(update={
            "required_context": [], "required_credentials": [], "workflow_ir_digest": digest(ir.semantic_payload())})
    await registry.upsert_capability(capability)
    artifact = artifact.model_copy(update={"workflow_ir_digest": digest(ir.semantic_payload()),
        "compiled_semantic_digest": compiled.semantic_digest,
        "compiled_full_digest": RuntimeBindingStore.compute_full_digest(compiled.n8n_graph, dependencies),
        "compiler_version": compiled.compiler_version, "node_catalog_version": compiled.node_catalog_version})
    await registry.record_artifact(artifact)
    bindings = RuntimeBindingStore(store)
    await bindings.record(artifact_id=artifact.artifact_id, ir=ir.model_dump(mode="json"),
        semantic_graph=compiled.semantic_graph, runtime_graph=compiled.n8n_graph, readiness_errors=[], dependencies=dependencies)
    await bindings.mark_deployed(artifact.artifact_id, artifact.n8n_workflow_id)
    await store.execute("UPDATE automation_artifacts SET lifecycle_state='ADMITTED' WHERE artifact_id=?", (artifact.artifact_id,))
    return ir, compiled, await registry.get_artifact(artifact.artifact_id)


class StatefulN8n:
    def __init__(self, *, drift=False, activation_visible=True, engine_success=True):
        self.workflows = {}
        self.requests = []
        self.credentials = []
        self.drift, self.activation_visible, self.engine_success = drift, activation_visible, engine_success
        self.transport = httpx.MockTransport(self.handle)

    def seed(self, workflow_id, graph, *, active=True):
        self.workflows[workflow_id] = {**copy.deepcopy(graph), "id": workflow_id, "active": active}
        for helper_id in RuntimeBindingStore.dependency_ids(graph):
            self.workflows.setdefault(helper_id, {**N8nProvisioner.helper_graph("HTTP_GET", ENDPOINT, "workerCredential1"), "id": helper_id, "active": False})

    def handle(self, request):
        self.requests.append(request)
        path, method = request.url.path, request.method
        if path == "/rest/settings":
            return httpx.Response(200, json={"data": {"versionCli": "2.39.7"}})
        if path == "/api/v1/credentials/schema/httpHeaderAuth":
            return httpx.Response(200, json={"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"}}})
        if path == "/api/v1/credentials" and method == "POST":
            self.credentials.append(json.loads(request.content))
            return httpx.Response(200, json={"id": f"credential{len(self.credentials)}"})
        if path == "/api/v1/workflows" and method == "POST":
            workflow_id = f"workflow{len(self.workflows)+1}"
            self.seed(workflow_id, json.loads(request.content), active=False)
            return httpx.Response(200, json={"id": workflow_id})
        if path.startswith("/api/v1/workflows/"):
            workflow_id = path.split("/")[4]
            if workflow_id not in self.workflows:
                return httpx.Response(404)
            if method == "GET":
                graph = copy.deepcopy(self.workflows[workflow_id])
                if self.drift:
                    graph["nodes"][-1]["continueOnFail"] = True
                return httpx.Response(200, json=graph)
            if path.endswith("/activate") and method == "POST":
                self.workflows[workflow_id]["active"] = self.activation_visible
                return httpx.Response(200, json=self.workflows[workflow_id])
            if path.endswith("/deactivate") and method == "POST":
                self.workflows[workflow_id]["active"] = False
                return httpx.Response(200, json=self.workflows[workflow_id])
        if path.startswith("/webhook/") and method == "POST":
            body = json.loads(request.content)
            assert body["capability_grant"] and body["grant"] and body["step_grants"]
            assert "X-Van-Internal-Token" not in request.headers
            return httpx.Response(200, json={"executionId": "n8n-exec-1", "run_id": body["run_id"], "success": self.engine_success})
        return httpx.Response(404)
