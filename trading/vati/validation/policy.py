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

#: Bumped whenever a threshold changes. Sealed into every certificate so an old
#: certificate cannot silently claim the current policy's authority.
VALIDATION_POLICY_VERSION = "validation-policy/1.0.0"


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


__all__ = [
    "VALIDATION_POLICY_VERSION",
    "ValidationPolicy",
    "ValidationStatistics",
    "ValidationVerdict",
    "DEFAULT_POLICY",
    "evaluate",
]
