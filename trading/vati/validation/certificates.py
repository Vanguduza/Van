"""Sealed validation evidence (§8, §10; TRD-ENH-013/020).

Promotion today requires an owner signature and a non-empty `evidence_refs`
list of opaque strings. That proves *someone signed*, never *what was proven* —
so the gate cannot tell a walk-forward report from the word "ok".

A certificate is the semantic content that `evidence_refs` never carried. It is
sealed by hash, names the data and code it was computed against, and carries the
validation policy version so an old certificate cannot borrow a newer policy's
authority.

Two kinds, one discipline:

* `StrategyValidationCertificate` gates capsule promotion.
* `FeatureValidationCertificate` gates a feature entering a capsule's
  `required_features`, and it measures *incremental* value over a named
  baseline. Standalone correlation with returns is how a registry acquires five
  colinear trend measures and manufactures confluence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from vati.core.canonical import canonical_hash
from vati.validation.policy import (
    DEFAULT_POLICY,
    VALIDATION_POLICY_VERSION,
    ValidationPolicy,
    ValidationStatistics,
    evaluate,
)

GREEN = "GREEN"
RED = "RED"

#: Feature admission states. A feature may be useful in shadow and still not be
#: admitted to production dependencies.
FEATURE_REJECTED_REDUNDANT = "REJECTED_REDUNDANT"
FEATURE_REJECTED_UNSTABLE = "REJECTED_UNSTABLE"
FEATURE_SHADOW_APPROVED = "SHADOW_APPROVED"
FEATURE_PRODUCTION_ADMITTED = "PRODUCTION_ADMITTED"

#: Above this absolute correlation with the baseline, a feature is a restatement.
MAX_BASELINE_CORRELATION = 0.90
#: Below this incremental expectancy delta there is nothing to admit.
MIN_INCREMENTAL_EXPECTANCY = 0.0


class CertificateError(ValueError):
    """A certificate that cannot support the claim being made on it."""


@dataclass(frozen=True)
class StrategyValidationCertificate:
    certificate_id: str
    strategy_id: str
    strategy_version: str
    capsule_hash: str
    data_manifest_hash: str
    #: Immutable validation outputs/manifests that produced the statistics.
    evidence_refs: tuple[str, ...]
    feature_set_version: str
    cost_model_revision: str
    stats: ValidationStatistics
    expectancy_R: float
    expectancy_lower_bound_R: float
    profit_factor: float
    max_drawdown: float
    cost_stress_2x: str = RED
    latency_slippage_stress: str = RED
    parameter_perturbation_stability: str = RED
    leakage_switch_result: str = RED
    feature_certificate_refs: tuple[str, ...] = ()
    regime_breakdown: Mapping[str, Any] = field(default_factory=dict)
    cpcv_configuration: Mapping[str, Any] = field(default_factory=dict)
    validation_policy_version: str = VALIDATION_POLICY_VERSION
    validation_hash: str = ""

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("stats", "validation_hash")}
        d["stats"] = self.stats.as_dict()
        d["evidence_refs"] = list(self.evidence_refs)
        d["feature_certificate_refs"] = list(self.feature_certificate_refs)
        d["regime_breakdown"] = dict(self.regime_breakdown)
        d["cpcv_configuration"] = dict(self.cpcv_configuration)
        return d

    def sealed(self) -> "StrategyValidationCertificate":
        return StrategyValidationCertificate(
            **{**self.__dict__, "validation_hash": canonical_hash(self.as_dict())})

    def verify_seal(self) -> bool:
        """A tampered certificate must not pass as its own evidence."""
        return bool(self.validation_hash) and self.validation_hash == canonical_hash(self.as_dict())


def evaluate_strategy_certificate(
    cert: StrategyValidationCertificate,
    *,
    policy: ValidationPolicy = DEFAULT_POLICY,
) -> tuple[bool, tuple[str, ...]]:
    """Fail closed, naming every unmet condition."""
    reasons: list[str] = []
    if not cert.verify_seal():
        reasons.append("certificate_seal_invalid")
    if cert.validation_policy_version != policy.version:
        reasons.append(f"policy_version:{cert.validation_policy_version}!={policy.version}")
    verdict = evaluate(cert.stats, policy)
    reasons.extend(verdict.reasons)
    for name, value in (
        ("cost_stress_2x", cert.cost_stress_2x),
        ("latency_slippage_stress", cert.latency_slippage_stress),
        ("parameter_perturbation_stability", cert.parameter_perturbation_stability),
        ("leakage_switch_result", cert.leakage_switch_result),
    ):
        if value != GREEN:
            reasons.append(f"{name}:{value}")
    if not cert.data_manifest_hash:
        reasons.append("no_data_manifest")
    if not cert.evidence_refs or any(not str(ref).strip() for ref in cert.evidence_refs):
        reasons.append("no_validation_evidence_refs")
    return (not reasons), tuple(reasons)


@dataclass(frozen=True)
class FeatureValidationCertificate:
    certificate_id: str
    feature_id: str
    feature_version: str
    baseline_feature_set_hash: str
    candidate_feature_set_hash: str
    instruments: tuple[str, ...]
    regimes: tuple[str, ...]
    timeframes: tuple[str, ...]
    redundancy_correlation: float
    incremental_expectancy_delta: float
    incremental_dsr_probability: float
    incremental_pbo_probability: float
    walk_forward_delta: float
    mutual_information_delta: Optional[float] = None
    regime_stability: Mapping[str, float] = field(default_factory=dict)
    instrument_stability: Mapping[str, float] = field(default_factory=dict)
    leakage_result: str = RED
    status: str = FEATURE_REJECTED_UNSTABLE
    validation_policy_version: str = VALIDATION_POLICY_VERSION
    certificate_hash: str = ""

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "certificate_hash"}
        for key in ("instruments", "regimes", "timeframes"):
            d[key] = list(getattr(self, key))
        d["regime_stability"] = dict(self.regime_stability)
        d["instrument_stability"] = dict(self.instrument_stability)
        return d

    def sealed(self) -> "FeatureValidationCertificate":
        return FeatureValidationCertificate(
            **{**self.__dict__, "certificate_hash": canonical_hash(self.as_dict())})

    def verify_seal(self) -> bool:
        return bool(self.certificate_hash) and self.certificate_hash == canonical_hash(self.as_dict())


def classify_feature_certificate(
    cert: FeatureValidationCertificate,
    *,
    policy: ValidationPolicy = DEFAULT_POLICY,
    max_baseline_correlation: float = MAX_BASELINE_CORRELATION,
) -> tuple[str, tuple[str, ...]]:
    """Decide admission from the evidence, not from the submitter's claim.

    Redundancy is checked before value: a feature that restates the baseline can
    show a positive delta purely as noise, and admitting it is how confluence
    becomes double-counting.
    """
    reasons: list[str] = []

    if not cert.verify_seal():
        return FEATURE_REJECTED_UNSTABLE, ("certificate_seal_invalid",)
    if abs(cert.redundancy_correlation) > max_baseline_correlation:
        return FEATURE_REJECTED_REDUNDANT, (
            f"redundancy_correlation:{cert.redundancy_correlation:.3f}>{max_baseline_correlation}",)
    if cert.leakage_result != GREEN:
        return FEATURE_REJECTED_UNSTABLE, (f"leakage_result:{cert.leakage_result}",)

    if cert.incremental_expectancy_delta <= MIN_INCREMENTAL_EXPECTANCY:
        reasons.append(f"incremental_expectancy_delta:{cert.incremental_expectancy_delta:.4f}<=0")
    if cert.incremental_dsr_probability < policy.min_dsr_probability:
        reasons.append(
            f"incremental_dsr_probability:{cert.incremental_dsr_probability:.4f}<{policy.min_dsr_probability}")
    if cert.incremental_pbo_probability > policy.max_pbo_probability:
        reasons.append(
            f"incremental_pbo_probability:{cert.incremental_pbo_probability:.4f}>{policy.max_pbo_probability}")
    if cert.walk_forward_delta <= 0:
        reasons.append(f"walk_forward_delta:{cert.walk_forward_delta:.4f}<=0")
    # A feature that helps in one regime and hurts in another is not stable.
    negative_regimes = sorted(k for k, v in cert.regime_stability.items() if v < 0)
    if negative_regimes:
        reasons.append("regime_instability:" + ",".join(negative_regimes))

    if reasons:
        return FEATURE_SHADOW_APPROVED if cert.incremental_expectancy_delta > 0 else FEATURE_REJECTED_UNSTABLE, tuple(reasons)
    return FEATURE_PRODUCTION_ADMITTED, ()


__all__ = [
    "GREEN", "RED",
    "FEATURE_PRODUCTION_ADMITTED", "FEATURE_REJECTED_REDUNDANT",
    "FEATURE_REJECTED_UNSTABLE", "FEATURE_SHADOW_APPROVED",
    "MAX_BASELINE_CORRELATION",
    "CertificateError",
    "FeatureValidationCertificate", "StrategyValidationCertificate",
    "classify_feature_certificate", "evaluate_strategy_certificate",
]
