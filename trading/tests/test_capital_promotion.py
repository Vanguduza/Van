"""Phase 11/12: per-strategy budgets, capital proposals, Allocator V1.

This is the only phase that can raise a live ceiling, so the tests are mostly
about what cannot happen.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from decimal import Decimal as D

import pytest

from conftest import mandate_dict
from vati.arbiter.candidate import CandidateOpportunity
from vati.arbiter.portfolio_allocator import (
    V0_FORBIDDEN_INPUTS,
    AllocatorV1,
    OpportunityPortfolioAllocator,
)
from vati.risk import capital_promotion as cap_mod
from vati.risk.capital_promotion import (
    MAX_INCREASE_FACTOR,
    MIN_LIVE_SAMPLE,
    CapitalBudgetProposal,
    CapitalEfficiency,
    edge_floor_R,
    evaluate_proposal,
)
from vati.risk.contracts import Direction
from vati.risk.mandate import MandateError, PlatformCeilings, TradingMandate

SID = "FX-TREND-PULLBACK-01"


def _mandate(**kw):
    """`mandate_dict` signs itself with the correct act; just parse it."""
    from conftest import owner_authority
    d = mandate_dict(allowed_strategies=[SID, "OTHER"], **kw)
    return TradingMandate.from_mapping(d, authority=owner_authority().verifier)


# --- per-strategy budgets -------------------------------------------------

def test_absent_budget_falls_back_to_the_mandate_ceiling():
    """An unamended mandate behaves exactly as it did before."""
    m = _mandate(max_risk_per_trade="0.01")
    assert m.risk_budget_for(SID) == D("0.01")
    assert m.strategy_risk_budgets == {}


def test_a_budget_narrows_the_ceiling_for_one_strategy():
    m = _mandate(max_risk_per_trade="0.01", strategy_risk_budgets={SID: "0.0030"})
    assert m.risk_budget_for(SID) == D("0.0030")
    assert m.risk_budget_for("OTHER") == D("0.01")


def test_a_budget_can_never_widen_beyond_the_mandate():
    with pytest.raises(MandateError, match="exceeds max_risk_per_trade"):
        _mandate(max_risk_per_trade="0.005", strategy_risk_budgets={SID: "0.02"})


def test_a_budget_cannot_exceed_the_platform_ceiling():
    with pytest.raises(MandateError, match="exceeds"):
        _mandate(max_risk_per_trade="0.02", max_open_stop_risk="0.06",
                 strategy_risk_budgets={SID: "0.05"})


@pytest.mark.parametrize("value", ["0", "-0.001", "1", "2"])
def test_a_budget_outside_a_sane_fraction_is_refused(value):
    """`_fraction` rejects anything outside (0,1) before the ceiling checks run."""
    with pytest.raises(MandateError):
        _mandate(strategy_risk_budgets={SID: value})


def test_a_budget_for_an_unlisted_strategy_is_refused():
    with pytest.raises(MandateError, match="not in allowed_strategies"):
        _mandate(strategy_risk_budgets={"GHOST-01": "0.001"})


def test_risk_budget_for_always_takes_the_minimum():
    m = _mandate(max_risk_per_trade="0.01", strategy_risk_budgets={SID: "0.0030"})
    assert m.risk_budget_for(SID) <= m.max_risk_per_trade


# --- edge floor -----------------------------------------------------------

def test_edge_floor_separates_two_strategies_with_the_same_mean():
    """+0.34R [-0.02,+0.70] and +0.34R [+0.22,+0.46] are not the same proposition."""
    tight = [D("0.30"), D("0.35"), D("0.32"), D("0.36"), D("0.31")] * 8
    wide = [D("-0.9"), D("1.8"), D("0.1"), D("-0.5"), D("1.2")] * 8
    assert edge_floor_R(tight) > edge_floor_R(wide)


def test_edge_floor_is_below_the_mean():
    xs = [D("0.3")] * 5 + [D("0.5")] * 5
    mean = sum(xs) / D(len(xs))
    assert edge_floor_R(xs) < mean


def test_edge_floor_needs_a_sample():
    assert edge_floor_R([D("1")]) is None


# --- capital efficiency ---------------------------------------------------

def test_same_R_different_holding_time_is_not_the_same_trade():
    fast = CapitalEfficiency(expected_R=D("0.3"), mean_risk_days=D("0.1"))
    slow = CapitalEfficiency(expected_R=D("0.3"), mean_risk_days=D("4"))
    assert fast.expected_R_per_risk_day > slow.expected_R_per_risk_day


def test_financing_and_rollover_reduce_efficiency():
    plain = CapitalEfficiency(expected_R=D("0.3"), mean_risk_days=D("4"))
    charged = CapitalEfficiency(expected_R=D("0.3"), mean_risk_days=D("4"),
                                financing_cost_R=D("0.05"), rollover_cost_R=D("0.03"))
    assert charged.expected_R_per_risk_day < plain.expected_R_per_risk_day


def test_fill_probability_discounts_expected_r():
    certain = CapitalEfficiency(expected_R=D("0.3"), mean_risk_days=D("1"))
    unlikely = CapitalEfficiency(expected_R=D("0.3"), mean_risk_days=D("1"),
                                 fill_probability=D("0.4"))
    assert unlikely.expected_R_per_risk_day < certain.expected_R_per_risk_day


# --- proposals ------------------------------------------------------------

def _proposal(**kw) -> CapitalBudgetProposal:
    base = dict(
        proposal_id="p1", account_alias="fx", strategy_id=SID, strategy_version="1.0.0",
        current_budget=D("0.0050"), proposed_budget=D("0.0075"), validation_hash="vh",
        live_sample=60, shadow_sample=200, expectancy_R=D("0.34"), edge_floor_R=D("0.22"),
        max_drawdown=D("0.08"), tail_risk=D("0.12"), capital_efficiency=D("0.15"),
        created_at_ms=0, expires_at_ms=10_000,
    )
    base.update(kw)
    return CapitalBudgetProposal(**base).sealed()


def _verdict(p, **kw):
    args = dict(now_ms=1_000, mandate_max_risk_per_trade=D("0.02"),
                platform_max_risk_per_trade=D("0.02"))
    args.update(kw)
    return evaluate_proposal(p, **args)


def test_a_well_evidenced_proposal_is_admissible():
    assert _verdict(_proposal()).admissible


def test_a_proposal_cannot_apply_itself():
    """It has no mutation method and no reference to a mandate."""
    for name in ("apply", "commit", "mutate", "update_mandate", "sign"):
        assert not hasattr(CapitalBudgetProposal, name)
    tree = ast.parse(inspect.getsource(cap_mod))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "vati.risk.mandate" not in mods


def test_a_non_positive_edge_floor_is_refused():
    v = _verdict(_proposal(edge_floor_R=D("-0.02")))
    assert not v.admissible and any("edge_floor" in r for r in v.reasons)


def test_a_thin_live_sample_is_refused_however_good_the_backtest():
    v = _verdict(_proposal(live_sample=MIN_LIVE_SAMPLE - 1, shadow_sample=100_000))
    assert not v.admissible and any("insufficient_live_sample" in r for r in v.reasons)


def test_a_proposal_without_a_certificate_is_refused():
    v = _verdict(_proposal(validation_hash=""))
    assert not v.admissible and "no_validation_certificate" in v.reasons


def test_a_proposal_beyond_the_mandate_is_refused():
    v = _verdict(_proposal(proposed_budget=D("0.05")))
    assert not v.admissible and any("exceeds_mandate" in r for r in v.reasons)


def test_a_more_than_doubling_increase_is_refused():
    v = _verdict(_proposal(current_budget=D("0.001"), proposed_budget=D("0.010")))
    assert not v.admissible and any("increase_factor" in r for r in v.reasons)
    assert MAX_INCREASE_FACTOR == D("2")


def test_an_expired_proposal_is_refused():
    v = _verdict(_proposal(expires_at_ms=500))
    assert not v.admissible and any("expired" in r for r in v.reasons)


def test_a_tampered_proposal_fails_its_seal():
    import dataclasses
    p = dataclasses.replace(_proposal(), proposed_budget=D("0.02"))
    v = _verdict(p)
    assert not v.admissible and "proposal_seal_invalid" in v.reasons


def test_regime_instability_is_refused():
    v = _verdict(_proposal(regime_stability={"BULL": "0.2", "RANGE": "-0.1"}))
    assert not v.admissible and any("regime_instability" in r for r in v.reasons)


# --- Allocator V1 ---------------------------------------------------------

def _cand(**kw):
    base = dict(
        candidate_id="x", account_alias="fx", venue="deriv", symbol="EURUSD",
        strategy_id=SID, strategy_version="1", capsule_hash="c", strategy_state="DEMO",
        generated_at_ms=0, valid_from_ms=0, valid_until_ms=60_000, mtf_state_hash="m",
        source_state_hashes=("s",), feature_contract_hash="f", direction=Direction.LONG,
        entry=D("1.1"), stop=D("1.09"), targets=(D("1.12"),), horizon="SWING",
        cost_multiple=D("3"))
    base.update(kw)
    return CandidateOpportunity(**base).sealed()


def test_v1_credits_a_positive_edge_floor():
    a = AllocatorV1()
    plain = a.rank([_cand(candidate_id="a")], now_ms=0)[0]
    evidenced = a.rank([_cand(candidate_id="b", edge_floor_R=D("0.4"))], now_ms=0)[0]
    assert evidenced.allocation_utility > plain.allocation_utility


def test_v1_credits_capital_efficiency():
    a = AllocatorV1()
    slow = a.rank([_cand(candidate_id="a", expected_R_per_risk_day=D("0.01"))], now_ms=0)[0]
    fast = a.rank([_cand(candidate_id="b", expected_R_per_risk_day=D("3"))], now_ms=0)[0]
    assert fast.allocation_utility > slow.allocation_utility


def test_v1_still_excludes_confidence():
    """The calibration gate has not been passed, so the exclusion stands."""
    a = AllocatorV1()
    low = a.rank([_cand(candidate_id="a", confidence_score=D("0.01"))], now_ms=0)[0]
    high = a.rank([_cand(candidate_id="a", confidence_score=D("0.99"))], now_ms=0)[0]
    assert low.allocation_utility == high.allocation_utility
    src = textwrap.dedent(inspect.getsource(AllocatorV1._utility))
    attrs = {n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute)}
    assert not (attrs & set(V0_FORBIDDEN_INPUTS))


def test_v1_has_no_sizing_api_either():
    for name in ("reserve_heat", "allocate_size", "preapprove"):
        assert not hasattr(AllocatorV1, name)


def test_missing_evidence_is_not_punished_into_oblivion():
    """A candidate with no edge floor is uncredited, not zeroed."""
    assert AllocatorV1().rank([_cand()], now_ms=0)[0].allocation_utility > 0
