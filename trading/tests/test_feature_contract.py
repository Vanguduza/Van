"""P0-B: required_features is an executable contract (blueprint Rev 1.1 §5.2)."""

from __future__ import annotations

import pytest

from vati.intelligence.feature_contract import (
    FEATURE_CONTRACT_UNSATISFIED,
    FeatureAvailability,
    FeatureContractValidator,
    FeatureRequirement,
    availability_from_context,
    availability_from_feature_vector,
    requirements_from_capsule,
)

V = FeatureContractValidator()


def _av(**kw):
    base = dict(feature_id="atr", present=True, as_of_ms=1_000, timeframe="M15")
    base.update(kw)
    return FeatureAvailability(**base)


def test_satisfied_contract():
    v = V.validate(requirements=[FeatureRequirement("atr")], available={"atr": _av()}, now_ms=1_000)
    assert v.satisfied and v.reasons == ()


def test_missing_feature_is_unsatisfied():
    v = V.validate(requirements=[FeatureRequirement("adx")], available={}, now_ms=1_000)
    assert not v.satisfied and v.missing == ("adx",)


def test_present_but_none_is_unsatisfied():
    """The case the old code silently accepted."""
    v = V.validate(requirements=[FeatureRequirement("atr")],
                   available={"atr": _av(value_is_none=True)}, now_ms=1_000)
    assert not v.satisfied and v.none_valued == ("atr",)


def test_stale_feature_is_unsatisfied():
    v = V.validate(requirements=[FeatureRequirement("atr", max_age_ms=100)],
                   available={"atr": _av(as_of_ms=0)}, now_ms=1_000)
    assert not v.satisfied and v.stale == ("atr",)


def test_wrong_timeframe_is_unsatisfied():
    v = V.validate(requirements=[FeatureRequirement("atr", timeframe="H1")],
                   available={"atr": _av(timeframe="M15")}, now_ms=1_000)
    assert not v.satisfied and v.invalid_timeframe == ("atr",)


def test_wrong_venue_class_is_unsatisfied():
    v = V.validate(requirements=[FeatureRequirement("obv", venue_classes=frozenset({"ZSE_EQUITY"}))],
                   available={"obv": _av(feature_id="obv", venue_class="FX_SPOT")}, now_ms=1_000)
    assert not v.satisfied and v.unsupported_for_venue == ("obv",)


def test_insufficient_history_is_unsatisfied():
    v = V.validate(requirements=[FeatureRequirement("atr", minimum_history=200)],
                   available={"atr": _av(history_bars=50)}, now_ms=1_000)
    assert not v.satisfied and v.insufficient_history == ("atr",)


def test_bad_provenance_is_unsatisfied():
    v = V.validate(requirements=[FeatureRequirement("atr")],
                   available={"atr": _av(provenance_ok=False)}, now_ms=1_000)
    assert not v.satisfied and v.bad_provenance == ("atr",)


def test_degraded_feed_is_unsatisfied():
    v = V.validate(requirements=[FeatureRequirement("atr")],
                   available={"atr": _av(degraded=True)}, now_ms=1_000)
    assert not v.satisfied and v.degraded == ("atr",)


def test_every_failure_is_named_not_just_the_first():
    v = V.validate(
        requirements=[FeatureRequirement("adx"), FeatureRequirement("atr", max_age_ms=10)],
        available={"atr": _av(as_of_ms=0)}, now_ms=1_000)
    assert len(v.reasons) == 2


def test_verdict_is_hashed():
    a = V.validate(requirements=[FeatureRequirement("atr")], available={"atr": _av()}, now_ms=1_000)
    b = V.validate(requirements=[FeatureRequirement("adx")], available={}, now_ms=1_000)
    assert a.verdict_hash and a.verdict_hash != b.verdict_hash


def test_zse_context_features_are_available(zse_snapshot=None):
    """ZSE capsules declare fundamentals that never lived in the price vector."""
    from vati.strategies.base import StrategyContext, ZseSnapshot
    from vati.zse.currency import CurrencyRegime
    from decimal import Decimal
    snap = ZseSnapshot(symbol="DLTA", exchange="ZSE", last_price=Decimal("1"),
                       adv_20d_shares=Decimal("1000"), trading_days_of_20=18,
                       median_spread_pct=Decimal("0.01"), value_score=Decimal("0.7"),
                       days_since_results=10, post_results_drift_pct=None,
                       currency_regime=CurrencyRegime.ANCHORED, round_trip_cost_pct=Decimal("0.02"),
                       liquidity_haircut=Decimal("0.1"))
    ctx = StrategyContext(round_trip_cost_pct=Decimal("0.02"), zse=snap)
    av = availability_from_context(ctx, as_of_ms=1_000)
    # `adv_20d` is the capsule's vocabulary; `adv_20d_shares` is the snapshot's.
    for fid in ("value_score", "adv_20d", "median_spread_pct", "currency_regime"):
        assert fid in av, fid


def test_requirements_read_the_key_nothing_read():
    import json
    with open("trading/strategies/registry/FX-TREND-PULLBACK-01.json") as fh:
        doc = json.load(fh)
    reqs = requirements_from_capsule(doc)
    assert {r.feature_id for r in reqs} == set(doc["required_features"])
