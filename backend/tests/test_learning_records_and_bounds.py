"""P1-LEARN-002, P1-LEARN-003, P1-LEARN-004 — learning that happens, and cannot widen.

P1-LEARN-001 gave the learning stores a feed. It did not give `StrategyLearning` one, and
the reason turned out to be structural rather than an omission: every method on it keys on
`mission_class`, and no mission carried one. §25's "which capability sequences work" and
§41's "measurable strategy improvement in >= 3 production mission classes" were both
unanswerable, not because the invariants were wrong — the promotion gate genuinely refuses
without eval evidence — but because a row could never exist.

The class is the typed resolver's intent, which the command path already computed and threw
away. Wiring it makes the store fill, which immediately raises the question P1-LEARN-002
asked: what stops a sequence proven under an A4 mission being offered back to a mission the
owner capped at A2? Nobody would have widened anything; authority would have been acquired
by accumulation. So the ceiling a strategy was exercised under is recorded and compared.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from van_gateway.evolution.radar import (
    PromotionState,
    RadarError,
    StrategyLearning,
    StrategyOutcome,
)
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
    s = Store(str(tmp_path / "learn.sqlite3"))
    await s.migrate()
    return s


class FixedLedger:
    def status(self):
        return {
            "ledger_available": True, "chain_ok": True, "head": "h1",
            "kill_switch_active": True, "kill_switch_triggers": ["OWNER_HALT"],
            "ledger_stale": False,
        }

    def trade_detail(self, trade_intent_id):
        return {"status": "FILLED", "filled_qty": "1", "fill_price": "2"}


async def _run_mission(
    svc, *, mission_class, capabilities, terminal, action_class=ActionClass.A2,
):
    """A mission that really executed `capabilities`, taken to a terminal state."""
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
        authority_envelope=AuthorityEnvelope(max_action_class=action_class),
    )
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING):
        mission = await svc.transition(mission.mission_id, target=target)
    for index, capability_id in enumerate(capabilities):
        await svc.add_activity(
            mission_id=mission.mission_id, activity_type="WORK",
            capability_id=capability_id, executor="HERMES",
            executor_ref=f"ref-{index}",
        )
    # Only the verification outcomes are reachable through VERIFYING; a refusal or a
    # cancellation leaves from RUNNING. Driving each terminal state by its real path
    # matters here, because the point of these tests is what the *state machine* produces.
    if terminal in (MissionState.VERIFIED_SUCCESS, MissionState.PARTIAL_SUCCESS,
                    MissionState.UNVERIFIABLE, MissionState.FAILED):
        await svc.transition(mission.mission_id, target=MissionState.VERIFYING)
    return await svc.transition(mission.mission_id, target=terminal)


def _svc(store):
    from van_gateway.verification.production import build_mission_registry

    class NoNotebooks:
        async def notebook_enterprise_get(self, notebook_id):  # pragma: no cover
            raise RuntimeError("not used")

    return MissionService(
        store,
        learning=LearningFeed(store),
        verifiers=build_mission_registry(
            store=store, trading=FixedLedger(), knowledge=NoNotebooks(),
        ),
    )


@pytest.mark.asyncio
class TestAStrategyIsSomethingVanActuallyDid:
    async def test_a_verified_mission_records_the_sequence_it_ran(self, store):
        svc = _svc(store)
        await _run_mission(
            svc, mission_class="TRADING_HALT", capabilities=["a", "b"],
            terminal=MissionState.VERIFIED_SUCCESS,
        )
        rows = await store.fetchall("SELECT * FROM execution_strategies")
        assert len(rows) == 1
        assert rows[0]["mission_class"] == "TRADING_HALT"
        assert rows[0]["capability_sequence_json"] == Store.dumps(["a", "b"])
        assert int(rows[0]["success_count"]) == 1
        assert int(rows[0]["failure_count"]) == 0

    async def test_the_same_sequence_accumulates_rather_than_duplicating(self, store):
        svc = _svc(store)
        for _ in range(3):
            await _run_mission(
                svc, mission_class="TRADING_HALT", capabilities=["a", "b"],
                terminal=MissionState.VERIFIED_SUCCESS,
            )
        rows = await store.fetchall("SELECT * FROM execution_strategies")
        assert len(rows) == 1
        assert int(rows[0]["success_count"]) == 3

    async def test_a_different_order_is_a_different_strategy(self, store):
        """Order is the thing being learned, so ["a","b"] and ["b","a"] are not one row."""
        svc = _svc(store)
        await _run_mission(svc, mission_class="X", capabilities=["a", "b"],
                           terminal=MissionState.VERIFIED_SUCCESS)
        await _run_mission(svc, mission_class="X", capabilities=["b", "a"],
                           terminal=MissionState.VERIFIED_SUCCESS)
        rows = await store.fetchall("SELECT * FROM execution_strategies")
        assert len(rows) == 2

    async def test_a_mission_that_was_never_verified_is_not_a_success(self, store):
        """Finishing is not succeeding, and a strategy must not accumulate a promotion
        record out of runs nothing ever checked."""
        svc = _svc(store)
        await _run_mission(
            svc, mission_class="X", capabilities=["a"], terminal=MissionState.UNVERIFIABLE,
        )
        row = (await store.fetchall("SELECT * FROM execution_strategies"))[0]
        assert int(row["success_count"]) == 0

    async def test_a_mission_that_was_never_verified_is_not_a_failure_either(self, store):
        """P1-LEARN-005 — and this assertion used to say `failure_count == 1`.

        That is the shape of the defect and the shape of the test that hid it: the
        implementation collapsed every non-verified terminal state into a failure, and this
        test pinned the collapse rather than catching it. UNVERIFIABLE means VAN does not
        know. Recording "does not know" as "does not work" is how a strategy accumulates a
        demotion record out of VAN's own blind spots.
        """
        svc = _svc(store)
        await _run_mission(
            svc, mission_class="X", capabilities=["a"], terminal=MissionState.UNVERIFIABLE,
        )
        row = (await store.fetchall("SELECT * FROM execution_strategies"))[0]
        assert int(row["failure_count"]) == 0
        assert int(row["inconclusive_count"]) == 1

    @pytest.mark.parametrize(
        "terminal",
        [
            MissionState.CANCELLED,
            MissionState.BLOCKED_POLICY,
            MissionState.BLOCKED_UNSAFE,
            MissionState.EXPIRED,
            MissionState.UNVERIFIABLE,
            MissionState.PARTIAL_SUCCESS,
        ],
    )
    async def test_no_terminal_state_but_failure_punishes_the_strategy(self, store, terminal):
        """Every neighbour of the discovered bug, not only the one that was found.

        A policy refusal is a statement about authority. A cancellation is a statement
        about the owner changing their mind. An expiry is as likely to be the runtime as
        the approach. None of them is evidence that the strategy does not work, and
        `auto_demote` fires below a 60% rate over three runs — so three cancellations would
        have demoted a strategy that had never once failed. Promotion needs eval evidence
        and ten runs; demotion needs neither, which makes that damage cheap to do and
        expensive to undo.
        """
        svc = _svc(store)
        await _run_mission(svc, mission_class="X", capabilities=["a"], terminal=terminal)
        row = (await store.fetchall("SELECT * FROM execution_strategies"))[0]
        assert int(row["failure_count"]) == 0, terminal
        assert int(row["success_count"]) == 0, terminal
        assert int(row["inconclusive_count"]) == 1, terminal

    async def test_a_real_execution_failure_still_counts(self, store):
        """The other half: FAILED is the one non-success state that is evidence."""
        svc = _svc(store)
        await _run_mission(
            svc, mission_class="X", capabilities=["a"], terminal=MissionState.FAILED,
        )
        row = (await store.fetchall("SELECT * FROM execution_strategies"))[0]
        assert int(row["failure_count"]) == 1
        assert int(row["inconclusive_count"]) == 0

    async def test_cancellations_cannot_demote_a_working_strategy(self, store):
        """The consequence, driven end to end rather than asserted on a counter."""
        from van_gateway.evolution.radar import PromotionState, StrategyLearning

        svc = _svc(store)
        for _ in range(10):
            await _run_mission(
                svc, mission_class="X", capabilities=["a"],
                terminal=MissionState.VERIFIED_SUCCESS,
            )
        learning = StrategyLearning(store)
        strategy_id = str((await store.fetchall("SELECT * FROM execution_strategies"))[0]["strategy_id"])
        await learning.promote(
            strategy_id, target=PromotionState.PREFERRED, eval_run_id="eval-1",
        )
        for _ in range(10):
            await _run_mission(
                svc, mission_class="X", capabilities=["a"], terminal=MissionState.CANCELLED,
            )
        assert await learning.auto_demote() == []
        row = await store.fetchone(
            "SELECT promotion_state FROM execution_strategies WHERE strategy_id = ?",
            (strategy_id,),
        )
        assert str(row["promotion_state"]) == "PREFERRED"

    async def test_a_mission_that_executed_nothing_produces_no_strategy(self, store):
        """The common case today: the gateway delegates and Hermes creates the work.

        Recording an empty sequence would make every free-form command look like the same
        successful approach, which is worse than recording nothing.
        """
        svc = _svc(store)
        await _run_mission(
            svc, mission_class="GENERAL_OWNER_INTENT", capabilities=[],
            terminal=MissionState.VERIFIED_SUCCESS,
        )
        assert await store.fetchall("SELECT * FROM execution_strategies") == []


@pytest.mark.asyncio
class TestLearningCannotWidenAuthority:
    """P1-LEARN-002 — §27's rule, at the one place it could quietly be broken."""

    async def test_the_recorded_ceiling_is_what_was_actually_run(self, store):
        svc = _svc(store)
        await _run_mission(
            svc, mission_class="X", capabilities=["a"],
            terminal=MissionState.VERIFIED_SUCCESS, action_class=ActionClass.A2,
        )
        row = (await store.fetchall("SELECT * FROM execution_strategies"))[0]
        assert str(row["max_action_class"]) == "A2"

    async def test_the_ceiling_rises_only_to_meet_a_real_run(self, store):
        svc = _svc(store)
        await _run_mission(svc, mission_class="X", capabilities=["a"],
                           terminal=MissionState.VERIFIED_SUCCESS, action_class=ActionClass.A2)
        await _run_mission(svc, mission_class="X", capabilities=["a"],
                           terminal=MissionState.VERIFIED_SUCCESS, action_class=ActionClass.A4)
        row = (await store.fetchall("SELECT * FROM execution_strategies"))[0]
        assert str(row["max_action_class"]) == "A4"
        # And it does not fall back down, because A4 has genuinely been run.
        await _run_mission(svc, mission_class="X", capabilities=["a"],
                           terminal=MissionState.VERIFIED_SUCCESS, action_class=ActionClass.A1)
        row = (await store.fetchall("SELECT * FROM execution_strategies"))[0]
        assert str(row["max_action_class"]) == "A4"

    async def test_a_strategy_is_not_offered_to_a_mission_authorised_for_less(self, store):
        """The finding itself. Nobody widens anything; authority is simply acquired."""
        learning = StrategyLearning(store)
        wide = await learning.find_or_register(
            mission_class="X", capability_sequence=["dangerous"],
            max_action_class=ActionClass.A4,
        )
        narrow = await learning.find_or_register(
            mission_class="X", capability_sequence=["safe"],
            max_action_class=ActionClass.A1,
        )
        for strategy_id in (wide, narrow):
            for _ in range(10):
                await learning.record_outcome(strategy_id, outcome=StrategyOutcome.SUCCESS)
            await learning.promote(
                strategy_id, target=PromotionState.PREFERRED, eval_run_id="eval-1",
            )

        offered = await learning.permitted_for("X", envelope_max_action_class=ActionClass.A2)
        assert [r["strategy_id"] for r in offered] == [narrow]
        # The wider one is not hidden or demoted — it is simply not an answer to this
        # question. Concealing it would make the learning surface lie about what VAN knows.
        everything = await learning.preferred_for("X")
        assert {r["strategy_id"] for r in everything} == {wide, narrow}

    async def test_an_envelope_that_reaches_far_enough_is_offered_everything(self, store):
        learning = StrategyLearning(store)
        wide = await learning.find_or_register(
            mission_class="X", capability_sequence=["dangerous"],
            max_action_class=ActionClass.A4,
        )
        for _ in range(10):
            await learning.record_outcome(wide, outcome=StrategyOutcome.SUCCESS)
        await learning.promote(wide, target=PromotionState.PREFERRED, eval_run_id="e")
        offered = await learning.permitted_for("X", envelope_max_action_class=ActionClass.A4)
        assert [r["strategy_id"] for r in offered] == [wide]

    async def test_promotion_still_needs_eval_evidence_and_a_sample(self, store):
        """The guard this finding sits next to, checked here so the two cannot drift."""
        learning = StrategyLearning(store)
        strategy_id = await learning.find_or_register(
            mission_class="X", capability_sequence=["a"], max_action_class=ActionClass.A1,
        )
        with pytest.raises(RadarError, match="REQUIRES_EVAL"):
            await learning.promote(strategy_id, target=PromotionState.PREFERRED)
        with pytest.raises(RadarError, match="INSUFFICIENT_EVIDENCE"):
            await learning.promote(
                strategy_id, target=PromotionState.PREFERRED, eval_run_id="e",
            )


@pytest.mark.asyncio
class TestRegressionDemotionRuns:
    """P1-LEARN-004 — §41's auto-demotion existed and nothing called it."""

    async def test_a_strategy_that_stopped_working_is_demoted(self, store):
        learning = StrategyLearning(store)
        strategy_id = await learning.find_or_register(
            mission_class="X", capability_sequence=["a"], max_action_class=ActionClass.A1,
        )
        for _ in range(10):
            await learning.record_outcome(strategy_id, outcome=StrategyOutcome.SUCCESS)
        await learning.promote(strategy_id, target=PromotionState.PREFERRED, eval_run_id="e")
        for _ in range(10):
            await learning.record_outcome(strategy_id, outcome=StrategyOutcome.FAILURE)

        assert await learning.auto_demote() == [strategy_id]
        row = await store.fetchone(
            "SELECT promotion_state FROM execution_strategies WHERE strategy_id = ?",
            (strategy_id,),
        )
        assert str(row["promotion_state"]) == "DEMOTED"
        # And a demoted strategy is no longer offered to anything.
        assert await learning.permitted_for("X", envelope_max_action_class=ActionClass.A4) == []

    async def test_the_scheduler_runs_it(self, monkeypatch, tmp_path):
        """The finding was "no caller", so the caller is what is asserted."""
        from cryptography.fernet import Fernet

        from van_gateway.config import get_settings

        monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "sched.sqlite3"))
        monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("VAN_INGRESS_TOKEN", "learn-ingress-token-0123456789")
        get_settings.cache_clear()
        try:
            from van_gateway.app import create_app

            app = create_app()
            names = set(app.state.scheduler.jobs)
            assert "learning.auto_demote" in names
        finally:
            get_settings.cache_clear()


class TestAuthorityIsPolicyDataNotALearnedParameter:
    """P1-LEARN-002's other half, stated as the invariant the finding asked for.

    The strategy guard above stops a proven sequence reaching a mission authorised for
    less. This is the wider claim: the mapping from an action to its authority class to
    the gate it must pass is *policy data*, and no learning path may write it. The
    guarantee is worth having as a structural test rather than a convention, because the
    breach would not look like a breach — it would look like a store getting better at
    its job.
    """

    #: The tables that decide what VAN is permitted to do. A learning module writing any
    #: of these would be authority changing itself.
    AUTHORITY_TABLES = (
        "action_definitions",
        "permission_grants",
        "capability_registry",
        "capability_grants",
        "standing_automation_authorities",
        "automation_capabilities",
        "domain_trust",
        "proactive_policies",
    )

    #: The packages whose whole job is to conclude things from what happened.
    LEARNING_PACKAGES = ("learning", "evolution")

    def test_no_learning_module_writes_an_authority_table(self):
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1] / "van_gateway"
        # Comments are stripped so a table named in a comment explaining why it is never
        # written does not read as a write. String literals are not: the write is *in* a
        # string literal, which is the whole point.
        write = re.compile(
            r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+(\w+)", re.IGNORECASE
        )
        offences = []
        for package in self.LEARNING_PACKAGES:
            for path in (root / package).rglob("*.py"):
                source = "\n".join(
                    line.split("#", 1)[0] for line in path.read_text().splitlines()
                )
                for _verb, table in write.findall(source):
                    if table in self.AUTHORITY_TABLES:
                        offences.append(f"{path.relative_to(root)} writes {table}")
        assert offences == [], offences

    def test_the_invariant_covers_the_tables_that_exist(self):
        """A list naming a table that was renamed away would pass while guarding nothing."""
        import asyncio
        import tempfile

        from van_gateway.storage.db import Store

        async def tables():
            store = Store(tempfile.mkdtemp() + "/schema.sqlite3")
            await store.migrate()
            rows = await store.fetchall(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            return {str(r["name"]) for r in rows}

        present = asyncio.run(tables())
        missing = [t for t in self.AUTHORITY_TABLES if t not in present]
        assert missing == [], missing

    def test_earned_autonomy_can_never_mint_standing_authority(self):
        """§31, and the other shape the same breach takes.

        `domain_trust` is the one authority-adjacent store learning legitimately moves,
        and it is safe only because the earned ceiling is capped below every level that
        acts without asking. If that cap were ever raised, a domain could earn its way to
        unprompted action — which is the finding's own example, one layer over.
        """
        from van_gateway.proactive.autonomy import (
            MAX_EARNED_LEVEL,
            AutonomyLevel,
            DomainTrust,
        )

        acts_without_asking = [
            level for level in AutonomyLevel
            if level.ordinal > MAX_EARNED_LEVEL.ordinal
        ]
        assert acts_without_asking, "the cap guards nothing if it is the top level"

        spotless = DomainTrust(domain="anything", verified_successes=10_000)
        assert spotless.earned_ceiling is MAX_EARNED_LEVEL
        assert spotless.effective_ceiling.ordinal <= MAX_EARNED_LEVEL.ordinal
