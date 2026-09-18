"""Rev 1.3 §§76-77, 99-100 — the workflow health model and automatic degradation.

§77's requirement is short and consequential: *"VAN should stop routing critical
tasks through degraded workflows."* That only works if degradation happens by
itself, from what runs actually did, rather than waiting for someone to notice.

So health is recorded per capability **version**, not per capability. A repair
produces a new version, and the old version's failure record is not the new
one's to carry — otherwise a repaired workflow would inherit a reputation it did
not earn, and the ladder would never climb back.

Two failure classes are treated differently from the rest:

* a *verification* failure is the worst kind, because the engine reported
  success and the world disagreed (§80). It degrades faster;
* a *transient* failure is not a health event at all. §244 is explicit that a
  transient HTTP timeout must not trigger regeneration, and counting it here
  would do exactly that by another route.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum

from van_gateway.storage.db import Store


class HealthStatus(str, Enum):
    GREEN = "GREEN"
    DEGRADED = "DEGRADED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    QUARANTINED = "QUARANTINED"


class FailureClass(str, Enum):
    """§77 — what kind of failure this was, because they do not weigh the same."""

    SCHEMA = "SCHEMA"
    CREDENTIAL = "CREDENTIAL"
    CONNECTOR = "CONNECTOR"
    VERIFICATION = "VERIFICATION"
    TRANSIENT = "TRANSIENT"
    SECURITY = "SECURITY"
    UNKNOWN = "UNKNOWN"

    @property
    def counts_against_health(self) -> bool:
        # §244 — a transient timeout is not evidence that the workflow is wrong.
        return self is not FailureClass.TRANSIENT


#: How many consecutive counted failures move GREEN -> DEGRADED.
DEGRADE_AFTER = {
    FailureClass.VERIFICATION: 1,
    FailureClass.SCHEMA: 2,
    FailureClass.CREDENTIAL: 2,
    FailureClass.CONNECTOR: 2,
    FailureClass.UNKNOWN: 3,
}
#: And how many move DEGRADED -> REPAIR_REQUIRED.
REPAIR_AFTER = {
    FailureClass.VERIFICATION: 2,
    FailureClass.SCHEMA: 3,
    FailureClass.CREDENTIAL: 3,
    FailureClass.CONNECTOR: 3,
    FailureClass.UNKNOWN: 5,
}
#: Sample window for the p95. Small on purpose: this is a health signal, not a
#: performance archive, and §101 keeps the full timing series separately.
DURATION_WINDOW = 50


@dataclass(frozen=True)
class WorkflowHealth:
    capability_id: str
    workflow_version: int
    runs: int
    verified_successes: int
    failures: int
    consecutive_failures: int
    mean_duration_ms: int
    p95_duration_ms: int | None
    repair_count: int
    last_verified_at_ms: int | None
    last_failure_class: FailureClass | None
    status: HealthStatus

    @property
    def routable(self) -> bool:
        """§77 — only GREEN takes new work without a second thought."""
        return self.status is HealthStatus.GREEN

    @property
    def verified_success_rate(self) -> float:
        return self.verified_successes / self.runs if self.runs else 0.0


class WorkflowHealthService:
    """Records run outcomes and lets the ladder fall — and climb back — by itself."""

    def __init__(self, store: Store) -> None:
        self.store = store

    # ------------------------------------------------------------- recording

    async def record_success(
        self,
        *,
        capability_id: str,
        workflow_version: int,
        duration_ms: int,
        verified: bool,
        now_ms: int | None = None,
    ) -> WorkflowHealth:
        """A verified success is the only kind that heals a degraded workflow.

        §17: an engine success is not an owner success, so an unverified run
        neither degrades the workflow nor clears its failure streak — it simply
        is not evidence either way.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self._row(capability_id, workflow_version)
        samples = (json.loads(row["duration_samples_json"]) if row else [])[-DURATION_WINDOW + 1:]
        samples.append(max(0, int(duration_ms)))

        runs = int(row["runs"]) if row else 0
        status = HealthStatus(str(row["status"])) if row else HealthStatus.GREEN
        consecutive = int(row["consecutive_failures"]) if row else 0
        if verified:
            consecutive = 0
            if status is HealthStatus.DEGRADED:
                # A degraded workflow that verifies again is healthy again. Nothing
                # climbs out of REPAIR_REQUIRED or QUARANTINED this way: those need
                # a repair and a fresh admission (§245).
                status = HealthStatus.GREEN

        await self._write(
            capability_id=capability_id,
            workflow_version=workflow_version,
            runs=runs + 1,
            verified_successes=(int(row["verified_successes"]) if row else 0) + (1 if verified else 0),
            failures=int(row["failures"]) if row else 0,
            consecutive_failures=consecutive,
            total_duration_ms=(int(row["total_duration_ms"]) if row else 0) + max(0, int(duration_ms)),
            samples=samples,
            repair_count=int(row["repair_count"]) if row else 0,
            last_verified_at_ms=now if verified else (row["last_verified_at_ms"] if row else None),
            last_failure_class=(row["last_failure_class"] if row else None),
            status=status,
            now=now,
        )
        return await self.get(capability_id, workflow_version)  # type: ignore[return-value]

    async def record_failure(
        self,
        *,
        capability_id: str,
        workflow_version: int,
        failure_class: FailureClass,
        duration_ms: int = 0,
        now_ms: int | None = None,
    ) -> WorkflowHealth:
        """§77 — repeated counted failures walk the workflow down the ladder."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self._row(capability_id, workflow_version)
        samples = (json.loads(row["duration_samples_json"]) if row else [])[-DURATION_WINDOW + 1:]
        if duration_ms:
            samples.append(max(0, int(duration_ms)))

        status = HealthStatus(str(row["status"])) if row else HealthStatus.GREEN
        consecutive = (int(row["consecutive_failures"]) if row else 0)
        if failure_class.counts_against_health:
            consecutive += 1
            status = self._next_status(status, failure_class, consecutive)

        await self._write(
            capability_id=capability_id,
            workflow_version=workflow_version,
            runs=(int(row["runs"]) if row else 0) + 1,
            verified_successes=int(row["verified_successes"]) if row else 0,
            failures=(int(row["failures"]) if row else 0) + 1,
            consecutive_failures=consecutive,
            total_duration_ms=(int(row["total_duration_ms"]) if row else 0) + max(0, int(duration_ms)),
            samples=samples,
            repair_count=int(row["repair_count"]) if row else 0,
            last_verified_at_ms=row["last_verified_at_ms"] if row else None,
            last_failure_class=failure_class.value,
            status=status,
            now=now,
        )
        return await self.get(capability_id, workflow_version)  # type: ignore[return-value]

    @staticmethod
    def _next_status(
        current: HealthStatus, failure_class: FailureClass, consecutive: int
    ) -> HealthStatus:
        if current in (HealthStatus.REPAIR_REQUIRED, HealthStatus.QUARANTINED):
            return current
        if failure_class is FailureClass.SECURITY:
            # §47 — a security failure never degrades gracefully.
            return HealthStatus.QUARANTINED
        if consecutive >= REPAIR_AFTER.get(failure_class, 5):
            return HealthStatus.REPAIR_REQUIRED
        if consecutive >= DEGRADE_AFTER.get(failure_class, 3):
            return HealthStatus.DEGRADED
        return current

    # -------------------------------------------------------------- mutation

    async def quarantine(
        self, capability_id: str, workflow_version: int, *, now_ms: int | None = None
    ) -> None:
        """§47 — an explicit, terminal stop. Nothing routes here again."""
        await self._set_status(capability_id, workflow_version, HealthStatus.QUARANTINED, now_ms)

    async def mark_repaired(
        self, capability_id: str, workflow_version: int, *, now_ms: int | None = None
    ) -> None:
        """Called when a repair is promoted, on the *new* version's row (§245)."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            INSERT INTO automation_workflow_health(
              capability_id, workflow_version, repair_count, status, updated_at_ms
            ) VALUES (?, ?, 1, 'GREEN', ?)
            ON CONFLICT(capability_id, workflow_version) DO UPDATE SET
              repair_count = repair_count + 1,
              consecutive_failures = 0,
              status = 'GREEN',
              updated_at_ms = excluded.updated_at_ms
            """,
            (capability_id, workflow_version, now),
        )

    async def _set_status(
        self, capability_id: str, workflow_version: int, status: HealthStatus, now_ms: int | None
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            INSERT INTO automation_workflow_health(
              capability_id, workflow_version, status, updated_at_ms
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(capability_id, workflow_version) DO UPDATE SET
              status = excluded.status, updated_at_ms = excluded.updated_at_ms
            """,
            (capability_id, workflow_version, status.value, now),
        )

    # --------------------------------------------------------------- reading

    async def get(self, capability_id: str, workflow_version: int) -> WorkflowHealth | None:
        row = await self._row(capability_id, workflow_version)
        if row is None:
            return None
        runs = int(row["runs"])
        return WorkflowHealth(
            capability_id=capability_id,
            workflow_version=workflow_version,
            runs=runs,
            verified_successes=int(row["verified_successes"]),
            failures=int(row["failures"]),
            consecutive_failures=int(row["consecutive_failures"]),
            mean_duration_ms=int(int(row["total_duration_ms"]) / runs) if runs else 0,
            p95_duration_ms=row["p95_duration_ms"],
            repair_count=int(row["repair_count"]),
            last_verified_at_ms=row["last_verified_at_ms"],
            last_failure_class=(
                FailureClass(str(row["last_failure_class"])) if row["last_failure_class"] else None
            ),
            status=HealthStatus(str(row["status"])),
        )

    async def needing_attention(self) -> list[WorkflowHealth]:
        """Everything that is no longer GREEN, for the health endpoint and repair."""
        rows = await self.store.fetchall(
            "SELECT capability_id, workflow_version FROM automation_workflow_health "
            "WHERE status != 'GREEN' ORDER BY updated_at_ms DESC"
        )
        out = []
        for row in rows:
            health = await self.get(str(row["capability_id"]), int(row["workflow_version"]))
            if health is not None:
                out.append(health)
        return out

    async def counts_by_status(self) -> dict[str, int]:
        rows = await self.store.fetchall(
            "SELECT status, COUNT(*) AS n FROM automation_workflow_health GROUP BY status"
        )
        counts = {status.value: 0 for status in HealthStatus}
        for row in rows:
            counts[str(row["status"])] = int(row["n"])
        return counts

    # --------------------------------------------------------------- helpers

    async def _row(self, capability_id: str, workflow_version: int):
        return await self.store.fetchone(
            "SELECT * FROM automation_workflow_health "
            "WHERE capability_id = ? AND workflow_version = ?",
            (capability_id, workflow_version),
        )

    async def _write(
        self,
        *,
        capability_id: str,
        workflow_version: int,
        runs: int,
        verified_successes: int,
        failures: int,
        consecutive_failures: int,
        total_duration_ms: int,
        samples: list[int],
        repair_count: int,
        last_verified_at_ms: int | None,
        last_failure_class: str | None,
        status: HealthStatus,
        now: int,
    ) -> None:
        await self.store.execute(
            """
            INSERT INTO automation_workflow_health(
              capability_id, workflow_version, runs, verified_successes, failures,
              consecutive_failures, total_duration_ms, duration_samples_json,
              p95_duration_ms, repair_count, last_verified_at_ms, last_failure_class,
              status, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(capability_id, workflow_version) DO UPDATE SET
              runs=excluded.runs, verified_successes=excluded.verified_successes,
              failures=excluded.failures, consecutive_failures=excluded.consecutive_failures,
              total_duration_ms=excluded.total_duration_ms,
              duration_samples_json=excluded.duration_samples_json,
              p95_duration_ms=excluded.p95_duration_ms, repair_count=excluded.repair_count,
              last_verified_at_ms=excluded.last_verified_at_ms,
              last_failure_class=excluded.last_failure_class,
              status=excluded.status, updated_at_ms=excluded.updated_at_ms
            """,
            (
                capability_id, workflow_version, runs, verified_successes, failures,
                consecutive_failures, total_duration_ms, Store.dumps(samples),
                percentile(samples, 95), repair_count, last_verified_at_ms,
                last_failure_class, status.value, now,
            ),
        )


def percentile(samples: list[int], pct: int) -> int | None:
    """Nearest-rank. Exact on small windows, which is what this one always is."""
    if not samples:
        return None
    ordered = sorted(samples)
    rank = max(1, min(len(ordered), -(-pct * len(ordered) // 100)))
    return int(ordered[rank - 1])


__all__ = [
    "DEGRADE_AFTER",
    "REPAIR_AFTER",
    "FailureClass",
    "HealthStatus",
    "WorkflowHealth",
    "WorkflowHealthService",
    "percentile",
]
