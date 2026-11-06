"""Durable worker reports, correlated only by a gateway-observed run receipt."""
from __future__ import annotations

import time
import uuid
import logging
from typing import TYPE_CHECKING, Any

from van_gateway.mission.models import MissionState
from van_gateway.models import PrincipalType

if TYPE_CHECKING:
    from van_gateway.mission.service import MissionService


class HermesResultInbox:
    LEASE_MS = 120_000
    OUTCOMES = frozenset({"COMPLETED", "FAILED", "WAITING_FOR_OWNER", "WAITING_EXTERNAL"})
    TERMINAL_REPORTS = frozenset({"COMPLETED", "FAILED"})

    def __init__(self, missions: MissionService) -> None:
        self.missions = missions
        self.store = missions.store

    async def ingest(self, *, hermes_run_id: str, outcome: str, summary: str = "") -> dict[str, Any]:
        from van_gateway.mission.service import MissionError

        run_id = hermes_run_id.strip()
        outcome = outcome.strip().upper()
        if not run_id:
            raise MissionError("HERMES_RUN_ID_REQUIRED")
        if outcome not in self.OUTCOMES:
            raise MissionError("HERMES_RESULT_UNSUPPORTED", outcome)
        now = int(time.time() * 1000)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "SELECT outcome FROM hermes_result_inbox WHERE hermes_run_id = ? "
                "AND outcome IN ('COMPLETED', 'FAILED') ORDER BY result_id LIMIT 1", (run_id,),
            )
            terminal = await cur.fetchone()
            cur = await db.execute(
                "SELECT result_id FROM hermes_result_inbox WHERE hermes_run_id = ? AND outcome = ?",
                (run_id, outcome),
            )
            existing = await cur.fetchone()
            if terminal is not None and terminal["outcome"] != outcome and existing is None:
                await db.rollback()
                raise MissionError("HERMES_RESULT_CONFLICT", f"{outcome} after {terminal['outcome']}")
            if existing is None:
                cur = await db.execute(
                    "INSERT INTO hermes_result_inbox(hermes_run_id, outcome, summary, received_at_ms) "
                    "VALUES (?, ?, ?, ?)", (run_id, outcome, summary, now),
                )
                result_id = int(cur.lastrowid)
            else:
                result_id = int(existing["result_id"])
            await db.commit()

        # Legacy start events are a durable binding written by previous gateway versions.
        # New requests are bound only by bind(), after an actual create-run receipt.
        binding = await self.store.fetchone(
            "SELECT mission_id FROM hermes_run_bindings WHERE hermes_run_id = ?", (run_id,),
        )
        if binding is None:
            legacy = await self.missions.for_hermes_run(run_id)
            if legacy is not None:
                await self.bind(mission_id=legacy.mission_id, hermes_run_id=run_id)
        await self.reconcile(hermes_run_id=run_id)
        row = await self.store.fetchone("SELECT * FROM hermes_result_inbox WHERE result_id = ?", (result_id,))
        assert row is not None
        if row["state"] == "REJECTED":
            raise MissionError(str(row["refusal_code"]), run_id)
        mission = await self.missions.for_hermes_run(run_id)
        return {
            "hermes_run_id": run_id,
            "receipt_id": result_id,
            "receipt_state": row["state"],
            "status": "APPLIED" if row["state"] == "APPLIED" else "WAITING_FOR_BINDING" if mission is None else "QUEUED",
            "mission_id": mission.mission_id if mission else None,
            "state": mission.state.value if mission else None,
            "verification_state": mission.verification_state.value if mission else None,
            "final_outcome": mission.final_outcome if mission else None,
        }

    async def bind(
        self, *, mission_id: str, hermes_run_id: str, deadline_ms: int | None = None,
    ):
        from van_gateway.mission.service import MissionError

        run_id = hermes_run_id.strip()
        if not run_id:
            raise MissionError("HERMES_RUN_ID_REQUIRED")
        if await self.missions.get(mission_id) is None:
            raise MissionError("MISSION_UNKNOWN", mission_id)
        now = int(time.time() * 1000)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "SELECT hermes_run_id, mission_id FROM hermes_run_bindings "
                "WHERE hermes_run_id = ? OR mission_id = ?", (run_id, mission_id),
            )
            for row in await cur.fetchall():
                if row["hermes_run_id"] != run_id or row["mission_id"] != mission_id:
                    await db.rollback()
                    raise MissionError("HERMES_RUN_BINDING_CONFLICT", run_id)
            await db.execute(
                "INSERT OR IGNORE INTO hermes_run_bindings(hermes_run_id, mission_id, bound_at_ms) "
                "VALUES (?, ?, ?)", (run_id, mission_id, now),
            )
            if deadline_ms is not None:
                await db.execute(
                    "UPDATE missions SET deadline_ms = COALESCE(deadline_ms, ?), updated_at_ms = ? "
                    "WHERE mission_id = ?", (deadline_ms, now, mission_id),
                )
            await db.commit()
        await self._ensure_started(run_id)
        try:
            await self.reconcile(hermes_run_id=run_id)
        except Exception as exc:
            # The dispatch receipt and worker report are already durable. A failed
            # observation must not turn an accepted handoff into a second remote send.
            logging.getLogger("van.mission").warning(
                "Hermes callback retained for retry", extra={"hermes_run_id": run_id, "error_class": type(exc).__name__},
            )
        return await self.missions.get(mission_id)

    async def _ensure_started(self, run_id: str) -> None:
        from van_gateway.mission.service import MissionError

        binding = await self.store.fetchone(
            "SELECT * FROM hermes_run_bindings WHERE hermes_run_id = ?", (run_id,),
        )
        if binding is None or binding["started_at_ms"] is not None:
            return
        mission_id = str(binding["mission_id"])
        mission = await self.missions.get(mission_id)
        if mission is None:
            raise MissionError("MISSION_UNKNOWN", mission_id)
        if mission.state in {MissionState.AUTHORIZED, MissionState.WAITING_EXTERNAL, MissionState.RESUME_AUTHORIZED}:
            try:
                await self.missions.transition(
                    mission_id, target=MissionState.RUNNING, expected=mission.state,
                    actor=PrincipalType.SYSTEM, summary="delegated to the Hermes agent runtime",
                    evidence_ref=f"hermes-run:{run_id}",
                )
            except MissionError as exc:
                if exc.code != "MISSION_STATE_PRECONDITION_FAILED":
                    raise
                # A cancellation or another callback won; neither may be overwritten.
        await self.store.execute(
            "UPDATE hermes_run_bindings SET started_at_ms = ? "
            "WHERE hermes_run_id = ? AND started_at_ms IS NULL", (int(time.time() * 1000), run_id),
        )

    async def reconcile(self, *, hermes_run_id: str | None = None) -> int:
        """Recover queued/restarted reports without sending another remote operation."""
        from van_gateway.mission.service import MissionError

        query = (
            "SELECT DISTINCT i.hermes_run_id FROM hermes_result_inbox i "
            "JOIN hermes_run_bindings b USING (hermes_run_id) "
            "WHERE i.state = 'RECEIVED' OR (i.state = 'APPLYING' AND i.lease_until_ms <= ?)"
        )
        params: tuple[Any, ...] = (int(time.time() * 1000),)
        if hermes_run_id is not None:
            query = query.replace("WHERE ", "WHERE i.hermes_run_id = ? AND (") + ")"
            params = (hermes_run_id, *params)
        runs = await self.store.fetchall(query, params)
        applied = 0
        for run in runs:
            run_id = str(run["hermes_run_id"])
            await self._ensure_started(run_id)
            while True:
                owner = uuid.uuid4().hex
                now = int(time.time() * 1000)
                async with self.store.connection() as db:
                    await db.execute("BEGIN IMMEDIATE")
                    cur = await db.execute(
                        "SELECT * FROM hermes_result_inbox WHERE hermes_run_id = ? "
                        "AND state IN ('RECEIVED', 'APPLYING') ORDER BY result_id LIMIT 1", (run_id,),
                    )
                    row = await cur.fetchone()
                    if row is None or (row["state"] == "APPLYING" and int(row["lease_until_ms"] or 0) > now):
                        await db.rollback()
                        break
                    result_id = int(row["result_id"])
                    await db.execute(
                        "UPDATE hermes_result_inbox SET state = 'APPLYING', lease_owner = ?, lease_until_ms = ? "
                        "WHERE result_id = ?", (owner, now + self.LEASE_MS, result_id),
                    )
                    await db.commit()
                try:
                    await self.missions.apply_hermes_result(
                        hermes_run_id=run_id, outcome=str(row["outcome"]), summary=str(row["summary"]),
                    )
                except MissionError as exc:
                    # A state race is recoverable; policy/terminal conflicts are final.
                    retry = exc.code == "MISSION_STATE_PRECONDITION_FAILED"
                    await self._finish(
                        result_id, owner, state="RECEIVED" if retry else "REJECTED",
                        refusal_code=None if retry else exc.code,
                    )
                    if retry:
                        break
                except Exception:
                    await self._finish(result_id, owner, state="RECEIVED")
                    raise
                else:
                    await self._finish(result_id, owner, state="APPLIED")
                    applied += 1
        return applied

    async def _finish(self, result_id: int, owner: str, *, state: str, refusal_code: str | None = None) -> None:
        await self.store.execute(
            "UPDATE hermes_result_inbox SET state = ?, refusal_code = ?, applied_at_ms = ?, "
            "lease_owner = NULL, lease_until_ms = NULL WHERE result_id = ? AND lease_owner = ?",
            (state, refusal_code, int(time.time() * 1000) if state in {"APPLIED", "REJECTED"} else None, result_id, owner),
        )
