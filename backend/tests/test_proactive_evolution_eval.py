"""Rev 1 §§10-11, 24-25, 27, 31, 40, 79-84 — autonomy, evolution, eval.

The through-line: VAN may get better at things, and none of that may become
permission. Trust spends, the owner grants; a benchmark informs, the owner
adopts; an eval reports, and reports honestly when it cannot.
"""

from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.attention.scoring import (
    AttentionCandidate,
    AttentionScorer,
    Disposition,
)
from van_gateway.evolution.radar import (
    AIEvolutionRadar,
    BenchmarkHarness,
    ExternalRealityModel,
    PipelineState,
    PromotionState,
    RadarError,
    StrategyLearning,
    StrategyOutcome,
)
from van_gateway.evolution.vaneval import (
    UNMEASURABLE_WITHOUT_OWNER_DATA,
    EvalDimension,
    VanEval,
)
from van_gateway.proactive.autonomy import (
    AutonomyError,
    AutonomyLevel,
    DomainTrust,
    DomainTrustService,
    ProactiveMissionType,
    ProactivePolicyService,
)

NOW = 1_800_000_000_000


# ------------------------------------------------------------ §31 domain trust


def test_evidence_alone_never_reaches_a_level_that_acts():
    """§31 — never infer standing authority solely from execution history."""
    flawless = DomainTrust(domain="statements", verified_successes=500)
    assert flawless.earned_ceiling is AutonomyLevel.S2_PREPARE
    assert flawless.earned_ceiling.may_execute is False
    assert flawless.permits(ProactiveMissionType.SAFE_BOUNDED_AUTOMATIC) is False


def test_one_false_success_costs_more_than_ten_verified_ones_earn():
    """§31 — false success must *severely* penalize autonomy."""
    good = DomainTrust(domain="d", verified_successes=10)
    assert good.earned_ceiling is AutonomyLevel.S2_PREPARE
    lied_once = DomainTrust(domain="d", verified_successes=10, false_successes=1)
    assert lied_once.has_unrecovered_false_success is True
    assert lied_once.earned_ceiling is AutonomyLevel.S0_RESPOND_ONLY
    # Netting the penalty back to "even" would treat a domain that misreported
    # as equivalent to one that never ran. Demonstrated recovery is the way out.
    recovered = DomainTrust(domain="d", verified_successes=20, false_successes=1,
                            recovery_successes=1)
    assert recovered.has_unrecovered_false_success is False
    assert recovered.earned_ceiling is AutonomyLevel.S2_PREPARE


def test_demonstrated_unreliability_suspends_an_owner_grant():
    """A grant is not a licence to keep going after VAN has shown it cannot."""
    granted = DomainTrust(
        domain="d", owner_granted_ceiling=AutonomyLevel.S4_STANDING_AUTHORITY,
        verified_successes=1, false_successes=1,
    )
    assert granted.effective_ceiling is AutonomyLevel.S0_RESPOND_ONLY
    recovered = DomainTrust(
        domain="d", owner_granted_ceiling=AutonomyLevel.S4_STANDING_AUTHORITY,
        verified_successes=20, false_successes=1, recovery_successes=1,
    )
    assert recovered.effective_ceiling is AutonomyLevel.S4_STANDING_AUTHORITY


def test_autonomy_is_domain_specific():
    """§30 — competence in one place must not buy permission in another."""
    trusted = DomainTrust(domain="statements", verified_successes=20,
                          owner_granted_ceiling=AutonomyLevel.S3_REVERSIBLE_EXECUTION)
    untouched = DomainTrust(domain="calendar")
    assert trusted.permits(ProactiveMissionType.SAFE_BOUNDED_AUTOMATIC) is True
    assert untouched.permits(ProactiveMissionType.SAFE_BOUNDED_AUTOMATIC) is False


async def test_trust_is_recorded_and_ceiling_recomputed(tmp_path):
    service = DomainTrustService(await make_store(tmp_path))
    for _ in range(12):
        await service.record("statements", verified_success=1, now_ms=NOW)
    trust = await service.get("statements")
    assert trust.earned_ceiling is AutonomyLevel.S2_PREPARE
    with pytest.raises(AutonomyError, match="NOT_PERMITTED"):
        await service.assert_may_run("statements", ProactiveMissionType.SAFE_BOUNDED_AUTOMATIC)
    await service.assert_may_run("statements", ProactiveMissionType.RECOMMENDATION)


async def test_a_grant_requires_owner_evidence(tmp_path):
    service = DomainTrustService(await make_store(tmp_path))
    with pytest.raises(AutonomyError, match="REQUIRES_OWNER_EVIDENCE"):
        await service.grant("calendar", level=AutonomyLevel.S3_REVERSIBLE_EXECUTION,
                            evidence_ref="")
    await service.grant("calendar", level=AutonomyLevel.S3_REVERSIBLE_EXECUTION,
                        evidence_ref="decision://d1", now_ms=NOW)
    trust = await service.get("calendar")
    assert trust.effective_ceiling is AutonomyLevel.S3_REVERSIBLE_EXECUTION


async def test_a_proactive_policy_records_the_owner_evidence(tmp_path):
    store = await make_store(tmp_path)
    trust = DomainTrustService(store)
    policies = ProactivePolicyService(store, trust)
    allowed, reason = await policies.may_create(
        domain="ci", mission_type=ProactiveMissionType.SAFE_BOUNDED_AUTOMATIC
    )
    assert allowed is False and "ceiling" in reason

    await policies.grant_policy(
        domain="ci", autonomy_level=AutonomyLevel.S3_REVERSIBLE_EXECUTION,
        mission_class="ci_recovery", owner_evidence_ref="decision://d2", now_ms=NOW,
    )
    allowed, reason = await policies.may_create(
        domain="ci", mission_type=ProactiveMissionType.SAFE_BOUNDED_AUTOMATIC
    )
    assert allowed is True and reason is None


# ------------------------------------------------------- §§10, 29 attention


async def test_an_internally_recoverable_error_is_suppressed(tmp_path):
    """§29 — VAN handling its own transient failure is not news."""
    scorer = AttentionScorer(await make_store(tmp_path))
    result = await scorer.score(
        AttentionCandidate(
            source="automation", dedupe_key="n8n-retry", importance=0.9, urgency=0.9,
            internally_recoverable=True,
        ),
        now_ms=NOW,
    )
    assert result.disposition is Disposition.SUPPRESS
    assert result.reason == "internally_recoverable"


async def test_the_second_alert_for_one_thing_becomes_a_digest(tmp_path):
    """§29 — one decision request, not a stream of reminders about it."""
    scorer = AttentionScorer(await make_store(tmp_path))
    candidate = AttentionCandidate(
        source="browser", dedupe_key="scope-extension-1", importance=0.9, urgency=0.9,
        actionability=1.0, owner_relevance=1.0, confidence=1.0,
    )
    first = await scorer.score(candidate, now_ms=NOW)
    second = await scorer.score(candidate, now_ms=NOW + 1000)
    assert first.disposition is Disposition.URGENT_INTERRUPT
    assert second.disposition is Disposition.DIGEST
    assert second.reason == "duplicate_within_window"


async def test_quiet_hours_hold_everything_but_a_genuine_urgent(tmp_path):
    scorer = AttentionScorer(await make_store(tmp_path))
    ordinary = await scorer.score(
        AttentionCandidate(source="s", dedupe_key="a", importance=0.7, urgency=0.6,
                           actionability=0.6, confidence=1.0),
        quiet_hours=True, now_ms=NOW,
    )
    assert ordinary.disposition is Disposition.DIGEST
    urgent = await scorer.score(
        AttentionCandidate(source="s", dedupe_key="b", importance=1.0, urgency=1.0,
                           actionability=1.0, owner_relevance=1.0, novelty=1.0,
                           confidence=1.0, interruption_cost=0.0),
        quiet_hours=True, now_ms=NOW,
    )
    assert urgent.disposition is Disposition.URGENT_INTERRUPT


async def test_interruption_cost_genuinely_subtracts(tmp_path):
    """Otherwise "important" becomes the only field and everything claims it."""
    scorer = AttentionScorer(await make_store(tmp_path))
    cheap = AttentionCandidate(source="s", dedupe_key="c1", importance=0.8, urgency=0.8,
                               confidence=1.0, interruption_cost=0.0)
    costly = AttentionCandidate(source="s", dedupe_key="c2", importance=0.8, urgency=0.8,
                                confidence=1.0, interruption_cost=1.0)
    assert cheap.score > costly.score


async def test_attention_metrics_admit_what_they_cannot_measure(tmp_path):
    scorer = AttentionScorer(await make_store(tmp_path))
    assert (await scorer.metrics(now_ms=NOW))["measured"] is False
    await scorer.score(
        AttentionCandidate(source="s", dedupe_key="x", importance=0.5), now_ms=NOW
    )
    metrics = await scorer.metrics(now_ms=NOW + 1000)
    assert metrics["measured"] is True
    # §55 — nuisance rate needs owner reactions that do not exist yet.
    assert metrics["nuisance_rate"] is None


# --------------------------------------------- §§79-84 reality and evolution


async def test_an_external_observation_needs_a_source(tmp_path):
    reality = ExternalRealityModel(await make_store(tmp_path))
    with pytest.raises(ValueError, match="requires_source"):
        await reality.observe(subject="model-x", claim="deprecated",
                              source_kind="blog", source_ref="")


async def test_disagreement_with_the_owner_is_recorded_not_resolved(tmp_path):
    """§22 — the separation that stops personalisation becoming an echo chamber."""
    reality = ExternalRealityModel(await make_store(tmp_path))
    await reality.observe(
        subject="provider-api", claim="v1 auth was removed in March",
        source_kind="release_notes", source_ref="https://example.com/notes",
        contradicts_owner_belief=True, now_ms=NOW,
    )
    contradictions = await reality.contradictions()
    assert len(contradictions) == 1
    assert "v1 auth" in contradictions[0]["claim"]


async def test_a_technology_cannot_be_adopted_without_benchmark_and_owner(tmp_path):
    """§45.14 — Technology Radar attempts direct adoption without approval."""
    radar = AIEvolutionRadar(await make_store(tmp_path))
    tech = await radar.discover(name="Shiny Model", category="frontier_model", now_ms=NOW)
    for state in (PipelineState.WATCH, PipelineState.BENCHMARK, PipelineState.SHADOW,
                  PipelineState.PROPOSED):
        await radar.transition(tech.technology_id, target=state, now_ms=NOW)

    with pytest.raises(RadarError, match="NOT_ADMISSIBLE"):
        await radar.transition(tech.technology_id, target=PipelineState.ADMITTED,
                               owner_decision_ref="decision://x", now_ms=NOW)

    await radar.update(tech.technology_id, benchmark_digest="sha256:abc",
                       security_profile="reviewed", licence="MIT", now_ms=NOW)
    with pytest.raises(RadarError, match="REQUIRES_OWNER_DECISION"):
        await radar.transition(tech.technology_id, target=PipelineState.ADMITTED, now_ms=NOW)

    admitted = await radar.transition(
        tech.technology_id, target=PipelineState.ADMITTED,
        owner_decision_ref="decision://owner-1", now_ms=NOW,
    )
    assert admitted.pipeline_state is PipelineState.ADMITTED


async def test_the_pipeline_cannot_be_skipped(tmp_path):
    radar = AIEvolutionRadar(await make_store(tmp_path))
    tech = await radar.discover(name="Fast Track", category="agent_framework", now_ms=NOW)
    with pytest.raises(RadarError, match="ILLEGAL_TRANSITION"):
        await radar.transition(tech.technology_id, target=PipelineState.ADMITTED,
                               owner_decision_ref="d", now_ms=NOW)


async def test_regression_needs_two_runs_not_one_bad_day(tmp_path):
    harness = BenchmarkHarness(await make_store(tmp_path))
    await harness.record_run(
        suite="coding", technology_id="tech_a",
        results=[{"passed": True}] * 9 + [{"passed": False}], now_ms=NOW,
    )
    assert await harness.regressed("coding", "tech_a") is False
    await harness.record_run(
        suite="coding", technology_id="tech_a",
        results=[{"passed": True}] * 5 + [{"passed": False}] * 5, now_ms=NOW + 1000,
    )
    assert await harness.regressed("coding", "tech_a") is True


async def test_an_unknown_benchmark_suite_is_refused(tmp_path):
    harness = BenchmarkHarness(await make_store(tmp_path))
    with pytest.raises(RadarError, match="SUITE_UNKNOWN"):
        await harness.record_run(suite="vibes", results=[])


# ------------------------------------------------------- §25 strategy learning


async def test_a_strategy_cannot_be_preferred_on_a_lucky_streak(tmp_path):
    learning = StrategyLearning(await make_store(tmp_path))
    strategy_id = await learning.register(
        mission_class="statement_collection",
        capability_sequence=["knowledge.vekl.retrieve", "automation.workflow.execute"],
        now_ms=NOW,
    )
    with pytest.raises(RadarError, match="REQUIRES_EVAL"):
        await learning.promote(strategy_id, target=PromotionState.PREFERRED)
    for _ in range(3):
        await learning.record_outcome(strategy_id, outcome=StrategyOutcome.SUCCESS, now_ms=NOW)
    with pytest.raises(RadarError, match="INSUFFICIENT_EVIDENCE"):
        await learning.promote(strategy_id, target=PromotionState.PREFERRED,
                               eval_run_id="eval_1")
    for _ in range(9):
        await learning.record_outcome(strategy_id, outcome=StrategyOutcome.SUCCESS, now_ms=NOW)
    promoted = await learning.promote(strategy_id, target=PromotionState.PREFERRED,
                                      eval_run_id="eval_1")
    assert promoted["promotion_state"] == "PREFERRED"


async def test_demotion_is_automatic_where_promotion_is_not(tmp_path):
    """Removing trust from something that stopped working needs no ceremony."""
    learning = StrategyLearning(await make_store(tmp_path))
    strategy_id = await learning.register(
        mission_class="research", capability_sequence=["research.exa.search"], now_ms=NOW
    )
    for _ in range(10):
        await learning.record_outcome(strategy_id, outcome=StrategyOutcome.SUCCESS, now_ms=NOW)
    await learning.promote(strategy_id, target=PromotionState.PREFERRED, eval_run_id="e1")
    for _ in range(20):
        await learning.record_outcome(strategy_id, outcome=StrategyOutcome.FAILURE, now_ms=NOW)
    assert strategy_id in await learning.auto_demote(now_ms=NOW)


# ------------------------------------------------------------------ §40 eval


async def test_vaneval_reports_unmeasured_rather_than_a_flattering_pass(tmp_path):
    """§41 — do not self-award. §55 — never claim a target met on no data."""
    report = await VanEval(await make_store(tmp_path)).run(now_ms=NOW)
    for dimension in report["dimensions"]:
        assert dimension["meets_target"] is not True
        if not dimension["measured"]:
            assert dimension["score"] is None
            assert dimension["unmeasurable_reason"]
    assert report["summary"]["overall_score"] is None


async def test_the_owner_dependent_dimensions_say_what_would_make_them_measurable(tmp_path):
    report = await VanEval(await make_store(tmp_path)).run(now_ms=NOW)
    by_dim = {d["dimension"]: d for d in report["dimensions"]}
    symbiosis = by_dim[EvalDimension.COGNITIVE_SYMBIOSIS.value]
    assert symbiosis["measured"] is False
    assert "ground-truth" in symbiosis["unmeasurable_reason"]
    assert set(UNMEASURABLE_WITHOUT_OWNER_DATA) == {
        EvalDimension.COGNITIVE_SYMBIOSIS, EvalDimension.VOICE, EvalDimension.OWNER_UX
    }


async def test_an_unevidenced_verified_success_is_disqualifying(tmp_path):
    """Not a deduction — §41's false-verified-success target is zero."""
    store = await make_store(tmp_path)
    await store.execute(
        "INSERT INTO missions(mission_id, owner_principal_id, origin, origin_channel, title, "
        "goal, state, created_at_ms, updated_at_ms, verification_state) "
        "VALUES ('m1','o','OWNER_UI','UI','t','g','VERIFIED_SUCCESS',1,1,'VERIFIED')"
    )
    report = await VanEval(store).run(now_ms=NOW)
    authority = {d["dimension"]: d for d in report["dimensions"]}["authority_security"]
    assert authority["measured"] is True
    assert authority["score"] == 0.0
    assert authority["details"]["verified_without_receipt"] == 1
