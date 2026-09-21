"""TRD-REV51-095 blind reviewer / canary, 096 budget and degradation ladder."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.cognition.blind_reviewer import (
    CANARY_FLAWS,
    MIN_CANARIES_FOR_HEALTH,
    BlindReviewer,
    CanaryHealth,
    ReviewVerdict,
    blind_packet,
    plant_canary,
    select_canary,
)
from vati.cognition.budget import (
    PROTECTED_CONTROLS,
    RUNG_EFFECTS,
    BudgetViolation,
    CognitiveBudget,
    Rung,
)
from vati.cognition.contracts import ModelRole, normalise
from vati.core.events import EventKind
from vati.core.ledger import Ledger

D = Decimal


def _assess(ctx="ctx", model="fable-5.1"):
    return normalise({"verdict": "REDUCE", "reason_codes": ["EVIDENCE_THIN"],
                      "risk_multiplier": "0.5", "confidence": "0.9",
                      "narrative": "thin precedent"},
                     model_id=model, role=ModelRole.PRIMARY, context_hash=ctx, now_ms=1)


# ------------------------------------------------------------ 095 blindness
def test_the_packet_carries_no_authorship():
    p = blind_packet(_assess(), {"symbol": "EURUSD"})
    flat = str(p.body())
    for tell in ("fable", "PRIMARY", "model_id", "confidence", "contract_version"):
        assert tell not in flat


def test_confidence_is_withheld_so_certainty_is_not_reviewed_instead_of_reasoning():
    assert "confidence" not in blind_packet(_assess(), {}).body()


def test_the_same_assessment_and_context_produce_the_same_packet_id():
    a, ctx = _assess(), {"symbol": "EURUSD"}
    assert blind_packet(a, ctx).packet_id == blind_packet(a, ctx).packet_id


def test_two_models_writing_the_same_argument_are_indistinguishable():
    one = blind_packet(_assess(model="fable-5.1"), {"s": 1})
    two = blind_packet(_assess(model="gpt-5.6-sol"), {"s": 1})
    assert one.body() | {"packet_id": ""} == two.body() | {"packet_id": ""}


# -------------------------------------------------------------- 095 canaries
def test_canary_selection_is_deterministic_and_replayable():
    ids = [f"p{i}" for i in range(400)]
    first = [select_canary(i) for i in ids]
    second = [select_canary(i) for i in ids]
    assert [f.flaw_id if f else None for f in first] == [f.flaw_id if f else None for f in second]


def test_canaries_are_a_minority_of_packets():
    hits = sum(1 for i in range(1_000) if select_canary(f"p{i}"))
    assert 0 < hits < 300


def test_every_planted_flaw_is_an_internal_contradiction_not_a_market_opinion():
    base = blind_packet(_assess(), {"symbol": "EURUSD"})
    for flaw in CANARY_FLAWS:
        broken = plant_canary(base, flaw)
        if flaw.flaw_id == "REDUCE_WITHOUT_REDUCTION":
            assert broken.verdict == "REDUCE" and broken.risk_multiplier == "1"
        if flaw.flaw_id == "ABSTAIN_WITH_SIZE":
            assert broken.verdict == "ABSTAIN" and Decimal(broken.risk_multiplier) > 0


def _reviewer(fn, **kw) -> BlindReviewer:
    return BlindReviewer(reviewer_id="reviewer-a", review_fn=fn, **kw)


def _run(reviewer, n=200):
    for i in range(n):
        reviewer.review(_assess(ctx=f"ctx{i}"), {"i": i}, now_ms=1_000 + i)


def test_a_reviewer_that_catches_its_canaries_is_healthy_and_believed():
    def careful(p):
        if p.verdict == "REDUCE" and Decimal(p.risk_multiplier) >= 1:
            return {"verdict": "DISSENT", "note": "reduce that does not reduce"}
        if p.verdict == "ABSTAIN" and Decimal(p.risk_multiplier) > 0:
            return {"verdict": "DISSENT", "note": "abstain carrying size"}
        if "four hundred comparable" in p.reasoning and "EVIDENCE_THIN" in p.reason_codes:
            return {"verdict": "DISSENT", "note": "reasons contradict the verdict"}
        if p.verdict == "CONCUR" and p.context.get("event_minutes_to_release"):
            return {"verdict": "DISSENT", "note": "release inside the horizon"}
        return {"verdict": "CONCUR"}
    r = _reviewer(careful)
    _run(r)
    assert r.canaries_seen >= MIN_CANARIES_FOR_HEALTH
    assert r.canary_health() is CanaryHealth.HEALTHY
    assert r.trusted_reviews()


def test_a_rubber_stamp_reviewer_fails_and_its_whole_record_is_discarded():
    """Not filtered down to the good ones: a reviewer that missed planted
    contradictions has told you nothing about the packets it passed."""
    r = _reviewer(lambda p: {"verdict": "CONCUR"})
    _run(r)
    assert r.canary_health() is CanaryHealth.FAILING
    assert r.trusted_reviews() == []
    assert r.dissents() == []
    assert r.report()["verdicts_trusted"] is False


def test_too_few_canaries_is_unproven_rather_than_healthy():
    r = _reviewer(lambda p: {"verdict": "DISSENT"})
    for i in range(4):
        r.review(_assess(ctx=f"c{i}"), {}, now_ms=i)
    assert r.canary_health() is CanaryHealth.UNPROVEN


def test_a_reviewer_that_raises_does_not_thereby_approve():
    r = _reviewer(lambda p: (_ for _ in ()).throw(RuntimeError("down")))
    rev = r.review(_assess(), {}, now_ms=1)
    assert rev.verdict is ReviewVerdict.CANNOT_ASSESS


def test_an_unreadable_verdict_is_not_agreement():
    r = _reviewer(lambda p: {"verdict": "sure, looks fine"})
    assert r.review(_assess(), {}, now_ms=1).verdict is ReviewVerdict.CANNOT_ASSESS


def test_reviews_are_ledgered_against_the_context():
    led = Ledger(":memory:")
    r = _reviewer(lambda p: {"verdict": "CONCUR"}, ledger=led)
    r.review(_assess(ctx="ctx-z"), {}, now_ms=5)
    assert led.count(EventKind.BLIND_REVIEW) == 1
    assert [e.correlation_id for e in led.iter(EventKind.BLIND_REVIEW)] == ["ctx-z"]


def test_canary_flaws_are_recorded_by_name_on_the_review():
    r = _reviewer(lambda p: {"verdict": "DISSENT"})
    _run(r, 60)
    canaries = [rev for rev in r._reviews if rev.was_canary]
    assert canaries and all(c.canary_flaw_id for c in canaries)


# --------------------------------------------------------------- 096 ladder
def _budget(**kw) -> CognitiveBudget:
    return CognitiveBudget(micros_per_window=1_000, invocations_per_window=100, **kw)


def test_a_full_budget_runs_everything():
    d = _budget().check(now_ms=0)
    assert d.allowed and d.rung is Rung.FULL
    assert d.include_review and d.include_optional_context and not d.high_impact_only


def test_the_ladder_withdraws_review_first():
    b = _budget()
    b.spend(micros=600, now_ms=0)
    d = b.check(now_ms=0)
    assert d.rung is Rung.NO_REVIEW and not d.include_review
    assert d.include_optional_context and d.allowed


def test_then_optional_context():
    b = _budget()
    b.spend(micros=800, now_ms=0)
    assert b.check(now_ms=0).rung is Rung.REDUCED_CONTEXT
    assert not b.check(now_ms=0).include_optional_context


def test_then_high_impact_only():
    b = _budget()
    b.spend(micros=950, now_ms=0)
    assert not b.check(now_ms=0, is_high_impact=False).allowed
    assert b.check(now_ms=0, is_high_impact=True).allowed


def test_the_bottom_rung_is_no_cognition_which_is_the_deterministic_path():
    b = _budget()
    b.spend(micros=1_000, now_ms=0)
    d = b.check(now_ms=0, is_high_impact=True)
    assert d.rung is Rung.SUSPENDED and not d.allowed
    assert "Risk Authority approved" in RUNG_EFFECTS[Rung.SUSPENDED]


def test_every_rung_withdraws_an_addition_and_none_names_a_protection():
    for rung, effect in RUNG_EFFECTS.items():
        assert not any(c in effect for c in PROTECTED_CONTROLS)


def test_running_out_of_invocations_counts_as_running_out():
    b = CognitiveBudget(micros_per_window=1_000_000, invocations_per_window=2)
    b.spend(micros=1, now_ms=0)
    b.spend(micros=1, now_ms=0)
    assert not b.check(now_ms=0, is_high_impact=True).allowed


def test_the_window_rolls_and_the_allowance_returns():
    b = CognitiveBudget(micros_per_window=100, invocations_per_window=5, window_ms=1_000)
    b.spend(micros=100, now_ms=0)
    assert b.check(now_ms=0).rung is Rung.SUSPENDED
    assert b.check(now_ms=5_000).rung is Rung.FULL


def test_spend_follows_the_context_not_the_model():
    b = _budget()
    b.spend(micros=40, now_ms=0, context_hash="ctx")
    b.spend(micros=60, now_ms=0, context_hash="ctx")
    assert b.spent_on("ctx") == 100


def test_an_operator_floor_can_only_reduce_what_cognition_does():
    b = _budget()
    b.set_floor(Rung.HIGH_IMPACT_ONLY)
    assert b.check(now_ms=0, is_high_impact=False).allowed is False
    b.set_floor(None)
    assert b.check(now_ms=0).rung is Rung.FULL


def test_a_floor_cannot_promote_a_degraded_budget():
    b = _budget()
    b.spend(micros=1_000, now_ms=0)
    b.set_floor(Rung.FULL)
    assert b.check(now_ms=0, is_high_impact=True).rung is Rung.SUSPENDED


@pytest.mark.parametrize("control", PROTECTED_CONTROLS)
def test_degrading_a_deterministic_control_is_a_loud_error(control):
    with pytest.raises(BudgetViolation) as e:
        CognitiveBudget.assert_protections_intact([control])
    assert control in str(e.value)


def test_degrading_only_cognition_additions_is_fine():
    CognitiveBudget.assert_protections_intact(["blind_review", "analogue_retrieval"])


def test_a_zero_budget_must_be_stated_as_a_suspension():
    with pytest.raises(ValueError):
        CognitiveBudget(micros_per_window=0, invocations_per_window=10)


def test_a_negative_spend_is_refused():
    with pytest.raises(ValueError):
        _budget().spend(micros=-5, now_ms=0)


def test_budget_decisions_are_ledgered_against_the_context():
    led = Ledger(":memory:")
    _budget(ledger=led).check(now_ms=1, context_hash="ctx-b")
    assert led.count(EventKind.COGNITIVE_BUDGET) == 1



def test_qualification_runtime_joins_exam_and_blind_review_without_promotion():
    from vati.cognition.contracts import ModelRole, normalise
    from vati.cognition.qualification import CognitionQualificationRuntime
    from vati.core.events import EventKind
    from vati.core.ledger import Ledger

    ledger = Ledger(":memory:")
    q = CognitionQualificationRuntime(ledger=ledger)

    def answer(context):
        situation = str(context.get("situation", ""))
        if "certified strategy" in situation:
            return {"verdict": "CONCUR", "risk_multiplier": "1",
                    "confidence": "0.5", "reason_codes": []}
        reason = (
            "EVENT_PROXIMITY" if "FOMC" in situation
            else "CONTEXT_INCOMPLETE" if "without a risk_state" in situation
            else "CORRELATION_CROWDED" if "correlated" in situation
            else "EVIDENCE_THIN"
        )
        return {"verdict": "ABSTAIN", "risk_multiplier": "0",
                "confidence": "0.5", "reason_codes": [reason]}

    result = q.run_baseline_exam(
        answer, model_id="candidate", now_ms=100)
    assert result.paper_id == "rev51-baseline"
    assert ledger.count(EventKind.DECISION_EXAM) == 1

    assessment = normalise(
        {"verdict": "FLAG", "risk_multiplier": "1", "confidence": "0.4",
         "reason_codes": ["EVIDENCE_THIN"], "narrative": "thin sample"},
        model_id="candidate", role=ModelRole.PRIMARY,
        context_hash="ctx", now_ms=100)
    review = q.blind_review(
        assessment, {"sample": 4}, reviewer_id="reviewer",
        review_fn=lambda _packet: {
            "verdict": "CONCUR", "reason_codes": [], "note": "checked"},
        now_ms=101)
    assert review.reviewer_id == "reviewer"
    assert ledger.count(EventKind.BLIND_REVIEW) == 1
    assert not hasattr(result, "promote")
