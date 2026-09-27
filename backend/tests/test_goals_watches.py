from __future__ import annotations

import pytest

from van_gateway.attention.engine import AttentionEngine
from van_gateway.goals.models import (
    GoalCreate, GoalPatch, GoalStatus, WatchCreate, WatchObservation,
    WatchSourceKind, WatchStatus,
)
from van_gateway.goals.service import GoalService
from van_gateway.storage.db import Store


@pytest.mark.asyncio
async def test_goal_is_distinct_from_mission_and_tracks_milestones(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=GoalService(store,AttentionEngine(store))
    goal=await service.create(GoalCreate(title="Prepare launch",milestones=["Design","Ship"]))
    assert goal.status is GoalStatus.ACTIVE
    assert len(goal.milestones)==2
    goal=await service.set_milestone(goal.goal_id,goal.milestones[0].milestone_id,True)
    assert goal.milestones[0].done is True
    goal=await service.link_mission(goal.goal_id,"mission-1")
    assert goal.mission_ids==["mission-1"]
    goal=await service.patch(goal.goal_id,GoalPatch(status=GoalStatus.COMPLETED))
    assert goal.completed_at_ms is not None


@pytest.mark.asyncio
async def test_watch_change_and_failure_streak_dedupe_reset(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    attention=AttentionEngine(store)
    service=GoalService(store,attention)
    watch=await service.create_watch(WatchCreate(
        title="Page changed",source_kind=WatchSourceKind.BROWSER,target="https://example.com",
        condition={"kind":"CHANGED"},interval_seconds=60,
    ),now_ms=1000)
    first=await service.record_observation(watch.watch_id,WatchObservation(observation="a"),now_ms=2000)
    assert first["triggered"] is False
    second=await service.record_observation(watch.watch_id,WatchObservation(observation="b"),now_ms=3000)
    assert second["triggered"] is True

    fail1=await service.record_observation(watch.watch_id,WatchObservation(success=False,error_code="offline"),now_ms=4000)
    fail2=await service.record_observation(watch.watch_id,WatchObservation(success=False,error_code="offline"),now_ms=5000)
    assert fail1["failure_streak"]==fail2["failure_streak"]==1
    await service.record_observation(watch.watch_id,WatchObservation(observation="b"),now_ms=6000)
    fail3=await service.record_observation(watch.watch_id,WatchObservation(success=False,error_code="offline"),now_ms=7000)
    assert fail3["failure_streak"]==2


@pytest.mark.asyncio
async def test_watch_pauses_after_three_consecutive_failures(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=GoalService(store,AttentionEngine(store))
    watch=await service.create_watch(WatchCreate(
        title="Availability",source_kind=WatchSourceKind.PROVIDER,target="sku:1",
        condition={"kind":"BOOLEAN_TRUE"},interval_seconds=60,
    ))
    for _ in range(2):
        result=await service.record_observation(watch.watch_id,WatchObservation(success=False,error_code="down"))
        assert result["paused"] is False
    result=await service.record_observation(watch.watch_id,WatchObservation(success=False,error_code="down"))
    assert result["paused"] is True
    assert (await service.get_watch(watch.watch_id)).status is WatchStatus.PAUSED


class _Ready:
    ready = True


class _FakeHarness:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    async def status(self):
        return _Ready()

    async def navigate(self, task, url):
        self.calls.append((task.task_id, url))
        return {
            "url": url,
            "title": "Availability",
            "extraction": {"visible_text": self.text},
        }


@pytest.mark.asyncio
async def test_scheduler_runner_reads_public_watch_without_agent_loop(tmp_path):
    from van_gateway.browser.service import BrowserSessionBroker, BrowserTaskService
    from van_gateway.goals.watch_runner import WatchRunner

    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    attention=AttentionEngine(store)
    service=GoalService(store,attention)
    watch=await service.create_watch(WatchCreate(
        title="OpenMuse release",
        source_kind=WatchSourceKind.BROWSER,
        target="https://example.com/releases",
        condition={"kind":"TEXT_CONTAINS","text":"available"},
        interval_seconds=60,
    ),now_ms=1000)
    broker=BrowserSessionBroker(store)
    tasks=BrowserTaskService(store,broker)
    harness=_FakeHarness("not available")
    runner=WatchRunner(service,tasks=tasks,broker=broker,harness=harness)

    first=await runner.run(now_ms=1000)
    assert first=={"due":1,"checked":1,"triggered":1,"failed":0}
    assert len(harness.calls)==1

    # Same condition remains present: no second edge-trigger alert.
    await store.execute("UPDATE watches SET next_run_at_ms = ? WHERE watch_id = ?",(2000,watch.watch_id))
    second=await runner.run(now_ms=2000)
    assert second["triggered"]==0


@pytest.mark.asyncio
async def test_browser_watch_rejects_local_or_insecure_target(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=GoalService(store,AttentionEngine(store))
    for target in ("http://example.com", "https://localhost/x", "https://127.0.0.1/x"):
        with pytest.raises(Exception,match="WATCH_BROWSER_TARGET_INVALID"):
            await service.create_watch(WatchCreate(
                title="bad",source_kind=WatchSourceKind.BROWSER,target=target,
                condition={"kind":"CHANGED"},interval_seconds=60,
            ))
