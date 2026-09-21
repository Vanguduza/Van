"""Rev 1 §§5, 42 — binding specialist execution to Missions.

Mission Core is only worth having if the work VAN actually does shows up in it.
Until a browser task or an automation run is an Activity, the owner's Missions
page is a list of intentions and the real execution lives in five subsystem
tables nobody surfaces together.

§5 is explicit that this must not be done by absorption: *"Do not delete mature
existing subsystem state prematurely; integrate and backfill safely."* So the
binding is a reference, not a move. `browser_tasks` stays authoritative for
browser execution detail and `automation_runs` for workflow runs; an Activity
records that a mission caused that row to exist and mirrors only the state the
owner needs to see.

That gives the one property this has to have: binding is **idempotent and
reversible**. Running the backfill twice produces the same Activities, and
dropping every Activity loses nothing that cannot be rebuilt from the subsystem
tables it points at.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from van_gateway.mission.models import ActivityState
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.storage.db import Store

#: How a subsystem's own terminal vocabulary maps onto Activity state. Both
#: subsystems already settled on the same words for the same things, which is
#: why Mission Core adopted that vocabulary rather than inventing a third.
_BROWSER_STATE = {
    "PENDING": ActivityState.PENDING,
    "LEASED": ActivityState.RUNNING,
    "RUNNING": ActivityState.RUNNING,
    "WAITING_FOR_OWNER": ActivityState.WAITING,
    "RESUME_AUTHORIZED": ActivityState.WAITING,
    "VERIFYING": ActivityState.RUNNING,
    "COMPLETED": ActivityState.COMPLETED,
    "FAILED": ActivityState.FAILED,
    "DENIED": ActivityState.FAILED,
    "BLOCKED_POLICY": ActivityState.FAILED,
    "BLOCKED_UNSAFE": ActivityState.FAILED,
    "CANCELLED": ActivityState.SKIPPED,
    "EXPIRED": ActivityState.FAILED,
}
_AUTOMATION_STATE = {
    "PENDING": ActivityState.PENDING,
    "SUBMITTED": ActivityState.RUNNING,
    "VERIFIED_SUCCESS": ActivityState.COMPLETED,
    "PARTIAL_SUCCESS": ActivityState.COMPLETED,
    "UNVERIFIABLE": ActivityState.COMPLETED,
    "FAILED": ActivityState.FAILED,
}

#: Which declared capability each executor's work is performed under. Kept here
#: rather than guessed per call so a subsystem cannot bind work to a capability
#: it was never declared to provide.
BROWSER_CAPABILITY = "browser.semantic.extract"
AUTOMATION_CAPABILITY = "automation.workflow.execute"


@dataclass(frozen=True)
class BackfillReport:
    """§42 — deterministic and reversible, so the numbers must be checkable."""

    browser_tasks_bound: int = 0
    automation_runs_bound: int = 0
    already_bound: int = 0
    unbindable: int = 0

    @property
    def total_bound(self) -> int:
        return self.browser_tasks_bound + self.automation_runs_bound


class MissionBinder:
    """Creates and refreshes the Activity that stands for subsystem execution."""

    def __init__(self, store: Store, missions: MissionService) -> None:
        self.store = store
        self.missions = missions

    # -------------------------------------------------------------- binding

    async def bind_browser_task(
        self, *, mission_id: str, task_id: str, capability_id: str = BROWSER_CAPABILITY
    ) -> str | None:
        """Bind one browser task. Returns the activity_id, or None if already bound."""
        return await self._bind(
            mission_id=mission_id, executor="BROWSER_FABRIC", executor_ref=task_id,
            activity_type="browser.task", capability_id=capability_id,
        )

    async def bind_automation_run(
        self, *, mission_id: str, run_id: str, capability_id: str = AUTOMATION_CAPABILITY
    ) -> str | None:
        return await self._bind(
            mission_id=mission_id, executor="AUTOMATION_FABRIC", executor_ref=run_id,
            activity_type="automation.run", capability_id=capability_id,
        )

    async def _bind(
        self, *, mission_id: str, executor: str, executor_ref: str,
        activity_type: str, capability_id: str,
    ) -> str | None:
        existing = await self.existing_activity_id(executor, executor_ref)
        if existing is not None:
            # Idempotent: the same subsystem row never grows a second Activity.
            return None
        activity = await self.missions.add_activity(
            mission_id=mission_id, activity_type=activity_type,
            capability_id=capability_id, executor=executor, executor_ref=executor_ref,
        )
        return activity.activity_id

    async def existing_activity_id(self, executor: str, executor_ref: str) -> str | None:
        row = await self.store.fetchone(
            "SELECT activity_id FROM mission_activities WHERE executor = ? AND executor_ref = ?",
            (executor, executor_ref),
        )
        return None if row is None else str(row["activity_id"])

    # ---------------------------------------------------------------- sync

    async def sync_from_subsystems(self, mission_id: str, *, now_ms: int | None = None) -> int:
        """Refresh bound Activities from the tables that actually own their state.

        Pull rather than push: the subsystems were authoritative before Mission
        Core existed and still are, so an Activity that disagrees with
        `browser_tasks` is the Activity that is wrong. Making this a read means
        there is no write path that could let the mirror drift and then be
        believed.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        activities = await self.missions.activities(mission_id)
        synced = 0
        for activity in activities:
            if activity.executor_ref is None:
                continue
            if activity.executor == "BROWSER_FABRIC":
                row = await self.store.fetchone(
                    "SELECT status, error_code, evidence_pointer FROM browser_tasks "
                    "WHERE task_id = ?",
                    (activity.executor_ref,),
                )
                mapping = _BROWSER_STATE
            elif activity.executor == "AUTOMATION_FABRIC":
                row = await self.store.fetchone(
                    "SELECT status, error_code, evidence_pointer FROM automation_runs "
                    "WHERE run_id = ?",
                    (activity.executor_ref,),
                )
                mapping = _AUTOMATION_STATE
            else:
                continue
            if row is None:
                continue
            target = mapping.get(str(row["status"]))
            if target is None or target is activity.state:
                continue
            await self.missions.set_activity_state(
                activity.activity_id, state=target, error_class=row["error_code"],
                evidence_ref=row["evidence_pointer"], now_ms=now,
            )
            synced += 1
        return synced

    # ------------------------------------------------------------- backfill

    async def backfill(self, *, mission_id: str, now_ms: int | None = None) -> BackfillReport:
        """§42 — adopt pre-existing subsystem rows into a mission.

        Deliberately explicit about which mission adopts the work: there is no
        way to infer from a browser task which mission caused it, and inventing
        one would attach real execution history to the wrong owner-visible unit.
        A caller that does not know must not guess either, which is why this
        takes a mission_id rather than trying to reconstruct the association.
        """
        mission = await self.missions.get(mission_id)
        if mission is None:
            raise MissionError("MISSION_UNKNOWN", mission_id)

        browser_bound = automation_bound = already = unbindable = 0
        for table, id_column, binder in (
            ("browser_tasks", "task_id", self.bind_browser_task),
            ("automation_runs", "run_id", self.bind_automation_run),
        ):
            rows = await self.store.fetchall(
                f"SELECT {id_column} AS ref FROM {table} ORDER BY {id_column}"
            )
            for row in rows:
                ref = str(row["ref"])
                executor = "BROWSER_FABRIC" if table == "browser_tasks" else "AUTOMATION_FABRIC"
                if await self.existing_activity_id(executor, ref) is not None:
                    already += 1
                    continue
                try:
                    kwargs = {"task_id": ref} if table == "browser_tasks" else {"run_id": ref}
                    created = await binder(mission_id=mission_id, **kwargs)
                except MissionError:
                    # A capability the mission's envelope does not permit is not
                    # silently attached. §7 holds during backfill too.
                    unbindable += 1
                    continue
                if created is None:
                    already += 1
                elif table == "browser_tasks":
                    browser_bound += 1
                else:
                    automation_bound += 1

        await self.sync_from_subsystems(mission_id, now_ms=now_ms)
        return BackfillReport(
            browser_tasks_bound=browser_bound, automation_runs_bound=automation_bound,
            already_bound=already, unbindable=unbindable,
        )

    async def unbind_all(self, mission_id: str) -> int:
        """§42 — reversible. Nothing that only lived in an Activity is lost.

        Every Activity created by binding is a pointer at a subsystem row that
        still exists, so removing them costs no execution history. Provided so
        "reversible" is something the code can do rather than something the
        commit message claims.
        """
        rows = await self.store.fetchall(
            "SELECT activity_id FROM mission_activities "
            "WHERE mission_id = ? AND executor_ref IS NOT NULL",
            (mission_id,),
        )
        for row in rows:
            await self.store.execute(
                "DELETE FROM mission_events WHERE activity_id = ?", (row["activity_id"],)
            )
            await self.store.execute(
                "DELETE FROM mission_activities WHERE activity_id = ?", (row["activity_id"],)
            )
        return len(rows)


__all__ = ["AUTOMATION_CAPABILITY", "BROWSER_CAPABILITY", "BackfillReport", "MissionBinder"]
