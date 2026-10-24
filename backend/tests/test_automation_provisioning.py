"""Deploy actual typed n8n resources, verify readback, and refuse partial admission."""
from __future__ import annotations

import copy
import json

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from automation_runtime_fixture import DOMAIN, ENDPOINT, WORKER_TOKEN, StatefulN8n, bound_compile, public_ir
from conftest_automation import make_store, policy_with_domains, sample_artifact, sample_capability
from van_gateway.action.service import ActionRuntime
from van_gateway.automation.api import AutomationApi
from van_gateway.automation.canonical import digest
from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.models import WorkflowLifecycle, WorkflowStepEffect
from van_gateway.automation.n8n_client import N8nClientError, N8nManagementClient
from van_gateway.automation.provisioner import N8nProvisioner, ProvisioningError, graph_matches
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.command.standing import StandingAutomationAuthorityService
from van_gateway.config import get_settings
from van_gateway.models import ActionClass

INTERNAL = "provisioning-control-test-token"


@pytest_asyncio.fixture
async def candidate(tmp_path):
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    compiler = AutomationCompiler(policy_with_domains(DOMAIN))
    ir = public_ir()
    compiled = compiler.compile(ir)
    await registry.upsert_capability(sample_capability(action_class=ir.action_class,
        lifecycle=WorkflowLifecycle.PROPOSED).model_copy(update={"required_context": [], "required_credentials": []}))
    artifact = sample_artifact(lifecycle=WorkflowLifecycle.PROPOSED, n8n_workflow_id=None).model_copy(update={
        "workflow_ir_digest": digest(ir.semantic_payload()), "compiled_semantic_digest": compiled.semantic_digest,
        "compiled_full_digest": compiled.full_digest})
    await registry.record_artifact(artifact)
    await RuntimeBindingStore(store).record(artifact_id=artifact.artifact_id, ir=ir.model_dump(mode="json"),
        semantic_graph=compiled.semantic_graph, runtime_graph=None, readiness_errors=list(compiled.readiness_errors))
    manager = StatefulN8n()
    client = N8nManagementClient(None, base_url="http://127.0.0.1:5678/api/v1", api_key="manager-token",
        enabled=True, transport=manager.transport)
    settings = get_settings().model_copy(update={"automation_enabled": True, "internal_control_token": INTERNAL,
        "internal_control_scoped_tokens": f"automation_worker:{WORKER_TOKEN}",
        "device_enrolment_token": "", "observability_token": "", "automation_worker_endpoint": ENDPOINT,
        "automation_source_credentials_file": ""})
    provisioner = N8nProvisioner(store, settings=settings, client=client, registry=registry, compiler=compiler)
    return store, registry, ir, artifact, manager, client, settings, provisioner


async def test_real_helpers_and_parent_are_created_read_back_and_reused(candidate):
    store, registry, ir, artifact, manager, _client, _settings, provisioner = candidate
    deployed = await provisioner.provision(artifact.artifact_id, ENDPOINT)
    assert deployed["binding_state"] == "DEPLOYED"
    assert manager.credentials == [{"name": "van-automation-worker", "type": "httpHeaderAuth",
        "data": {"name": "X-Van-Internal-Token", "value": WORKER_TOKEN}}]
    assert WORKER_TOKEN not in json.dumps(deployed)
    assert artifact.compiled_semantic_digest == deployed["semantic_digest"]
    parent = manager.workflows[deployed["n8n_workflow_id"]]
    references = [node["parameters"]["workflowId"]["value"] for node in parent["nodes"] if node["type"].endswith("executeWorkflow")]
    assert references and all(reference in manager.workflows for reference in references)
    for reference in references:
        helper = manager.workflows[reference]
        assert helper["nodes"][0]["type"].endswith("executeWorkflowTrigger")
        assert helper["nodes"][1]["credentials"]["httpHeaderAuth"]["id"] == "credential1"
        assert helper["nodes"][1]["parameters"]["url"] == ENDPOINT
    assert all("vanOperation" not in node["parameters"] and "vanInput" not in node["parameters"] for node in parent["nodes"])
    assert (await registry.get_artifact(artifact.artifact_id)).lifecycle_state is WorkflowLifecycle.PROPOSED
    before = len(manager.requests)
    assert (await provisioner.provision(artifact.artifact_id, ENDPOINT))["n8n_workflow_id"] == deployed["n8n_workflow_id"]
    assert len(manager.requests) == before + 1 + len(deployed["dependencies"]) and manager.requests[-1].method == "GET"


@pytest.mark.parametrize("scoped,legacy", [
    ("", INTERNAL),
    (f"automation_worker,automation:{WORKER_TOKEN}", INTERNAL),
    (f"automation_worker:{WORKER_TOKEN}", WORKER_TOKEN),
    (f"automation_worker:{WORKER_TOKEN};automation_worker:second-token-0123456789abcdef-abc", INTERNAL),
])
async def test_worker_credential_must_be_one_dedicated_narrow_role(candidate, scoped, legacy):
    *_prefix, settings, provisioner = candidate
    manager = candidate[4]
    provisioner.settings = settings.model_copy(update={"internal_control_scoped_tokens": scoped, "internal_control_token": legacy})
    with pytest.raises(ProvisioningError, match="DEDICATED_AUTOMATION_WORKER_CREDENTIAL_REQUIRED"):
        await provisioner.provision(candidate[3].artifact_id, ENDPOINT)
    assert not manager.requests


async def test_helper_drift_refuses_parent_creation_and_keeps_candidate(candidate):
    store, registry, _ir, artifact, manager, _client, _settings, provisioner = candidate
    manager.drift = True
    with pytest.raises(ProvisioningError, match="N8N_HELPER_READBACK_MISMATCH"):
        await provisioner.provision(artifact.artifact_id, ENDPOINT)
    binding = await RuntimeBindingStore(store).get(artifact.artifact_id)
    assert binding["binding_state"] == "CANDIDATE"
    assert (await registry.get_artifact(artifact.artifact_id)).n8n_workflow_id is None
    assert len(manager.workflows) == 1


async def test_unsupported_source_adapter_refuses_before_manager_write(candidate):
    store, _registry, ir, artifact, manager, _client, _settings, provisioner = candidate
    steps = list(ir.steps)
    steps[1] = steps[1].model_copy(update={"credential_alias": "connector://broker/primary"})
    ir = ir.model_copy(update={"steps": steps, "credential_requirements": ["connector://broker/primary"]})
    binding = await RuntimeBindingStore(store).get(artifact.artifact_id)
    await RuntimeBindingStore(store).record(artifact_id=artifact.artifact_id, ir=ir.model_dump(mode="json"),
        semantic_graph=binding["semantic_graph"], runtime_graph=None, readiness_errors=[])
    with pytest.raises(ProvisioningError, match="GATEWAY_CREDENTIAL_ADAPTER_UNAVAILABLE"):
        await provisioner.provision(artifact.artifact_id, ENDPOINT)
    assert not manager.requests


@pytest.mark.parametrize("fault", ["timeout", "malformed_id", "unsupported_schema"])
async def test_credential_create_fault_never_retries_ambiguous_write(fault):
    requests = []
    def handle(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"properties": {} if fault == "unsupported_schema" else {"name": {}, "value": {}}})
        if fault == "timeout":
            raise httpx.ReadTimeout("private transport detail")
        return httpx.Response(200, json={"id": 123})
    client = N8nManagementClient(None, enabled=True, base_url="http://127.0.0.1:5678/api/v1", api_key="k", transport=httpx.MockTransport(handle))
    with pytest.raises(N8nClientError):
        await client.create_worker_credential(WORKER_TOKEN)
    assert len([request for request in requests if request.method == "POST"]) == (0 if fault == "unsupported_schema" else 1)


def test_actual_sink_completes_unsorted_linear_graph_without_losing_edge():
    ir = public_ir()
    ir = ir.model_copy(update={"steps": [ir.steps[0], ir.steps[2], ir.steps[1]]})
    compiled = bound_compile(ir)
    assert compiled.deployable
    names = compiled.node_names
    graph = compiled.n8n_graph
    assert graph["connections"][names["s_http02"]]["main"][0][0]["node"] == names["s_evid03"] + "_request"
    assert graph["connections"][names["s_evid03"]]["main"][0][0]["node"] == "999_run_response"


def test_semantic_identity_does_not_depend_on_real_deployment_ids():
    ir = public_ir()
    first, second = bound_compile(ir, helper_id="actualOne"), bound_compile(ir, helper_id="actualTwo")
    assert first.semantic_digest == second.semantic_digest and first.full_digest != second.full_digest


def test_declared_precondition_is_not_silently_ignored_by_runtime():
    ir = public_ir()
    steps = list(ir.steps)
    steps[-1] = steps[-1].model_copy(update={"precondition": {"account_locked": False}})
    compiled = bound_compile(ir.model_copy(update={"steps": steps}))
    assert not compiled.deployable
    assert "PRIMITIVE_CONTRACT_INVALID:s_evid03:DSL_PREDICATE_INVALID" in compiled.readiness_errors


def test_supported_mutation_cannot_be_deployed_under_read_authority():
    ir = public_ir()
    steps = list(ir.steps)
    steps[-1] = steps[-1].model_copy(update={"action_class": ActionClass.A1,
        "effects": [WorkflowStepEffect.READ],
        "postcondition": None})
    compiled = bound_compile(ir.model_copy(update={"steps": steps}))
    assert not compiled.deployable
    assert any(error.startswith("PRIMITIVE_ACTION_CLASS_UNDERDECLARED:s_evid03") for error in compiled.readiness_errors)


@pytest.mark.parametrize("endpoint", ["http://127.0.0.1:8079/v1/automation/worker/step", "https://8.8.8.8/v1/automation/worker/step", "https://worker.internal/v1/automation/worker/step"])
async def test_worker_endpoint_cannot_provision_unusable_or_public_callback(candidate, endpoint):
    with pytest.raises(ValueError, match="private_worker_endpoint"):
        await candidate[-1].provision(candidate[3].artifact_id, endpoint)
    assert not candidate[4].requests


async def _api(candidate):
    from types import SimpleNamespace
    store, registry, _ir, _artifact, _manager, client, settings, _provisioner = candidate
    authority = CommandAuthorityService(store)
    dispatcher = SimpleNamespace(client=client, actions=ActionRuntime(store))
    api = AutomationApi(store, settings, registry=registry, hot_index=HotWorkflowIndex(),
        standing=StandingAutomationAuthorityService(store, authority), policy=policy_with_domains(DOMAIN), dispatcher=dispatcher)
    app = FastAPI()
    app.include_router(api.router)
    return api, AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


async def test_provision_validate_activate_readback_then_atomic_admission(candidate):
    store, registry, ir, artifact, manager, _client, _settings, _provisioner = candidate
    api, ac = await _api(candidate)
    headers = {"X-Van-Internal-Token": INTERNAL}
    async with ac:
        response = await ac.post(f"/v1/automation/workflows/{artifact.artifact_id}/provision", headers=headers)
        assert response.status_code == 200, response.text
        for expected, target in [("PROPOSED", "QUARANTINED"), ("QUARANTINED", "VALIDATED"), ("VALIDATED", "ADMITTED")]:
            response = await ac.post("/v1/automation/admit", headers=headers, json={"artifact_id": artifact.artifact_id,"expected":expected,"target":target})
            assert response.status_code == 200, response.text
    cap = await registry.get_capability(artifact.capability_id)
    definition = await api.dispatcher.actions.get_definition(f"automation.workflow.{cap.capability_id}")
    current = await registry.get_artifact(artifact.artifact_id)
    assert cap.lifecycle_state is WorkflowLifecycle.ADMITTED and cap.action_class == definition.action_class == ir.action_class
    assert cap.workflow_ir_digest == digest(ir.semantic_payload()) and cap.runtime_workflow_ref == current.n8n_workflow_id
    assert manager.workflows[current.n8n_workflow_id]["active"] is True


async def test_failed_activation_readback_never_admits_capability(candidate):
    _store, registry, _ir, artifact, manager, _client, _settings, provisioner = candidate
    await provisioner.provision(artifact.artifact_id, ENDPOINT)
    await registry.transition(artifact.artifact_id, expected=WorkflowLifecycle.PROPOSED, target=WorkflowLifecycle.QUARANTINED)
    await registry.transition(artifact.artifact_id, expected=WorkflowLifecycle.QUARANTINED, target=WorkflowLifecycle.VALIDATED)
    manager.activation_visible = False
    _api_object, ac = await _api(candidate)
    async with ac:
        response = await ac.post("/v1/automation/admit", headers={"X-Van-Internal-Token": INTERNAL},
            json={"artifact_id":artifact.artifact_id,"expected":"VALIDATED","target":"ADMITTED"})
    assert response.status_code == 409 and response.json()["detail"] == "WORKFLOW_ACTIVATION_READBACK_MISMATCH"
    assert (await registry.get_artifact(artifact.artifact_id)).lifecycle_state is WorkflowLifecycle.VALIDATED


async def test_illegal_transition_has_no_management_effect(candidate):
    _api_object, ac = await _api(candidate)
    async with ac:
        response = await ac.post("/v1/automation/admit", headers={"X-Van-Internal-Token": INTERNAL},
            json={"artifact_id":candidate[3].artifact_id,"expected":"PROPOSED","target":"ADMITTED"})
    assert response.status_code == 409 and "illegal_transition" in response.json()["detail"]
    assert not candidate[4].requests


async def test_helper_edit_under_same_id_refuses_admission_and_reuse(candidate):
    _store, registry, _ir, artifact, manager, _client, _settings, provisioner = candidate
    deployed = await provisioner.provision(artifact.artifact_id, ENDPOINT)
    helper_id = next(iter(deployed["dependencies"]))
    manager.workflows[helper_id]["nodes"][1]["parameters"]["url"] = "https://8.8.8.8/exfiltrate"
    with pytest.raises(ProvisioningError, match="N8N_RUNTIME_HELPER_DRIFT"):
        await provisioner.provision(artifact.artifact_id, ENDPOINT)
    await registry.transition(artifact.artifact_id, expected=WorkflowLifecycle.PROPOSED, target=WorkflowLifecycle.QUARANTINED)
    await registry.transition(artifact.artifact_id, expected=WorkflowLifecycle.QUARANTINED, target=WorkflowLifecycle.VALIDATED)
    _api_object, ac = await _api(candidate)
    async with ac:
        response = await ac.post("/v1/automation/admit", headers={"X-Van-Internal-Token": INTERNAL},
            json={"artifact_id":artifact.artifact_id,"expected":"VALIDATED","target":"ADMITTED"})
    assert response.status_code == 409 and response.json()["detail"] == "N8N_RUNTIME_HELPER_DRIFT"
    assert (await registry.get_artifact(artifact.artifact_id)).lifecycle_state is WorkflowLifecycle.VALIDATED
    assert not any(request.url.path.endswith("/activate") for request in manager.requests)


def test_engine_failure_flags_and_modified_credential_are_graph_drift():
    graph = bound_compile(public_ir()).n8n_graph
    changed = copy.deepcopy(graph)
    changed["nodes"][1]["credentials"]["httpHeaderAuth"]["id"] = "owner-authority-token"
    assert not graph_matches(graph, changed)
    changed = copy.deepcopy(graph)
    changed["nodes"][-1]["continueOnFail"] = True
    assert not graph_matches(graph, changed)
