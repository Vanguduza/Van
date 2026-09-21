"""Phase 8: the first research tranche, and the rules that gate it."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.intelligence.feature_registry import (
    default_registry,
    research_tranche,
    volume_tranche,
)
from vati.intelligence.features import adx, dmi, donchian, ema, multi_horizon_roc, ppo, roc
from vati.market_data.bars import Bar


def _bars(values, spread="0.0001"):
    out = []
    for i, v in enumerate(values):
        px = Decimal(str(v))
        out.append(Bar("EURUSD", i * 60_000, (i + 1) * 60_000, px, px + Decimal("0.002"),
                       px - Decimal("0.002"), px, Decimal("10"), 5, Decimal(spread)))
    return out


TREND = _bars([1.10 + 0.001 * i for i in range(120)])
DOWN = _bars([1.22 - 0.001 * i for i in range(120)])
CHOP = _bars([1.10 + 0.002 * ((i % 4) - 1.5) for i in range(120)])


# --- ADX / DMI ------------------------------------------------------------

def test_adx_separates_trend_from_range():
    assert adx(TREND) > adx(CHOP)


def test_adx_is_direction_agnostic():
    """Strength, not direction: a clean downtrend is as strong as a clean uptrend."""
    assert adx(DOWN) > adx(CHOP)


def test_dmi_signs_the_direction():
    up_p, up_m = dmi(TREND)
    dn_p, dn_m = dmi(DOWN)
    assert up_p > up_m and dn_m > dn_p


def test_adx_returns_none_without_enough_history():
    assert adx(TREND[:10]) is None


# --- Donchian -------------------------------------------------------------

def test_donchian_position_is_bounded_and_high_in_an_uptrend():
    hi, lo, pos = donchian(TREND)
    assert Decimal("0") <= pos <= Decimal("1") and pos > Decimal("0.8")
    assert hi > lo


def test_donchian_position_is_low_in_a_downtrend():
    _, _, pos = donchian(DOWN)
    assert pos < Decimal("0.2")


def test_flat_channel_is_the_midpoint_not_a_division_error():
    flat = _bars([1.10] * 40)
    _, _, pos = donchian(flat)
    assert pos == Decimal("0.5")


# --- PPO ------------------------------------------------------------------

def test_ppo_is_positive_in_an_uptrend_and_negative_in_a_downtrend():
    assert ppo([b.close for b in TREND]) > 0
    assert ppo([b.close for b in DOWN]) < 0


def test_ppo_is_comparable_across_price_levels_where_macd_is_not():
    """The reason PPO was chosen over MACD for the tranche."""
    low = [Decimal("1.10") + Decimal("0.001") * i for i in range(120)]
    high = [c * Decimal("1000") for c in low]
    a, b = ppo(low), ppo(high)
    assert abs(a - b) < Decimal("0.0001"), "PPO is scale-free"
    macd_low = ema(low, 12) - ema(low, 26)
    macd_high = ema(high, 12) - ema(high, 26)
    assert abs(macd_high - macd_low) > Decimal("1"), "MACD is not"


# --- ROC ------------------------------------------------------------------

def test_multi_horizon_roc_reports_every_horizon():
    r = multi_horizon_roc([b.close for b in TREND])
    assert set(r) == {"roc_5", "roc_20", "roc_60"}
    assert all(v is not None for v in r.values())


def test_horizons_can_disagree_which_is_the_informative_part():
    """Up this week, down this quarter — one number cannot say that."""
    values = [1.20 - 0.002 * i for i in range(80)] + [1.04 + 0.004 * i for i in range(20)]
    closes = [b.close for b in _bars(values)]
    r = multi_horizon_roc(closes)
    assert r["roc_5"] > 0 and r["roc_60"] < 0


def test_roc_handles_a_zero_base_without_raising():
    assert roc([Decimal("0"), Decimal("1")], 1) is None


# --- gating ---------------------------------------------------------------

def test_every_tranche_feature_requires_a_certificate():
    assert all(d.certificate_required for d in research_tranche())


def test_founding_features_do_not_require_one():
    r = default_registry()
    assert not any(d.certificate_required for d in r.for_venue("FX_SPOT"))


def test_only_one_member_of_each_redundant_pair_is_offered():
    """MACD/PPO and Donchian/Keltner: the rule is admit one, then beat it."""
    ids = {d.feature_id for d in research_tranche()}
    assert "ppo" in ids and "macd" not in ids
    assert "donchian_position" in ids and "keltner_position" not in ids


def test_fx_gets_an_activity_proxy_and_zse_gets_real_volume():
    by_id = {d.feature_id: d for d in volume_tranche()}
    assert by_id["obv"].venue_classes == frozenset({"ZSE_EQUITY", "VFEX"})
    assert by_id["obv"].source_semantics == "EXCHANGE_TRADED_VOLUME"
    fx = by_id["tick_activity_percentile"]
    assert "FX_SPOT" in fx.venue_classes
    assert fx.source_semantics == "BROKER_TICK_ACTIVITY"


def test_no_volume_feature_offers_traded_volume_to_fx():
    for d in volume_tranche():
        if d.source_semantics == "EXCHANGE_TRADED_VOLUME":
            assert not (d.venue_classes & {"FX_SPOT", "CFD", "SYNTHETIC"}), d.feature_id


def test_tranche_features_can_be_registered():
    r = default_registry()
    for d in research_tranche() + volume_tranche():
        r.register(d)
    assert "adx" in r.ids() and "obv" in r.ids()
