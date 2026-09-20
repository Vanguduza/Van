"""TRD-ENH-012/014: venue-aware registry and functional confluence."""

from __future__ import annotations

import pytest

from vati.intelligence.confluence import (
    AXES,
    NEUTRAL,
    OPPOSING,
    SUPPORTIVE,
    UNKNOWN,
    ConfluenceAxis,
    ConfluenceEngine,
)
from vati.intelligence.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureRegistryError,
    default_registry,
    research_tranche,
)
from vati.validation.certificates import GREEN, FeatureValidationCertificate


# --- registry -------------------------------------------------------------

def test_fx_cannot_claim_exchange_traded_volume():
    """Spot FX is decentralised OTC; no consolidated traded volume exists."""
    with pytest.raises(FeatureRegistryError, match="EXCHANGE_TRADED_VOLUME"):
        FeatureDefinition(
            feature_id="obv", version="1.0.0", family="VOLUME_ACTIVITY",
            required_inputs=("volume",), venue_classes=frozenset({"FX_SPOT"}),
            allowed_timeframes=frozenset({"H1"}), minimum_history=20,
            source_semantics="EXCHANGE_TRADED_VOLUME", implementation_ref="x")


def test_fx_volume_activity_is_allowed_with_an_honest_semantic():
    d = FeatureDefinition(
        feature_id="tick_activity", version="1.0.0", family="VOLUME_ACTIVITY",
        required_inputs=("ticks",), venue_classes=frozenset({"FX_SPOT"}),
        allowed_timeframes=frozenset({"H1"}), minimum_history=20,
        source_semantics="BROKER_TICK_ACTIVITY", implementation_ref="x")
    assert d.source_semantics == "BROKER_TICK_ACTIVITY"


def test_zse_may_claim_exchange_traded_volume():
    d = FeatureDefinition(
        feature_id="adv_20d", version="1.0.0", family="LIQUIDITY",
        required_inputs=("fundamentals",), venue_classes=frozenset({"ZSE_EQUITY"}),
        allowed_timeframes=frozenset({"D1"}), minimum_history=1,
        source_semantics="EXCHANGE_TRADED_VOLUME", implementation_ref="x")
    assert d.applies_to("ZSE_EQUITY") and not d.applies_to("FX_SPOT")


def test_unknown_family_and_venue_are_refused():
    with pytest.raises(FeatureRegistryError, match="family"):
        FeatureDefinition("x", "1.0.0", "VIBES", (), frozenset({"FX_SPOT"}),
                          frozenset({"H1"}), 1, "PRICE_OHLC", "r")
    with pytest.raises(FeatureRegistryError, match="venue class"):
        FeatureDefinition("x", "1.0.0", "TREND", (), frozenset({"MOON"}),
                          frozenset({"H1"}), 1, "PRICE_OHLC", "r")


def test_redefinition_at_the_same_version_is_refused():
    r = FeatureRegistry()
    a = FeatureDefinition("atr", "1.0.0", "VOLATILITY", ("ohlc",), frozenset({"FX_SPOT"}),
                          frozenset({"H1"}), 15, "PRICE_OHLC", "r")
    r.register(a)
    r.register(a)  # identical is fine
    with pytest.raises(FeatureRegistryError, match="bump the version"):
        r.register(FeatureDefinition("atr", "1.0.0", "VOLATILITY", ("ohlc",), frozenset({"FX_SPOT"}),
                                     frozenset({"H1"}), 99, "PRICE_OHLC", "r"))


def test_default_registry_declares_what_compute_features_produces():
    from vati.intelligence.features import FeatureVector
    r = default_registry()
    skip = {"symbol", "as_of_ms", "complete", "history_bars", "feature_version", "timeframe"}
    produced = {f for f in FeatureVector.__dataclass_fields__ if f not in skip}
    assert produced <= set(r.ids()), sorted(produced - set(r.ids()))


def test_zse_fundamentals_are_not_offered_to_fx():
    r = default_registry()
    fx = {d.feature_id for d in r.for_venue("FX_SPOT")}
    assert "value_score" not in fx and "adv_20d" not in fx


def test_founding_features_need_no_certificate_but_new_ones_do():
    r = default_registry()
    assert r.require("atr").certificate_required is False
    new = FeatureDefinition("adx", "1.0.0", "TREND", ("ohlc",), frozenset({"FX_SPOT"}),
                            frozenset({"H1"}), 30, "PRICE_OHLC", "r")
    assert new.certificate_required is True


def test_research_feature_definition_is_not_production_admission():
    r = default_registry()
    adx = next(d for d in research_tranche() if d.feature_id == "adx")
    r.register(adx)
    assert r.require("adx") == adx
    assert not r.is_production_admitted("adx")


def test_feature_certificate_is_the_only_path_to_production_admission():
    r = default_registry()
    adx = next(d for d in research_tranche() if d.feature_id == "adx")
    cert = FeatureValidationCertificate(
        certificate_id="fvc-adx",
        feature_id="adx",
        feature_version="1.0.0",
        baseline_feature_set_hash="baseline",
        candidate_feature_set_hash="candidate",
        instruments=("EURUSD", "GBPUSD"),
        regimes=("BULL", "BEAR"),
        timeframes=("H1",),
        redundancy_correlation=0.2,
        incremental_expectancy_delta=0.08,
        incremental_dsr_probability=0.98,
        incremental_pbo_probability=0.04,
        walk_forward_delta=0.05,
        regime_stability={"BULL": 0.1, "BEAR": 0.05},
        leakage_result=GREEN,
    ).sealed()
    admission_hash = r.admit(adx, cert)
    assert admission_hash == cert.certificate_hash
    assert r.is_production_admitted("adx")


# --- confluence -----------------------------------------------------------

def test_confluence_has_no_decision_method():
    """The point of the module: it reports, it does not decide."""
    from vati.intelligence import confluence
    for name in ("buy", "sell", "size", "execute", "approve", "signal"):
        assert not hasattr(confluence.ConfluenceState, name)
        assert not hasattr(confluence.ConfluenceEngine, name)


def test_colinear_evidence_collapses_into_one_axis():
    """Five trend measures are one trend axis, not five votes."""
    e = ConfluenceEngine()
    s = e.build(symbol="EURUSD", as_of_ms=1, axes=[
        ConfluenceAxis("trend", SUPPORTIVE, ("ema_slope",)),
        ConfluenceAxis("trend", SUPPORTIVE, ("macd",)),
        ConfluenceAxis("trend", SUPPORTIVE, ("ppo",)),
    ])
    assert len(s.axes) == 1
    assert s.axis("trend").evidence_refs == ("ema_slope", "macd", "ppo")


def test_disagreement_within_an_axis_is_recorded_not_averaged_away():
    e = ConfluenceEngine()
    s = e.build(symbol="EURUSD", as_of_ms=1, axes=[
        ConfluenceAxis("momentum", SUPPORTIVE, ("rsi:H1",)),
        ConfluenceAxis("momentum", OPPOSING, ("rsi:M15",)),
    ])
    assert s.axis("momentum").state == NEUTRAL
    assert set(s.axis("momentum").disagreement_refs) == {"rsi:H1", "rsi:M15"}
    assert s.disagreeing_axes == ("momentum",)


def test_absent_axis_is_unknown_not_neutral():
    """No evidence is not balanced evidence."""
    s = ConfluenceEngine().build(symbol="EURUSD", as_of_ms=1,
                                 axes=[ConfluenceAxis("trend", SUPPORTIVE, ("x",))])
    assert s.axis("cross_asset").state == UNKNOWN


def test_narration_comes_from_stored_evidence():
    s = ConfluenceEngine().build(symbol="EURUSD", as_of_ms=1, axes=[
        ConfluenceAxis("trend", SUPPORTIVE, ("adx:H1",), timeframe="H1"),
        ConfluenceAxis("structure", OPPOSING, ("h4_resistance",), timeframe="H4"),
    ])
    lines = s.narrate()
    assert "trend on H1: supportive" in lines
    assert "structure on H4: opposing" in lines


def test_unknown_axis_or_state_is_refused():
    e = ConfluenceEngine()
    with pytest.raises(ValueError, match="axis"):
        e.build(symbol="X", as_of_ms=1, axes=[ConfluenceAxis("vibes", SUPPORTIVE)])
    with pytest.raises(ValueError, match="state"):
        e.build(symbol="X", as_of_ms=1, axes=[ConfluenceAxis("trend", "BULLISH")])


def test_confluence_state_is_hashed_and_order_independent():
    e = ConfluenceEngine()
    a = e.build(symbol="X", as_of_ms=1, axes=[ConfluenceAxis("trend", SUPPORTIVE, ("a",)),
                                              ConfluenceAxis("event", NEUTRAL, ("b",))])
    b = e.build(symbol="X", as_of_ms=1, axes=[ConfluenceAxis("event", NEUTRAL, ("b",)),
                                              ConfluenceAxis("trend", SUPPORTIVE, ("a",))])
    assert a.state_hash == b.state_hash and a.state_hash
