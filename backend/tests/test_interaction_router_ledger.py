"""Reviewer I minor 6 — router steps are written to the browser task ledger and the §8
counters survive a restart.

Before: /v1/browser/interaction/step wrote nothing (no browser_evidence row, no task
record) and RouterMetrics lived only in memory.
"""

from __future__ import annotations

import asyncio

from test_browser_interaction_router import (
    HEADERS,
    FakeJev,
    FakeStagehand,
    _env,  # noqa: F401 - fixture
    _http,
    make_router,
    proposes,
    shadow,
    step,
    T_LINK,
)
from tests.conftest_automation import make_store
from van_gateway.browser.interaction_router import (
    ROUTER_STEP_EVIDENCE_KIND,
    RouterStepLedger,
    StepState,
)
from van_gateway.browser.models import AutonomyTier, BrowserStrategy
from van_gateway.browser.service import BrowserTaskService
from van_gateway.models import ActionClass
from van_gateway.verification import observations


async def _real_task(store):
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    return await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.STAGEHAND,
        autonomy_tier=AutonomyTier.L4_STAGEHAND_ACT, action_class=ActionClass.A2,
        target_domain="docs.example.com", goal="find the install page",
    )


def _step_for(task, **kw):
    s = step(**kw)
    s.task = task
    return s


async def test_each_step_is_recorded_with_lane_outcome_and_verification(tmp_path):
    store = await make_store(tmp_path)
    task = await _real_task(store)
    ledger = RouterStepLedger(store)
    router = make_router(ledger=ledger, jev_client=FakeJev(shadow("click", T_LINK)),
                         semantic_fallback=FakeStagehand(None))
    first = await router.route(_step_for(task))
    router.jev_client = FakeJev(proposes("click", T_LINK))
    second = await router.route(_step_for(task))
    records = await ledger.steps_for_task(task.task_id)
    assert [r["lane"] for r in records] == ["OWNER_TAKEOVER", "JEV"]
    assert [r["state"] for r in records] == ["OWNER_TAKEOVER", "VERIFIED_SUCCESS"]
    assert records[1]["verification"]["outcome"] == "VERIFIED"
    assert records[1]["action"] == {"lane": "JEV", "operation": "click", "target_id": T_LINK, "action_class": "A2"}
    assert records[0]["shadow_jev"]["lifecycle_state"] == "SHADOW"
    assert first.ledger_ref and second.ledger_ref and first.ledger_ref != second.ledger_ref
    # Nothing page-derived beyond codes: no locator ever reaches the record.
    assert "a#install" not in str(records)


async def test_counters_are_rederived_from_the_ledger_after_a_restart(tmp_path):
    store = await make_store(tmp_path)
    task = await _real_task(store)
    router = make_router(ledger=RouterStepLedger(store))
    for _ in range(3):
        await router.route(_step_for(task))
    before = dict(router.metrics.counts)
    assert before["total_steps"] == 3 and before["jev_executed"] == 3
    restarted = make_router(ledger=RouterStepLedger(store))
    await restarted.ensure_metrics_loaded()
    assert restarted.metrics.counts == before
    await restarted.route(_step_for(task))
    assert restarted.metrics.counts["total_steps"] == 4


async def test_interleaved_steps_each_record_only_their_own_increments(tmp_path):
    store = await make_store(tmp_path)
    task = await _real_task(store)

    class SlowJev(FakeJev):
        async def propose_action(self, **kw):
            await asyncio.sleep(0.01)
            return await super().propose_action(**kw)

    router = make_router(ledger=RouterStepLedger(store), jev_client=SlowJev(proposes("click", T_LINK)))
    await asyncio.gather(*(router.route(_step_for(task)) for _ in range(4)))
    records = await RouterStepLedger(store).steps_for_task(task.task_id)
    assert len(records) == 4
    assert all(r["metric_increments"]["total_steps"] == 1 for r in records)
    assert all(r["metric_increments"]["jev_executed"] == 1 for r in records)


async def test_a_ledger_failure_is_reported_not_hidden(tmp_path):
    class BrokenLedger:
        async def persisted_counters(self):
            return {}

        async def record(self, *a):
            raise OSError("disk")

    router = make_router(ledger=BrokenLedger())
    result = await router.route(step())
    assert result.state is StepState.VERIFIED_SUCCESS
    assert "ROUTER_STEP_LEDGER_WRITE_FAILED:OSError" in result.reasons


async def test_router_step_records_are_not_mission_browser_evidence(tmp_path):
    """A refused/failed step is not "evidence captured" for the mission read-back."""
    store = await make_store(tmp_path)
    task = await _real_task(store)
    await store.execute(
        "INSERT INTO missions(mission_id, owner_principal_id, origin, origin_channel, "
        "title, goal, created_at_ms, updated_at_ms) VALUES ('m1', 'owner', 'OWNER_VOICE', 'VOICE', 't', 'g', 0, 0)",
    )
    await store.execute(
        "INSERT INTO mission_activities(activity_id, mission_id, activity_type, capability_id, "
        "executor, executor_ref, started_at_ms) VALUES ('act1', 'm1', 'BROWSE', 'cap', 'BROWSER_FABRIC', ?, 0)",
        (task.task_id,),
    )
    router = make_router(ledger=RouterStepLedger(store), jev_client=FakeJev(None),
                         semantic_fallback=FakeStagehand(None))
    await router.route(_step_for(task))
    assert await observations.browser_evidence_readback(store, "m1") == {"evidence_captured": False}
    rows = await store.fetchall("SELECT kind FROM browser_evidence WHERE task_id = ?", (task.task_id,))
    assert [r["kind"] for r in rows] == [ROUTER_STEP_EVIDENCE_KIND]


async def test_http_step_is_listed_in_the_task_evidence_and_metrics_say_persisted(_env, tmp_path):
    router = make_router()
    ac, api = await _http(tmp_path, router)
    router.ledger = RouterStepLedger(api.store)
    async with ac:
        await ac.post("/v1/browser/profiles", json={"profile_alias": "public_research"}, headers=HEADERS)
        created = await ac.post("/v1/browser/tasks", json={
            "profile_alias": "public_research", "strategy": "STAGEHAND",
            "autonomy_tier": "L4_STAGEHAND_ACT", "action_class": "A2",
            "target_domain": "docs.example.com", "goal": "find the install page",
        }, headers=HEADERS)
        task_id = created.json()["task_id"]
        stepped = await ac.post("/v1/browser/interaction/step", json={
            "task_id": task_id, "action_class_ceiling": "A2",
            "deterministic_action": {"operation": "click", "locator": "#go"},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "Install"},
        }, headers=HEADERS)
        evidence = await ac.get(f"/v1/browser/tasks/{task_id}/evidence", headers=HEADERS)
        metrics = await ac.get("/v1/browser/interaction/metrics", headers=HEADERS)
    assert stepped.status_code == 200, stepped.text
    assert stepped.json()["ledger_ref"].startswith("browser-evidence://")
    kinds = [row["kind"] for row in evidence.json()]
    assert kinds == [ROUTER_STEP_EVIDENCE_KIND]
    assert metrics.json()["persisted"] is True


def test_production_wiring_has_a_ledger_when_a_store_is_given():
    from van_gateway.browser.interaction_router import build_interaction_router
    from van_gateway.config import Settings

    router = build_interaction_router(settings=Settings(), harness=object(), stagehand=object(),
                                      jev_client=None, store=object())
    assert isinstance(router.ledger, RouterStepLedger)
    assert router.status()["metrics_persisted"] is True
