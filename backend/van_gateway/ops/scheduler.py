"""The thing that actually calls the due work.

P3-OPS-004: `ReminderService.fire_due` existed, was correct, and had no caller
outside its own test. A reminder the owner set came due and nothing happened —
the row sat at `OPEN` until somebody hit an endpoint that happened to sweep it,
and no endpoint did. "Set a reminder" was a feature VAN could accept and could
not perform.

Four properties this scheduler has that a bare `while True: await sleep(n)` does
not, each because of a way that shape fails:

**It remembers when a job last ran.** `scheduler_runs` is read at startup, so a
restart does not re-run everything as though the process had never existed. A
restart loop with an in-memory "last run" re-fires every job on every restart.

**A failing job does not stop the loop, and does not pass silently.** Each run is
recorded with its outcome; a raised exception becomes `outcome="FAILED"` with the
error class, the loop continues, and `last_run` reports the failure. The two
failure modes to avoid are a scheduler that dies on one bad job and a scheduler
that swallows errors until someone notices the work is not happening.

**It reports.** `status()` is what `GET /v1/observability/health` reads, so
"is the scheduler running" is answerable without attaching a debugger.

**It does not fire while the loop is stopped.** `run_once` is separated from the
loop so tests drive it deterministically, rather than sleeping and hoping.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from van_gateway.observability import instruments
from van_gateway.observability.logging import log_event
from van_gateway.storage.db import Store

LOGGER = logging.getLogger("van.scheduler")

JobFn = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    interval_seconds: int
    run: JobFn
    #: Up to this fraction of the interval is added at random to each next-due time,
    #: so N gateways (or N restarts) do not all hit SQLite on the same second.
    jitter: float = 0.1


class OpsScheduler:
    def __init__(self, store: Store, jobs: tuple[ScheduledJob, ...] = ()) -> None:
        self.store = store
        self.jobs = {job.name: job for job in jobs}
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._next_due: dict[str, float] = {}
        self._tick_seconds = 1.0

    # ------------------------------------------------------------------ state

    async def last_run(self, job_name: str) -> dict[str, Any] | None:
        rows = await self.store.fetchall(
            "SELECT job_name, run_at_unix, finished_at_unix, outcome, detail_json "
            "FROM scheduler_runs WHERE job_name = ? ORDER BY run_at_unix DESC LIMIT 1",
            (job_name,),
        )
        if not rows:
            return None
        row = dict(rows[0])
        row["detail"] = json.loads(row.pop("detail_json"))
        return row

    async def prime(self, *, now_unix: int | None = None) -> None:
        """Set each job's next-due time from what the database remembers."""
        now = now_unix if now_unix is not None else int(time.time())
        for name, job in self.jobs.items():
            previous = await self.last_run(name)
            last = int(previous["run_at_unix"]) if previous else None
            if last is None:
                # Never run: due immediately. A first-boot gateway should fire the
                # reminder that came due while it was being installed.
                self._next_due[name] = float(now)
            else:
                self._next_due[name] = float(last + job.interval_seconds)

    def due(self, *, now_unix: float) -> list[ScheduledJob]:
        return [
            job for name, job in self.jobs.items()
            if self._next_due.get(name, 0.0) <= now_unix
        ]

    # ----------------------------------------------------------------- running

    async def run_job(self, job: ScheduledJob, *, now_unix: int | None = None) -> dict[str, Any]:
        started = now_unix if now_unix is not None else int(time.time())
        with instruments.timed() as elapsed:
            try:
                detail = await job.run()
                outcome = "OK"
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                detail = {"error_class": type(exc).__name__, "error": str(exc)}
                outcome = "FAILED"
                instruments.record_error(type(exc).__name__, f"scheduler:{job.name}")
                log_event(
                    LOGGER, logging.ERROR, "scheduled job failed",
                    error_class=type(exc).__name__, result=outcome,
                    detail={"job": job.name, "error": str(exc)},
                )
        finished = int(time.time())
        await self.store.execute(
            "INSERT OR REPLACE INTO scheduler_runs(job_name, run_at_unix, finished_at_unix, "
            "outcome, detail_json) VALUES (?, ?, ?, ?, ?)",
            (job.name, started, finished, outcome, Store.dumps(detail)),
        )
        spread = job.interval_seconds * job.jitter
        self._next_due[job.name] = started + job.interval_seconds + random.uniform(0, spread)
        if outcome == "OK":
            log_event(
                LOGGER, logging.INFO, "scheduled job completed",
                result=outcome, detail={"job": job.name, "duration_ms": round(elapsed[0]), **detail},
            )
        return {"job": job.name, "outcome": outcome, "detail": detail,
                "duration_ms": round(elapsed[0])}

    async def run_once(self, *, now_unix: int | None = None) -> list[dict[str, Any]]:
        """Run every job that is due. The unit of work a test drives."""
        now = now_unix if now_unix is not None else int(time.time())
        return [await self.run_job(job, now_unix=now) for job in self.due(now_unix=now)]

    async def _loop(self) -> None:
        await self.prime()
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the loop itself must survive
                log_event(LOGGER, logging.ERROR, "scheduler tick failed",
                          error_class=type(exc).__name__, detail={"error": str(exc)})
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._tick_seconds)
            except asyncio.TimeoutError:
                continue

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="van-ops-scheduler")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        self._task = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "jobs": [
                {
                    "name": name,
                    "interval_seconds": job.interval_seconds,
                    "next_due_unix": int(self._next_due.get(name, 0)),
                    "last_run": await self.last_run(name),
                }
                for name, job in sorted(self.jobs.items())
            ],
        }


__all__ = ["JobFn", "OpsScheduler", "ScheduledJob"]
