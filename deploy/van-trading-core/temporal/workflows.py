from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow


TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}


@workflow.defn(name="van-critical-durable-v1")
class VanDurableWorkflow:
    """Durable coordination state for critical VAN processes.

    This workflow intentionally owns no trading/order authority and performs no arbitrary
    network calls. Domain work remains behind existing VAN authority boundaries; Temporal
    owns the part it is good at: replay-safe state, long waits, checkpoints and recovery.
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "status": "CREATED",
            "checkpoints": [],
        }

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        self._state = {
            "workflow_id": workflow.info().workflow_id,
            "process_kind": str(request.get("process_kind", "")),
            "idempotency_key": str(request.get("idempotency_key", "")),
            "payload": dict(request.get("payload") or {}),
            "status": "RUNNING",
            "detail": "",
            "evidence_pointer": None,
            "checkpoints": [],
        }
        await workflow.execute_activity(
            "record_temporal_checkpoint",
            {
                "workflow_id": self._state["workflow_id"],
                "process_kind": self._state["process_kind"],
                "status": "RUNNING",
                "detail": "workflow_started",
            },
            start_to_close_timeout=timedelta(seconds=15),
        )

        timeout_seconds = max(1, min(int(request.get("timeout_seconds", 86_400)), 30 * 24 * 3600))
        try:
            await workflow.wait_condition(
                lambda: self._state["status"] in TERMINAL,
                timeout=timedelta(seconds=timeout_seconds),
            )
        except asyncio.TimeoutError:
            self._state["status"] = "TIMED_OUT"
            self._state["detail"] = "durable_wait_timeout"

        await workflow.execute_activity(
            "record_temporal_checkpoint",
            {
                "workflow_id": self._state["workflow_id"],
                "process_kind": self._state["process_kind"],
                "status": self._state["status"],
                "detail": self._state.get("detail", ""),
                "evidence_pointer": self._state.get("evidence_pointer"),
            },
            start_to_close_timeout=timedelta(seconds=15),
        )
        return dict(self._state)

    @workflow.signal(name="command")
    async def command(self, signal: dict[str, Any]) -> None:
        command = str(signal.get("command", "")).upper()
        detail = str(signal.get("detail", ""))[:4000]
        evidence_pointer = signal.get("evidence_pointer")
        payload = dict(signal.get("payload") or {})

        if self._state.get("status") in TERMINAL:
            return
        if command == "CHECKPOINT":
            checkpoints = list(self._state.get("checkpoints") or [])
            checkpoints.append(
                {
                    "detail": detail,
                    "evidence_pointer": evidence_pointer,
                    "payload": payload,
                }
            )
            self._state["checkpoints"] = checkpoints[-64:]
            return
        if command == "COMPLETE":
            self._state["status"] = "COMPLETED"
        elif command == "FAIL":
            self._state["status"] = "FAILED"
        elif command == "CANCEL":
            self._state["status"] = "CANCELLED"
        else:
            return
        self._state["detail"] = detail
        self._state["evidence_pointer"] = evidence_pointer

    @workflow.query(name="status")
    def status(self) -> dict[str, Any]:
        return dict(self._state)
