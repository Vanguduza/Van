"""P0-A: the DSR gate must reject what `> 0` admitted (blueprint Rev 1.1 §5.1)."""

from __future__ import annotations

import pytest

from vati.backtest import deflated_sharpe
from vati.learning.curriculum import CURRICULUM
from vati.validation.policy import (
    DEFAULT_POLICY,
    VALIDATION_POLICY_VERSION,
    ValidationPolicy,
    ValidationStatistics,
    evaluate,
)


def _stats(**kw) -> ValidationStatistics:
    base = dict(
        observed_sharpe=0.6, dsr_probability=0.99, pbo_probability=0.05,
        n_trials=1, n_observations=200, walk_forward_windows=5,
    )
    base.update(kw)
    return ValidationStatistics(**base)


#: A plausible-looking overfit: a small positive per-observation Sharpe selected
#: from 500 trials on a short sample. This is the shape the `> 0` gate admits,
#: and the shape most likely to reach a promotion request.
_OVERFIT = dict(n_obs=60, skew=-0.5, kurtosis=5.0, n_trials=500, sr_variance_across_trials=0.05)


def test_gt_zero_admits_a_strategy_dsr_calls_certainly_overfit():
    """The defect: DSR ~1e-6 means essentially certain selection bias, and `> 0` passes it.

    `> 0` does reject the *extremes* — `math.erf` saturates, so a sufficiently
    negative z underflows to exactly 0.0. The gate leaks over the range that
    actually reaches a promotion request: a small positive Sharpe from many trials.
    """
    p = deflated_sharpe(0.10, **_OVERFIT)
    assert p > 0, "a `> 0` gate admits this"
    assert p < 0.001, "while DSR itself says it is essentially certainly overfit"
    assert p < DEFAULT_POLICY.min_dsr_probability, "the policy gate must not admit it"


def test_gt_zero_even_admits_a_negative_sharpe_within_the_non_underflowing_range():
    p = deflated_sharpe(-0.02, n_obs=60, skew=-0.5, kurtosis=5.0, n_trials=100,
                        sr_variance_across_trials=0.05)
    assert p > 0, "negative observed Sharpe, still admitted by `> 0`"
    assert not evaluate(_stats(observed_sharpe=-0.02, dsr_probability=p)).passed


def test_overfit_candidate_fails_the_policy_gate():
    p = deflated_sharpe(0.10, **_OVERFIT)
    v = evaluate(_stats(observed_sharpe=0.10, dsr_probability=p))
    assert not v.passed
    assert any(r.startswith("dsr_probability:") for r in v.reasons)


def test_high_dsr_and_low_pbo_passes():
    assert evaluate(_stats()).passed


def test_low_dsr_fails():
    v = evaluate(_stats(dsr_probability=0.90))
    assert not v.passed and any("dsr_probability" in r for r in v.reasons)


def test_pbo_above_threshold_fails():
    v = evaluate(_stats(pbo_probability=0.5))
    assert not v.passed and any("pbo_probability" in r for r in v.reasons)


def test_insufficient_observations_fails_even_with_perfect_dsr():
    v = evaluate(_stats(n_observations=5, dsr_probability=1.0))
    assert not v.passed and any("insufficient_observations" in r for r in v.reasons)


def test_insufficient_walk_forward_fails():
    v = evaluate(_stats(walk_forward_windows=1))
    assert not v.passed and any("insufficient_walk_forward" in r for r in v.reasons)


def test_every_unmet_condition_is_named_not_just_the_first():
    v = evaluate(_stats(dsr_probability=0.1, pbo_probability=0.9, walk_forward_windows=0))
    assert len(v.reasons) == 3


def test_policy_version_is_sealed_into_the_verdict():
    assert evaluate(_stats()).policy_version == VALIDATION_POLICY_VERSION


def test_mutation_threshold_to_zero_would_admit_a_negative_sharpe_strategy():
    """§48 mutation `DSR threshold 0.95 -> 0`. This test must fail if applied."""
    vacuous = ValidationPolicy(min_dsr_probability=0.0, max_pbo_probability=1.0,
                               min_observations=0, min_walk_forward_windows=0)
    p = deflated_sharpe(0.10, **_OVERFIT)
    assert evaluate(_stats(dsr_probability=p), vacuous).passed, "the mutation is real"
    assert not evaluate(_stats(dsr_probability=p)).passed, "the shipped policy rejects it"


def test_curriculum_renders_active_policy():
    """S3: the stage string is generated, not a third copy of the numbers."""
    assert DEFAULT_POLICY.describe() in CURRICULUM[0].pass_criteria
    assert "0.95" in CURRICULUM[0].pass_criteria
