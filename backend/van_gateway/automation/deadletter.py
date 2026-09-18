"""Rev 1.3 §246 — the dead-letter table, and the rule behind it.

*"Do not infinite-retry."* Bounded retry has to end somewhere, and the only
acceptable somewhere is a durable row that names what failed, how many times,
and what a person should do about it. A silent drop and an endless retry are the
same bug wearing different clothes.

Every row therefore carries a `next_action`. A dead letter with no stated next
action is an unactionable dead letter, which is why the field is required rather
than nullable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from van_gateway.automation.canonical import new_id
from van_gateway.automation.workflow_health import FailureClass
from van_gateway.storage.db import Store


class NextAction(str, Enum):
    """Who has to do what. Every dead letter states one."""

    OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"
    OPERATOR_INVESTIGATION = "OPERATOR_INVESTIGATION"
    CREDENTIAL_REFRESH = "CREDENTIAL_REFRESH"
    AWAIT_REPAIR = "AWAIT_REPAIR"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    NO_ACTION_EXTERNAL_OUTAGE = "NO_ACTION_EXTERNAL_OUTAGE"


#: The default mapping from why it failed to who picks it up.
NEXT_ACTION_FOR = {
    FailureClass.CREDENTIAL: NextAction.CREDENTIAL_REFRESH,
    FailureClass.SECURITY: NextAction.SECURITY_REVIEW,
    FailureClass.SCHEMA: NextAction.AWAIT_REPAIR,
    FailureClass.VERIFICATION: NextAction.OWNER_DECISION_REQUIRED,
    FailureClass.CONNECTOR: NextAction.NO_ACTION_EXTERNAL_OUTAGE,
    FailureClass.TRANSIENT: NextAction.NO_ACTION_EXTERNAL_OUTAGE,
    FailureClass.UNKNOWN: NextAction.OPERATOR_INVESTIGATION,
}


@dataclass(frozen=True)
class DeadLetter:
    dead_letter_id: str
    run_id: str | None
    event_id: str | None
    capability_id: str | None
    failure_class: FailureClass
    last_error_code: str | None
    attempt_count: int
    evidence_refs: tuple[str, ...]
    next_action: NextAction
    created_at_ms: int
    resolved_at_ms: int | None = None
    resolution: str | None = None

    @property
    def open(self) -> bool:
        return self.resolved_at_ms is None


class DeadLetterService:
    """Where bounded retry ends. Nothing here retries by itself."""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def record(
        self,
        *,
        failure_class: FailureClass,
        attempt_count: int,
        run_id: str | None = None,
        event_id: str | None = None,
        capability_id: str | None = None,
        last_error_code: str | None = None,
        evidence_refs: list[str] | None = None,
        next_action: NextAction | None = None,
        detail: dict[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> DeadLetter:
        """Idempotent per run: a second bounded failure updates the attempt count.

        Without that, a retry loop would produce a queue of near-identical rows
        and the attempt count — the thing that says "this is not transient" —
        would be spread across all of them.
        """
        if run_id is None and event_id is None:
            raise ValueError("dead_letter_requires_run_or_event")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        action = next_action or NEXT_ACTION_FOR.get(
            failure_class, NextAction.OPERATOR_INVESTIGATION
        )
        refs = sorted(set(evidence_refs or []))

        if run_id is not None:
            existing = await self.store.fetchone(
                "SELECT dead_letter_id FROM automation_dead_letter WHERE run_id = ?", (run_id,)
            )
            if existing is not None:
                await self.store.execute(
                    "UPDATE automation_dead_letter SET attempt_count = ?, last_error_code = ?, "
                    "failure_class = ?, next_action = ?, evidence_refs_json = ?, "
                    "updated_at_ms = ? WHERE dead_letter_id = ?",
                    (
                        max(1, attempt_count), last_error_code, failure_class.value,
                        action.value, Store.dumps(refs), now, str(existing["dead_letter_id"]),
                    ),
                )
                return await self.get(str(existing["dead_letter_id"]))  # type: ignore[return-value]

        dead_letter_id = new_id("deadletter")
        await self.store.execute(
            """
            INSERT INTO automation_dead_letter(
              dead_letter_id, run_id, event_id, capability_id, failure_class,
              last_error_code, attempt_count, evidence_refs_json, next_action,
              detail_json, created_at_ms, updated_at_ms, resolved_at_ms, resolution
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                dead_letter_id, run_id, event_id, capability_id, failure_class.value,
                last_error_code, max(1, attempt_count), Store.dumps(refs), action.value,
                Store.dumps(detail or {}), now, now,
            ),
        )
        return await self.get(dead_letter_id)  # type: ignore[return-value]

    async def resolve(
        self, dead_letter_id: str, *, resolution: str, now_ms: int | None = None
    ) -> bool:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE automation_dead_letter SET resolved_at_ms = ?, resolution = ?, "
                "updated_at_ms = ? WHERE dead_letter_id = ? AND resolved_at_ms IS NULL",
                (now, resolution, now, dead_letter_id),
            )
            await db.commit()
            return cur.rowcount == 1

    async def get(self, dead_letter_id: str) -> DeadLetter | None:
        row = await self.store.fetchone(
            "SELECT * FROM automation_dead_letter WHERE dead_letter_id = ?", (dead_letter_id,)
        )
        return None if row is None else self._row(row)

    async def open_letters(self, limit: int = 100) -> list[DeadLetter]:
        rows = await self.store.fetchall(
            "SELECT * FROM automation_dead_letter WHERE resolved_at_ms IS NULL "
            "ORDER BY created_at_ms DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        )
        return [self._row(row) for row in rows]

    async def open_count(self) -> int:
        row = await self.store.fetchone(
            "SELECT COUNT(*) AS n FROM automation_dead_letter WHERE resolved_at_ms IS NULL"
        )
        return int(row["n"]) if row else 0

    @staticmethod
    def _row(row: Any) -> DeadLetter:
        import json

        return DeadLetter(
            dead_letter_id=str(row["dead_letter_id"]),
            run_id=row["run_id"],
            event_id=row["event_id"],
            capability_id=row["capability_id"],
            failure_class=FailureClass(str(row["failure_class"])),
            last_error_code=row["last_error_code"],
            attempt_count=int(row["attempt_count"]),
            evidence_refs=tuple(json.loads(str(row["evidence_refs_json"]))),
            next_action=NextAction(str(row["next_action"])),
            created_at_ms=int(row["created_at_ms"]),
            resolved_at_ms=row["resolved_at_ms"],
            resolution=row["resolution"],
        )


__all__ = ["NEXT_ACTION_FOR", "DeadLetter", "DeadLetterService", "NextAction"]
