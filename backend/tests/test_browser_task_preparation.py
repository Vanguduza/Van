"""Canonical owner command Mission preparation is bounded, read-only and durable."""
import time
import pytest
from test_browser_producer_api import fabric, ready, NOW, PID, PRINCIPAL
from van_gateway.action.service import ActionRuntime
from van_gateway.browser.task_preparation import BrowserTaskPreparationService, PREPARE_ACTION
from van_gateway.browser.action_plans import PlanError
from van_gateway.browser.service import BrowserTaskService
from van_gateway.command.authority import CommandAuthorityService, CommandAuthorityRecord
from van_gateway.models import ActionClass, PrincipalType, OriginChannel
from van_gateway.mission.models import MissionOrigin, AuthorityEnvelope
from van_gateway.mission.service import MissionService
from van_gateway.mission.binding import MissionBinder


async def preparation(f, monkeypatch):
    monkeypatch.setattr(time,"time",lambda:NOW/1000)
    await ready(f)
    await f.producers.observe(producer_session_id=PID,principal=PRINCIPAL,event="target",target_id="tab",
        url="https://example.org/path?private=never-persisted",now_ms=NOW)
    parameters={"session_id":f.session.session_id,"target_domain":"example.org","goal":"Review the current page before choosing exact effects"}
    authority=CommandAuthorityService(f.store)
    await authority.seal(CommandAuthorityRecord(command_id="prepare",device_id="phone",principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="phone",origin_channel=OriginChannel.UI,signed_action_class=ActionClass.A3,effective_action_class=ActionClass.A3,
        typed_action_id=PREPARE_ACTION.action_id,typed_parameter_constraints=parameters,snapshot_id="prepare-snapshot",
        context_digest="digest",issued_at_unix=NOW//1000,expires_at_unix=NOW//1000+30,sealed_at_unix_ms=NOW))
    await f.store.execute("INSERT INTO context_snapshots(snapshot_id,command_id,kernel_revision,fact_ids_json,graph_evidence_refs_json,live_state_refs_json,policy_refs_json,compiled_at_ms,digest) VALUES('prepare-snapshot','prepare',1,'[]','[]','[]','[]',?,'digest')",(NOW,))
    runtime=ActionRuntime(f.store)
    await runtime.register(PREPARE_ACTION)
    execution=await runtime.begin(execution_id="prepare-execution",command_id="prepare",turn_id=None,action_id=PREPARE_ACTION.action_id,
        principal_type=PrincipalType.OWNER_DEVICE,requested_by="phone",idempotency_key="prepare-key",parameters=parameters,
        snapshot_id="prepare-snapshot",owner_approved=False)
    await f.store.execute("UPDATE action_executions SET status='EXECUTING' WHERE execution_id=?",(execution.execution_id,))
    execution=await runtime.get_execution(execution.execution_id)
    missions=MissionService(f.store)
    mission=await missions.create(owner_principal_id="phone",origin=MissionOrigin.OWNER_UI,origin_channel=OriginChannel.UI,
        title="Prepare current browser task",goal=parameters["goal"],authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A3,
        source_command_id="prepare"),now_ms=NOW)
    await f.store.execute("UPDATE missions SET state='RUNNING' WHERE mission_id=?",(mission.mission_id,))
    service=BrowserTaskPreparationService(store=f.store,sessions=f.sessions,producers=f.producers,tasks=BrowserTaskService(f.store),
        binder=MissionBinder(f.store,missions),command_authority=authority)
    return service,execution,parameters,mission


async def test_signed_preparation_binds_existing_mission_and_nonmutating_task_without_delegation(fabric,monkeypatch):
    service,execution,parameters,mission=await preparation(fabric,monkeypatch)
    result=await service.prepare(execution,parameters,mission.mission_id)
    assert result["success"] is True and result["mission_pending"] is True
    assert result["worker_started"] is False and result["control_delegated"] is False
    assert (await fabric.sessions.get(fabric.session.session_id)).mission_id == mission.mission_id
    task=await fabric.store.fetchone("SELECT * FROM browser_tasks WHERE task_id=?",(result["task_id"],))
    assert task["action_class"] == "A1" and task["status"] == "PENDING"
    assert (await fabric.store.fetchone("SELECT state FROM missions WHERE mission_id=?",(mission.mission_id,)))["state"] == "RUNNING"
    assert len(await fabric.store.fetchall("SELECT * FROM mission_activities WHERE mission_id=?",(mission.mission_id,))) == 2
    await service.prepare(execution,parameters,mission.mission_id)
    assert len(await fabric.store.fetchall("SELECT * FROM browser_tasks")) == 1
    origin=await fabric.store.fetchone("SELECT value FROM runtime_meta WHERE key LIKE 'browser_target_origin:%'")
    assert "private=never-persisted" not in origin["value"]
    assert not await fabric.store.fetchall("SELECT * FROM browser_control_producer_grants")


async def test_caller_cannot_supply_another_mission_or_change_domain(fabric,monkeypatch):
    service,execution,parameters,mission=await preparation(fabric,monkeypatch)
    with pytest.raises(PlanError,match="canonical_mission_mismatch"):
        await service.prepare(execution,parameters,"foreign-mission")
    with pytest.raises(ValueError,match="typed_parameter_mismatch"):
        await service.prepare(execution,{**parameters,"target_domain":"foreign.example"},mission.mission_id)
    assert not await fabric.store.fetchall("SELECT * FROM browser_tasks")


async def test_device_revocation_prevents_preparation_before_task_creation(fabric,monkeypatch):
    service,execution,parameters,mission=await preparation(fabric,monkeypatch)
    await fabric.store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='phone'")
    with pytest.raises(ValueError,match="revoked"):
        await service.prepare(execution,parameters,mission.mission_id)
    assert not await fabric.store.fetchall("SELECT * FROM browser_tasks")
