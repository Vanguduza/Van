"""Deterministic producers for VATI validation certificates.

The certificate dataclasses are immutable evidence containers; this module is the
canonical producer. It derives DSR/PBO and performance statistics from supplied
validation observations, binds immutable data/evidence references, and seals the
result. Callers may not hand this producer pre-computed DSR/PBO values.
"""

from __future__ import annotations

import math
from decimal import Decimal
from statistics import mean, stdev
from typing import Mapping, Sequence

from vati.backtest.metrics import compute_metrics, deflated_sharpe, pbo_cscv
from vati.core.canonical import canonical_hash
from vati.validation.certificates import (
    GREEN,
    FeatureValidationCertificate,
    StrategyValidationCertificate,
    classify_feature_certificate,
)
from vati.validation.policy import ValidationStatistics


def _sharpe(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    sd = stdev(xs)
    return mean(xs) / sd if sd else 0.0


def _trial_sharpes(matrix: Sequence[Sequence[float]]) -> list[float]:
    return [_sharpe(tuple(float(x) for x in row)) for row in matrix if len(row) >= 2]


def _sample_variance(xs: Sequence[float]) -> float:
    return stdev(xs) ** 2 if len(xs) >= 2 else 0.0


def _edge_floor(xs: Sequence[float], z: float = 1.6448536269514722) -> float:
    if len(xs) < 2:
        return float(xs[0]) if xs else 0.0
    return mean(xs) - z * stdev(xs) / math.sqrt(len(xs))


def build_strategy_validation_certificate(
    *,
    strategy_id: str,
    strategy_version: str,
    capsule_hash: str,
    data_manifest_hash: str,
    evidence_refs: Sequence[str],
    feature_set_version: str,
    cost_model_revision: str,
    pnls: Sequence[Decimal],
    r_multiples: Sequence[Decimal],
    start_equity: Decimal,
    trial_returns_matrix: Sequence[Sequence[float]],
    walk_forward_windows: int,
    cost_stress_2x: str,
    latency_slippage_stress: str,
    parameter_perturbation_stability: str,
    leakage_switch_result: str,
    feature_certificate_refs: Sequence[str] = (),
    regime_breakdown: Mapping[str, object] | None = None,
    cpcv_configuration: Mapping[str, object] | None = None,
    cpcv_partitions: int = 4,
) -> StrategyValidationCertificate:
    if not data_manifest_hash:
        raise ValueError("data_manifest_hash is required")
    refs = tuple(str(x) for x in evidence_refs if str(x).strip())
    if not refs:
        raise ValueError("at least one immutable validation evidence reference is required")
    if len(pnls) != len(r_multiples):
        raise ValueError("pnls and r_multiples must describe the same observations")
    if len(r_multiples) < 3:
        raise ValueError("at least three validation observations are required")
    trials = [tuple(float(v) for v in row) for row in trial_returns_matrix]
    if not trials:
        raise ValueError("trial_returns_matrix is required for DSR/PBO")
    n_obs = min(len(row) for row in trials)
    if n_obs < 3:
        raise ValueError("trial return histories are too short")
    trial_srs = _trial_sharpes(trials)
    metrics = compute_metrics(pnls, r_multiples, start_equity)
    dsr = deflated_sharpe(
        metrics.sharpe_per_trade,
        n_obs=len(r_multiples),
        skew=metrics.skew,
        kurtosis=metrics.kurtosis,
        n_trials=len(trials),
        sr_variance_across_trials=_sample_variance(trial_srs),
    )
    pbo = pbo_cscv(trials, partitions=cpcv_partitions)
    stats = ValidationStatistics(
        observed_sharpe=metrics.sharpe_per_trade,
        dsr_probability=dsr,
        pbo_probability=pbo,
        n_trials=len(trials),
        n_observations=len(r_multiples),
        walk_forward_windows=walk_forward_windows,
    )
    identity = canonical_hash({
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "capsule_hash": capsule_hash,
        "data_manifest_hash": data_manifest_hash,
        "evidence_refs": list(refs),
        "feature_set_version": feature_set_version,
        "cost_model_revision": cost_model_revision,
    })[:24]
    cert = StrategyValidationCertificate(
        certificate_id=f"svc_{identity}",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        capsule_hash=capsule_hash,
        data_manifest_hash=data_manifest_hash,
        evidence_refs=refs,
        feature_set_version=feature_set_version,
        cost_model_revision=cost_model_revision,
        stats=stats,
        expectancy_R=metrics.expectancy_r,
        expectancy_lower_bound_R=_edge_floor([float(x) for x in r_multiples]),
        profit_factor=metrics.profit_factor,
        max_drawdown=metrics.max_drawdown_pct,
        cost_stress_2x=cost_stress_2x,
        latency_slippage_stress=latency_slippage_stress,
        parameter_perturbation_stability=parameter_perturbation_stability,
        leakage_switch_result=leakage_switch_result,
        feature_certificate_refs=tuple(feature_certificate_refs),
        regime_breakdown=dict(regime_breakdown or {}),
        cpcv_configuration=dict(cpcv_configuration or {"partitions": cpcv_partitions}),
    )
    return cert.sealed()


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    aa, bb = list(a[:n]), list(b[:n])
    ma, mb = mean(aa), mean(bb)
    da = math.sqrt(sum((x - ma) ** 2 for x in aa))
    db = math.sqrt(sum((x - mb) ** 2 for x in bb))
    if not da or not db:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(aa, bb)) / (da * db)


def build_feature_validation_certificate(
    *,
    feature_id: str,
    feature_version: str,
    baseline_feature_set_hash: str,
    candidate_feature_set_hash: str,
    data_manifest_hash: str,
    evidence_refs: Sequence[str],
    instruments: Sequence[str],
    regimes: Sequence[str],
    timeframes: Sequence[str],
    baseline_returns: Sequence[float],
    candidate_returns: Sequence[float],
    trial_delta_matrix: Sequence[Sequence[float]],
    baseline_feature_series: Sequence[Sequence[float]],
    candidate_feature_series: Sequence[float],
    walk_forward_baseline: Sequence[float],
    walk_forward_candidate: Sequence[float],
    regime_stability: Mapping[str, float],
    instrument_stability: Mapping[str, float] | None = None,
    leakage_result: str = GREEN,
    mutual_information_delta: float | None = None,
    cpcv_partitions: int = 4,
) -> FeatureValidationCertificate:
    if not data_manifest_hash:
        raise ValueError("data_manifest_hash is required")
    refs = tuple(str(x) for x in evidence_refs if str(x).strip())
    if not refs:
        raise ValueError("at least one immutable validation evidence reference is required")
    n = min(len(baseline_returns), len(candidate_returns))
    if n < 3:
        raise ValueError("baseline/candidate validation histories are too short")
    delta = [float(candidate_returns[i]) - float(baseline_returns[i]) for i in range(n)]
    trials = [tuple(float(v) for v in row) for row in trial_delta_matrix]
    if not trials:
        raise ValueError("trial_delta_matrix is required for incremental DSR/PBO")
    candidate_series = tuple(float(x) for x in candidate_feature_series)
    correlations = [
        abs(_pearson(tuple(float(x) for x in series), candidate_series))
        for series in baseline_feature_series if len(series) >= 2
    ]
    redundancy = max(correlations, default=0.0)
    delta_sr = _sharpe(delta)
    delta_skew = 0.0
    delta_kurt = 3.0
    if len(delta) >= 3:
        m = mean(delta)
        sd = stdev(delta)
        if sd:
            delta_skew = sum(((x - m) / sd) ** 3 for x in delta) / len(delta)
            delta_kurt = sum(((x - m) / sd) ** 4 for x in delta) / len(delta)
    dsr = deflated_sharpe(
        delta_sr,
        n_obs=len(delta),
        skew=delta_skew,
        kurtosis=delta_kurt,
        n_trials=len(trials),
        sr_variance_across_trials=_sample_variance(_trial_sharpes(trials)),
    )
    pbo = pbo_cscv(trials, partitions=cpcv_partitions)
    wf_n = min(len(walk_forward_baseline), len(walk_forward_candidate))
    wf_delta = (
        mean(float(walk_forward_candidate[i]) - float(walk_forward_baseline[i]) for i in range(wf_n))
        if wf_n else 0.0
    )
    identity = canonical_hash({
        "feature_id": feature_id,
        "feature_version": feature_version,
        "baseline_feature_set_hash": baseline_feature_set_hash,
        "candidate_feature_set_hash": candidate_feature_set_hash,
        "data_manifest_hash": data_manifest_hash,
        "evidence_refs": list(refs),
    })[:24]
    cert = FeatureValidationCertificate(
        certificate_id=f"fvc_{identity}",
        feature_id=feature_id,
        feature_version=feature_version,
        baseline_feature_set_hash=baseline_feature_set_hash,
        candidate_feature_set_hash=candidate_feature_set_hash,
        instruments=tuple(instruments),
        regimes=tuple(regimes),
        timeframes=tuple(timeframes),
        redundancy_correlation=redundancy,
        incremental_expectancy_delta=mean(delta),
        incremental_dsr_probability=dsr,
        incremental_pbo_probability=pbo,
        walk_forward_delta=wf_delta,
        data_manifest_hash=data_manifest_hash,
        evidence_refs=refs,
        mutual_information_delta=mutual_information_delta,
        regime_stability=dict(regime_stability),
        instrument_stability=dict(instrument_stability or {}),
        leakage_result=leakage_result,
    ).sealed()
    status, _ = classify_feature_certificate(cert)
    return FeatureValidationCertificate(**{**cert.__dict__, "status": status, "certificate_hash": ""}).sealed()


__all__ = [
    "build_feature_validation_certificate",
    "build_strategy_validation_certificate",
]
