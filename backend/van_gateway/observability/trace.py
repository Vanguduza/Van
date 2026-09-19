"""The join an operator had to do by hand.

P2-OBS-001's cost is not that a correlation id was missing — it is what the
missing id made expensive. To answer "what happened to the thing I asked for" an
operator had to open the SQLite file and join `audit` on `command_id`, then
`missions` on `json_extract(authority_envelope_json, '$.source_command_id')`,
then `mission_events` and `mission_activities` on `mission_id`, then
`action_executions` back on `command_id`, then `action_receipts` on
`execution_id`. Six joins across five tables, two of them through JSON.

`CommandTrace` is that query, written once, returning the chain the blueprint
names: command -> mission -> Hermes run -> execution -> verification -> outcome.
Everything in it is keyed by one correlation id, and because the correlation id
is derived from the command id (see `correlation.py`) the trace works on rows
written before any of this existed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from van_gateway.observability.correlation import for_command
from van_gateway.storage.db import Store


@dataclass
class CommandTrace:
    correlation_id: str
    command_id: str
    audit: list[dict[str, Any]] = field(default_factory=list)
    missions: list[dict[str, Any]] = field(default_factory=list)
    mission_events: list[dict[str, Any]] = field(default_factory=list)
    activities: list[dict[str, Any]] = field(default_factory=list)
    executions: list[dict[str, Any]] = field(default_factory=list)
    receipts: list[dict[str, Any]] = field(default_factory=list)
    context_snapshots: list[dict[str, Any]] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(
            self.audit or self.missions or self.executions or self.context_snapshots
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "command_id": self.command_id,
            "found": self.found,
            "audit": self.audit,
            "missions": self.missions,
            "mission_events": self.mission_events,
            "activities": self.activities,
            "executions": self.executions,
            "receipts": self.receipts,
            "context_snapshots": self.context_snapshots,
        }


#: Columns are listed rather than `SELECT *` so a later migration that adds a
#: secret-bearing column does not silently start returning it on this route.
_AUDIT_COLUMNS = (
    "id, command_id, device_id, project_id, capability, approval, tool, result, "
    "failure_reason, evidence_pointer, created_at_unix, chain_seq"
)
_MISSION_COLUMNS = (
    "mission_id, owner_principal_id, project_id, origin, origin_channel, title, "
    "state, final_outcome, verification_state, created_at_ms, updated_at_ms, "
    "context_snapshot_id"
)
_EVENT_COLUMNS = (
    "event_id, mission_id, activity_id, event_type, actor, occurred_at_ms, severity, "
    "owner_visibility, summary, evidence_ref"
)
_ACTIVITY_COLUMNS = (
    "activity_id, mission_id, activity_type, capability_id, executor, executor_ref, "
    "state, attempt, started_at_ms, ended_at_ms, error_class"
)
_EXECUTION_COLUMNS = (
    "execution_id, command_id, turn_id, action_id, action_class, principal_type, "
    "requested_by, status, snapshot_id, submitted_at_ms, verified_at_ms, "
    "evidence_pointer, error_code, updated_at_unix_ms"
)
_RECEIPT_COLUMNS = (
    "receipt_id, execution_id, status, verifier_type, evidence_pointer, created_at_unix_ms"
)


class CommandTracer:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    async def _rows(db, sql: str, params: tuple) -> list[dict[str, Any]]:
        cursor = await db.execute(sql, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def trace(self, command_id: str) -> CommandTrace:
        trace = CommandTrace(correlation_id=for_command(command_id), command_id=command_id)
        async with self.store.connection() as db:
            trace.audit = await self._rows(
                db,
                f"SELECT {_AUDIT_COLUMNS} FROM audit WHERE command_id = ? "
                "ORDER BY COALESCE(chain_seq, 0), created_at_unix",
                (command_id,),
            )
            trace.missions = await self._rows(
                db,
                f"SELECT {_MISSION_COLUMNS} FROM missions "
                "WHERE json_extract(authority_envelope_json, '$.source_command_id') = ? "
                "ORDER BY created_at_ms",
                (command_id,),
            )
            mission_ids = [row["mission_id"] for row in trace.missions]
            if mission_ids:
                placeholders = ",".join("?" for _ in mission_ids)
                trace.mission_events = await self._rows(
                    db,
                    f"SELECT {_EVENT_COLUMNS} FROM mission_events "
                    f"WHERE mission_id IN ({placeholders}) ORDER BY occurred_at_ms",
                    tuple(mission_ids),
                )
                trace.activities = await self._rows(
                    db,
                    f"SELECT {_ACTIVITY_COLUMNS} FROM mission_activities "
                    f"WHERE mission_id IN ({placeholders}) ORDER BY started_at_ms",
                    tuple(mission_ids),
                )
            trace.executions = await self._rows(
                db,
                f"SELECT {_EXECUTION_COLUMNS} FROM action_executions "
                "WHERE command_id = ? ORDER BY updated_at_unix_ms",
                (command_id,),
            )
            execution_ids = [row["execution_id"] for row in trace.executions]
            if execution_ids:
                placeholders = ",".join("?" for _ in execution_ids)
                trace.receipts = await self._rows(
                    db,
                    f"SELECT {_RECEIPT_COLUMNS} FROM action_receipts "
                    f"WHERE execution_id IN ({placeholders}) ORDER BY created_at_unix_ms",
                    tuple(execution_ids),
                )
            trace.context_snapshots = await self._rows(
                db,
                "SELECT snapshot_id, command_id, kernel_revision, compiled_at_ms, digest "
                "FROM context_snapshots "
                "WHERE command_id = ? ORDER BY compiled_at_ms",
                (command_id,),
            )
        return trace


__all__ = ["CommandTrace", "CommandTracer"]
