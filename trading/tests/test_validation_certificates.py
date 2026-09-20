"""Phase 3: certificates are semantic evidence, not opaque strings."""

from __future__ import annotations

import dataclasses

import pytest

from vati.risk import StrategyState
from vati.strategies.capsule import CapsuleError, CapsuleRegistry
from vati.validation.certificates import (
    FEATURE_PRODUCTION_ADMITTED,
    FEATURE_REJECTED_REDUNDANT,
    FEATURE_REJECTED_UNSTABLE,
    FEATURE_SHADOW_APPROVED,
    GREEN,
    RED,
    FeatureValidationCertificate,
    classify_feature_certificate,
    evaluate_strategy_certificate,
    passing_certificate,
)

REG = "trading/strategies/registry"


# --- strategy certificate -------------------------------------------------

def test_passing_certificate_passes():
    ok, reasons = evaluate_strategy_certificate(passing_certificate(strategy_id="X"))
    assert ok and reasons == ()


def test_tampered_certificate_fails_its_own_seal():
    cert = passing_certificate(strategy_id="X")
    tampered = dataclasses.replace(cert, expectancy_R=99.0)
    ok, reasons = evaluate_strategy_certificate(tampered)
    assert not ok and "certificate_seal_invalid" in reasons


@pytest.mark.parametrize("field", [
    "cost_stress_2x", "latency_slippage_stress",
    "parameter_perturbation_stability", "leakage_switch_result",
])
def test_a_red_stress_result_fails(field):
    cert = dataclasses.replace(passing_certificate(strategy_id="X"), **{field: RED}).sealed()
    ok, reasons = evaluate_strategy_certificate(cert)
    assert not ok and any(r.startswith(field) for r in reasons)


def test_missing_data_manifest_fails():
    cert = dataclasses.replace(passing_certificate(strategy_id="X"), data_manifest_hash="").sealed()
    ok, reasons = evaluate_strategy_certificate(cert)
    assert not ok and "no_data_manifest" in reasons


def test_low_dsr_in_certificate_fails():
    base = passing_certificate(strategy_id="X")
    cert = dataclasses.replace(
        base, stats=dataclasses.replace(base.stats, dsr_probability=0.10)).sealed()
    ok, reasons = evaluate_strategy_certificate(cert)
    assert not ok and any("dsr_probability" in r for r in reasons)


# --- promotion gate -------------------------------------------------------

def _registry():
    from conftest_owner_authority import OwnerAuthorityHarness
    owner = OwnerAuthorityHarness()
    return owner, CapsuleRegistry.load_dir(REG, authority=owner.verifier)


def _sig(owner, sid, state):
    return owner.token(act="capsule-promote", subject=f"{sid}:{state}", issued_at_unix=1)


def test_promotion_to_demo_without_a_certificate_is_refused():
    owner, reg = _registry()
    sid = "FX-TREND-PULLBACK-01"   # already at DEMO in the registry
    with pytest.raises(CapsuleError, match="StrategyValidationCertificate"):
        reg.promote(sid, StrategyState.SHADOW, approval_signature_ref=_sig(owner, sid, "SHADOW"),
                    evidence_refs=["anything", "at", "all"], approved_at_unix=1)


def test_research_states_do_not_require_a_certificate():
    """Below DEMO a capsule is research; the gate starts where trust starts."""
    owner, reg = _registry()
    sid = "FX-EVENT-DRIFT-01"   # RESEARCH in the registry
    c = reg.promote(sid, StrategyState.BACKTEST, approval_signature_ref=_sig(owner, sid, "BACKTEST"),
                    evidence_refs=[], approved_at_unix=1)
    assert c.state is StrategyState.BACKTEST


def test_certificate_for_another_strategy_is_refused():
    owner, reg = _registry()
    sid = "FX-TREND-PULLBACK-01"   # already at DEMO in the registry
    with pytest.raises(CapsuleError, match="certificate is for"):
        reg.promote(sid, StrategyState.SHADOW, approval_signature_ref=_sig(owner, sid, "SHADOW"),
                    evidence_refs=["e"], approved_at_unix=1,
                    certificate=passing_certificate(strategy_id="SOMETHING-ELSE"))


def test_certificate_for_a_different_capsule_revision_is_refused():
    owner, reg = _registry()
    sid = "FX-TREND-PULLBACK-01"   # already at DEMO in the registry
    stale = passing_certificate(strategy_id=sid, capsule_hash="a" * 64)
    with pytest.raises(CapsuleError, match="different capsule revision"):
        reg.promote(sid, StrategyState.SHADOW, approval_signature_ref=_sig(owner, sid, "SHADOW"),
                    evidence_refs=["e"], approved_at_unix=1, certificate=stale)


def test_failing_certificate_is_refused_even_with_a_valid_signature():
    owner, reg = _registry()
    sid = "FX-TREND-PULLBACK-01"   # already at DEMO in the registry
    base = passing_certificate(strategy_id=sid, capsule_hash=reg.get(sid).capsule_hash)
    weak = dataclasses.replace(base, leakage_switch_result=RED).sealed()
    with pytest.raises(CapsuleError, match="validation policy"):
        reg.promote(sid, StrategyState.SHADOW, approval_signature_ref=_sig(owner, sid, "SHADOW"),
                    evidence_refs=["e"], approved_at_unix=1, certificate=weak)


def test_owner_signature_binds_the_validation_hash():
    owner, reg = _registry()
    sid = "FX-TREND-PULLBACK-01"   # already at DEMO in the registry
    cert = passing_certificate(strategy_id=sid, capsule_hash=reg.get(sid).capsule_hash)
    c = reg.promote(sid, StrategyState.SHADOW, approval_signature_ref=_sig(owner, sid, "SHADOW"),
                    evidence_refs=["e"], approved_at_unix=1, certificate=cert)
    assert c.data["validation_hash"] == cert.validation_hash


# --- feature certificate --------------------------------------------------

def _feature_cert(**kw) -> FeatureValidationCertificate:
    base = dict(
        certificate_id="fvc1", feature_id="adx", feature_version="1.0.0",
        baseline_feature_set_hash="base", candidate_feature_set_hash="cand",
        instruments=("EURUSD",), regimes=("BULL", "BEAR"), timeframes=("H1",),
        redundancy_correlation=0.2, incremental_expectancy_delta=0.08,
        incremental_dsr_probability=0.98, incremental_pbo_probability=0.04,
        walk_forward_delta=0.05, leakage_result=GREEN,
        regime_stability={"BULL": 0.1, "BEAR": 0.05},
    )
    base.update(kw)
    return FeatureValidationCertificate(**base).sealed()


def test_a_genuinely_incremental_feature_is_admitted():
    status, reasons = classify_feature_certificate(_feature_cert())
    assert status == FEATURE_PRODUCTION_ADMITTED and reasons == ()


def test_a_redundant_restatement_is_rejected_before_its_value_is_considered():
    """MACD and PPO are the same construction; a positive delta is noise."""
    status, reasons = classify_feature_certificate(
        _feature_cert(redundancy_correlation=0.97, incremental_expectancy_delta=0.5))
    assert status == FEATURE_REJECTED_REDUNDANT


def test_standalone_value_without_incremental_value_is_not_admitted():
    status, _ = classify_feature_certificate(_feature_cert(incremental_expectancy_delta=0.0))
    assert status != FEATURE_PRODUCTION_ADMITTED


def test_low_incremental_dsr_is_not_production_admitted():
    status, reasons = classify_feature_certificate(_feature_cert(incremental_dsr_probability=0.5))
    assert status == FEATURE_SHADOW_APPROVED
    assert any("incremental_dsr_probability" in r for r in reasons)


def test_a_feature_that_hurts_in_one_regime_is_not_admitted():
    status, reasons = classify_feature_certificate(
        _feature_cert(regime_stability={"BULL": 0.2, "RANGE": -0.1}))
    assert status != FEATURE_PRODUCTION_ADMITTED
    assert any("regime_instability" in r for r in reasons)


def test_leakage_red_is_rejected():
    status, _ = classify_feature_certificate(_feature_cert(leakage_result=RED))
    assert status == FEATURE_REJECTED_UNSTABLE


def test_tampered_feature_certificate_is_rejected():
    cert = dataclasses.replace(_feature_cert(), incremental_expectancy_delta=9.0)
    status, reasons = classify_feature_certificate(cert)
    assert status == FEATURE_REJECTED_UNSTABLE and "certificate_seal_invalid" in reasons
