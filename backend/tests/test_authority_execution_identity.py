"""Atomic first acceptance preserves immutable authority and execution identities."""
from __future__ import annotations

import asyncio
import time

import pytest

from van_gateway.action.models import ActionDefinition, ExecutionStatus, VerifierType
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.command.authority import CommandAuthorityError, CommandAuthorityRecord, CommandAuthorityService
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from van_gateway.storage.db import Store


@pytest.fixture
async def ledger(tmp_path):
    store=Store(str(tmp_path/"immutable-ledgers.sqlite"))
    await store.migrate()
    return store


def seal(snapshot="first"):
    now=int(time.time())
    return CommandAuthorityRecord(command_id="command",device_id="owner",principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:owner",origin_channel=OriginChannel.UI,signed_action_class=ActionClass.A3,
        effective_action_class=ActionClass.A3,snapshot_id=snapshot,context_digest=snapshot,
        issued_at_unix=now,expires_at_unix=now+60,sealed_at_unix_ms=now*1000)


async def test_concurrent_different_first_seals_have_one_immutable_winner(ledger):
    service=CommandAuthorityService(ledger)
    first=seal()
    second=first.model_copy(update={"snapshot_id":"second","context_digest":"second"})
    results=await asyncio.gather(service.seal(first),service.seal(second),return_exceptions=True)
    accepted=[r for r in results if not isinstance(r,Exception)]
    rejected=[r for r in results if isinstance(r,CommandAuthorityError)]
    assert len(accepted)==len(rejected)==1
    assert str(rejected[0])=="command_authority_conflict"
    assert await service.get("command")==accepted[0]
    assert len(await ledger.fetchall("SELECT * FROM runtime_meta WHERE key='command_authority:command'"))==1


async def test_identical_concurrent_seals_and_restart_recover_original(ledger):
    record=seal()
    service=CommandAuthorityService(ledger)
    assert await asyncio.gather(service.seal(record),service.seal(record))==[record,record]
    assert await CommandAuthorityService(Store(ledger.path)).seal(record)==record


async def runtime(store):
    service=ActionRuntime(store)
    await service.register(ActionDefinition(action_id="bounded.read",action_class=ActionClass.A2,
        allowed_principals={PrincipalType.OWNER_DEVICE},verifier_type=VerifierType.NONE))
    return service


def begin_args(**changes):
    result=dict(execution_id="execution",command_id="command",turn_id=None,action_id="bounded.read",
        principal_type=PrincipalType.OWNER_DEVICE,requested_by="device:owner",idempotency_key="idempotency",
        parameters={"target":"exact"},snapshot_id=None,owner_approved=False)
    result.update(changes)
    return result


async def test_different_lineage_cannot_resurrect_terminal_execution(ledger):
    service=await runtime(ledger)
    await service.begin(**begin_args())
    await service.fail_execution("execution",status=ExecutionStatus.EXECUTION_FAILED,error_code="actual-terminal-error")
    original=await service.get_execution("execution")
    with pytest.raises(ActionPolicyError,match="execution_identity_conflict"):
        await service.begin(**begin_args(command_id="other-command",idempotency_key="other-key"))
    assert await service.get_execution("execution")==original
    assert await service.begin(**begin_args())==original


@pytest.mark.parametrize("changes", [{"command_id":"other"},{"turn_id":"another-turn"},
    {"requested_by":"other-owner"},{"parameters":{"target":"different"}}])
async def test_existing_idempotency_cannot_substitute_another_identity(ledger,changes):
    service=await runtime(ledger)
    original=await service.begin(**begin_args())
    with pytest.raises(ActionPolicyError,match="idempotency_conflict"):
        await service.begin(**begin_args(**changes))
    assert await service.get_execution("execution")==original


async def test_concurrent_execution_id_collision_has_one_winner_and_no_receipt_overwrite(ledger):
    service=await runtime(ledger)
    results=await asyncio.gather(service.begin(**begin_args()),
        service.begin(**begin_args(command_id="other",idempotency_key="other-key")),return_exceptions=True)
    accepted=[r for r in results if not isinstance(r,Exception)]
    rejected=[r for r in results if isinstance(r,ActionPolicyError)]
    assert len(accepted)==len(rejected)==1 and str(rejected[0])=="execution_identity_conflict"
    assert await service.get_execution("execution")==accepted[0]


@pytest.mark.parametrize("update", ["enabled=0","action_class='A4'"])
async def test_current_definition_change_refuses_effect_without_execution_write(ledger,update):
    service=await runtime(ledger)
    original=await service.begin(**begin_args())
    await ledger.execute("UPDATE action_definitions SET "+update+" WHERE action_id='bounded.read'")
    with pytest.raises(ActionPolicyError,match="action_definition_disabled_or_changed"):
        await service.mark_executing("execution")
    assert await service.get_execution("execution")==original


@pytest.mark.parametrize("transition", ["submitted", "verifying", "failed"])
async def test_post_effect_transition_cannot_overwrite_committed_revocation(ledger, monkeypatch, transition):
    service = await runtime(ledger)
    await service.begin(**begin_args())
    await service.mark_executing("execution")
    if transition == "verifying":
        await service.mark_submitted("execution", correlation={"operation": "original"}, evidence_pointer="original-evidence")

    original_get = service.get_execution
    revoked = None

    async def read_then_revoke(execution_id):
        nonlocal revoked
        captured = await original_get(execution_id)
        if revoked is None:
            assert await service.revoke_privileged_for_device("device:owner") == 1
            revoked = await original_get(execution_id)
        return captured

    monkeypatch.setattr(service, "get_execution", read_then_revoke)
    if transition == "submitted":
        result = await service.mark_submitted("execution", correlation={"operation": "late-result"}, evidence_pointer="late-evidence")
    elif transition == "verifying":
        result = await service.mark_verifying("execution")
    else:
        result = await service.fail_execution("execution", status=ExecutionStatus.EXECUTION_FAILED,
            error_code="late-error", evidence_pointer="late-evidence")

    assert revoked is not None and revoked.status is ExecutionStatus.REVOKED
    assert result == revoked
    assert await original_get("execution") == revoked


@pytest.mark.parametrize("status", [ExecutionStatus.EXECUTION_FAILED, ExecutionStatus.PARTIAL_SUCCESS,
    ExecutionStatus.CONTEXT_INSUFFICIENT, ExecutionStatus.PRECONDITION_FAILED, ExecutionStatus.CONFLICTED_STATE])
async def test_device_revocation_preserves_existing_terminal_action_outcome(ledger, status):
    service = await runtime(ledger)
    await service.begin(**begin_args())
    original = await service.fail_execution("execution", status=status, error_code="original-terminal-error")
    assert original.terminal
    assert await service.revoke_privileged_for_device("device:owner") == 0
    assert await service.get_execution("execution") == original
