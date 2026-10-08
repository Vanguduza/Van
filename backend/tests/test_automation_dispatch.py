"""Rev 1.3 §§80-82, 165-167, 223, 422-423 — dispatch through the Action Runtime.

The property that matters most here is the one `config/automation/policy.yaml`
states as `engine_success_is_owner_success: false`: n8n reporting success is an
engine claim, and VAN only reports VERIFIED_SUCCESS when an independent observer
confirms the declared postcondition.
"""

from __future__ import annotations

import httpx
import pytest

from automation_runtime_fixture import StatefulN8n, seed_runtime

from conftest_automation import (
    enroll_device,
    make_action_runtime,
    make_store,
    seal_owner_command,
    seed_snapshot,
)
from van_gateway.action.models import ActionDefinition, ExecutionStatus, VerifierType
from van_gateway.action.service import ActionPolicyError
from van_gateway.automation.dispatch import AutomationDispatcher, DispatchError
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry, ReadinessEvidence
from van_gateway.automation.grants import RunGrantService
from van_gateway.automation.models import RunStatus
from van_gateway.automation.n8n_client import N8nManagementClient
from van_gateway.automation.registry import AutomationRegistry
from van_gateway.automation.verifier import (
    PostconditionSpec,
    VerificationOutcome,
    WorkflowVerifier,
)
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.models import ActionClass, PrincipalType

SIGNING_KEY = "dispatch-test-signing-key"
ACTION_ID = "automation.workflow.wfcap_statements"


class _Observer:
    """Stands in for the independent look at the target system."""

    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls = 0

    async def observe(self, spec, context):
        self.calls += 1
        return self.result


async def _build(tmp_path, *, observer: _Observer | None = None, engine_success: bool = True):
    store = await make_store(tmp_path)
    await enroll_device(store)
    authority = CommandAuthorityService(store)
    await seal_owner_command(authority, effective=ActionClass.A3)
    await seed_snapshot(store, "ctx-owner-1", "cmd-owner-1")

    actions = await make_action_runtime(store)
    await actions.register(
        ActionDefinition(
            action_id=ACTION_ID,
            action_class=ActionClass.A2,
            mutates_state=False,
            allowed_principals={
                PrincipalType.OWNER_DEVICE,
                PrincipalType.HERMES_AGENT,
                PrincipalType.AUTOMATION,
            },
            verifier_type=VerifierType.READ_BACK,
        )
    )

    registry = AutomationRegistry(store)
    # These tests provide their independent postcondition explicitly. An empty
    # IR verifier retains that contract while binding a real public read workflow
    # to its exact compiled graph, immutable hashes and deployed manager ID.
    _ir, compiled, artifact = await seed_runtime(store, registry, read_only=True, verifier={})
    engine = StatefulN8n(engine_success=engine_success)
    engine.seed(artifact.n8n_workflow_id, compiled.n8n_graph, active=True)

    runtime_registry = ExternalRuntimeRegistry(store)
    await runtime_registry.record_evidence(
        ReadinessEvidence(
            capability="n8n", evidence_pointer="gateway://automation/cert/1",
            runtime_version="2.39.7",
        )
    )
    client = N8nManagementClient(
        runtime_registry, base_url="http://127.0.0.1:5678/api/v1", api_key="k",
        enabled=True, expected_version="2.39.7", transport=engine.transport,
    )
    verifier = WorkflowVerifier({"READ_BACK": observer} if observer else {})
    dispatcher = AutomationDispatcher(
        store, actions=actions, authority=authority, registry=registry,
        grants=RunGrantService(store, signing_key=SIGNING_KEY), client=client,
        verifier=verifier, enabled=True,
    )
    return store, dispatcher


async def test_verified_run_reports_owner_success(tmp_path):
    observer = _Observer({"exists": True, "evidence_pointer": "gateway://evidence/1"})
    _store, dispatcher = await _build(tmp_path, observer=observer)
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={"broker_alias": "primary_mt5"},
        postcondition=PostconditionSpec(kind="READ_BACK", field=None),
    )
    assert result.status is RunStatus.VERIFIED_SUCCESS
    assert result.owner_success is True
    assert observer.calls == 1


async def test_engine_success_without_postcondition_is_not_owner_success(tmp_path):
    """§§21, 80 — 'the workflow ran' is not 'the thing happened'."""
    _store, dispatcher = await _build(tmp_path, observer=None)
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
        postcondition=None,
    )
    assert result.status is RunStatus.UNVERIFIABLE
    assert result.owner_success is False


async def test_engine_success_but_absent_postcondition_fails(tmp_path):
    """The engine says yes; the world says no. The world wins."""
    observer = _Observer({"exists": False})
    _store, dispatcher = await _build(tmp_path, observer=observer, engine_success=True)
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
        postcondition=PostconditionSpec(kind="READ_BACK"),
    )
    assert result.status is RunStatus.FAILED
    assert result.verification_outcome is VerificationOutcome.FAILED


async def test_incomplete_correlation_is_partial(tmp_path):
    """§166 — something exists, but we cannot prove it is ours."""
    observer = _Observer({"exists": True, "receipt_id": None})
    _store, dispatcher = await _build(tmp_path, observer=observer)
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
        postcondition=PostconditionSpec(kind="READ_BACK", correlation_keys=["receipt_id"]),
    )
    assert result.status is RunStatus.PARTIAL_SUCCESS


async def test_dispatch_disabled_fails_closed(tmp_path):
    _store, dispatcher = await _build(tmp_path)
    dispatcher.enabled = False
    with pytest.raises(DispatchError) as exc:
        await dispatcher.dispatch(
            capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
            principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
            snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
        )
    assert exc.value.code == "AUTOMATION_FABRIC_DISABLED"


async def test_unadmitted_capability_never_dispatches(tmp_path):
    """§36 — nothing executes before admission."""
    store, dispatcher = await _build(tmp_path)
    await store.execute(
        "UPDATE automation_artifacts SET lifecycle_state = 'PROPOSED' WHERE capability_id = ?",
        ("wfcap_statements",),
    )
    with pytest.raises(DispatchError) as exc:
        await dispatcher.dispatch(
            capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
            principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
            snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
        )
    assert exc.value.code == "CAPABILITY_NOT_ADMITTED"


async def test_missing_command_authority_denies_dispatch(tmp_path):
    """§223 — the Action Runtime, not the dispatcher, is the authority."""
    _store, dispatcher = await _build(tmp_path)
    with pytest.raises(DispatchError) as exc:
        await dispatcher.dispatch(
            capability_id="wfcap_statements", action_id=ACTION_ID,
            command_id="cmd-does-not-exist", principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="dev-owner-1", snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
        )
    assert exc.value.code == "AUTHORITY_DENIED"


async def test_snapshot_mismatch_denies_dispatch(tmp_path):
    _store, dispatcher = await _build(tmp_path)
    with pytest.raises(DispatchError) as exc:
        await dispatcher.dispatch(
            capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
            principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
            snapshot_id="ctx-someone-elses", turn_id="turn-1", inputs={},
        )
    assert exc.value.code == "AUTHORITY_DENIED"


async def test_unready_runtime_blocks_execution(tmp_path):
    """§369 — an unproven runtime cannot execute owner work."""
    store, dispatcher = await _build(tmp_path)
    await ExternalRuntimeRegistry(store).clear_evidence("n8n")
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
    )
    assert result.status is RunStatus.FAILED
    assert result.error_code == "AUTOMATION_FABRIC_UNAVAILABLE"


async def test_run_is_recorded_with_execution_linkage(tmp_path):
    observer = _Observer({"exists": True})
    store, dispatcher = await _build(tmp_path, observer=observer)
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
        postcondition=PostconditionSpec(kind="READ_BACK"),
    )
    row = await store.fetchone(
        "SELECT * FROM automation_runs WHERE run_id = ?", (result.run_id,)
    )
    assert row is not None
    assert row["execution_id"] == f"exec_{result.run_id}"
    assert row["n8n_execution_id"] == "n8n-exec-1"
    assert result.execution is not None
    assert result.execution.status is ExecutionStatus.VERIFIED_SUCCESS


@pytest.mark.parametrize("failure,code", [
    (httpx.ReadTimeout("private implementation detail"), "N8N_TIMEOUT"),
    (httpx.ConnectError("private implementation detail"), "N8N_UNREACHABLE"),
])
async def test_engine_transport_failure_closes_run_action_and_grant(tmp_path, failure, code):
    store, dispatcher = await _build(tmp_path)
    original = dispatcher.client.transport.handler
    posts = []

    def handler(request):
        if request.method == "POST":
            posts.append(request)
            raise failure
        return original(request)

    dispatcher.client.transport = httpx.MockTransport(handler)
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
    )
    assert len(posts) == 1
    assert result.status is RunStatus.FAILED
    assert result.error_code == code
    assert result.execution.status is ExecutionStatus.EXECUTION_FAILED
    assert result.execution.error_code == code
    row = await store.fetchone("SELECT status, error_code FROM automation_runs WHERE run_id = ?", (result.run_id,))
    assert row["status"] == "FAILED" and row["error_code"] == code
    nonce = await store.fetchone("SELECT status FROM automation_run_nonces WHERE run_id = ?", (result.run_id,))
    assert nonce["status"] == "REVOKED"


async def test_unconfigured_grant_signer_does_not_leave_an_authorized_action_or_call_n8n(tmp_path):
    store, dispatcher = await _build(tmp_path)
    dispatcher.grants = RunGrantService(store, signing_key="")
    requests = []
    dispatcher.client.transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(500))
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
    )
    assert requests == []
    assert result.status is RunStatus.FAILED
    assert result.error_code == "GRANT_SIGNING_KEY_UNCONFIGURED"
    assert result.execution.status is ExecutionStatus.PRECONDITION_FAILED


async def test_unknown_action_does_not_create_an_orphan_pending_run(tmp_path):
    store, dispatcher = await _build(tmp_path)
    with pytest.raises(DispatchError) as raised:
        await dispatcher.dispatch(
            capability_id="wfcap_statements", action_id="unknown-action", command_id="cmd-owner-1",
            principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
            snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
        )
    assert raised.value.code == "UNKNOWN_ACTION"
    assert int((await store.fetchone("SELECT COUNT(*) AS n FROM automation_runs"))["n"]) == 0


async def test_registered_action_cannot_replace_the_canonical_workflow_action(tmp_path):
    store, dispatcher = await _build(tmp_path)
    unbound_id = "automation.trading.statement.collect"
    await dispatcher.actions.register(ActionDefinition(action_id=unbound_id,
        action_class=ActionClass.A2, mutates_state=False,
        allowed_principals={PrincipalType.OWNER_DEVICE}, verifier_type=VerifierType.READ_BACK))
    with pytest.raises(DispatchError) as raised:
        await dispatcher.dispatch(capability_id="wfcap_statements", action_id=unbound_id,
            command_id="cmd-owner-1", principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="dev-owner-1", snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={})
    assert raised.value.code == "WORKFLOW_TYPED_ACTION_MISMATCH"
    assert (await store.fetchone("SELECT COUNT(*) AS n FROM automation_runs"))["n"] == 0


async def test_admitted_artifact_without_immutable_runtime_binding_never_dispatches(tmp_path):
    store, dispatcher = await _build(tmp_path)
    await store.execute("DELETE FROM automation_runtime_bindings")
    with pytest.raises(DispatchError) as raised:
        await dispatcher.dispatch(capability_id="wfcap_statements", action_id=ACTION_ID,
            command_id="cmd-owner-1", principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="dev-owner-1", snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={})
    assert raised.value.code == "WORKFLOW_RUNTIME_BINDING_UNVERIFIED"
    assert (await store.fetchone("SELECT COUNT(*) AS n FROM automation_runs"))["n"] == 0


async def test_deployed_graph_drift_never_reaches_the_run_webhook(tmp_path):
    store, dispatcher = await _build(tmp_path)
    original = dispatcher.client.transport.handler
    effects = []
    def handler(request):
        if request.method == "POST":
            effects.append(request)
        response = original(request)
        if request.method == "GET" and request.url.path.startswith("/api/v1/workflows/"):
            graph = response.json()
            graph["nodes"][-1]["continueOnFail"] = True
            return httpx.Response(200, json=graph)
        return response
    dispatcher.client.transport = httpx.MockTransport(handler)
    result = await dispatcher.dispatch(capability_id="wfcap_statements", action_id=ACTION_ID,
        command_id="cmd-owner-1", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="dev-owner-1", snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={})
    assert effects == []
    assert result.status is RunStatus.FAILED
    assert result.error_code == "N8N_RUNTIME_GRAPH_DRIFT"
    assert result.execution.status is ExecutionStatus.EXECUTION_FAILED
    assert (await store.fetchone("SELECT status FROM automation_run_nonces WHERE run_id=?", (result.run_id,)))["status"] == "REVOKED"


@pytest.mark.parametrize("mutation", ["callback_url", "credential"])
async def test_admitted_helper_drift_never_reaches_the_run_webhook(tmp_path, mutation):
    store, dispatcher = await _build(tmp_path)
    engine = dispatcher.client.transport.handler.__self__
    helper = engine.workflows["helper1"]
    callback = helper["nodes"][-1]
    if mutation == "callback_url":
        callback["parameters"]["url"] = "https://127.0.0.1:8079/v1/automation/worker/different"
    else:
        callback["credentials"]["httpHeaderAuth"]["id"] = "unadmittedWorkerCredential"
    result = await dispatcher.dispatch(capability_id="wfcap_statements", action_id=ACTION_ID,
        command_id="cmd-owner-1", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="dev-owner-1", snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={})
    assert result.status is RunStatus.FAILED
    assert result.error_code == "N8N_RUNTIME_HELPER_DRIFT"
    assert result.execution.status is ExecutionStatus.EXECUTION_FAILED
    assert not any(request.method == "POST" and request.url.path.startswith("/webhook/") for request in engine.requests)
    assert any(request.url.path == "/api/v1/workflows/helper1" for request in engine.requests)
    assert (await store.fetchone("SELECT status FROM automation_run_nonces WHERE run_id=?", (result.run_id,)))["status"] == "REVOKED"


async def test_weakened_capability_and_definition_cannot_lower_actual_ir_authority(tmp_path):
    store, dispatcher = await _build(tmp_path)
    capability = await dispatcher.registry.get_capability("wfcap_statements")
    await dispatcher.registry.upsert_capability(capability.model_copy(update={"action_class": ActionClass.A1}))
    definition = await dispatcher.actions.get_definition(ACTION_ID)
    await dispatcher.actions.register(definition.model_copy(update={"action_class": ActionClass.A1}))
    with pytest.raises(DispatchError) as raised:
        await dispatcher.dispatch(capability_id="wfcap_statements", action_id=ACTION_ID,
            command_id="cmd-owner-1", principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="dev-owner-1", snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={})
    assert raised.value.code == "WORKFLOW_ACTION_CLASS_MISMATCH"
    assert (await store.fetchone("SELECT COUNT(*) AS n FROM automation_runs"))["n"] == 0
    assert (await store.fetchone("SELECT COUNT(*) AS n FROM automation_run_nonces"))["n"] == 0
    assert dispatcher.client.transport.handler.__self__.requests == []


async def test_current_capability_principal_allowlist_refuses_before_minting(tmp_path):
    store, dispatcher = await _build(tmp_path)
    await store.execute("UPDATE automation_capabilities SET allowed_principals_json='[\"HERMES_AGENT\"]' WHERE capability_id='wfcap_statements'")
    with pytest.raises(DispatchError) as raised:
        await dispatcher.dispatch(capability_id="wfcap_statements", action_id=ACTION_ID,
            command_id="cmd-owner-1", principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="dev-owner-1", snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={})
    assert raised.value.code == "WORKFLOW_PRINCIPAL_REFUSED"
    assert (await store.fetchone("SELECT COUNT(*) AS n FROM automation_runs"))["n"] == 0
    assert (await store.fetchone("SELECT COUNT(*) AS n FROM automation_run_nonces"))["n"] == 0
    assert dispatcher.client.transport.handler.__self__.requests == []


async def test_origin_allowlist_uses_the_sealed_command_channel_before_minting(tmp_path):
    store, dispatcher = await _build(tmp_path)
    await store.execute("UPDATE automation_capabilities SET allowed_origin_channels_json='[\"TEXT\"]' WHERE capability_id='wfcap_statements'")
    with pytest.raises(DispatchError) as raised:
        await dispatcher.dispatch(capability_id="wfcap_statements", action_id=ACTION_ID,
            command_id="cmd-owner-1", principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="dev-owner-1", snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={})
    assert raised.value.code == "AUTHORITY_DENIED"
    assert (await store.fetchone("SELECT status,error_code FROM automation_runs"))["status"] == "FAILED"
    assert (await store.fetchone("SELECT COUNT(*) AS n FROM automation_run_nonces"))["n"] == 0
    assert dispatcher.client.transport.handler.__self__.requests == []


async def test_mission_ended_before_execution_prevents_engine_call_and_revokes_grant(tmp_path):
    store, dispatcher = await _build(tmp_path)
    requests = []
    dispatcher.client.transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(500))

    async def no_longer_authorized(_execution_id):
        raise ActionPolicyError("command_mission_terminal")

    dispatcher.actions.mark_executing = no_longer_authorized
    result = await dispatcher.dispatch(
        capability_id="wfcap_statements", action_id=ACTION_ID, command_id="cmd-owner-1",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        snapshot_id="ctx-owner-1", turn_id="turn-1", inputs={},
    )
    assert requests == []
    assert result.error_code == "command_mission_terminal"
    assert result.execution.status is ExecutionStatus.PRECONDITION_FAILED
    assert (await store.fetchone("SELECT status FROM automation_run_nonces WHERE run_id=?", (result.run_id,)))["status"] == "REVOKED"
