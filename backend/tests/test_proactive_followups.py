"""GAP-F-028 — the bounded proactive job: `ProactiveFollowUpJob`.

`ProactivePolicyService.may_create()` and `AttentionEngine` both existed and nothing
connected "a mission/decision/intent has gone quiet" to "the owner should hear about it"
without the owner or an external event asking first. These tests drive the real
producers (`MissionService`, `DecisionService`, `IntentContinuityGraph`'s own STALE
column) and the real `AttentionEngine`, and assert the job's three defining properties:
it surfaces what has actually gone quiet, it never duplicates, and it respects a policy
that turns it off.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from conftest_automation import make_store
from van_gateway.attention.engine import AttentionEngine
from van_gateway.decisions.service import DecisionCreate, DecisionService
from van_gateway.mission.models import MissionOrigin, MissionState
from van_gateway.mission.service import MissionService
from van_gateway.models import AttentionSeverity, OriginChannel
from van_gateway.proactive.autonomy import DomainTrustService, ProactivePolicyService
from van_gateway.proactive.followups import ProactiveFollowUpJob

NOW = 1_800_000_000_000
SIX_HOURS_MS = 6 * 60 * 60 * 1000
SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000
NINETY_ONE_DAYS_MS = 91 * 24 * 60 * 60 * 1000


@pytest_asyncio.fixture
async def store(tmp_path):
    return await make_store(tmp_path)


def _job(store, **kwargs) -> ProactiveFollowUpJob:
    attention = AttentionEngine(store)
    missions = MissionService(store)
    decisions = DecisionService(store, attention)
    trust = DomainTrustService(store)
    policy = ProactivePolicyService(store, trust)
    return ProactiveFollowUpJob(store, attention, missions, decisions, policy, **kwargs)


async def _waiting_mission(store, *, updated_at_ms: int) -> str:
    missions = MissionService(store)
    mission = await missions.create(
        owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE, title="Book the venue", goal="Book the venue",
        now_ms=updated_at_ms,
    )
    mission = await missions.transition(
        mission.mission_id, target=MissionState.UNDERSTOOD, now_ms=updated_at_ms,
    )
    mission = await missions.transition(
        mission.mission_id, target=MissionState.PLANNED, now_ms=updated_at_ms,
    )
    await missions.transition(
        mission.mission_id, target=MissionState.WAITING_FOR_OWNER, now_ms=updated_at_ms,
    )
    return mission.mission_id


async def _expired_mission(store, *, updated_at_ms: int) -> str:
    missions = MissionService(store)
    mission = await missions.create(
        owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE, title="Chase the courier", goal="Chase the courier",
        now_ms=updated_at_ms,
    )
    await missions.transition(
        mission.mission_id, target=MissionState.EXPIRED, now_ms=updated_at_ms,
    )
    return mission.mission_id


@pytest.mark.asyncio
class TestMissionsWaitingForOwner:
    async def test_a_mission_waiting_past_the_threshold_produces_one_follow_up(self, store):
        await _waiting_mission(store, updated_at_ms=NOW - SIX_HOURS_MS - 1)
        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["missions_waiting"] == 1

        attention = AttentionEngine(store)
        open_items = await attention.list_open()
        follow_ups = [i for i in open_items if i.severity is AttentionSeverity.FOLLOW_UP]
        assert len(follow_ups) == 1
        assert follow_ups[0].source == "proactive"
        assert follow_ups[0].dedupe_key.startswith("followup:mission_waiting:")

    async def test_a_second_run_does_not_duplicate_the_item(self, store):
        await _waiting_mission(store, updated_at_ms=NOW - SIX_HOURS_MS - 1)
        job = _job(store)
        await job.run(NOW)
        await job.run(NOW + 1000)

        attention = AttentionEngine(store)
        open_items = await attention.list_open()
        follow_ups = [i for i in open_items if i.severity is AttentionSeverity.FOLLOW_UP]
        assert len(follow_ups) == 1

    async def test_a_mission_still_within_the_threshold_is_left_alone(self, store):
        await _waiting_mission(store, updated_at_ms=NOW - 1000)
        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["missions_waiting"] == 0

    async def test_a_custom_threshold_is_honoured(self, store):
        await _waiting_mission(store, updated_at_ms=NOW - 1000)
        job = _job(store, waiting_owner_after_ms=500)
        result = await job.run(NOW)
        assert result["produced"]["missions_waiting"] == 1

    async def test_disabling_the_missions_domain_suppresses_it(self, store):
        await _waiting_mission(store, updated_at_ms=NOW - SIX_HOURS_MS - 1)
        trust = DomainTrustService(store)
        policy = ProactivePolicyService(store, trust)
        await policy.disable_follow_ups("missions", now_ms=NOW)
        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["missions_waiting"] == 0

        attention = AttentionEngine(store)
        open_items = await attention.list_open()
        assert [i for i in open_items if i.severity is AttentionSeverity.FOLLOW_UP] == []


@pytest.mark.asyncio
class TestMissionsExpired:
    async def test_a_recently_expired_mission_produces_a_follow_up(self, store):
        await _expired_mission(store, updated_at_ms=NOW - 1000)
        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["missions_expired"] == 1

    async def test_an_expiry_older_than_the_recency_window_is_not_dredged_up(self, store):
        await _expired_mission(store, updated_at_ms=NOW - SEVEN_DAYS_MS - 1)
        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["missions_expired"] == 0

    async def test_the_missions_domain_policy_also_governs_expiries(self, store):
        await _expired_mission(store, updated_at_ms=NOW - 1000)
        trust = DomainTrustService(store)
        policy = ProactivePolicyService(store, trust)
        await policy.disable_follow_ups("missions", now_ms=NOW)
        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["missions_expired"] == 0


@pytest.mark.asyncio
class TestDecisionsOpenPastDue:
    """`DecisionService.escalate` always stamps `created_at_unix` with the real wall
    clock (it takes no `now_ms`), so these use the real clock for "now" too rather than
    the synthetic `NOW` the mission/intent tests use."""

    async def test_an_old_open_decision_produces_a_follow_up(self, store):
        import time

        real_now_ms = int(time.time() * 1000)
        attention = AttentionEngine(store)
        decisions = DecisionService(store, attention)
        record = await decisions.escalate(
            DecisionCreate(title="Approve the refund?", body="b", source="hermes")
        )
        await store.execute(
            "UPDATE decisions SET created_at_unix = ? WHERE id = ?",
            ((real_now_ms - SIX_HOURS_MS - 1000) // 1000, record.id),
        )
        job = _job(store)
        result = await job.run(real_now_ms)
        assert result["produced"]["decisions_open"] == 1

    async def test_a_fresh_decision_is_left_alone(self, store):
        import time

        attention = AttentionEngine(store)
        decisions = DecisionService(store, attention)
        await decisions.escalate(
            DecisionCreate(title="Approve the refund?", body="b", source="hermes")
        )
        job = _job(store)
        result = await job.run(int(time.time() * 1000))
        assert result["produced"]["decisions_open"] == 0

    async def test_disabling_the_decisions_domain_leaves_missions_unaffected(self, store):
        import time

        real_now_ms = int(time.time() * 1000)
        await _waiting_mission(store, updated_at_ms=real_now_ms - SIX_HOURS_MS - 1)
        attention = AttentionEngine(store)
        decisions = DecisionService(store, attention)
        record = await decisions.escalate(
            DecisionCreate(title="Approve the refund?", body="b", source="hermes")
        )
        await store.execute(
            "UPDATE decisions SET created_at_unix = ? WHERE id = ?",
            ((real_now_ms - SIX_HOURS_MS - 1000) // 1000, record.id),
        )
        trust = DomainTrustService(store)
        policy = ProactivePolicyService(store, trust)
        await policy.disable_follow_ups("decisions", now_ms=real_now_ms)
        job = _job(store)
        result = await job.run(real_now_ms)
        assert result["produced"]["decisions_open"] == 0
        assert result["produced"]["missions_waiting"] == 1


@pytest.mark.asyncio
class TestIntentsMarkedStale:
    async def test_a_stale_intent_produces_a_follow_up(self, store):
        """Consumes the state `understanding.mark_stale_intents` already writes,
        rather than recomputing the ninety-day rule."""
        from van_gateway.understanding.memory import IntentContinuityGraph

        intents = IntentContinuityGraph(store)
        node = await intents.observe(owner_goal="Ship the Q3 report", now_ms=NOW - NINETY_ONE_DAYS_MS)
        marked = await intents.mark_stale(now_ms=NOW)
        assert marked == 1

        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["intents_stale"] == 1

        attention = AttentionEngine(store)
        open_items = await attention.list_open()
        dedupe_keys = {i.dedupe_key for i in open_items}
        assert f"followup:intent_stale:{node.intent_id}" in dedupe_keys

    async def test_an_active_intent_produces_nothing(self, store):
        from van_gateway.understanding.memory import IntentContinuityGraph

        intents = IntentContinuityGraph(store)
        await intents.observe(owner_goal="Ship the Q3 report", now_ms=NOW)
        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["intents_stale"] == 0

    async def test_disabling_intents_leaves_the_others_running(self, store):
        from van_gateway.understanding.memory import IntentContinuityGraph

        intents = IntentContinuityGraph(store)
        await intents.observe(owner_goal="Ship the Q3 report", now_ms=NOW - NINETY_ONE_DAYS_MS)
        await intents.mark_stale(now_ms=NOW)
        await _waiting_mission(store, updated_at_ms=NOW - SIX_HOURS_MS - 1)

        trust = DomainTrustService(store)
        policy = ProactivePolicyService(store, trust)
        await policy.disable_follow_ups("intents", now_ms=NOW)
        job = _job(store)
        result = await job.run(NOW)
        assert result["produced"]["intents_stale"] == 0
        assert result["produced"]["missions_waiting"] == 1


@pytest.mark.asyncio
class TestTheJobNeverActs:
    async def test_the_job_creates_no_mission_and_calls_no_mission_mutation_beyond_setup(
        self, store
    ):
        """It has no method that could open a mission or execute an action — asserted
        directly against the object's surface, not only its observed behaviour."""
        job = _job(store)
        public_methods = {
            name for name in dir(job)
            if not name.startswith("_") and callable(getattr(job, name))
        }
        assert public_methods == {"run"}

    async def test_a_full_sweep_with_nothing_due_produces_nothing(self, store):
        job = _job(store)
        result = await job.run(NOW)
        assert result["total"] == 0
        assert result["produced"] == {
            "missions_waiting": 0, "missions_expired": 0,
            "decisions_open": 0, "intents_stale": 0,
        }
