"""Rev 1.3 §§80-82, 165-167, 223, 422-423 — dispatch through the Action Runtime.

The property that matters most here is the one `config/automation/policy.yaml`
states as `engine_success_is_owner_success: false`: n8n reporting success is an
engine claim, and VAN only reports VERIFIED_SUCCESS when an independent observer
confirms the declared postcondition.
"""

from __future__ import annotations

import json

import httpx
import pytest

from conftest_automation import (
    enroll_device,
    make_action_runtime,
    make_store,
    sample_artifact,
    sample_capability,
    seal_owner_command,
    seed_snapshot,
)
from van_gateway.action.models import ActionDefinition, ExecutionStatus, VerifierType
from van_gateway.automation.dispatch import AutomationDispatcher, DispatchError
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry, ReadinessEvidence
from van_gateway.automation.grants import RunGrantService
from van_gateway.automation.models import RunStatus, WorkflowLifecycle
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
ACTION_ID = "automation.trading.statement.collect"


class _Observer:
    """Stands in for the independent look at the target system."""

    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls = 0

    async def observe(self, spec, context):
        self.calls += 1
        return self.result


def _transport(engine_success: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/settings"):
            return httpx.Response(200, json={"versionCli": "2.39.7"})
        if request.url.path.endswith("/run"):
            body = json.loads(request.content)
            # §159/§160 — the run envelope must carry a grant, not a VAN token.
            assert body["capability_grant"], "n8n must receive a run-scoped grant"
            assert "X-Van-Internal-Token" not in request.headers
            return httpx.Response(200, json={"executionId": "n8n-exec-9", "success": engine_success})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


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
    await registry.upsert_capability(sample_capability(action_class=ActionClass.A2))
    await registry.record_artifact(sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED))

    runtime_registry = ExternalRuntimeRegistry(store)
    await runtime_registry.record_evidence(
        ReadinessEvidence(
            capability="n8n", evidence_pointer="gateway://automation/cert/1",
            runtime_version="2.39.7",
        )
    )
    client = N8nManagementClient(
        runtime_registry, base_url="http://127.0.0.1:5678/api/v1", api_key="k",
        enabled=True, expected_version="2.39.7", transport=_transport(engine_success),
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
    assert row["n8n_execution_id"] == "n8n-exec-9"
    assert result.execution is not None
    assert result.execution.status is ExecutionStatus.VERIFIED_SUCCESS
