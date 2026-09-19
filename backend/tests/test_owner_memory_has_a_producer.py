"""P2-MEM-001 — §§65, 77, 78. Three owner-memory stores with no producer and no route.

`IntentContinuityGraph`, `DecisionFingerprints` and `StrategicMemory` were complete,
correct and referenced only by their own tests. Each is a concept VAN could describe and
had never seen an instance of: no mission observed a standing goal, no owner approval
recorded a decision, no rationale had anywhere to live, and `mark_stale` had no caller so
an intent observed once stayed ACTIVE forever.

The producer is the mission path, because that is where the owner's instructions and
approvals actually arrive. Curating these stores by hand is the design that produces empty
stores, which is what the audit found.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.models import (
    AuthorityEnvelope,
    MissionOrigin,
    MissionState,
    Sensitivity,
)
from van_gateway.mission.service import MissionService
from van_gateway.models import ActionClass, OriginChannel
from van_gateway.storage.db import Store
from van_gateway.understanding.memory import (
    DecisionFingerprints,
    IntentHorizon,
    IntentContinuityGraph,
    IntentEdgeType,
    IntentStatus,
    StrategicEntryType,
    StrategicMemory,
)

DAY_MS = 24 * 60 * 60 * 1000


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "mem.sqlite3"))
    await s.migrate()
    return s


def _svc(store):
    return MissionService(store, learning=LearningFeed(store))


async def _open(svc, *, goal, approved=False, project_id=None, constraints=()):
    return await svc.create(
        owner_principal_id="owner",
        origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,
        title=goal[:40], goal=goal,
        project_id=project_id,
        constraints=list(constraints),
        sensitivity=Sensitivity.ROUTINE,
        authority_envelope=AuthorityEnvelope(
            max_action_class=ActionClass.A4 if approved else ActionClass.A2,
            requires_owner_presence=approved,
        ),
    )


@pytest.mark.asyncio
class TestStandingGoalsComeFromMissions:
    async def test_opening_a_mission_observes_the_goal(self, store):
        svc = _svc(store)
        await _open(svc, goal="keep the trading ledger reconciled")
        rows = await store.fetchall("SELECT * FROM intent_nodes")
        assert len(rows) == 1
        assert str(rows[0]["owner_goal"]) == "keep the trading ledger reconciled"
        assert str(rows[0]["status"]) == "ACTIVE"

    async def test_asking_again_refreshes_the_standing_goal(self, store):
        """Keyed on the goal, so repetition is evidence the goal still matters.

        A second node would make STALE mean "recorded once" rather than "unmentioned for
        ninety days", which is the only reading that lets the status be acted on.
        """
        svc = _svc(store)
        for _ in range(3):
            await _open(svc, goal="keep the trading ledger reconciled")
        rows = await store.fetchall("SELECT * FROM intent_nodes")
        assert len(rows) == 1
        links = await store.fetchall("SELECT * FROM intent_missions")
        assert len(links) == 3

    async def test_every_mission_is_linked_to_its_goal(self, store):
        svc = _svc(store)
        mission = await _open(svc, goal="ship the release")
        row = await store.fetchone(
            "SELECT * FROM intent_missions WHERE mission_id = ?", (mission.mission_id,)
        )
        assert row is not None

    async def test_a_goal_nobody_mentions_goes_stale_and_a_mention_revives_it(self, store):
        graph = IntentContinuityGraph(store)
        node = await graph.observe(owner_goal="an old plan", now_ms=0)
        assert await graph.mark_stale(now_ms=graph.STALE_AFTER_MS + DAY_MS) == 1
        assert (await graph.get(node.intent_id)).status is IntentStatus.STALE
        # Mentioning it again is the owner saying it still matters.
        await graph.observe(owner_goal="an old plan", now_ms=graph.STALE_AFTER_MS + DAY_MS)
        assert (await graph.get(node.intent_id)).status is IntentStatus.ACTIVE

    async def test_a_recent_goal_is_not_swept(self, store):
        graph = IntentContinuityGraph(store)
        node = await graph.observe(owner_goal="a current plan", now_ms=0)
        assert await graph.mark_stale(now_ms=graph.STALE_AFTER_MS - 1) == 0
        assert (await graph.get(node.intent_id)).status is IntentStatus.ACTIVE

    async def test_the_scheduler_sweeps_stale_intents(self, monkeypatch, tmp_path):
        from cryptography.fernet import Fernet

        from van_gateway.config import get_settings

        monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "s.sqlite3"))
        monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("VAN_INGRESS_TOKEN", "mem-ingress-token-0123456789")
        get_settings.cache_clear()
        try:
            from van_gateway.app import create_app

            assert "understanding.mark_stale_intents" in create_app().state.scheduler.jobs
        finally:
            get_settings.cache_clear()

    async def test_a_one_off_request_does_not_become_a_standing_goal(self, store):
        """P2-MEM-003 — the defect this closes.

        Every mission goal was promoted straight into the standing-intent graph, so "what
        is on my calendar?" became a long-lived owner objective that stayed ACTIVE until
        the ninety-day stale sweep. §77's value is surfacing a newer instruction that
        contradicts an older standing goal; filling the graph with one-off requests gives
        it transient commands to contradict genuine goals with, which is worse than having
        no graph.
        """
        svc = _svc(store)
        await _open(svc, goal="what is on my calendar")
        row = (await store.fetchall("SELECT * FROM intent_nodes"))[0]
        assert str(row["horizon"]) == "EPHEMERAL"
        assert row["promoted_reason"] is None
        assert row["promoted_at_ms"] is None

    async def test_repetition_is_what_makes_something_standing(self, store):
        svc = _svc(store)
        graph = IntentContinuityGraph(store)
        for _ in range(graph.STANDING_AFTER_OBSERVATIONS):
            await _open(svc, goal="keep the trading ledger reconciled")
        row = (await store.fetchall("SELECT * FROM intent_nodes"))[0]
        assert str(row["horizon"]) == "STANDING"
        # Promotion records what caused it, so a standing goal can be argued with rather
        # than only observed.
        assert "times" in str(row["promoted_reason"])
        assert row["promoted_at_ms"] is not None

    async def test_one_short_of_the_threshold_is_still_not_standing(self, store):
        svc = _svc(store)
        graph = IntentContinuityGraph(store)
        for _ in range(graph.STANDING_AFTER_OBSERVATIONS - 1):
            await _open(svc, goal="check the ledger")
        row = (await store.fetchall("SELECT * FROM intent_nodes"))[0]
        assert str(row["horizon"]) != "STANDING"

    async def test_the_owner_saying_so_is_enough_on_its_own(self, store):
        """An owner declaration needs no corroboration — it is not VAN's inference."""
        graph = IntentContinuityGraph(store)
        node = await graph.observe(
            owner_goal="never trade on margin", owner_declared_standing=True,
        )
        assert node.horizon is IntentHorizon.STANDING
        assert node.observation_count == 1
        assert "the owner stated" in str(node.promoted_reason)

    async def test_a_project_goal_asked_twice_reaches_project_horizon(self, store):
        graph = IntentContinuityGraph(store)
        await graph.observe(owner_goal="finish the migration", project_id="van")
        node = await graph.observe(owner_goal="finish the migration", project_id="van")
        assert node.horizon is IntentHorizon.PROJECT
        assert "van" in str(node.promoted_reason)

    async def test_a_standing_goal_is_never_demoted_by_a_later_mention(self, store):
        """Only the owner retires an objective, which is the rule STALE already follows."""
        graph = IntentContinuityGraph(store)
        await graph.observe(owner_goal="a goal", owner_declared_standing=True)
        node = await graph.observe(owner_goal="a goal")
        assert node.horizon is IntentHorizon.STANDING

    def test_the_horizon_never_falls_whatever_the_inputs(self, store):
        """The invariant as a property rather than one example.

        Two separate guards prevent a demotion — the STANDING early return and the
        `current is EPHEMERAL` condition on the PROJECT branch — and each is redundant
        with the other, so a mutation of either survived a test written as an example.
        That is a fair warning: an invariant held by coincidence between two conditions is
        an invariant one refactor away from being lost. This asserts the property over
        every combination instead, so it holds however the branches are later arranged.
        """
        graph = IntentContinuityGraph(store)
        rank = {
            IntentHorizon.EPHEMERAL: 0,
            IntentHorizon.PROJECT: 1,
            IntentHorizon.STANDING: 2,
        }
        for current in IntentHorizon:
            for observations in range(1, graph.STANDING_AFTER_OBSERVATIONS + 3):
                for projects in ([], ["van"], ["van", "other"]):
                    for declared in (False, True):
                        horizon, reason = graph._horizon_for(
                            current=current,
                            observations=observations,
                            projects=projects,
                            owner_declared_standing=declared,
                        )
                        assert rank[horizon] >= rank[current], (
                            f"{current} -> {horizon} at observations={observations} "
                            f"projects={projects} declared={declared}"
                        )
                        # And a promotion always says what earned it, because a standing
                        # goal with no provenance cannot be argued with.
                        if horizon is not current:
                            assert reason, f"{current} -> {horizon} with no reason"

    def test_a_promotion_always_records_why(self, store):
        """Provenance, per the memory rule: never let an inference look like a statement.

        The two reasons are distinguishable on purpose — "the owner stated" and "asked for
        N times" are different kinds of evidence, and collapsing them would let VAN's own
        counting read as something the owner said.
        """
        graph = IntentContinuityGraph(store)
        declared, _ = graph._horizon_for(
            current=IntentHorizon.EPHEMERAL, observations=1, projects=[],
            owner_declared_standing=True,
        )
        assert declared is IntentHorizon.STANDING
        _, declared_reason = graph._horizon_for(
            current=IntentHorizon.EPHEMERAL, observations=1, projects=[],
            owner_declared_standing=True,
        )
        _, counted_reason = graph._horizon_for(
            current=IntentHorizon.EPHEMERAL,
            observations=graph.STANDING_AFTER_OBSERVATIONS, projects=[],
            owner_declared_standing=False,
        )
        assert "owner stated" in declared_reason
        assert "owner stated" not in counted_reason
        assert "times" in counted_reason

    async def test_repeated_system_observations_are_counted_as_what_they_are(self, store):
        """The count is observations, and every one of them came from the owner issuing a
        command. Nothing else writes to this graph, so repetition here cannot be VAN
        agreeing with itself."""
        svc = _svc(store)
        for _ in range(5):
            await _open(svc, goal="a repeated request")
        row = (await store.fetchall("SELECT * FROM intent_nodes"))[0]
        assert int(row["observation_count"]) == 5

    async def test_a_conflict_is_visible_from_both_sides(self, store):
        """The graph's whole value: a newer instruction that contradicts an older
        standing goal must be visible rather than silently winning."""
        graph = IntentContinuityGraph(store)
        old = await graph.observe(owner_goal="never trade on margin")
        new = await graph.observe(owner_goal="use leverage to hit the quarterly target")
        await graph.relate(
            from_intent_id=new.intent_id, to_intent_id=old.intent_id,
            edge_type=IntentEdgeType.CONFLICTS,
        )
        assert [n.intent_id for n in await graph.conflicts_for(old.intent_id)] == [new.intent_id]
        assert [n.intent_id for n in await graph.conflicts_for(new.intent_id)] == [old.intent_id]


@pytest.mark.asyncio
class TestDecisionsAreRecordedWithoutBeingInterpreted:
    async def test_an_approval_is_a_decision(self, store):
        svc = _svc(store)
        mission = await _open(svc, goal="halt trading", approved=True)
        rows = await store.fetchall(
            "SELECT * FROM decision_fingerprints WHERE mission_id = ?", (mission.mission_id,)
        )
        assert len(rows) == 1
        assert str(rows[0]["owner_choice"]).startswith("approved: halt trading")
        assert rows[0]["outcome"] is None

    async def test_ordinary_use_is_not_a_decision(self, store):
        """A command that needed no approval is not a choice.

        Recording one would fill §65's store with every time the owner used VAN, which
        would bury the decisions that were actually decisions.
        """
        svc = _svc(store)
        mission = await _open(svc, goal="what is on my calendar", approved=False)
        assert await store.fetchall(
            "SELECT * FROM decision_fingerprints WHERE mission_id = ?", (mission.mission_id,)
        ) == []

    async def test_nothing_is_inferred_about_why(self, store):
        """§12 — a fingerprint store that writes a plausible reason becomes a machine for
        justifying whatever the owner did last."""
        svc = _svc(store)
        mission = await _open(svc, goal="halt trading", approved=True)
        row = (await store.fetchall(
            "SELECT * FROM decision_fingerprints WHERE mission_id = ?", (mission.mission_id,)
        ))[0]
        assert row["inferred_reason"] is None
        assert row["owner_stated_reason"] is None
        # And so nothing can be falsified, because nothing was claimed.
        assert await DecisionFingerprints(store).falsified() == []

    async def test_the_outcome_is_recorded_when_the_mission_ends(self, store):
        svc = _svc(store)
        mission = await _open(svc, goal="halt trading", approved=True)
        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING, MissionState.FAILED):
            mission = await svc.transition(mission.mission_id, target=target)
        row = (await store.fetchall(
            "SELECT * FROM decision_fingerprints WHERE mission_id = ?", (mission.mission_id,)
        ))[0]
        assert str(row["outcome"]) == "failed"

    async def test_a_mission_nobody_approved_has_no_outcome_to_record(self, store):
        svc = _svc(store)
        mission = await _open(svc, goal="read something", approved=False)
        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING, MissionState.FAILED):
            mission = await svc.transition(mission.mission_id, target=target)
        assert await store.fetchall("SELECT * FROM decision_fingerprints") == []


@pytest.mark.asyncio
class TestStrategicMemoryIsTheOwnersToWrite:
    async def test_a_rejected_strategy_is_remembered_as_rejected(self, store):
        memory = StrategicMemory(store)
        await memory.record(
            project_id="van", entry_type=StrategicEntryType.REJECTED_STRATEGY,
            statement="poll Hermes for run status",
            rationale="a worker reporting on itself is not verification",
        )
        assert await memory.already_rejected("van", "poll Hermes for run status")
        assert not await memory.already_rejected("van", "read the provider back")

    async def test_rationale_is_scoped_to_its_project(self, store):
        memory = StrategicMemory(store)
        await memory.record(
            project_id="van", entry_type=StrategicEntryType.REJECTED_STRATEGY,
            statement="poll for status",
        )
        assert not await memory.already_rejected("other-project", "poll for status")
