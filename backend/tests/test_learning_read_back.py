"""GAP-F-008 — the learning read-back: `LearningFeed.strategies_for` gets a caller.

`strategies_for` (learning/feed.py) → `permitted_for`/`preferred_for` (evolution/radar.py)
was written, tested at the store layer, and never called by anything outside its own
definition — every mission outcome fed the learning stores and nothing downstream ever
read them back. These tests drive the real producer path (`MissionService` with a real
`LearningFeed`, through `record_strategy_outcome`) so what is asserted is the same thing
the symbiotic audit's acceptance criterion asks for: a mission whose strategy was
promoted changes what the next same-intent command can be told.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from van_gateway.evolution.radar import PromotionState, RadarError, StrategyLearning
from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.models import (
    AuthorityEnvelope,
    MissionOrigin,
    MissionState,
    SuccessContract,
)
from van_gateway.mission.service import MissionService
from van_gateway.models import ActionClass, OriginChannel
from van_gateway.storage.db import Store


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "learn_readback.sqlite3"))
    await s.migrate()
    return s


def _svc(store):
    from van_gateway.verification.production import build_mission_registry

    class NoNotebooks:
        async def notebook_enterprise_get(self, notebook_id):  # pragma: no cover
            raise RuntimeError("not used")

    class FixedLedger:
        def status(self):
            return {
                "ledger_available": True, "chain_ok": True, "head": "h1",
                "kill_switch_active": True, "kill_switch_triggers": ["OWNER_HALT"],
                "ledger_stale": False,
            }

        def trade_detail(self, trade_intent_id):
            return {"status": "FILLED", "filled_qty": "1", "fill_price": "2"}

    return MissionService(
        store,
        learning=LearningFeed(store),
        verifiers=build_mission_registry(
            store=store, trading=FixedLedger(), knowledge=NoNotebooks(),
        ),
    )


async def _run_mission(svc, *, mission_class, capabilities, terminal):
    """A mission that really executed `capabilities`, taken to a terminal state —
    the same producer path `mission/service.py` uses in production."""
    mission = await svc.create(
        owner_principal_id="owner",
        origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,
        title="t", goal="g",
        mission_class=mission_class,
        success_contract=SuccessContract(
            postconditions={"trade_intent_id": "ti-1", "trade_found": True},
            verifier_class="ledger-event",
        ),
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A2),
    )
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING):
        mission = await svc.transition(mission.mission_id, target=target)
    for index, capability_id in enumerate(capabilities):
        await svc.add_activity(
            mission_id=mission.mission_id, activity_type="WORK",
            capability_id=capability_id, executor="HERMES", executor_ref=f"ref-{index}",
        )
    if terminal in (MissionState.VERIFIED_SUCCESS, MissionState.PARTIAL_SUCCESS,
                    MissionState.UNVERIFIABLE, MissionState.FAILED):
        await svc.transition(mission.mission_id, target=MissionState.VERIFYING)
    return await svc.transition(mission.mission_id, target=terminal)


async def _promote_to_preferred(store, mission_class, capabilities, *, extra_runs=0):
    """Run the mission ten times to VERIFIED_SUCCESS and promote it — the only path
    `StrategyLearning.promote` accepts for PREFERRED (§25's eval-evidence gate)."""
    svc = _svc(store)
    for _ in range(10 + extra_runs):
        await _run_mission(
            svc, mission_class=mission_class, capabilities=capabilities,
            terminal=MissionState.VERIFIED_SUCCESS,
        )
    learning = StrategyLearning(store)
    row = await store.fetchone(
        "SELECT strategy_id FROM execution_strategies WHERE mission_class = ?",
        (mission_class,),
    )
    strategy_id = str(row["strategy_id"])
    await learning.promote(
        strategy_id, target=PromotionState.PREFERRED, eval_run_id="eval-readback-1",
    )
    return strategy_id


@pytest.mark.asyncio
class TestStrategiesForIsTheReadBack:
    async def test_a_freshly_run_strategy_is_not_yet_offered(self, store):
        """EXPERIMENTAL — real runs, no eval evidence — is a candidate, not a read-back."""
        svc = _svc(store)
        await _run_mission(
            svc, mission_class="RESEARCH_TASK", capabilities=["a", "b"],
            terminal=MissionState.VERIFIED_SUCCESS,
        )
        feed = LearningFeed(store)
        assert await feed.strategies_for(intent_id="RESEARCH_TASK") == []

    async def test_a_promoted_strategy_with_real_outcomes_is_offered(self, store):
        strategy_id = await _promote_to_preferred(
            store, "RESEARCH_TASK", ["search", "summarize"]
        )
        feed = LearningFeed(store)
        offered = await feed.strategies_for(intent_id="RESEARCH_TASK")
        assert len(offered) == 1
        row = offered[0]
        assert row["strategy_id"] == strategy_id
        assert row["permitted"] is True
        assert row["evidence_rate"] == 1.0
        assert row["outcome_counts"] == {"success": 10, "failure": 0, "inconclusive": 0}
        assert row["fingerprint"] and isinstance(row["fingerprint"], str)
        assert "search" in row["summary"] and "summarize" in row["summary"]

    async def test_an_unmentioned_intent_returns_nothing(self, store):
        await _promote_to_preferred(store, "RESEARCH_TASK", ["search"])
        feed = LearningFeed(store)
        assert await feed.strategies_for(intent_id="SOME_OTHER_INTENT") == []

    async def test_no_intent_id_returns_nothing(self, store):
        await _promote_to_preferred(store, "RESEARCH_TASK", ["search"])
        feed = LearningFeed(store)
        assert await feed.strategies_for(intent_id=None) == []
        assert await feed.strategies_for(intent_id="") == []

    async def test_a_demoted_strategy_is_excluded(self, store):
        """P1-LEARN-004 — auto_demote runs and the read-back must reflect it."""
        strategy_id = await _promote_to_preferred(store, "RESEARCH_TASK", ["search"])
        svc = _svc(store)
        for _ in range(10):
            await _run_mission(
                svc, mission_class="RESEARCH_TASK", capabilities=["search"],
                terminal=MissionState.FAILED,
            )
        learning = StrategyLearning(store)
        assert await learning.auto_demote() == [strategy_id]

        feed = LearningFeed(store)
        assert await feed.strategies_for(intent_id="RESEARCH_TASK") == []

    async def test_an_experimental_strategy_is_never_offered_however_many_runs(self, store):
        """Runs alone are not the gate — §25 promotion is, and nothing here bypasses it."""
        svc = _svc(store)
        for _ in range(20):
            await _run_mission(
                svc, mission_class="RESEARCH_TASK", capabilities=["search"],
                terminal=MissionState.VERIFIED_SUCCESS,
            )
        row = await store.fetchone(
            "SELECT promotion_state FROM execution_strategies WHERE mission_class = ?",
            ("RESEARCH_TASK",),
        )
        assert str(row["promotion_state"]) == "EXPERIMENTAL"
        feed = LearningFeed(store)
        assert await feed.strategies_for(intent_id="RESEARCH_TASK") == []

    async def test_an_admitted_strategy_with_no_production_runs_is_not_offered(self, store):
        """ADMITTED needs only an eval run (§25); this read-back needs a real outcome
        too (§41's "measurable improvement"), so a benchmark alone is not enough."""
        learning = StrategyLearning(store)
        strategy_id = await learning.find_or_register(
            mission_class="RESEARCH_TASK", capability_sequence=["search"],
            max_action_class=ActionClass.A1,
        )
        await learning.promote(
            strategy_id, target=PromotionState.ADMITTED, eval_run_id="eval-1",
        )
        feed = LearningFeed(store)
        assert await feed.strategies_for(intent_id="RESEARCH_TASK") == []

    async def test_results_are_bounded_by_limit(self, store):
        for name, capability in (("s1", "a"), ("s2", "b"), ("s3", "c")):
            await _promote_to_preferred(store, "RESEARCH_TASK", [capability])
        feed = LearningFeed(store)
        everything = await feed.strategies_for(intent_id="RESEARCH_TASK", limit=50)
        assert len(everything) == 3
        limited = await feed.strategies_for(intent_id="RESEARCH_TASK", limit=1)
        assert len(limited) == 1

    async def test_project_id_and_text_do_not_error_and_do_not_widen_the_match(self, store):
        """Accepted for call-shape symmetry (see the docstring); neither one is a
        wildcard — an intent that does not match `mission_class` still returns nothing."""
        await _promote_to_preferred(store, "RESEARCH_TASK", ["search"])
        feed = LearningFeed(store)
        offered = await feed.strategies_for(
            intent_id="RESEARCH_TASK", project_id="proj-1", text="find me a hotel",
        )
        assert len(offered) == 1
        assert await feed.strategies_for(
            intent_id="OTHER", project_id="proj-1", text="find me a hotel",
        ) == []

    async def test_a_strategy_proven_under_a_wider_envelope_still_carries_no_authority(
        self, store
    ):
        """P1-LEARN-002's invariant, restated for this caller: offering context is not
        granting execution. `ActionRuntime.begin` is what actually gates a run, and it
        does not read `canonical_context` at all."""
        svc = _svc(store)
        for _ in range(10):
            mission = await svc.create(
                owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
                origin_channel=OriginChannel.VOICE, title="t", goal="g",
                mission_class="RESEARCH_TASK",
                success_contract=SuccessContract(
                    postconditions={"trade_intent_id": "ti-1", "trade_found": True},
                    verifier_class="ledger-event",
                ),
                authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A4),
            )
            for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                           MissionState.AUTHORIZED, MissionState.RUNNING):
                mission = await svc.transition(mission.mission_id, target=target)
            await svc.add_activity(
                mission_id=mission.mission_id, activity_type="WORK",
                capability_id="dangerous", executor="HERMES", executor_ref="r",
            )
            await svc.transition(mission.mission_id, target=MissionState.VERIFYING)
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        learning = StrategyLearning(store)
        row = await store.fetchone(
            "SELECT strategy_id FROM execution_strategies WHERE mission_class = ?",
            ("RESEARCH_TASK",),
        )
        strategy_id = str(row["strategy_id"])
        await learning.promote(
            strategy_id, target=PromotionState.PREFERRED, eval_run_id="eval-1",
        )
        feed = LearningFeed(store)
        offered = await feed.strategies_for(intent_id="RESEARCH_TASK")
        assert offered[0]["strategy_id"] == strategy_id
        # The dict handed to `canonical_context` carries no action-class field at all —
        # there is nothing in it a consumer could read as a grant.
        assert "max_action_class" not in offered[0]
        assert "action_class" not in offered[0]

    async def test_promotion_still_refuses_without_eval_evidence(self, store):
        """The guard this read-back sits next to, so the two cannot silently drift."""
        learning = StrategyLearning(store)
        strategy_id = await learning.find_or_register(
            mission_class="X", capability_sequence=["a"], max_action_class=ActionClass.A1,
        )
        with pytest.raises(RadarError, match="REQUIRES_EVAL"):
            await learning.promote(strategy_id, target=PromotionState.ADMITTED)
