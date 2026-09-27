from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.computer_use.fabric import (
    ComputerInteractionFabric, ComputerUseError, OperationRequest, OperationState,
    OperationType, Surface,
)
from van_gateway.computer_use.lease import ComputerWorkerLeaseError, ComputerWorkerLeaseService
from van_gateway.computer_use.worker import (
    ComputerWorkerOutcomeUnknown, ComputerWorkerResult,
)
from van_gateway.models import ActionClass


class GoodWorker:
    async def status(self):
        return {"ready": True, "state": "READY"}

    async def execute(self, operation_id, request, lease):
        return ComputerWorkerResult(
            result={"operation_id": operation_id, "stdout": "ok"},
            output_sha256="a" * 64, exit_code=0,
        )


class UnknownWorker:
    async def execute(self, operation_id, request, lease):
        raise ComputerWorkerOutcomeUnknown("COMPUTER_OUTCOME_UNKNOWN")


class LeaseStealingWorker:
    def __init__(self, leases):
        self.leases = leases
        self.replacement = None

    async def execute(self, operation_id, request, lease):
        await self.leases.release(lease, now_ms=20)
        self.replacement = await self.leases.acquire(
            request.surface.value, "replacement", now_ms=21
        )
        return ComputerWorkerResult(
            result={"late": True}, output_sha256="b" * 64, exit_code=0,
        )


def terminal_request(op=OperationType.READ_TEXT, *, verifier="NONE"):
    return OperationRequest(
        mission_id="m1", surface=Surface.TERMINAL, target_application="owner-workspace",
        operation_type=op, action_class=ActionClass.A2 if not op.mutates else ActionClass.A3,
        verifier_type=verifier, scope={"path": "/workspace/readme.txt"},
    )


@pytest.mark.asyncio
async def test_worker_lease_generation_fences_stale_executor(tmp_path):
    store = await make_store(tmp_path)
    leases = ComputerWorkerLeaseService(store, ttl_ms=1000)
    first = await leases.acquire("TERMINAL", "op1", now_ms=10)
    await leases.release(first, now_ms=20)
    second = await leases.acquire("TERMINAL", "op2", now_ms=21)
    assert second.generation == first.generation + 1
    with pytest.raises(ComputerWorkerLeaseError, match="COMPUTER_WORKER_LOST_LEASE"):
        await leases.assert_active(first, now_ms=22)


@pytest.mark.asyncio
async def test_fabric_executes_registered_worker_and_seals_receipt(tmp_path):
    store = await make_store(tmp_path)
    fabric = ComputerInteractionFabric(
        store, worker_impls={Surface.TERMINAL: GoodWorker()}
    )
    result = await fabric.execute_operation(terminal_request())
    assert result["state"] == "COMPLETED"
    assert result["evidence_ref"].startswith("computer-receipt://")
    rows = await fabric.for_mission("m1")
    assert rows[0]["state"] == "COMPLETED"
    receipt = await store.fetchone(
        "SELECT * FROM computer_worker_receipts WHERE operation_id = ?",
        (result["operation_id"],),
    )
    assert receipt is not None and receipt["output_sha256"] == "a" * 64


@pytest.mark.asyncio
async def test_stale_worker_cannot_publish_completion(tmp_path):
    store = await make_store(tmp_path)
    leases = ComputerWorkerLeaseService(store)
    worker = LeaseStealingWorker(leases)
    fabric = ComputerInteractionFabric(
        store, worker_impls={Surface.TERMINAL: worker}
    )
    fabric.worker_leases = leases
    with pytest.raises(ComputerUseError, match="COMPUTER_WORKER_LOST_LEASE"):
        await fabric.execute_operation(terminal_request(), now_ms=10)
    rows = await fabric.for_mission("m1")
    assert rows[0]["state"] == OperationState.FAILED.value
    assert rows[0]["evidence_ref"] is None
    if worker.replacement is not None:
        await leases.release(worker.replacement, now_ms=30)


@pytest.mark.asyncio
async def test_unknown_mutation_outcome_is_not_reported_failed_or_success(tmp_path):
    store = await make_store(tmp_path)
    fabric = ComputerInteractionFabric(
        store, worker_impls={Surface.TERMINAL: UnknownWorker()}
    )
    req = terminal_request(OperationType.WRITE_TEXT, verifier="READ_BACK")
    with pytest.raises(ComputerUseError, match="OPERATION_OUTCOME_UNKNOWN"):
        await fabric.execute_operation(req)
    rows = await fabric.for_mission("m1")
    assert rows[0]["state"] == OperationState.OUTCOME_UNKNOWN.value
    assert rows[0]["evidence_ref"] is None
