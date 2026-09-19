"""Rev 1.3 §§101-103 — workflow and generation telemetry.

§102 names the core success metric plainly: *"HOT hit rate increases over
time."* That is the whole thesis of §§23-25 — that a fabric which learns is
cheap and one that regenerates is not — and it is a claim, not a fact, until it
is measured. This module is where it becomes measurable.

The counters are deliberately boring: counts and durations, no sampling, no
model. A metric that needs interpretation to read is a metric that can be talked
into saying whatever the reader wanted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from van_gateway.automation.canonical import new_id
from van_gateway.observability import instruments
from van_gateway.automation.workflow_health import percentile
from van_gateway.storage.db import Store


class CacheState(str, Enum):
    """§101 — which rung of the ladder served this run."""

    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"
    NATIVE = "NATIVE"
    BROWSER = "BROWSER"


@dataclass(frozen=True)
class RunTiming:
    """§101 — the phases, kept separate so a regression points somewhere."""

    run_id: str
    cache_state: CacheState
    capability_id: str | None = None
    workflow_version: int | None = None
    compile_time_ms: int = 0
    dispatch_time_ms: int = 0
    execution_time_ms: int = 0
    external_wait_ms: int = 0
    verification_time_ms: int = 0
    retry_count: int = 0
    failure_count: int = 0

    @property
    def total_ms(self) -> int:
        return (
            self.compile_time_ms
            + self.dispatch_time_ms
            + self.execution_time_ms
            + self.external_wait_ms
            + self.verification_time_ms
        )

    @property
    def van_overhead_ms(self) -> int:
        """Everything that is VAN's fault rather than the external system's.

        §57's SLOs are about this number: waiting on someone else's API is not a
        latency budget VAN controls, and mixing the two hides regressions.
        """
        return self.total_ms - self.external_wait_ms


@dataclass(frozen=True)
class GenerationEvent:
    """§102 — one capability-acquisition attempt."""

    goal_class: str
    medium: str
    outcome: str
    pattern_reused: bool = False
    ir_cache_hit: bool = False
    first_use_latency_ms: int = 0


@dataclass(frozen=True)
class LadderMetrics:
    """§§102-103 — the numbers that say whether the ladder is working."""

    total: int
    hot: int
    warm: int
    cold: int
    generation_failures: int
    pattern_reuse: int
    ir_cache_hits: int
    median_first_use_latency_ms: int
    window_ms: int
    by_medium: dict[str, int] = field(default_factory=dict)

    @property
    def hot_hit_rate(self) -> float:
        """The core success metric. Rising is the whole point (§102)."""
        return self.hot / self.total if self.total else 0.0

    @property
    def cold_generation_rate(self) -> float:
        return self.cold / self.total if self.total else 0.0

    @property
    def warm_specialisation_rate(self) -> float:
        return self.warm / self.total if self.total else 0.0

    @property
    def pattern_reuse_rate(self) -> float:
        return self.pattern_reuse / self.total if self.total else 0.0

    @property
    def ir_cache_hit_rate(self) -> float:
        return self.ir_cache_hits / self.total if self.total else 0.0


class TelemetryService:
    """Writes the counters and reads them back. Nothing here decides anything."""

    #: §103 — a rolling window, because "ever" is not a trend.
    DEFAULT_WINDOW_MS = 7 * 24 * 60 * 60 * 1000

    def __init__(self, store: Store) -> None:
        self.store = store

    # --------------------------------------------------------------- writing

    async def record_run(self, timing: RunTiming, *, now_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            INSERT INTO automation_run_telemetry(
              run_id, capability_id, workflow_version, cache_state, compile_time_ms,
              dispatch_time_ms, execution_time_ms, external_wait_ms, verification_time_ms,
              retry_count, failure_count, recorded_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              cache_state=excluded.cache_state,
              compile_time_ms=excluded.compile_time_ms,
              dispatch_time_ms=excluded.dispatch_time_ms,
              execution_time_ms=excluded.execution_time_ms,
              external_wait_ms=excluded.external_wait_ms,
              verification_time_ms=excluded.verification_time_ms,
              retry_count=excluded.retry_count, failure_count=excluded.failure_count,
              recorded_at_ms=excluded.recorded_at_ms
            """,
            (
                timing.run_id, timing.capability_id, timing.workflow_version,
                timing.cache_state.value, timing.compile_time_ms, timing.dispatch_time_ms,
                timing.execution_time_ms, timing.external_wait_ms,
                timing.verification_time_ms, timing.retry_count, timing.failure_count, now,
            ),
        )
        # P3-OBS-002: these counters were computed on request and returned to whoever
        # asked, which meant nobody. Recorded here as well, so "automation status" —
        # one of Gate 11's named metrics — leaves the process.
        instruments.record_automation_run(
            timing.cache_state, "failed" if timing.failure_count else "ok"
        )

    async def record_generation(
        self, event: GenerationEvent, *, now_ms: int | None = None
    ) -> str:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        generation_id = new_id("generation")
        await self.store.execute(
            """
            INSERT INTO automation_generation_telemetry(
              generation_id, goal_class, medium, outcome, pattern_reused, ir_cache_hit,
              first_use_latency_ms, recorded_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generation_id, event.goal_class, event.medium, event.outcome,
                1 if event.pattern_reused else 0, 1 if event.ir_cache_hit else 0,
                max(0, event.first_use_latency_ms), now,
            ),
        )
        return generation_id

    # --------------------------------------------------------------- reading

    async def ladder_metrics(
        self, *, window_ms: int | None = None, now_ms: int | None = None
    ) -> LadderMetrics:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        window = self.DEFAULT_WINDOW_MS if window_ms is None else window_ms
        since = now - window

        rows = await self.store.fetchall(
            "SELECT medium, outcome, pattern_reused, ir_cache_hit, first_use_latency_ms "
            "FROM automation_generation_telemetry WHERE recorded_at_ms >= ?",
            (since,),
        )
        by_medium: dict[str, int] = {}
        latencies: list[int] = []
        hot = warm = cold = failures = reuse = cache_hits = 0
        for row in rows:
            medium = str(row["medium"])
            by_medium[medium] = by_medium.get(medium, 0) + 1
            if medium == "N8N_HOT":
                hot += 1
            elif medium == "N8N_WARM":
                warm += 1
            elif medium == "WORKFLOW_COMPILER":
                cold += 1
            outcome = str(row["outcome"])
            if outcome not in ("ADMITTED_CANDIDATE", "REQUIRES_OWNER_APPROVAL", "SERVED"):
                failures += 1
            reuse += int(row["pattern_reused"])
            cache_hits += int(row["ir_cache_hit"])
            latencies.append(int(row["first_use_latency_ms"]))

        return LadderMetrics(
            total=len(rows), hot=hot, warm=warm, cold=cold,
            generation_failures=failures, pattern_reuse=reuse, ir_cache_hits=cache_hits,
            median_first_use_latency_ms=percentile(latencies, 50) or 0,
            window_ms=window, by_medium=by_medium,
        )

    async def run_latency(
        self, *, capability_id: str | None = None, window_ms: int | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """§57 — p50/p95 of what VAN controls, kept apart from external wait."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        since = now - (self.DEFAULT_WINDOW_MS if window_ms is None else window_ms)
        if capability_id is None:
            rows = await self.store.fetchall(
                "SELECT * FROM automation_run_telemetry WHERE recorded_at_ms >= ?", (since,)
            )
        else:
            rows = await self.store.fetchall(
                "SELECT * FROM automation_run_telemetry WHERE recorded_at_ms >= ? "
                "AND capability_id = ?",
                (since, capability_id),
            )
        overheads: list[int] = []
        totals: list[int] = []
        by_state: dict[str, int] = {}
        retries = 0
        for row in rows:
            timing = RunTiming(
                run_id=str(row["run_id"]),
                cache_state=CacheState(str(row["cache_state"])),
                compile_time_ms=int(row["compile_time_ms"]),
                dispatch_time_ms=int(row["dispatch_time_ms"]),
                execution_time_ms=int(row["execution_time_ms"]),
                external_wait_ms=int(row["external_wait_ms"]),
                verification_time_ms=int(row["verification_time_ms"]),
            )
            overheads.append(timing.van_overhead_ms)
            totals.append(timing.total_ms)
            state = timing.cache_state.value
            by_state[state] = by_state.get(state, 0) + 1
            retries += int(row["retry_count"])
        return {
            "runs": len(rows),
            "by_cache_state": by_state,
            "retry_count": retries,
            "van_overhead_p50_ms": percentile(overheads, 50) or 0,
            "van_overhead_p95_ms": percentile(overheads, 95) or 0,
            "total_p50_ms": percentile(totals, 50) or 0,
            "total_p95_ms": percentile(totals, 95) or 0,
        }


__all__ = [
    "CacheState",
    "GenerationEvent",
    "LadderMetrics",
    "RunTiming",
    "TelemetryService",
]
