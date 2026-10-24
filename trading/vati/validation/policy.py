"""Validation thresholds as one object (blueprint Rev 1.1 §5.1, P0-A).

`deflated_sharpe()` returns a *probability* — `_norm_cdf(z)`. A gate of
`deflated Sharpe > 0` therefore accepts vanishingly small probabilities across
most practical inputs (and can even admit a negative observed Sharpe); only
extreme tails that numerically underflow/saturate to exactly zero are refused.
The defect is semantic: a probability must be compared with the validation
policy threshold, not merely with zero.

The fix is not a better literal. It is a named field whose units are obvious
(`dsr_probability`, not `deflated Sharpe`) and one object that owns the numbers,
so a second copy cannot drift away from the first. `curriculum.py` renders its
stage text from here rather than restating it.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

#: Bumped when thresholds, numerical validity or estimator semantics change. Sealed into every certificate so an old
#: certificate cannot silently claim the current policy's authority.
VALIDATION_POLICY_VERSION = "validation-policy/1.1.0"


@dataclass(frozen=True)
class ValidationPolicy:
    """Thresholds a strategy or feature must clear. Probabilities, not ratios."""

    #: P(observed Sharpe > expected max Sharpe of `n_trials` unskilled trials).
    min_dsr_probability: float = 0.95
    #: P(the selected configuration underperforms the median out of sample).
    max_pbo_probability: float = 0.10
    #: Below this many observations the DSR estimate is not meaningful.
    min_observations: int = 30
    #: A single walk-forward window proves nothing about stability.
    min_walk_forward_windows: int = 3
    version: str = VALIDATION_POLICY_VERSION

    def describe(self) -> str:
        """The one rendering of these numbers. Callers never restate them."""
        return (
            f"DSR probability >= {self.min_dsr_probability}, "
            f"PBO <= {self.max_pbo_probability}"
        )


DEFAULT_POLICY = ValidationPolicy()


@dataclass(frozen=True)
class ValidationStatistics:
    """What a validation run measured, in the units the gate actually compares."""

    observed_sharpe: float
    dsr_probability: float
    pbo_probability: float
    n_trials: int
    n_observations: int
    walk_forward_windows: int = 0
    validation_policy_version: str = VALIDATION_POLICY_VERSION

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ValidationVerdict:
    passed: bool
    reasons: tuple[str, ...]
    policy_version: str

    def as_dict(self) -> dict:
        return {"passed": self.passed, "reasons": list(self.reasons), "policy_version": self.policy_version}


def evaluate(stats: ValidationStatistics, policy: ValidationPolicy = DEFAULT_POLICY) -> ValidationVerdict:
    """Fail closed: every unmet condition is named, not just the first."""
    reasons: list[str] = []
    # Threshold comparisons alone accept some impossible values (e.g. DSR=2,
    # PBO=-1). No hash or owner signature makes malformed statistics evidence.
    for name in ("dsr_probability", "pbo_probability"):
        value = getattr(stats, name)
        if not finite_number(value) or not 0 <= value <= 1:
            reasons.append(f"invalid_probability:{name}")
    for name, minimum in (("n_trials", 1), ("n_observations", 0), ("walk_forward_windows", 0)):
        value = getattr(stats, name)
        if type(value) is not int or value < minimum:
            reasons.append(f"invalid_count:{name}")
    if not finite_number(stats.observed_sharpe):
        reasons.append("invalid_observed_sharpe")
    if stats.validation_policy_version != policy.version:
        reasons.append(f"statistics_policy_version:{stats.validation_policy_version}!={policy.version}")
    if reasons:
        return ValidationVerdict(False, tuple(reasons), policy.version)
    if stats.n_observations < policy.min_observations:
        reasons.append(
            f"insufficient_observations:{stats.n_observations}<{policy.min_observations}"
        )
    if stats.walk_forward_windows < policy.min_walk_forward_windows:
        reasons.append(
            f"insufficient_walk_forward:{stats.walk_forward_windows}<{policy.min_walk_forward_windows}"
        )
    # The defect this module exists for: a probability compared against 0 admits
    # everything, so the comparison is against the policy threshold and the field
    # name says which quantity is being compared.
    if not (stats.dsr_probability >= policy.min_dsr_probability):
        reasons.append(
            f"dsr_probability:{stats.dsr_probability:.4f}<{policy.min_dsr_probability}"
        )
    if not (stats.pbo_probability <= policy.max_pbo_probability):
        reasons.append(
            f"pbo_probability:{stats.pbo_probability:.4f}>{policy.max_pbo_probability}"
        )
    return ValidationVerdict(not reasons, tuple(reasons), policy.version)


def finite_number(value) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


__all__ = [
    "VALIDATION_POLICY_VERSION",
    "ValidationPolicy",
    "ValidationStatistics",
    "ValidationVerdict",
    "DEFAULT_POLICY",
    "evaluate",
]
