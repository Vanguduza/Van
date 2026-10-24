"""Invalid statistics and silently dropped observations cannot qualify a model."""
from dataclasses import replace
from decimal import Decimal as D
from itertools import combinations
from statistics import mean, stdev

import pytest

from conftest import passing_certificate
from test_validation_certificates import _feature_cert
from test_validation_policy import _stats
from vati.validation.policy import evaluate
from vati.validation.certificates import (
    FEATURE_PRODUCTION_ADMITTED, FEATURE_REJECTED_UNSTABLE,
    classify_feature_certificate, evaluate_strategy_certificate,
)


@pytest.mark.parametrize("field,value", [("dsr_probability",2.0),("pbo_probability",-0.1),
    ("n_trials",0),("n_trials",True),("n_observations",200.5),("walk_forward_windows",5.5),
    ("observed_sharpe",float("inf")),("observed_sharpe",float("nan")),
    ("validation_policy_version","superseded-policy")])
def test_invalid_or_wrong_version_statistics_are_refused(field, value):
    assert not evaluate(_stats(**{field:value})).passed


@pytest.mark.parametrize("field", ["redundancy_correlation","incremental_expectancy_delta",
    "incremental_dsr_probability","incremental_pbo_probability","walk_forward_delta"])
def test_nonfinite_feature_statistics_cannot_receive_production_admission(field):
    cert = _feature_cert(**{field:float("nan")})
    status, reasons = classify_feature_certificate(cert)
    assert status == FEATURE_REJECTED_UNSTABLE and reasons


def test_feature_policy_version_and_probability_ranges_are_checked():
    for patch in ({"validation_policy_version":"superseded-policy"},
                  {"incremental_dsr_probability":2.0}, {"incremental_pbo_probability":-1.0},
                  {"regime_stability":{"BULL":float("nan"),"BEAR":0.1}}):
        assert classify_feature_certificate(_feature_cert(**patch))[0] == FEATURE_REJECTED_UNSTABLE


def test_known_adverse_instrument_evidence_cannot_be_ignored():
    status, reasons = classify_feature_certificate(_feature_cert(instrument_stability={"EURUSD":-0.1}))
    assert status != FEATURE_PRODUCTION_ADMITTED
    assert any("instrument_instability" in reason for reason in reasons)


@pytest.mark.parametrize("field,value", [("expectancy_R",float("nan")),
    ("expectancy_lower_bound_R",float("inf")),("max_drawdown",-0.1),("profit_factor",-1.0)])
def test_malformed_performance_cannot_pass_a_sealed_certificate(field, value):
    cert = replace(passing_certificate(strategy_id="validity"),**{field:value}).sealed()
    assert cert.verify_seal()
    assert not evaluate_strategy_certificate(cert)[0]


def test_no_losses_profit_factor_is_explicitly_unbounded_not_a_nonfinite_sharpe():
    cert = replace(passing_certificate(strategy_id="validity"),profit_factor=float("inf")).sealed()
    assert evaluate_strategy_certificate(cert)[0]


def independent_pbo(matrix, partitions):
    boundaries = [(i*len(matrix[0])//partitions,(i+1)*len(matrix[0])//partitions) for i in range(partitions)]
    def score(row, groups):
        values = [row[k] for group in groups for k in range(*boundaries[group])]
        sd = stdev(values) if len(values)>1 else 0
        return mean(values)/sd if sd else 0
    failures = []
    for groups in combinations(range(partitions), partitions//2):
        remaining = [i for i in range(partitions) if i not in groups]
        chosen = max(range(len(matrix)),key=lambda i:score(matrix[i],groups))
        scores = [score(row,remaining) for row in matrix]
        rank = sum(value<scores[chosen] for value in scores)/max(1,len(matrix)-1)
        failures.append(rank<0.5)
    return sum(failures)/len(failures)


def test_cscv_keeps_every_observation_when_partitions_do_not_divide_length():
    from vati.backtest.metrics import pbo_cscv
    matrix = [[1.0,-1.0,3.0,1.0,-5.0,-6.0],[-1.0,2.0,-2.0,2.0,7.0,8.0]]
    assert pbo_cscv(matrix,partitions=4) == independent_pbo(matrix,4)


def test_cscv_refuses_ragged_or_nonfinite_trial_rows():
    from vati.backtest.metrics import pbo_cscv
    for matrix in ([[1,2,3,4],[1,2,3]], [[1,2,3,4],[1,2,float("nan"),4]]):
        with pytest.raises(ValueError):
            pbo_cscv(matrix,partitions=4)


@pytest.mark.parametrize("change", [{"dsr_probability":2.0}, {"n_trials":0},
    {"validation_policy_version":"superseded-policy"}])
def test_actual_signed_capsule_promotion_cannot_bypass_statistical_validity(change):
    from test_validation_certificates import _registry, _sig
    from vati.risk import StrategyState
    from vati.strategies.capsule import CapsuleError
    owner, registry = _registry()
    sid = "FX-TREND-PULLBACK-01"
    before = registry.get(sid)
    base = passing_certificate(strategy_id=sid, capsule_hash=before.capsule_hash)
    invalid = replace(base,stats=replace(base.stats,**change)).sealed()
    signature = _sig(owner,sid,"SHADOW",invalid)
    with pytest.raises(CapsuleError, match="validation policy"):
        registry.promote(sid,StrategyState.SHADOW,approval_signature_ref=signature,
            evidence_refs=["controlled-validation-fixture"],approved_at_unix=1,certificate=invalid)
    assert registry.get(sid).capsule_hash == before.capsule_hash


def feature_inputs():
    from vati.validation.certificates import GREEN
    return dict(feature_id="candidate",feature_version="1",baseline_feature_set_hash="base",
        candidate_feature_set_hash="candidate",data_manifest_hash="controlled-fixture",evidence_refs=("fixture:aligned",),
        instruments=("TEST",),regimes=("NORMAL",),timeframes=("H1",),baseline_returns=[.01,-.02,.03,-.01],
        candidate_returns=[.02,-.01,.04,.01],trial_delta_matrix=[[.01,.01,.01,.02],[.02,.005,.02,.01]],
        baseline_feature_series=[[1,2,3,4]],candidate_feature_series=[2,4,1,3],
        walk_forward_baseline=[.01,.02],walk_forward_candidate=[.02,.03],regime_stability={"NORMAL":.01},
        leakage_result=GREEN)


@pytest.mark.parametrize("change", [{"candidate_returns":[.02,-.01,.04]},
    {"candidate_returns":[.02,-.01,.04,float("nan")]}, {"baseline_returns":[.01,-.02,.03,True]},
    {"walk_forward_candidate":[.02]}, {"baseline_feature_series":[[1,2,3]]},
    {"baseline_feature_series":[[1]]}, {"trial_delta_matrix":[[.01,.02,.03,.04],[.01,.02,.03]]}])
def test_actual_feature_producer_refuses_truncation_or_nonfinite_inputs(change):
    from vati.validation.builder import build_feature_validation_certificate
    with pytest.raises(ValueError):
        build_feature_validation_certificate(**(feature_inputs()|change))


def test_actual_feature_producer_retains_a_valid_aligned_control():
    from vati.validation.builder import build_feature_validation_certificate
    assert build_feature_validation_certificate(**feature_inputs()).verify_seal()


@pytest.mark.parametrize("has_edge", [False, True])
def test_actual_producer_and_signed_consumer_distinguish_declared_null_and_positive_controls(has_edge):
    """A controlled statistical oracle, never market or temporal qualification."""
    from test_validation_certificates import _registry, _sig
    from vati.risk import StrategyState
    from vati.strategies.capsule import CapsuleError
    from vati.validation.builder import build_strategy_validation_certificate
    from vati.validation.certificates import GREEN
    owner, registry = _registry()
    sid = "FX-TREND-PULLBACK-01"
    old = registry.get(sid)
    returns = ([D("1"),D("1"),D("1"),D("-1")] if has_edge else
               [D("1"),D("-1"),D("1"),D("-1")])*50
    trials = [[float(r) for r in returns], [float(r)-.1 for r in returns],
              [float(r)-.2 for r in returns], [float(r)-.3 for r in returns]]
    cert = build_strategy_validation_certificate(strategy_id=sid,strategy_version=old.version,
        capsule_hash=old.capsule_hash,data_manifest_hash="fixture:null-and-positive-controls",
        evidence_refs=("fixture:declared-population-not-market-data",),feature_set_version="fixture/1",
        cost_model_revision="fixture-known-net-costs/1",pnls=[r*10 for r in returns],r_multiples=returns,
        start_equity=D("10000"),trial_returns_matrix=trials,walk_forward_windows=4,
        cost_stress_2x=GREEN,latency_slippage_stress=GREEN,parameter_perturbation_stability=GREEN,
        leakage_switch_result=GREEN)
    assert evaluate_strategy_certificate(cert)[0] is has_edge
    signature = _sig(owner,sid,"SHADOW",cert)
    if has_edge:
        result = registry.promote(sid,StrategyState.SHADOW,approval_signature_ref=signature,
            evidence_refs=list(cert.evidence_refs),approved_at_unix=1,certificate=cert)
        assert result.state is StrategyState.SHADOW
    else:
        with pytest.raises(CapsuleError,match="validation policy"):
            registry.promote(sid,StrategyState.SHADOW,approval_signature_ref=signature,
                evidence_refs=list(cert.evidence_refs),approved_at_unix=1,certificate=cert)
        assert registry.get(sid).capsule_hash == old.capsule_hash
