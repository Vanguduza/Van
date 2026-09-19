"""Rev 1 §§9, 14, 64-78, 87 — epistemics, context compilation, understanding.

The property under test across all of it is the one §22 names as mandatory:
personalisation must not become an echo chamber. That means owner belief never
becomes factual authority, accumulated model confidence never becomes a fact,
and a correction always outranks accumulation.
"""

from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.context_compiler.compiler import (
    ContextCompiler,
    ContextSection,
)
from van_gateway.epistemics.models import (
    Claim,
    Provenance,
    SemanticClass,
    may_promote,
)
from van_gateway.reasoning.kernel import (
    REQUIRED_COUNTERFACTUALS,
    AssumptionStatus,
    ChallengeMode,
    CriticFinding,
    CriticalReasoningKernel,
    Importance,
    ReasoningError,
    required_mode,
)
from van_gateway.understanding.memory import (
    CognitiveComplementMap,
    DecisionFingerprints,
    IntentContinuityGraph,
    IntentEdgeType,
    SharedVocabularyRegistry,
    StrategicEntryType,
    StrategicMemory,
    SymbioticGrowthLedger,
    VocabularyEntry,
)
from van_gateway.understanding.owner_model import (
    AssertionState,
    OwnerCognitiveModel,
    OwnerModelError,
    OwnerModelField,
)


async def seed_episodes(store, *names: str) -> dict[str, str]:
    """Real missions for the assertions to be evidenced by (P1-SYM-001).

    `episode_ref` used to be a free string, so three typos were three episodes. It now has
    to name a mission or a command that exists, which means a test that wants evidence has
    to produce something that happened.
    """
    from van_gateway.mission.models import MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    missions = MissionService(store)
    out: dict[str, str] = {}
    for name in names:
        mission = await missions.create(
            owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
            origin_channel=OriginChannel.VOICE, title=name, goal=name,
        )
        out[name] = f"mission:{mission.mission_id}"
    return out


NOW = 1_800_000_000_000


def _claim(cid, statement, klass, *, project=None, group=None, observed=NOW, conf=0.8):
    return Claim(
        claim_id=cid, statement=statement, semantic_class=klass, project_id=project,
        contradiction_group=group, created_at_ms=observed,
        provenance=Provenance(
            source_kind="test", source_ref=f"ref://{cid}", observed_at_ms=observed,
            confidence=conf, evidence_refs=[f"ev://{cid}"],
        ),
    )


# -------------------------------------------------------------- §14 epistemics


def test_owner_belief_is_not_factual_authority():
    """§67 — the sentence this whole layer exists to enforce."""
    assert SemanticClass.OWNER_PREFERENCE.is_factual_authority is False
    assert SemanticClass.OWNER_INSTRUCTION.is_factual_authority is False
    assert SemanticClass.OWNER_INSTRUCTION.is_owner_authority is True
    assert SemanticClass.FACT_VERIFIED.is_factual_authority is True
    assert SemanticClass.PROJECT_TRUTH.is_factual_authority is True


def test_a_model_inference_can_never_promote_itself_to_fact():
    """§45.12 — model tries to convert belief into FACT_VERIFIED."""
    assert may_promote(SemanticClass.MODEL_INFERENCE, SemanticClass.FACT_VERIFIED) is False
    assert may_promote(SemanticClass.EXTERNAL_CLAIM, SemanticClass.PROJECT_TRUTH) is False
    assert may_promote(SemanticClass.OWNER_PREFERENCE, SemanticClass.FACT_VERIFIED) is False
    # A model may not mint an owner preference either.
    assert may_promote(SemanticClass.MODEL_INFERENCE, SemanticClass.OWNER_PREFERENCE) is False
    # Legitimate movement is still allowed.
    assert may_promote(SemanticClass.FACT_UNVERIFIED, SemanticClass.FACT_VERIFIED) is True


def test_a_nonowner_claim_without_provenance_is_illformed():
    """§41 — provenance on 100% of non-owner facts."""
    bare = Claim(claim_id="c1", statement="x", semantic_class=SemanticClass.FACT_VERIFIED)
    assert bare.is_wellformed is False
    owned = Claim(
        claim_id="c2", statement="I prefer terse updates",
        semantic_class=SemanticClass.OWNER_PREFERENCE,
    )
    assert owned.is_wellformed is True


def test_owner_preferences_do_not_expire_on_a_clock():
    """A preference that "expires" makes VAN forget the owner for no reason."""
    ancient = _claim("c3", "terse updates", SemanticClass.OWNER_PREFERENCE, observed=0)
    assert ancient.staleness_at_ms(NOW) is False
    stale_fact = _claim("c4", "the API returns 200", SemanticClass.FACT_VERIFIED, observed=0)
    assert stale_fact.staleness_at_ms(NOW) is True


# --------------------------------------------------------- §9 context compiler


def test_cross_project_isolation_is_hard():
    """§9 — excluded, not ranked down, and counted so it is visible."""
    compiler = ContextCompiler()
    packet = compiler.compile(
        packet_id="p1", project_id="alpha", now_ms=NOW,
        claims={
            ContextSection.PROJECT_TRUTH: [
                _claim("a", "alpha fact", SemanticClass.PROJECT_TRUTH, project="alpha"),
                _claim("b", "beta secret", SemanticClass.PROJECT_TRUTH, project="beta"),
            ]
        },
    )
    statements = [line["statement"] for lines in packet.sections.values() for line in lines]
    assert "alpha fact" in statements
    assert "beta secret" not in statements
    assert packet.selection_stats["dropped_cross_project"] == 1


def test_a_stale_claim_is_carried_but_loses_authority():
    """Dropping it silently would let VAN act as though it never knew."""
    compiler = ContextCompiler()
    packet = compiler.compile(
        packet_id="p2", now_ms=NOW,
        claims={
            ContextSection.RETRIEVED_KNOWLEDGE: [
                _claim("old", "was true last month", SemanticClass.FACT_VERIFIED, observed=0)
            ]
        },
    )
    line = packet.sections["retrieved_knowledge"][0]
    assert line["stale"] is True
    assert line["factual_authority"] is False
    assert packet.factual_claims() == []
    assert packet.stale_claim_ids == ["old"]


def test_contradicting_claims_stay_together():
    """§14 — including only the higher-scored side manufactures false confidence."""
    compiler = ContextCompiler()
    packet = compiler.compile(
        packet_id="p3", now_ms=NOW,
        claims={
            ContextSection.RETRIEVED_KNOWLEDGE: [
                _claim("x1", "the build is green", SemanticClass.FACT_VERIFIED, group="build"),
                _claim("x2", "the build is red", SemanticClass.EXTERNAL_CLAIM, group="build"),
            ]
        },
    )
    assert packet.contradiction_groups == {"build": ["x1", "x2"]}
    statements = [l["statement"] for ls in packet.sections.values() for l in ls]
    assert "the build is green" in statements and "the build is red" in statements


def test_the_budget_is_enforced_by_dropping_the_least_useful():
    """§9 — a compiler that overruns hands the reasoner a silent truncation."""
    compiler = ContextCompiler()
    many = [
        _claim(f"n{i}", f"environment detail {i}" * 10, SemanticClass.EXTERNAL_CLAIM)
        for i in range(60)
    ]
    packet = compiler.compile(
        packet_id="p4", token_budget=200, now_ms=NOW,
        claims={
            ContextSection.AUTHORITY_CONTEXT: [
                _claim("auth", "mission ceiling is A2", SemanticClass.PROJECT_TRUTH)
            ],
            ContextSection.CURRENT_ENVIRONMENT: many,
        },
    )
    assert packet.within_budget
    assert packet.selection_stats["dropped_budget"] > 0
    # Authority survives the squeeze: acting with the wrong ceiling is worse
    # than acting with less information.
    kept = [l["statement"] for ls in packet.sections.values() for l in ls]
    assert "mission ceiling is A2" in kept


def test_an_illformed_claim_never_reaches_the_reasoner():
    compiler = ContextCompiler()
    packet = compiler.compile(
        packet_id="p5", now_ms=NOW,
        claims={
            ContextSection.RETRIEVED_KNOWLEDGE: [
                Claim(claim_id="bad", statement="unsourced",
                      semantic_class=SemanticClass.FACT_VERIFIED)
            ]
        },
    )
    assert packet.selection_stats["dropped_illformed"] == 1
    assert packet.sections == {}


# ------------------------------------------------------- §64 owner model


async def test_one_emphatic_conversation_does_not_mint_a_trait(tmp_path):
    """§74 — independence is by episode, not by observation."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    episodes = await seed_episodes(store, "m1")
    for _ in range(5):
        assertion = await model.observe(
            owner_principal_id="owner", field=OwnerModelField.COMMUNICATION_PREFERENCE,
            value="prefers terse status updates", episode_ref=episodes["m1"],
        )
    assert assertion.independent_episodes == 1
    assert assertion.state is AssertionState.OBSERVED


async def test_evidence_promotes_to_candidate_then_evidenced_but_never_confirmed(tmp_path):
    """P1-SYM-001 — three episodes used to produce CONFIRMED, and the calibration engine
    then told the owner their preference was owner-confirmed. Nobody had asked them."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    episodes = await seed_episodes(store, "m1", "m2", "m3")
    states = []
    for name in ("m1", "m2", "m3"):
        assertion = await model.observe(
            owner_principal_id="owner", field=OwnerModelField.COMMUNICATION_PREFERENCE,
            value="terse", episode_ref=episodes[name],
        )
        states.append(assertion.state)
    assert states == [
        AssertionState.OBSERVED, AssertionState.CANDIDATE, AssertionState.EVIDENCED
    ]
    assert assertion.may_act_on is True, "a well-evidenced preference is still actionable"

    confirmed = await model.confirm(assertion.assertion_id)
    assert confirmed.state is AssertionState.CONFIRMED


async def test_an_episode_that_did_not_happen_is_not_evidence(tmp_path):
    """The ladder counts distinct references, so an unresolvable one is a vote."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    for rubbish in ("m1", "mission-1", "", "mission:", "mission:does-not-exist", "note:x"):
        with pytest.raises(OwnerModelError):
            await model.observe(
                owner_principal_id="owner",
                field=OwnerModelField.COMMUNICATION_PREFERENCE,
                value="terse", episode_ref=rubbish,
            )


async def test_an_autonomy_bearing_trait_never_confirms_from_evidence_alone(tmp_path):
    """§45.16 — inferred preference must not widen autonomy by itself."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    episodes = await seed_episodes(store, "m1", "m2", "m3", "m4", "m5")
    for episode in episodes.values():
        assertion = await model.observe(
            owner_principal_id="owner", field=OwnerModelField.DELEGATION_PREFERENCE,
            value="happy for VAN to act without asking", episode_ref=episode,
        )
    assert assertion.is_autonomy_bearing is True
    assert assertion.state is AssertionState.CANDIDATE
    assert assertion.may_act_on is False
    # Only the owner promotes it.
    confirmed = await model.confirm(assertion.assertion_id)
    assert confirmed.state is AssertionState.CONFIRMED and confirmed.may_act_on is True


async def test_a_correction_outranks_any_amount_of_evidence(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    episodes = await seed_episodes(store, "m1", "m2", "m3", "m4")
    a = await model.observe(
        owner_principal_id="owner", field=OwnerModelField.EVIDENCE_PREFERENCE,
        value="wants summaries", episode_ref=episodes["m1"],
    )
    await model.reject(a.assertion_id)
    for name in ("m2", "m3", "m4"):
        again = await model.observe(
            owner_principal_id="owner", field=OwnerModelField.EVIDENCE_PREFERENCE,
            value="wants summaries", episode_ref=episodes[name],
        )
    assert again.state is AssertionState.REJECTED
    assert again.may_act_on is False


async def test_a_correction_supersedes_rather_than_edits(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    episodes = await seed_episodes(store, "m1")
    original = await model.observe(
        owner_principal_id="owner", field=OwnerModelField.REASONING_PREFERENCE,
        value="wants short answers", episode_ref=episodes["m1"],
    )
    replacement = await model.correct(original.assertion_id, new_value="wants full evidence")
    assert replacement.state is AssertionState.CONFIRMED
    stale = await model.get(original.assertion_id)
    assert stale.state is AssertionState.SUPERSEDED
    assert stale.superseded_by == replacement.assertion_id
    # The Understanding surface shows the live one, not the superseded.
    view = await model.understanding("owner")
    values = [e["value"] for e in view["fields"]["reasoning_preferences"]]
    assert values == ["wants full evidence"]


# --------------------------------------------------- §§76-78, 87 memory stores


async def test_vocabulary_needs_anti_examples_to_be_operational(tmp_path):
    """§19 — learn meaning, do not mimic vocabulary."""
    registry = SharedVocabularyRegistry(await make_store(tmp_path))
    vague = VocabularyEntry(
        term="full implementation", owner_meaning="everything done",
        system_operationalization="",
    )
    assert vague.is_operational is False
    sharp = VocabularyEntry(
        term="full implementation",
        owner_meaning="working end to end, not interfaces",
        system_operationalization="every declared capability has an executable path and a test",
        anti_examples=["interface-only", "stubs without backends", "green unit tests alone"],
    )
    await registry.define(sharp)
    assert sharp.is_operational is True
    assert (await registry.resolve("Full Implementation")).anti_examples


async def test_project_scoped_vocabulary_wins(tmp_path):
    registry = SharedVocabularyRegistry(await make_store(tmp_path))
    await registry.define(VocabularyEntry(
        term="resume", owner_meaning="continue", system_operationalization="global",
        anti_examples=["restart"],
    ))
    await registry.define(VocabularyEntry(
        term="resume", owner_meaning="continue the whole closure",
        system_operationalization="project specific", anti_examples=["last visible task only"],
        project_id="van",
    ))
    assert (await registry.resolve("resume", project_id="van")).system_operationalization == (
        "project specific"
    )
    assert (await registry.resolve("resume")).system_operationalization == "global"


async def test_a_conflicting_newer_intent_is_visible_not_silently_winning(tmp_path):
    """§20 — contradictory newer instructions are the thing worth surfacing."""
    graph = IntentContinuityGraph(await make_store(tmp_path))
    old = await graph.observe(owner_goal="keep the fabric minimal", project_id="van")
    new = await graph.observe(owner_goal="add every integration we can", project_id="van")
    await graph.relate(
        from_intent_id=new.intent_id, to_intent_id=old.intent_id,
        edge_type=IntentEdgeType.CONFLICTS,
    )
    conflicts = await graph.conflicts_for(old.intent_id)
    assert [c.intent_id for c in conflicts] == [new.intent_id]


async def test_an_unmentioned_intent_goes_stale_not_abandoned(tmp_path):
    graph = IntentContinuityGraph(await make_store(tmp_path))
    node = await graph.observe(owner_goal="ship the trading core", now_ms=0)
    assert await graph.mark_stale(now_ms=NOW) == 1
    assert (await graph.get(node.intent_id)).status.value == "STALE"
    # Mentioning it again revives it rather than needing a new node.
    await graph.observe(owner_goal="ship the trading core", now_ms=NOW)
    assert (await graph.get(node.intent_id)).status.value == "ACTIVE"


async def test_strategic_memory_remembers_what_was_already_rejected(tmp_path):
    memory = StrategicMemory(await make_store(tmp_path))
    await memory.record(
        project_id="van", entry_type=StrategicEntryType.REJECTED_STRATEGY,
        statement="Use a single monolithic agent loop",
        rationale="§2.2 — Hermes is the sole runtime; a second loop is forbidden",
    )
    assert await memory.already_rejected("van", "single monolithic agent loop") is True
    assert await memory.already_rejected("van", "something nobody tried") is False


async def test_a_decision_outcome_can_falsify_its_inferred_reason(tmp_path):
    """§12 — outcomes must be able to falsify earlier inferred patterns."""
    fingerprints = DecisionFingerprints(await make_store(tmp_path))
    decision_id = await fingerprints.record(
        owner_choice="ship without the extra review",
        inferred_reason="owner optimises for speed over caution",
        options_considered=["ship now", "review first"],
    )
    await fingerprints.record_outcome(
        decision_id, outcome="regression reached production",
        reassessment="owner optimised for a deadline, not for speed in general",
    )
    falsified = await fingerprints.falsified()
    assert len(falsified) == 1
    assert "deadline" in falsified[0]["reassessment"]


async def test_a_vulnerability_candidate_requires_task_evidence(tmp_path):
    """§18 — no psychological diagnoses; task observations only."""
    complement = CognitiveComplementMap(await make_store(tmp_path))
    with pytest.raises(ValueError, match="requires_evidence"):
        await complement.upsert(
            domain="architecture", owner_vulnerability_candidate="declares closure early"
        )
    await complement.upsert(
        domain="architecture", owner_vulnerability_candidate="declares closure early",
        van_strength="exhaustive repository reconciliation",
        evidence_refs=["mission://m1", "mission://m2"],
    )
    assert len(await complement.all()) == 1


async def test_an_adaptation_needing_confirmation_is_not_in_force_until_confirmed(tmp_path):
    """§26 — the owner must be able to correct or reject a material change."""
    ledger = SymbioticGrowthLedger(await make_store(tmp_path))
    change_id = await ledger.record(
        observed_pattern="owner always asks for the evidence",
        previous_behavior="summarise findings",
        new_behavior="lead with evidence refs",
        reason="three missions in a row ended with the same request",
        evidence_refs=["mission://a", "mission://b", "mission://c"],
    )
    assert await ledger.effective() == []
    assert len(await ledger.awaiting_owner()) == 1
    await ledger.confirm(change_id)
    assert len(await ledger.effective()) == 1
    assert await ledger.revert(change_id) is True
    assert await ledger.effective() == []


# -------------------------------------------------------- §§66-71 reasoning


def test_high_consequence_work_demands_a_stronger_mode():
    """§28 — encoded, because the moment it matters is the moment it is skipped."""
    assert required_mode(consequential=False, irreversible=False) is ChallengeMode.BALANCED
    assert required_mode(consequential=True, irreversible=False) is ChallengeMode.CRITICAL
    assert required_mode(consequential=True, irreversible=True) is ChallengeMode.RED_TEAM
    assert ChallengeMode.RED_TEAM.requires_disconfirming_search is True


async def test_an_assessment_claiming_rigour_it_did_not_do_is_refused(tmp_path):
    kernel = CriticalReasoningKernel(await make_store(tmp_path))
    with pytest.raises(ReasoningError, match="MODE_REQUIREMENTS_UNMET"):
        await kernel.assess(
            problem_statement="should we migrate the ledger?",
            challenge_mode=ChallengeMode.RED_TEAM,
            alternatives=["do nothing"],
            recommended_next_action="migrate",
        )


async def test_a_cited_fact_without_a_source_is_refused(tmp_path):
    """§41 — hallucinated evidence = 0, enforced rather than measured after."""
    kernel = CriticalReasoningKernel(await make_store(tmp_path))
    with pytest.raises(ReasoningError, match="UNSOURCED_FACT"):
        await kernel.assess(
            problem_statement="p", challenge_mode=ChallengeMode.BALANCED,
            known_facts=[{"statement": "the API is down", "factual_authority": True}],
            alternatives=["a", "b"], recommended_next_action="x",
        )


async def test_unanswered_high_severity_criticism_makes_advice_unactionable(tmp_path):
    """§17 — no critic gains execution authority, but its findings still count."""
    kernel = CriticalReasoningKernel(await make_store(tmp_path))
    assessment = await kernel.assess(
        problem_statement="ship it?", challenge_mode=ChallengeMode.CRITICAL,
        alternatives=["ship", "wait", "partial"], recommended_next_action="ship",
        critic_findings=[
            CriticFinding(kind="ignored_alternative", detail="rollback not considered",
                          severity="HIGH")
        ],
    )
    assert assessment.has_unaddressed_criticism is True
    assert assessment.is_actionable is False


async def test_missing_counterfactuals_are_reported(tmp_path):
    kernel = CriticalReasoningKernel(await make_store(tmp_path))
    assessment = await kernel.assess(
        problem_statement="p", challenge_mode=ChallengeMode.BALANCED,
        alternatives=["a", "b"],
        counterfactuals=[{"question": REQUIRED_COUNTERFACTUALS[0], "answer": "we stop"}],
    )
    missing = kernel.missing_counterfactuals(assessment)
    assert REQUIRED_COUNTERFACTUALS[0] not in missing
    assert len(missing) == len(REQUIRED_COUNTERFACTUALS) - 1


async def test_irreversible_work_blocks_on_unverified_high_impact_assumptions(tmp_path):
    """§15 — verify or falsify before irreversible work, as a callable gate.

    The ledger has a real foreign key to missions: an assumption that belongs to
    no mission is one nobody will ever be prompted to settle.
    """
    from van_gateway.mission.models import MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    store = await make_store(tmp_path)
    mission = await MissionService(store).create(
        owner_principal_id="owner", origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE, title="migrate", goal="migrate the ledger",
    )
    kernel = CriticalReasoningKernel(store)
    assumption = await kernel.record_assumption(
        mission_id=mission.mission_id, claim="the broker API still accepts v1 auth",
        source="OWNER_INSTRUCTION", importance=Importance.CRITICAL,
    )
    assert assumption.blocks_irreversible_work is True
    with pytest.raises(ReasoningError, match="UNVERIFIED_HIGH_IMPACT"):
        await kernel.assert_safe_for_irreversible_work(mission.mission_id)

    with pytest.raises(ReasoningError, match="REQUIRES_EVIDENCE"):
        await kernel.resolve_assumption(
            assumption.assumption_id, status=AssumptionStatus.VERIFIED
        )
    await kernel.resolve_assumption(
        assumption.assumption_id, status=AssumptionStatus.VERIFIED,
        evidence_refs=["probe://broker-auth"],
    )
    await kernel.assert_safe_for_irreversible_work(mission.mission_id)


async def test_agreeing_with_a_factual_premise_without_evidence_is_recorded(tmp_path):
    """§17 — a metric nobody records is a metric nobody can fail."""
    kernel = CriticalReasoningKernel(await make_store(tmp_path))
    await kernel.assess_premise(
        owner_premise="the migration already ran in production",
        van_position="agreed", semantic_class=SemanticClass.FACT_VERIFIED, now_ms=NOW,
    )
    metrics = await kernel.sycophancy_metrics(now_ms=NOW + 1000)
    assert metrics["measured"] is True
    assert metrics["unsupported_agreement_rate"] == 1.0
    assert metrics["meets_target"] is False

    # Correcting the premise, with evidence, is the behaviour being encouraged.
    await kernel.assess_premise(
        owner_premise="the migration already ran in production",
        van_position="schema_migrations shows version 11, not 12",
        semantic_class=SemanticClass.FACT_VERIFIED,
        evidence_refs=["db://schema_migrations"], corrected=True, now_ms=NOW,
    )
    metrics = await kernel.sycophancy_metrics(now_ms=NOW + 1000)
    assert metrics["unsupported_agreement_rate"] == 0.5
    assert metrics["correction_rate"] == 0.5


async def test_metrics_report_unmeasured_rather_than_a_flattering_zero(tmp_path):
    """§55 — never report a target as met when it has never been tested."""
    kernel = CriticalReasoningKernel(await make_store(tmp_path))
    metrics = await kernel.sycophancy_metrics()
    assert metrics["measured"] is False
    assert metrics["unsupported_agreement_rate"] is None
    assert metrics["meets_target"] is None
