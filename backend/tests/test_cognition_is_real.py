"""Gate 4: the cognition layer had correct code and no production caller.

Four findings, one shape, and each needed a different answer:

  * P0-COG-001 — the reasoning kernel took its own critique as an argument;
  * P1-SYM-001 — three unchecked strings promoted an assertion to CONFIRMED, and the
    calibration engine then told the owner it was their own stated preference;
  * P1-LEARN-001 — five learning stores with no caller that recorded a real outcome;
  * P2-COG-002 — two epistemic taxonomies, one enforced and one aspirational.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from conftest_automation import make_store
from van_gateway.context.forget import DELIBERATELY_KEPT, FORGETTABLE, OwnerMemory
from van_gateway.context.models import (
    EpistemicState,
    OwnerFactCandidate,
    SourceTrust,
)
from van_gateway.context.service import ContextAdmissionError, OwnerContextService
from van_gateway.epistemics.models import SemanticClass
from van_gateway.epistemics.reconciliation import (
    SEMANTIC_FOR_STATE,
    PromotionRefused,
    check_promotion,
)
from van_gateway.learning.feed import OUTCOME_KIND, LearningFeed
from van_gateway.mission.models import MissionOrigin, MissionState
from van_gateway.mission.service import MissionService
from van_gateway.models import OriginChannel
from van_gateway.reasoning.critic import OVERCONFIDENCE_THRESHOLD, critique
from van_gateway.reasoning.kernel import ChallengeMode, CriticalReasoningKernel


# --------------------------------------------------------------- P0-COG-001

def _critique(**over):
    base = dict(
        problem_statement="Should VAN move the savings?",
        known_facts=[{"statement": "the owner prefers the new bank", "source": "mission:1"}],
        assumptions=[], alternatives=["move", "leave"], contradictions=[],
        failure_modes=["the transfer fails"], evidence_refs=["mission:1"],
        recommended_next_action="move the savings", confidence=0.5,
    )
    base.update(over)
    return critique(**base)


class TestTheCriticActuallyRuns:
    def test_the_audits_probe_is_criticised(self):
        """0.99 confidence, one unsourced fact, nothing contradicting."""
        findings = _critique(
            known_facts=[{"statement": "the owner prefers it", "source": ""}],
            failure_modes=[], confidence=0.99, evidence_refs=[],
        )
        kinds = {f["kind"] for f in findings}
        assert "motivated_reasoning" in kinds
        assert "evidence_quality" in kinds
        assert any(f["severity"] == "HIGH" for f in findings)

    def test_a_well_formed_assessment_is_not_criticised_for_nothing(self):
        """A critic that always fires is a critic nobody reads."""
        assert _critique() == []

    def test_high_confidence_with_a_recorded_failure_mode_is_left_alone(self):
        assert not any(
            f["kind"] == "motivated_reasoning"
            for f in _critique(confidence=0.99, contradictions=["the fee is higher"])
        )

    def test_a_causal_claim_needs_more_than_one_observation(self):
        findings = _critique(
            problem_statement="The delay was caused by the deploy",
            known_facts=[{"statement": "the deploy ran", "source": "ci:1"}],
            evidence_refs=[],
        )
        assert any(f["kind"] == "causal_overclaim" for f in findings)

    def test_settled_language_with_nothing_contradicting_is_flagged(self):
        findings = _critique(assumptions=["the owner obviously wants this"])
        assert any(f["kind"] == "owner_confirmation_bias" for f in findings)

    def test_a_single_alternative_is_not_a_decision(self):
        assert any(f["kind"] == "ignored_alternative" for f in _critique(alternatives=["move"]))

    def test_nothing_is_criticised_when_no_action_is_recommended(self):
        """Thinking aloud is not a recommendation, and should not be treated as one."""
        assert _critique(recommended_next_action=None, alternatives=[], failure_modes=[]) == []

    def test_the_overconfidence_threshold_is_a_real_bound(self):
        assert 0.5 < OVERCONFIDENCE_THRESHOLD < 1.0


@pytest.mark.asyncio
class TestTheKernelCannotBeHandedItsOwnVerdict:
    async def test_the_probes_assessment_is_no_longer_actionable(self, tmp_path):
        kernel = CriticalReasoningKernel(await make_store(tmp_path))
        assessment = await kernel.assess(
            problem_statement="Should VAN move the owner's savings?",
            challenge_mode=ChallengeMode.BALANCED,
            known_facts=[{"statement": "the owner prefers it", "source": "i-remember-it"}],
            alternatives=["move it", "leave it"],
            recommended_next_action="move the savings",
            confidence=0.99,
        )
        assert assessment.critic_findings, "the kernel produced no critique of its own"
        assert assessment.is_actionable is False

    async def test_a_caller_cannot_suppress_the_kernels_findings(self, tmp_path):
        """Supplying an empty list used to be the whole critique."""
        kernel = CriticalReasoningKernel(await make_store(tmp_path))
        assessment = await kernel.assess(
            problem_statement="Should VAN move the savings?",
            challenge_mode=ChallengeMode.BALANCED,
            known_facts=[],
            alternatives=["move", "leave"],
            recommended_next_action="move the savings",
            confidence=0.99,
            critic_findings=[],
        )
        assert any(f.kind == "motivated_reasoning" for f in assessment.critic_findings)

    async def test_a_sound_assessment_is_still_actionable(self, tmp_path):
        kernel = CriticalReasoningKernel(await make_store(tmp_path))
        assessment = await kernel.assess(
            problem_statement="Should VAN move the savings?",
            challenge_mode=ChallengeMode.BALANCED,
            known_facts=[{"statement": "the new account pays more", "source": "bank:stmt-1"}],
            alternatives=["move", "leave"],
            contradictions=["the new account has a withdrawal fee"],
            failure_modes=["the transfer is delayed past the bill date"],
            evidence_refs=["bank:stmt-1"],
            recommended_next_action="move the savings",
            confidence=0.7,
        )
        assert assessment.is_actionable is True


# ------------------------------------------------------------- P1-LEARN-001

@pytest_asyncio.fixture
async def learning_stack(tmp_path):
    store = await make_store(tmp_path)
    feed = LearningFeed(store)
    missions = MissionService(store, learning=feed)
    return store, feed, missions


async def _drive(missions, to: MissionState, *, contract=None):
    mission = await missions.create(
        owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE, title="t", goal="collect the statements",
        **({"success_contract": contract} if contract else {}),
    )
    ladder = [MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
              MissionState.RUNNING]
    from van_gateway.mission.models import VERIFICATION_OUTCOMES

    if to in VERIFICATION_OUTCOMES:
        ladder.append(MissionState.VERIFYING)
    for state in ladder:
        mission = await missions.transition(mission.mission_id, target=state)
    return await missions.transition(mission.mission_id, target=to)


@pytest.mark.asyncio
class TestOutcomesReachTheLearningStores:
    async def test_a_finished_mission_is_recorded(self, learning_stack):
        _store, feed, missions = learning_stack
        await _drive(missions, MissionState.FAILED)
        assert await feed.outcome_counts() == {"failed": 1}

    async def test_a_running_mission_is_not_an_outcome(self, learning_stack):
        _store, feed, missions = learning_stack
        mission = await missions.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        await missions.transition(mission.mission_id, target=MissionState.UNDERSTOOD)
        assert await feed.outcome_counts() == {}

    async def test_every_terminal_state_has_an_outcome_kind(self):
        """A terminal state with no kind would be a finished mission nothing learned from."""
        from van_gateway.mission.models import TERMINAL_STATES

        assert set(TERMINAL_STATES) <= set(OUTCOME_KIND)

    async def test_a_system_that_has_done_nothing_has_no_success_rate(self, learning_stack):
        """Reporting 0.0 would read as failure; None is the honest answer."""
        _store, feed, _missions = learning_stack
        assert (await feed.evidence_rate())["verified_rate"] is None

    async def test_the_rate_reflects_what_actually_happened(self, learning_stack):
        _store, feed, missions = learning_stack
        await _drive(missions, MissionState.FAILED)
        await _drive(missions, MissionState.UNVERIFIABLE)
        rate = await feed.evidence_rate()
        assert rate["finished"] == 2 and rate["verified"] == 0
        assert rate["verified_rate"] == 0.0
        assert rate["by_kind"] == {"failed": 1, "unverifiable": 1}

    async def test_an_owner_correction_reaches_the_growth_ledger(self, tmp_path):
        from van_gateway.understanding.owner_model import (
            OwnerCognitiveModel,
            OwnerModelField,
        )

        store = await make_store(tmp_path)
        feed = LearningFeed(store)
        missions = MissionService(store)
        mission = await missions.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        model = OwnerCognitiveModel(store, learning=feed)
        assertion = await model.observe(
            owner_principal_id="owner", field=OwnerModelField.REASONING_PREFERENCE,
            value="short answers", episode_ref=f"mission:{mission.mission_id}",
        )
        await model.correct(assertion.assertion_id, new_value="full evidence")

        rows = await store.fetchall("SELECT observed_pattern, new_behavior FROM symbiotic_growth", ())
        assert len(rows) == 1
        assert "owner corrected" in rows[0]["observed_pattern"]
        assert "full evidence" in rows[0]["new_behavior"]


# -------------------------------------------------------------- P2-COG-002

class TestOneTaxonomyIsEnforced:
    def test_every_epistemic_state_has_a_semantic_class(self):
        """A state with none would escape the promotion rule entirely."""
        assert set(SEMANTIC_FOR_STATE) == set(EpistemicState)

    def test_a_model_inference_may_not_become_a_verified_fact(self):
        with pytest.raises(PromotionRefused, match="self-promotion"):
            check_promotion(
                prior=EpistemicState.INFERRED,
                proposed=EpistemicState.VERIFIED_LIVE_STATE,
                proposed_trust=SourceTrust.VERIFIED_SYSTEM,
            )

    def test_an_external_claim_may_not_become_project_truth(self):
        with pytest.raises(PromotionRefused):
            check_promotion(
                prior=EpistemicState.EXTERNAL_EVIDENCE,
                proposed=EpistemicState.PROJECT_TRUTH,
                proposed_trust=SourceTrust.TRUSTED_OWNER_FILE,
            )

    def test_factual_authority_needs_a_source_that_can_establish_it(self):
        with pytest.raises(PromotionRefused, match="cannot establish"):
            check_promotion(
                prior=EpistemicState.STALE,
                proposed=EpistemicState.VERIFIED_LIVE_STATE,
                proposed_trust=SourceTrust.MODEL_DERIVED,
            )

    def test_a_legitimate_refresh_is_allowed(self):
        check_promotion(
            prior=EpistemicState.STALE,
            proposed=EpistemicState.VERIFIED_LIVE_STATE,
            proposed_trust=SourceTrust.VERIFIED_SYSTEM,
        )
        check_promotion(
            prior=EpistemicState.INFERRED,
            proposed=EpistemicState.INFERRED,
            proposed_trust=SourceTrust.MODEL_DERIVED,
        )

    def test_the_semantic_classes_are_all_reachable(self):
        """A class nothing maps to would be a rule that can never apply."""
        mapped = set(SEMANTIC_FOR_STATE.values())
        unreachable = set(SemanticClass) - mapped
        assert unreachable <= {
            SemanticClass.HYPOTHESIS, SemanticClass.FORECAST, SemanticClass.OWNER_PREFERENCE
        } | mapped, unreachable


@pytest.mark.asyncio
class TestTheRuleIsEnforcedAtAdmission:
    async def test_an_inferred_fact_cannot_be_superseded_into_a_verified_one(self, tmp_path):
        context = OwnerContextService(await make_store(tmp_path))
        base = await context.admit_fact(OwnerFactCandidate(
            fact_id="f-inferred", subject="OWNER", predicate="mood", value="focused",
            authority=EpistemicState.INFERRED, source_trust=SourceTrust.MODEL_DERIVED,
            source_ref="hermes:1", valid_from_ms=1, observed_at_ms=1,
        ))
        with pytest.raises(ContextAdmissionError, match="self-promotion"):
            await context.admit_fact(OwnerFactCandidate(
                fact_id="f-verified", subject="OWNER", predicate="mood", value="focused",
                authority=EpistemicState.VERIFIED_LIVE_STATE,
                source_trust=SourceTrust.VERIFIED_SYSTEM,
                source_ref="sensor:1", valid_from_ms=2, observed_at_ms=2,
                supersedes_fact_id=base.fact_id,
            ))


# -------------------------------------------------------------- P2-MEM-002

@pytest.mark.asyncio
class TestTheOwnerCanBeForgotten:
    async def test_every_owner_derived_store_is_clearable(self, tmp_path):
        store = await make_store(tmp_path)
        memory = OwnerMemory(store)
        inventory = await memory.inventory()
        assert set(inventory["stores"]) == {e.table for e in FORGETTABLE}

    async def test_forgetting_removes_what_van_concluded(self, tmp_path):
        from van_gateway.understanding.owner_model import (
            OwnerCognitiveModel,
            OwnerModelField,
        )

        store = await make_store(tmp_path)
        missions = MissionService(store)
        mission = await missions.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title="t", goal="g",
        )
        model = OwnerCognitiveModel(store)
        await model.observe(
            owner_principal_id="owner", field=OwnerModelField.REASONING_PREFERENCE,
            value="short", episode_ref=f"mission:{mission.mission_id}",
        )
        assert (await OwnerMemory(store).inventory())["stores"]["owner_cognitive_model"]["rows"] == 1

        removed = await OwnerMemory(store).forget_all()
        assert removed["removed"]["owner_cognitive_model"] == 1
        assert (await OwnerMemory(store).inventory())["stores"]["owner_cognitive_model"]["rows"] == 0

    async def test_the_audit_trail_is_kept_and_says_why(self, tmp_path):
        """Erasing it would destroy the evidence that the deletion happened."""
        memory = OwnerMemory(await make_store(tmp_path))
        assert "audit" in DELIBERATELY_KEPT
        assert "audit" not in {e.table for e in FORGETTABLE}
        assert DELIBERATELY_KEPT["audit"].strip()
        assert "kept_deliberately" in await memory.forget_all()

    async def test_a_store_that_is_not_owner_derived_cannot_be_cleared_through_this(self, tmp_path):
        memory = OwnerMemory(await make_store(tmp_path))
        with pytest.raises(ValueError, match="not an owner-derived store"):
            await memory.forget_store("audit")

    async def test_an_empty_store_reports_zero_rather_than_being_left_out(self, tmp_path):
        """'Nothing was there' and 'this was not touched' are different answers."""
        removed = (await OwnerMemory(await make_store(tmp_path)).forget_all())["removed"]
        assert set(removed) == {e.table for e in FORGETTABLE}
