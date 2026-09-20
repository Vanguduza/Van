"""Phase 7: dependency, tail risk, overlap, allocation evidence."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.arbiter.candidate import CandidateOpportunity
from vati.arbiter.portfolio_allocator import OpportunityPortfolioAllocator
from vati.learning.allocation import (
    EXPIRED,
    NOT_SELECTED,
    RISK_REJECTED,
    ROUTER_REFUSED,
    SIMULATED_EVIDENCE_WEIGHT,
    AllocationEpisode,
    RejectedOutcome,
)
from vati.learning.overlap import (
    HIGH,
    LOW,
    MEDIUM,
    UNKNOWN,
    OverlapEvidence,
    StrategyOverlapDetector,
)
from vati.risk.contracts import Direction
from vati.risk.dependency import (
    CONSERVATIVE_UNKNOWN_CORRELATION,
    PortfolioDependencyEngine,
)
from vati.risk.expected_shortfall import Position, expected_shortfall, portfolio_variance
from vati.risk.factors import FactorRegistry

ENGINE = PortfolioDependencyEngine()


def _assess(symbol, open_positions, risk="100", direction=1):
    return ENGINE.assess(candidate_id="c", symbol=symbol, candidate_risk=Decimal(risk),
                         direction=direction, open_positions=open_positions, now_ms=1)


# --- expected shortfall ---------------------------------------------------

def test_es_rises_with_correlation():
    p = [Position("EURUSD", Decimal("100")), Position("GBPUSD", Decimal("100"))]
    assert expected_shortfall(p, {("EURUSD", "GBPUSD"): 0.9}) > expected_shortfall(
        p, {("EURUSD", "GBPUSD"): 0.0})


def test_opposing_directions_reduce_portfolio_variance():
    same = [Position("EURUSD", Decimal("100"), 1), Position("GBPUSD", Decimal("100"), 1)]
    hedge = [Position("EURUSD", Decimal("100"), 1), Position("GBPUSD", Decimal("100"), -1)]
    rho = {("EURUSD", "GBPUSD"): 0.9}
    assert portfolio_variance(hedge, rho, default_correlation=0.5) < portfolio_variance(
        same, rho, default_correlation=0.5)


def test_empty_book_has_zero_es():
    assert expected_shortfall([], {}) == Decimal("0")


# --- correlation multiplier (F2) ------------------------------------------

def test_correlation_multiplier_is_populated_not_one_by_default():
    """F2: the field existed, was serialised and consumed, and was always 1."""
    snap = _assess("GBPUSD", [Position("EURUSD", Decimal("100"))])
    assert snap.correlation_multiplier < Decimal("1")


def test_multiplier_is_always_within_zero_and_one():
    for risk in ("1", "100", "10000", "1000000"):
        snap = _assess("GBPUSD", [Position("EURUSD", Decimal("100"))], risk=risk)
        assert Decimal("0") <= snap.correlation_multiplier <= Decimal("1")


def test_a_large_correlated_addition_is_cut_hardest():
    small = _assess("GBPUSD", [Position("EURUSD", Decimal("100"))], risk="10")
    large = _assess("GBPUSD", [Position("EURUSD", Decimal("100"))], risk="10000")
    assert large.correlation_multiplier < small.correlation_multiplier


def test_first_position_in_an_empty_book_is_not_reduced():
    assert _assess("EURUSD", []).correlation_multiplier == Decimal("1")


def test_unknown_pair_falls_back_to_a_conservative_default_not_independence():
    """A portfolio that looks diversified because nobody measured it."""
    engine = PortfolioDependencyEngine(factors=FactorRegistry({}))
    snap = engine.assess(candidate_id="c", symbol="MYSTERY2", candidate_risk=Decimal("100"),
                         direction=1, open_positions=[Position("MYSTERY1", Decimal("100"))], now_ms=1)
    assert snap.estimate_basis == "CONSERVATIVE_DEFAULT"
    assert CONSERVATIVE_UNKNOWN_CORRELATION > 0.5


def test_factor_overlap_is_used_when_returns_are_unavailable():
    snap = _assess("GBPUSD", [Position("EURUSD", Decimal("100"))])
    assert snap.estimate_basis == "FACTOR_OVERLAP"


def test_measured_correlation_takes_precedence():
    engine = PortfolioDependencyEngine(correlations={("EURUSD", "GBPUSD"): 0.1})
    snap = engine.assess(candidate_id="c", symbol="GBPUSD", candidate_risk=Decimal("100"),
                         direction=1, open_positions=[Position("EURUSD", Decimal("100"))], now_ms=1)
    assert snap.estimate_basis == "MEASURED"


def test_stressed_model_differs_from_the_normal_one():
    """Correlations converge under stress; sizing on the calm estimate sizes for the easy case."""
    snap = _assess("GBPUSD", [Position("EURUSD", Decimal("100"))])
    assert snap.normal_model_hash != snap.stressed_model_hash
    assert snap.stressed_incremental_es >= Decimal("0")


def test_snapshot_is_sealed():
    assert _assess("GBPUSD", [Position("EURUSD", Decimal("100"))]).dependency_hash


def test_dependency_reaches_the_allocator_as_a_penalty():
    def dep(c):
        return _assess(c.symbol, [Position("EURUSD", Decimal("100"))])

    a = OpportunityPortfolioAllocator(dependency_fn=dep)
    c = CandidateOpportunity(
        candidate_id="x", account_alias="fx", venue="deriv", symbol="GBPUSD",
        strategy_id="S", strategy_version="1", capsule_hash="c", strategy_state="DEMO",
        generated_at_ms=0, valid_from_ms=0, valid_until_ms=60_000, mtf_state_hash="m",
        source_state_hashes=("s",), feature_contract_hash="f", direction=Direction.LONG,
        entry=Decimal("1.1"), stop=Decimal("1.09"), targets=(Decimal("1.12"),),
        horizon="SWING", cost_multiple=Decimal("3")).sealed()
    d = a.rank([c], now_ms=0)[0]
    assert d.correlation_multiplier < Decimal("1")
    assert "dependency_penalty" in d.score_components


# --- strategy overlap -----------------------------------------------------

D = StrategyOverlapDetector()


def _ev(**kw):
    base = dict(strategy_a="A", strategy_b="B", instrument_overlap=0.0, factor_overlap=0.0,
                direction_overlap=0.0, regime_overlap=0.0, entry_time_overlap=0.0,
                return_correlation=None, drawdown_co_occurrence=None, paired_sample=0)
    base.update(kw)
    return OverlapEvidence(**base)


def test_same_instrument_and_direction_is_high_overlap():
    v = D.assess(_ev(instrument_overlap=1.0, factor_overlap=1.0,
                     direction_overlap=1.0, regime_overlap=1.0, entry_time_overlap=1.0))
    assert v.level == HIGH


def test_structural_overlap_works_with_no_return_history():
    v = D.assess(_ev(instrument_overlap=1.0, factor_overlap=1.0, direction_overlap=1.0))
    assert v.basis == "STRUCTURAL_ONLY" and v.level in (MEDIUM, HIGH)


def test_small_return_sample_is_not_treated_as_evidence():
    v = D.assess(_ev(instrument_overlap=0.2, return_correlation=0.95, paired_sample=5))
    assert v.basis == "STRUCTURAL_ONLY"
    assert any("return_sample_too_small" in r for r in v.reasons)


def test_sufficient_returns_can_raise_the_level_above_structure():
    v = D.assess(_ev(instrument_overlap=0.1, return_correlation=0.92, paired_sample=100))
    assert v.level == HIGH and v.basis == "STRUCTURAL_AND_RETURNS"


def test_no_evidence_at_all_is_unknown():
    assert D.assess(_ev()).level == UNKNOWN


def test_unknown_overlap_is_not_treated_as_low():
    """Reduce-only, and an unmeasured pair is not assumed independent."""
    assert D.multiplier(D.assess(_ev())) < Decimal("1")


@pytest.mark.parametrize("level_ev,expected", [
    (dict(instrument_overlap=1.0, factor_overlap=1.0, direction_overlap=1.0,
          regime_overlap=1.0, entry_time_overlap=1.0), Decimal("0.5")),
    (dict(instrument_overlap=0.1), Decimal("1")),
])
def test_overlap_multiplier_is_reduce_only(level_ev, expected):
    m = D.multiplier(D.assess(_ev(**level_ev)))
    assert m == expected and Decimal("0") <= m <= Decimal("1")


# --- allocation episode ---------------------------------------------------

def _episode(rejected):
    return AllocationEpisode("e1", "fx", 1, "snap", "allocator/0.1.0",
                             ("taken",), tuple(rejected)).sealed()


def test_regret_measures_the_best_legitimately_passed_over_alternative():
    ep = _episode([RejectedOutcome("passed", NOT_SELECTED, Decimal("1.8"))])
    assert ep.regret_R({"taken": Decimal("0.3")}) == Decimal("1.5")


def test_a_risk_rejection_is_never_allocator_regret():
    """The gate was right; counting it would teach routing around risk controls."""
    ep = _episode([RejectedOutcome("risky", RISK_REJECTED, Decimal("9.0"))])
    assert ep.regret_R({"taken": Decimal("0.3")}) == Decimal("0")
    assert "risky" in ep.excluded_from_regret()


@pytest.mark.parametrize("reason", [RISK_REJECTED, ROUTER_REFUSED])
def test_gate_refusals_are_excluded_from_regret(reason):
    ep = _episode([RejectedOutcome("x", reason, Decimal("9.0"))])
    assert ep.regret_R({"taken": Decimal("0")}) == Decimal("0")


def test_an_invalid_ex_ante_setup_does_not_count():
    """Hindsight guard: validity is frozen at decision time."""
    ep = _episode([RejectedOutcome("p", NOT_SELECTED, Decimal("5.0"), ex_ante_valid=False)])
    assert ep.regret_R({"taken": Decimal("0")}) == Decimal("0")


def test_taking_the_best_option_yields_zero_regret():
    ep = _episode([RejectedOutcome("p", NOT_SELECTED, Decimal("0.1"))])
    assert ep.regret_R({"taken": Decimal("2.0")}) == Decimal("0")


def test_counterfactual_evidence_is_weighted_down():
    assert _episode([]).evidence_weight == SIMULATED_EVIDENCE_WEIGHT < Decimal("1")


def test_episode_is_sealed():
    assert _episode([]).episode_hash
