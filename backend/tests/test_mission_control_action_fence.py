"""A pause arriving after authorization prevents actual execution admission."""
from __future__ import annotations

import asyncio
import json

import pytest

from conftest_automation import enroll_device, make_store, seal_owner_command
from van_gateway.action.models import ActionDefinition, ExecutionStatus, VerifierType
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.command.authority import CommandAuthorityError, CommandAuthorityService
from van_gateway.mission.control import MissionExecutionControlService
from van_gateway.models import ActionClass, PrincipalType

ACTION = ActionDefinition(action_id="test.bounded.effect", action_class=ActionClass.A3,
                          mutates_state=True, allowed_principals={PrincipalType.OWNER_DEVICE},
                          verifier_type=VerifierType.NONE)


@pytest.fixture
async def execution(tmp_path):
    store = await make_store(tmp_path)
    await enroll_device(store)
    authority = CommandAuthorityService(store)
    record = await seal_owner_command(authority, command_id="command", typed_action_id=None)
    await store.execute(
        "INSERT INTO missions(mission_id,owner_principal_id,origin,origin_channel,title,goal,state,"
        "authority_envelope_json,created_at_ms,updated_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("mission", "device:dev-owner-1", "OWNER_UI", "UI", "Bounded effect", "Finish existing command", "RUNNING",
         json.dumps({"source_command_id":"command"}), 1, 1),
    )
    runtime = ActionRuntime(store)
    await runtime.register(ACTION)
    # Context is a real foreign key in the ledger even for an isolated unit action.
    await store.execute(
        "INSERT INTO context_snapshots(snapshot_id,command_id,kernel_revision,fact_ids_json,graph_evidence_refs_json,live_state_refs_json,policy_refs_json,compiled_at_ms,digest) VALUES (?, ?, 1,'[]','[]','[]','[]',1,'digest')",
        (record.snapshot_id, "command"),
    )
    current = await runtime.begin(execution_id="effect", command_id="command", turn_id=record.turn_id,
        action_id=ACTION.action_id, principal_type=record.principal_type, requested_by=record.requested_by,
        idempotency_key="effect-idempotency-key", parameters={}, snapshot_id=record.snapshot_id, owner_approved=False)
    assert current.status is ExecutionStatus.AUTHORIZED
    return store, runtime, authority, record, MissionExecutionControlService(store)


async def check_authority(authority, record):
    return await authority.authorize_action(command_id=record.command_id, action=ACTION,
        principal_type=record.principal_type, requested_by=record.requested_by,
        snapshot_id=record.snapshot_id, turn_id=record.turn_id, parameters={})


async def pause(controls, generation=0, operation="PAUSE", request_id="owner-pause-1"):
    return await controls.request(mission_id="mission", request_id=request_id,
        operation=operation, expected_generation=generation, requested_by="device:dev-owner-1")


async def test_pause_after_authorization_refuses_action_without_executing_write_then_resume_admits(execution):
    store, runtime, authority, record, controls = execution
    await check_authority(authority, record)
    before = await runtime.get_execution("effect")
    await pause(controls)
    with pytest.raises(CommandAuthorityError, match="MISSION_DISPATCH_PAUSED"):
        await check_authority(authority, record)
    with pytest.raises(ActionPolicyError, match="MISSION_DISPATCH_PAUSED"):
        await runtime.mark_executing("effect")
    assert await runtime.get_execution("effect") == before
    await pause(controls, generation=1, operation="RESUME", request_id="owner-resume-1")
    accepted, _ = await check_authority(authority, record)
    assert accepted == record
    assert (await runtime.mark_executing("effect")).status is ExecutionStatus.EXECUTING


async def test_pause_writer_commit_precedes_waiting_execution_writer_and_refuses(execution):
    store, runtime, _, _, controls = execution
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("INSERT INTO mission_execution_controls(mission_id,generation,desired_execution,updated_at_ms) VALUES('mission',1,'PAUSED',1)")
        pending = asyncio.create_task(runtime.mark_executing("effect"))
        done, _ = await asyncio.wait({pending}, timeout=0.02)
        assert not done
        await db.commit()
    with pytest.raises(ActionPolicyError, match="MISSION_DISPATCH_PAUSED"):
        await pending
    assert (await runtime.get_execution("effect")).status is ExecutionStatus.AUTHORIZED


async def test_terminal_mission_keeps_existing_authority_error_contract(execution):
    store, runtime, authority, record, _ = execution
    await store.execute("UPDATE missions SET state='CANCELLED' WHERE mission_id='mission'")
    with pytest.raises(CommandAuthorityError, match="command_mission_terminal"):
        await check_authority(authority, record)
    with pytest.raises(ActionPolicyError, match="command_mission_terminal"):
        await runtime.mark_executing("effect")
    assert (await runtime.get_execution("effect")).status is ExecutionStatus.AUTHORIZED
