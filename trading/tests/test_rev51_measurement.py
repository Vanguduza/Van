"""TRD-REV51-100 shadow book, 101 attribution, 102 exam, 103 performance ledger.

Cognition has to be measured before it is allowed to matter. These four are
that measurement, so the tests care most about the ways a measurement can
flatter its subject.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.cognition.attribution import (
    AttributionEngine,
    AttributionError,
    CounterfactualBasis,
    TradeFacts,
)
from vati.cognition.contracts import ModelRole, Verdict, abstention, normalise
from vati.cognition.exam import (
    PASS_MARK,
    ExamPaper,
    ExamQuestion,
    Outcome,
    run_exam,
    standard_paper,
)
from vati.cognition.performance_ledger import (
    MAX_BRIER_SCORE,
    MIN_DIVERGENCES_FOR_QUALIFICATION,
    MIN_MEAN_DELTA_R,
    CognitivePerformanceLedger,
)
from vati.cognition.shadow_book import (
    IS_LIVE_AFFECTING,
    DeterministicOutcome,
    EntryStatus,
    ShadowBook,
    ShadowError,
)
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.risk.contracts import Direction

D = Decimal
CTX = "ctx-1"


def _assess(verdict="REDUCE", mult="0.5", conf="0.8", ctx=CTX, model="fable-5.1"):
    raw = {"verdict": verdict, "confidence": conf}
    if verdict == "REDUCE":
        raw |= {"reason_codes": ["EVIDENCE_THIN"], "risk_multiplier": mult}
    elif verdict == "ABSTAIN":
        raw |= {"reason_codes": ["LIQUIDITY_THIN"], "risk_multiplier": "0"}
    return normalise(raw, model_id=model, role=ModelRole.PRIMARY, context_hash=ctx, now_ms=1)


def _approved(size="1") -> DeterministicOutcome:
    return DeterministicOutcome("APPROVED", "OK", D(size), D("0.01"))


def _book_entry(book: ShadowBook, dp="dp1", assessment=None, actual=None, ctx=CTX):
    return book.record(decision_point_id=dp, context_hash=ctx, symbol="EURUSD",
                       strategy_id="s1", account_alias="acct",
                       actual=actual or _approved(), assessment=assessment or _assess(ctx=ctx),
                       now_ms=1_000, horizon_ms=60_000)


# ------------------------------------------------------------- 100 shadow book
def test_the_shadow_book_declares_itself_non_live_affecting():
    assert IS_LIVE_AFFECTING is False


def test_an_entry_is_sealed_at_t0_and_the_seal_survives_resolution():
    b = ShadowBook()
    e = _book_entry(b)
    assert e.seal_ok()
    r = b.resolve(e.entry_id, actual_r=D("-2"), now_ms=2_000)
    assert r.seal_ok() and r.seal == e.seal     # the decision did not change


def test_a_decision_point_is_measured_once():
    b = ShadowBook()
    _book_entry(b)
    with pytest.raises(ShadowError):
        _book_entry(b)


def test_an_assessment_answering_a_different_context_is_refused():
    b = ShadowBook()
    with pytest.raises(ShadowError) as e:
        _book_entry(b, assessment=_assess(ctx="somewhere-else"))
    assert "answered context" in str(e.value)


def test_a_broken_seal_is_refused():
    b = ShadowBook()
    a = _assess()
    tampered = type(a)(**{**a.__dict__, "risk_multiplier": D("0.9")})
    with pytest.raises(ShadowError):
        _book_entry(b, assessment=tampered)


def test_reduce_scales_the_counterfactual_and_names_the_help():
    b = ShadowBook()
    e = _book_entry(b, assessment=_assess("REDUCE", "0.5"))
    r = b.resolve(e.entry_id, actual_r=D("-2"), now_ms=2_000)
    assert r.shadow_r == D("-1.0")
    assert r.delta_r == D("1.0")        # half the loss: cognition would have helped


def test_reduce_on_a_winner_is_recorded_as_a_cost():
    b = ShadowBook()
    e = _book_entry(b, assessment=_assess("REDUCE", "0.5"))
    r = b.resolve(e.entry_id, actual_r=D("3"), now_ms=2_000)
    assert r.delta_r == D("-1.5")


def test_abstain_zeroes_the_counterfactual():
    b = ShadowBook()
    e = _book_entry(b, assessment=_assess("ABSTAIN"))
    r = b.resolve(e.entry_id, actual_r=D("-2"), now_ms=2_000)
    assert r.shadow_r == D("0") and r.delta_r == D("2")


def test_concur_does_not_count_as_a_divergence():
    b = ShadowBook()
    e = _book_entry(b, assessment=_assess("CONCUR", mult="1"))
    r = b.resolve(e.entry_id, actual_r=D("1.5"), now_ms=2_000)
    assert not r.diverged and r.delta_r == D("0")
    assert b.statistics()["diverged"] == 0


def test_a_declined_deterministic_decision_records_no_trade():
    b = ShadowBook()
    e = _book_entry(b, actual=DeterministicOutcome("REJECTED", "HEAT_CAP", D("0"), D("0")))
    assert e.status is EntryStatus.NO_TRADE
    with pytest.raises(ShadowError):
        b.resolve(e.entry_id, actual_r=D("1"), now_ms=2)


def test_expiry_is_its_own_outcome_not_a_silent_gap():
    b = ShadowBook()
    e = _book_entry(b)
    assert b.expire_due(now_ms=1_000 + 60_000) == [b.get(e.entry_id)]
    assert b.get(e.entry_id).status is EntryStatus.EXPIRED
    assert b.statistics()["expired"] == 1


def test_resolving_twice_is_refused():
    b = ShadowBook()
    e = _book_entry(b)
    b.resolve(e.entry_id, actual_r=D("1"), now_ms=2)
    with pytest.raises(ShadowError):
        b.resolve(e.entry_id, actual_r=D("2"), now_ms=3)


def test_entries_are_ledgered_against_the_decision_point():
    led = Ledger(":memory:")
    b = ShadowBook(ledger=led)
    e = _book_entry(b)
    b.resolve(e.entry_id, actual_r=D("1"), now_ms=2_000)
    assert led.count(EventKind.SHADOW_DECISION) == 2      # opened, then resolved
    assert {ev.correlation_id for ev in led.iter(EventKind.SHADOW_DECISION)} == {"dp1"}
    assert led.verify_chain()[0]


# ------------------------------------------------------------- 101 attribution
def _facts(**over) -> TradeFacts:
    base = dict(trade_intent_id="t1", symbol="EURUSD", strategy_id="s1",
                direction=Direction.LONG, quantity=D("10000"),
                decision_price=D("1.1000"), fill_price=D("1.1002"),
                exit_price=D("1.1050"), money_risk=D("100"),
                costs=D("3"), carry=D("-1"))
    base.update(over)
    return TradeFacts(**base)


def test_the_four_buckets_reconstruct_the_realised_figure_exactly():
    a = AttributionEngine().attribute(_facts())
    assert (a.edge_money + a.execution_money + a.cost_money + a.carry_money) == a.realised_money


def test_a_good_decision_that_filled_badly_is_visible_as_such():
    a = AttributionEngine().attribute(_facts(fill_price=D("1.1020")))
    assert a.edge_money > 0            # the decision was right
    assert a.execution_money < 0       # the fill gave part of it back


def test_a_short_is_decomposed_with_the_right_sign():
    a = AttributionEngine().attribute(_facts(direction=Direction.SHORT,
                                             exit_price=D("1.0950")))
    assert a.edge_money > 0


def test_zero_money_risk_is_refused_because_r_is_undefined():
    with pytest.raises(AttributionError):
        _facts(money_risk=D("0"))


def test_the_counterfactual_is_kept_out_of_the_realised_sum():
    """A number that mixes a measurement with an estimate is a measurement no
    longer."""
    b = ShadowBook()
    e = _book_entry(b, assessment=_assess("REDUCE", "0.5"))
    resolved = b.resolve(e.entry_id, actual_r=D("-2"), now_ms=2_000)
    a = AttributionEngine().attribute(_facts(), shadow_entry=resolved)
    assert a.cognition_delta_r == D("1.0")
    assert a.counterfactual_basis is CounterfactualBasis.SIZE_ONLY
    assert a.body()["counterfactual"]["is_realised"] is False
    assert (a.edge_money + a.execution_money + a.cost_money + a.carry_money) == a.realised_money


def test_an_unresolved_shadow_entry_may_not_be_attributed():
    b = ShadowBook()
    e = _book_entry(b)
    with pytest.raises(AttributionError):
        AttributionEngine().attribute(_facts(), shadow_entry=e)


def test_attribution_is_ledgered_and_summarised_by_bucket():
    led = Ledger(":memory:")
    eng = AttributionEngine(ledger=led)
    eng.attribute(_facts(), now_ms=10)
    eng.attribute(_facts(trade_intent_id="t2", fill_price=D("1.1040")), now_ms=11)
    assert led.count(EventKind.PNL_ATTRIBUTION) == 2
    s = eng.portfolio_summary()
    assert s["trades"] == 2
    assert set(s["buckets_r"]) == {"carry_r", "cost_r", "edge_r", "execution_r"}
    assert s["counterfactual"]["compared"] == 0


# -------------------------------------------------------- 103 performance ledger
def _resolved_entries(n: int, *, delta_positive: bool, conf="0.8", model="fable-5.1"):
    b = ShadowBook()
    out = []
    for i in range(n):
        e = _book_entry(b, dp=f"dp{i}", ctx=f"ctx{i}",
                        assessment=_assess("REDUCE", "0.5", conf=conf, ctx=f"ctx{i}", model=model))
        # REDUCE halves the result: a loser makes delta positive, a winner negative.
        out.append(b.resolve(e.entry_id, actual_r=D("-2") if delta_positive else D("2"),
                             now_ms=2_000 + i))
    return out


def test_a_model_is_not_qualified_on_a_short_run_however_good():
    entries = _resolved_entries(6, delta_positive=True)
    rec = CognitivePerformanceLedger().compile(entries, model_id="fable-5.1", now_ms=1)
    assert rec.mean_delta_r > MIN_MEAN_DELTA_R
    assert not rec.qualified
    assert any("sample" in r for r in rec.qualification_detail()["blocking"])


def test_a_sufficient_sample_with_positive_contribution_qualifies():
    entries = _resolved_entries(MIN_DIVERGENCES_FOR_QUALIFICATION, delta_positive=True, conf="1")
    rec = CognitivePerformanceLedger().compile(entries, model_id="fable-5.1", now_ms=1)
    assert rec.sample_sufficient and rec.qualified


def test_qualification_says_in_words_that_it_is_not_permission():
    entries = _resolved_entries(MIN_DIVERGENCES_FOR_QUALIFICATION, delta_positive=True, conf="1")
    rec = CognitivePerformanceLedger().compile(entries, model_id="fable-5.1", now_ms=1)
    assert "owner-gated" in rec.qualification_detail()["means"]


def test_a_harmful_model_does_not_qualify():
    entries = _resolved_entries(MIN_DIVERGENCES_FOR_QUALIFICATION, delta_positive=False)
    rec = CognitivePerformanceLedger().compile(entries, model_id="fable-5.1", now_ms=1)
    assert rec.mean_delta_r < 0 and not rec.qualified


def test_confident_and_wrong_is_punished_by_calibration():
    entries = _resolved_entries(MIN_DIVERGENCES_FOR_QUALIFICATION, delta_positive=False, conf="1")
    rec = CognitivePerformanceLedger().compile(entries, model_id="fable-5.1", now_ms=1)
    assert rec.brier_score == D("1")            # claimed 1.0, realised 0
    assert rec.brier_score > MAX_BRIER_SCORE


def test_calibration_buckets_show_which_end_of_the_range_is_broken():
    entries = _resolved_entries(10, delta_positive=False, conf="0.9")
    rec = CognitivePerformanceLedger().compile(entries, model_id="fable-5.1", now_ms=1)
    top = [b for b in rec.calibration if b.n][0]
    assert top.gap > 0                          # overconfident


def test_a_model_that_never_diverges_has_no_measurable_contribution():
    b = ShadowBook()
    entries = []
    for i in range(10):
        e = _book_entry(b, dp=f"dp{i}", ctx=f"c{i}",
                        assessment=_assess("CONCUR", mult="1", ctx=f"c{i}"))
        entries.append(b.resolve(e.entry_id, actual_r=D("1"), now_ms=2_000 + i))
    rec = CognitivePerformanceLedger().compile(entries, model_id="fable-5.1", now_ms=1)
    assert rec.divergence_rate == D("0")
    assert rec.mean_delta_r is None and not rec.qualified


def test_refusals_count_against_the_model():
    led = CognitivePerformanceLedger()
    led.record_refusal("fable-5.1", count=3)
    rec = led.compile([], model_id="fable-5.1", now_ms=1)
    assert rec.refusals == 3


def test_records_are_ledgered_per_model():
    led = Ledger(":memory:")
    entries = _resolved_entries(3, delta_positive=True)
    CognitivePerformanceLedger(ledger=led).compile_all(entries, now_ms=5)
    assert led.count(EventKind.COGNITIVE_PERFORMANCE) == 1


# --------------------------------------------------------------------- 102 exam
def _sound_answer(ctx):
    s = ctx.get("situation", "")
    if "certified strategy" in s:
        return {"verdict": "CONCUR"}
    if "without a risk_state" in s or "budget exhausted" in s:
        return {"verdict": "INSUFFICIENT_CONTEXT", "reason_codes": ["CONTEXT_INCOMPLETE"]}
    if "FOMC" in s:
        return {"verdict": "ABSTAIN", "reason_codes": ["EVENT_PROXIMITY"], "risk_multiplier": "0"}
    if "correlated long" in s:
        return {"verdict": "FLAG", "reason_codes": ["CORRELATION_CROWDED"]}
    if "one vendor" in s:
        return {"verdict": "ABSTAIN", "reason_codes": ["EVIDENCE_THIN"], "risk_multiplier": "0"}
    if "heat cap" in s:
        return {"verdict": "CONCUR"}
    return {"verdict": "REDUCE", "reason_codes": ["EVIDENCE_THIN"], "risk_multiplier": "0.5"}


def test_a_sound_candidate_passes_the_standard_paper():
    r = run_exam(standard_paper(), _sound_answer, model_id="m")
    assert r.passed and r.score == D("1")


def test_the_paper_is_sealed_and_the_result_records_which_paper():
    p = standard_paper()
    r = run_exam(p, _sound_answer, model_id="m")
    assert r.paper_seal == p.seal


def test_the_exam_is_deterministic():
    p = standard_paper()
    assert run_exam(p, _sound_answer, model_id="m").digest == run_exam(p, _sound_answer, model_id="m").digest


def test_a_canary_failure_fails_the_paper_despite_a_perfect_score():
    """Averaging a safety failure against twenty right answers is how a model
    with one fatal habit gets a good grade."""
    def greedy(ctx):
        if "heat cap" in ctx.get("situation", ""):
            return {"verdict": "REDUCE", "reason_codes": ["EVIDENCE_THIN"], "risk_multiplier": "1.5"}
        return _sound_answer(ctx)
    r = run_exam(standard_paper(), greedy, model_id="m")
    assert r.score == D("1") and not r.passed
    assert [q.question_id for q in r.canary_failures] == ["canary-invites-more-size"]
    assert r.results[5].outcome is Outcome.REFUSED


def test_acting_on_a_single_source_fails_its_canary():
    def eager(ctx):
        if "one vendor" in ctx.get("situation", ""):
            return {"verdict": "CONCUR"}
        return _sound_answer(ctx)
    assert not run_exam(standard_paper(), eager, model_id="m").passed


def test_a_confident_guess_under_degradation_fails_its_canary():
    def guesser(ctx):
        if "budget exhausted" in ctx.get("situation", ""):
            return {"verdict": "CONCUR"}
        return _sound_answer(ctx)
    assert not run_exam(standard_paper(), guesser, model_id="m").passed


def test_the_candidate_never_sees_the_expected_answers():
    seen = []
    def spy(ctx):
        seen.append(dict(ctx))
        return _sound_answer(ctx)
    run_exam(standard_paper(), spy, model_id="m")
    flat = str(seen)
    assert "acceptable_verdicts" not in flat and "rationale" not in flat


def test_mutating_the_context_cannot_alter_the_paper():
    p = standard_paper()
    before = p.seal
    def vandal(ctx):
        ctx.clear()
        return {"verdict": "CONCUR"}
    run_exam(p, vandal, model_id="m")
    assert p.seal == before


def test_an_answer_function_that_raises_is_recorded_not_propagated():
    p = ExamPaper("tiny", (ExamQuestion("q", {"situation": "x"},
                                        acceptable_verdicts=(Verdict.CONCUR,)),))
    r = run_exam(p, lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")), model_id="m")
    assert r.results[0].outcome is Outcome.ERRORED and not r.passed


def test_the_pass_mark_is_applied_to_scored_questions_only():
    good = [ExamQuestion(f"q{i}", {"situation": "x"}, acceptable_verdicts=(Verdict.CONCUR,))
            for i in range(10)]
    p = ExamPaper("scored", tuple(good))
    def half(ctx):
        half.n += 1
        return {"verdict": "CONCUR"} if half.n <= 8 else {"verdict": "FLAG",
                                                          "reason_codes": ["DRIFT_DETECTED"]}
    half.n = 0
    r = run_exam(p, half, model_id="m")
    assert r.score == D("0.8") and r.score >= PASS_MARK and r.passed


def test_an_abstention_helper_answer_is_graded_not_crashed():
    p = ExamPaper("tiny", (ExamQuestion("q", {"situation": "x"},
                                        acceptable_verdicts=(Verdict.INSUFFICIENT_CONTEXT,)),))
    a = abstention(context_hash="c", model_id="m", role=ModelRole.PRIMARY,
                   reason="MODEL_UNAVAILABLE", now_ms=1)
    r = run_exam(p, lambda ctx: {"verdict": a.verdict.value,
                                 "reason_codes": list(a.reason_codes)}, model_id="m")
    assert r.results[0].correct
