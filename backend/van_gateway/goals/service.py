from __future__ import annotations

import json
import time
import uuid
from typing import Any

from van_gateway.attention.engine import AttentionEngine
from van_gateway.models import AttentionSeverity
from van_gateway.storage.db import Store

from .models import (
    Goal, GoalCreate, GoalMilestone, GoalPatch, GoalStatus,
    Watch, WatchConditionKind, WatchCreate, WatchObservation, WatchSourceKind, WatchStatus,
)


class GoalServiceError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class GoalService:
    """Owner Goals are long-lived desired outcomes; Missions remain executions."""

    def __init__(self, store: Store, attention: AttentionEngine) -> None:
        self.store = store
        self.attention = attention

    async def _goal(self, goal_id: str) -> Goal | None:
        row = await self.store.fetchone("SELECT * FROM owner_goals WHERE goal_id = ?", (goal_id,))
        if row is None:
            return None
        milestones = await self.store.fetchall(
            "SELECT * FROM goal_milestones WHERE goal_id = ? ORDER BY sort_order, created_at_ms",
            (goal_id,),
        )
        missions = await self.store.fetchall(
            "SELECT mission_id FROM goal_mission_links WHERE goal_id = ? ORDER BY linked_at_ms",
            (goal_id,),
        )
        return Goal(
            goal_id=row["goal_id"], title=row["title"], description=row["description"],
            status=GoalStatus(row["status"]), priority=int(row["priority"]),
            project_id=row["project_id"],
            evidence_refs=json.loads(row["evidence_refs_json"] or "[]"),
            milestones=[
                GoalMilestone(
                    milestone_id=m["milestone_id"], title=m["title"], done=bool(m["done"]),
                    due_at_ms=m["due_at_ms"], sort_order=int(m["sort_order"]),
                ) for m in milestones
            ],
            mission_ids=[m["mission_id"] for m in missions],
            created_at_ms=int(row["created_at_ms"]), updated_at_ms=int(row["updated_at_ms"]),
            completed_at_ms=row["completed_at_ms"],
        )

    async def create(self, body: GoalCreate, *, now_ms: int | None = None) -> Goal:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        goal_id = f"goal_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO owner_goals(
              goal_id, title, description, status, priority, project_id, evidence_refs_json,
              created_at_ms, updated_at_ms, completed_at_ms
            ) VALUES (?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, NULL)
            """,
            (goal_id, body.title.strip(), body.description.strip(), body.priority,
             body.project_id, Store.dumps(body.evidence_refs), now, now),
        )
        for order, title in enumerate(body.milestones):
            if title.strip():
                await self.store.execute(
                    """
                    INSERT INTO goal_milestones(
                      milestone_id, goal_id, title, done, due_at_ms, sort_order, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, 0, NULL, ?, ?, ?)
                    """,
                    (f"gms_{uuid.uuid4().hex}", goal_id, title.strip(), order, now, now),
                )
        goal = await self._goal(goal_id)
        assert goal is not None
        return goal

    async def get(self, goal_id: str) -> Goal | None:
        return await self._goal(goal_id)

    async def list(self, status: GoalStatus | None = None, limit: int = 100) -> list[Goal]:
        params: list[Any] = []
        where = ""
        if status is not None:
            where = " WHERE status = ?"; params.append(status.value)
        rows = await self.store.fetchall(
            f"SELECT goal_id FROM owner_goals{where} ORDER BY priority DESC, updated_at_ms DESC LIMIT ?",
            tuple(params + [max(1, min(limit, 500))]),
        )
        out=[]
        for row in rows:
            goal=await self._goal(row["goal_id"])
            if goal is not None: out.append(goal)
        return out

    async def patch(self, goal_id: str, body: GoalPatch, *, now_ms: int | None = None) -> Goal:
        current = await self._goal(goal_id)
        if current is None:
            raise GoalServiceError("GOAL_UNKNOWN")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        title = current.title if body.title is None else body.title.strip()
        description = current.description if body.description is None else body.description.strip()
        priority = current.priority if body.priority is None else body.priority
        status = current.status if body.status is None else body.status
        completed_at = current.completed_at_ms
        if status is GoalStatus.COMPLETED and current.status is not GoalStatus.COMPLETED:
            completed_at = now
        elif status is not GoalStatus.COMPLETED:
            completed_at = None
        await self.store.execute(
            """
            UPDATE owner_goals SET title = ?, description = ?, priority = ?, status = ?,
                                   completed_at_ms = ?, updated_at_ms = ?
             WHERE goal_id = ?
            """,
            (title, description, priority, status.value, completed_at, now, goal_id),
        )
        updated=await self._goal(goal_id); assert updated is not None
        return updated

    async def set_milestone(self, goal_id: str, milestone_id: str, done: bool, *, now_ms: int | None = None) -> Goal:
        if await self._goal(goal_id) is None:
            raise GoalServiceError("GOAL_UNKNOWN")
        row=await self.store.fetchone(
            "SELECT milestone_id FROM goal_milestones WHERE goal_id = ? AND milestone_id = ?",
            (goal_id,milestone_id),
        )
        if row is None: raise GoalServiceError("MILESTONE_UNKNOWN")
        now=int(time.time()*1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE goal_milestones SET done = ?, updated_at_ms = ? WHERE milestone_id = ?",
            (1 if done else 0, now, milestone_id),
        )
        goal=await self._goal(goal_id); assert goal is not None
        return goal

    async def link_mission(self, goal_id: str, mission_id: str, *, now_ms: int | None = None) -> Goal:
        if await self._goal(goal_id) is None: raise GoalServiceError("GOAL_UNKNOWN")
        now=int(time.time()*1000) if now_ms is None else now_ms
        await self.store.execute(
            "INSERT OR IGNORE INTO goal_mission_links(goal_id, mission_id, linked_at_ms) VALUES (?, ?, ?)",
            (goal_id, mission_id, now),
        )
        goal=await self._goal(goal_id); assert goal is not None
        return goal

    @staticmethod
    def _watch(row: Any) -> Watch:
        return Watch(
            watch_id=row["watch_id"], goal_id=row["goal_id"], title=row["title"],
            source_kind=WatchSourceKind(row["source_kind"]), target=row["target"],
            condition=json.loads(row["condition_json"] or "{}"),
            interval_seconds=int(row["interval_seconds"]), status=WatchStatus(row["status"]),
            consecutive_failures=int(row["consecutive_failures"]),
            failure_streak=int(row["failure_streak"]), next_run_at_ms=int(row["next_run_at_ms"]),
            last_success_at_ms=row["last_success_at_ms"],
            last_observation=None if row["last_observation_json"] is None else json.loads(row["last_observation_json"]),
            created_at_ms=int(row["created_at_ms"]), updated_at_ms=int(row["updated_at_ms"]),
        )

    async def create_watch(self, body: WatchCreate, *, now_ms: int | None = None) -> Watch:
        if body.goal_id and await self._goal(body.goal_id) is None:
            raise GoalServiceError("GOAL_UNKNOWN")
        kind_raw=str(body.condition.get("kind","")).upper()
        try: WatchConditionKind(kind_raw)
        except ValueError as exc: raise GoalServiceError("WATCH_CONDITION_INVALID") from exc
        now=int(time.time()*1000) if now_ms is None else now_ms
        watch_id=f"watch_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO watches(
              watch_id, goal_id, title, source_kind, target, condition_json, interval_seconds,
              status, consecutive_failures, failure_streak, next_run_at_ms, last_success_at_ms,
              last_observation_json, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 0, 0, ?, NULL, NULL, ?, ?)
            """,
            (watch_id, body.goal_id, body.title.strip(), body.source_kind.value, body.target.strip(),
             Store.dumps(body.condition), body.interval_seconds, now, now, now),
        )
        row=await self.store.fetchone("SELECT * FROM watches WHERE watch_id = ?",(watch_id,))
        assert row is not None; return self._watch(row)

    async def get_watch(self, watch_id: str) -> Watch | None:
        row=await self.store.fetchone("SELECT * FROM watches WHERE watch_id = ?",(watch_id,))
        return None if row is None else self._watch(row)

    async def list_watches(self, status: WatchStatus | None = None, limit: int = 100) -> list[Watch]:
        if status is None:
            rows=await self.store.fetchall("SELECT * FROM watches ORDER BY updated_at_ms DESC LIMIT ?",(max(1,min(limit,500)),))
        else:
            rows=await self.store.fetchall("SELECT * FROM watches WHERE status = ? ORDER BY updated_at_ms DESC LIMIT ?",(status.value,max(1,min(limit,500))))
        return [self._watch(row) for row in rows]

    async def set_watch_status(self, watch_id: str, status: WatchStatus, *, now_ms: int | None = None) -> Watch:
        if await self.get_watch(watch_id) is None: raise GoalServiceError("WATCH_UNKNOWN")
        now=int(time.time()*1000) if now_ms is None else now_ms
        await self.store.execute("UPDATE watches SET status = ?, updated_at_ms = ? WHERE watch_id = ?",(status.value,now,watch_id))
        out=await self.get_watch(watch_id); assert out is not None; return out

    @staticmethod
    def _condition_triggered(condition: dict[str, Any], previous: Any, current: Any) -> bool:
        kind=WatchConditionKind(str(condition.get("kind","")).upper())
        if kind is WatchConditionKind.CHANGED:
            return previous is not None and previous != current
        if kind is WatchConditionKind.BOOLEAN_TRUE:
            return bool(current) and not bool(previous)
        if kind is WatchConditionKind.TEXT_CONTAINS:
            needle=str(condition.get("text",""))
            return bool(needle) and needle in str(current) and (previous is None or needle not in str(previous))
        if kind in {WatchConditionKind.NUMERIC_ABOVE, WatchConditionKind.NUMERIC_BELOW}:
            threshold=float(condition["threshold"])
            value=float(current)
            old=None if previous is None else float(previous)
            return (value > threshold and (old is None or old <= threshold)) if kind is WatchConditionKind.NUMERIC_ABOVE else (value < threshold and (old is None or old >= threshold))
        return False

    async def record_observation(
        self, watch_id: str, body: WatchObservation, *, now_ms: int | None = None
    ) -> dict[str, Any]:
        watch=await self.get_watch(watch_id)
        if watch is None: raise GoalServiceError("WATCH_UNKNOWN")
        if watch.status is not WatchStatus.ACTIVE: raise GoalServiceError("WATCH_NOT_ACTIVE")
        now=int(time.time()*1000) if now_ms is None else now_ms
        run_id=f"wrun_{uuid.uuid4().hex}"
        if not body.success:
            failures=watch.consecutive_failures+1
            streak=watch.failure_streak + (1 if watch.consecutive_failures == 0 else 0)
            paused=failures >= 3
            await self.store.execute(
                """
                UPDATE watches SET consecutive_failures = ?, failure_streak = ?,
                   status = ?, next_run_at_ms = ?, updated_at_ms = ?
                 WHERE watch_id = ?
                """,
                (failures,streak,"PAUSED" if paused else "ACTIVE",now+watch.interval_seconds*1000,now,watch_id),
            )
            await self.store.execute(
                "INSERT INTO watch_runs(run_id, watch_id, status, observation_json, changed, error_code, created_at_ms) VALUES (?, ?, 'FAILED', NULL, 0, ?, ?)",
                (run_id,watch_id,body.error_code or "WATCH_SOURCE_FAILED",now),
            )
            severity=AttentionSeverity.BLOCKER if paused else AttentionSeverity.FOLLOW_UP
            await self.attention.upsert(
                title=(f"{watch.title} paused after repeated failures" if paused else f"{watch.title} could not be checked"),
                severity=severity, source="watch",
                dedupe_key=f"watch:{watch_id}:failure:{streak}",
                payload={"watch_id":watch_id,"failure_streak":streak,"failures":failures,"error_code":body.error_code},
            )
            return {"run_id":run_id,"triggered":False,"paused":paused,"failure_streak":streak}

        triggered=self._condition_triggered(watch.condition,watch.last_observation,body.observation)
        await self.store.execute(
            """
            UPDATE watches SET consecutive_failures = 0, last_success_at_ms = ?,
              last_observation_json = ?, next_run_at_ms = ?, updated_at_ms = ?
             WHERE watch_id = ?
            """,
            (now,Store.dumps(body.observation),now+watch.interval_seconds*1000,now,watch_id),
        )
        await self.store.execute(
            "INSERT INTO watch_runs(run_id, watch_id, status, observation_json, changed, error_code, created_at_ms) VALUES (?, ?, 'SUCCEEDED', ?, ?, NULL, ?)",
            (run_id,watch_id,Store.dumps(body.observation),1 if triggered else 0,now),
        )
        if triggered:
            await self.attention.upsert(
                title=watch.title, severity=AttentionSeverity.FOLLOW_UP, source="watch",
                dedupe_key=f"watch:{watch_id}:trigger:{run_id}",
                payload={"watch_id":watch_id,"observation":body.observation,"condition":watch.condition},
            )
        return {"run_id":run_id,"triggered":triggered,"paused":False,"failure_streak":watch.failure_streak}
