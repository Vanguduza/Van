"""P3-OPS-004 / P3-OPS-005 — due work is actually called, and only once.

`ReminderService.fire_due` existed, was correct, and had no caller. A reminder
the owner set came due and nothing happened. The tests here are about the two
ways a naive scheduler fails instead: re-running everything after a restart, and
dying on one bad job.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from conftest_automation import make_store
from van_gateway.ops.scheduler import OpsScheduler, ScheduledJob
from van_gateway.reminders.service import ReminderService
from van_gateway.models import ReminderCreate


@pytest.mark.asyncio
async def test_a_reminder_that_comes_due_is_fired_by_the_system_itself(tmp_path):
    store = await make_store(tmp_path)
    reminders = ReminderService(store)
    now = int(time.time())
    await reminders.create(ReminderCreate(
        text="call the bank", due_at_unix=now - 60, idempotency_key="r-1",
    ))
    fired: list[dict] = []

    async def sweep() -> dict:
        found = await reminders.fire_due()
        fired.extend(found)
        return {"fired": len(found)}

    scheduler = OpsScheduler(store, (ScheduledJob("reminders.fire_due", 60, sweep),))
    await scheduler.prime(now_unix=now)
    await scheduler.run_once(now_unix=now)
    assert [item["text"] for item in fired] == ["call the bank"]


@pytest.mark.asyncio
async def test_a_restart_does_not_re_run_everything(tmp_path):
    """An in-memory "last run" re-fires every job on every restart, which in a
    restart loop means firing the same work forever."""
    store = await make_store(tmp_path)
    runs = {"n": 0}

    async def job() -> dict:
        runs["n"] += 1
        return {"ran": runs["n"]}

    now = int(time.time())
    first = OpsScheduler(store, (ScheduledJob("ops.hourly", 3600, job),))
    await first.prime(now_unix=now)
    await first.run_once(now_unix=now)
    assert runs["n"] == 1

    # A brand-new scheduler object: the process restarted.
    second = OpsScheduler(store, (ScheduledJob("ops.hourly", 3600, job),))
    await second.prime(now_unix=now + 30)
    await second.run_once(now_unix=now + 30)
    assert runs["n"] == 1, "the restart re-ran a job that had just run"

    await second.prime(now_unix=now + 3700)
    await second.run_once(now_unix=now + 3700)
    assert runs["n"] == 2


@pytest.mark.asyncio
async def test_a_job_that_has_never_run_is_due_immediately(tmp_path):
    """A first-boot gateway should fire the reminder that came due while it was
    being installed, not wait out a full interval first."""
    store = await make_store(tmp_path)
    ran = asyncio.Event()

    async def job() -> dict:
        ran.set()
        return {}

    scheduler = OpsScheduler(store, (ScheduledJob("ops.daily", 86_400, job),))
    await scheduler.prime()
    await scheduler.run_once()
    assert ran.is_set()


@pytest.mark.asyncio
async def test_a_failing_job_is_recorded_and_the_loop_survives(tmp_path):
    """The two failure modes: a scheduler that dies on one bad job, and one that
    swallows errors until somebody notices the work is not happening."""
    store = await make_store(tmp_path)
    good = {"n": 0}

    async def bad() -> dict:
        raise RuntimeError("the external thing is down")

    async def fine() -> dict:
        good["n"] += 1
        return {}

    scheduler = OpsScheduler(store, (
        ScheduledJob("ops.bad", 60, bad), ScheduledJob("ops.fine", 60, fine),
    ))
    await scheduler.prime()
    results = {item["job"]: item for item in await scheduler.run_once()}
    assert results["ops.bad"]["outcome"] == "FAILED"
    assert results["ops.bad"]["detail"]["error_class"] == "RuntimeError"
    assert good["n"] == 1, "one job's failure stopped the others"

    last = await scheduler.last_run("ops.bad")
    assert last["outcome"] == "FAILED"
    assert "the external thing is down" in last["detail"]["error"]


@pytest.mark.asyncio
async def test_status_says_whether_the_scheduler_is_actually_running(tmp_path):
    """"Is the scheduler alive" must be answerable without attaching a debugger."""
    store = await make_store(tmp_path)
    ticks = {"n": 0}

    async def job() -> dict:
        ticks["n"] += 1
        return {}

    scheduler = OpsScheduler(store, (ScheduledJob("ops.tick", 3600, job),))
    assert scheduler.running is False
    await scheduler.start()
    try:
        for _ in range(50):
            if ticks["n"]:
                break
            await asyncio.sleep(0.02)
        assert scheduler.running is True
        status = await scheduler.status()
        assert status["running"] is True
        assert status["jobs"][0]["name"] == "ops.tick"
        assert status["jobs"][0]["last_run"]["outcome"] == "OK"
    finally:
        await scheduler.stop()
    assert scheduler.running is False


@pytest.mark.asyncio
async def test_the_next_due_time_is_jittered_so_restarts_do_not_synchronise(tmp_path):
    store = await make_store(tmp_path)

    async def job() -> dict:
        return {}

    nexts = set()
    for _ in range(8):
        scheduler = OpsScheduler(store, (ScheduledJob("ops.j", 3600, job, jitter=0.5),))
        await scheduler.prime(now_unix=1000)
        await scheduler.run_job(scheduler.jobs["ops.j"], now_unix=1000)
        nexts.add(scheduler._next_due["ops.j"])
    assert len(nexts) > 1, "every instance chose the same next-due second"
    assert all(4600 <= value <= 4600 + 1800 for value in nexts)
