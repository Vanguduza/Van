from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import mandate_dict, intent, snapshot
from vati.risk import Decision, Direction, LossModel, Multipliers, OpenPosition, RiskAuthority, SizingRejected, StrategyState, SymbolContract, TradingMandate, position_risk, size_illiquid_equity
from vati.zse import (
    CurrencyRegime, FactState, LiquidityProfile, VFEX_EQUITY_COSTS, VFEX_SPEC, ZSE_EQUITY_COSTS, ZSE_SPEC,
    breakeven_move, classify_currency_regime, liquidity_haircut, participation_cap, round_trip, usd_equivalent,
)
from vati.zse.currency import RateSnapshot


# ---------------------------------------------------------------- market facts
def test_zse_spec_blocks_live_until_conflicting_facts_verified():
    blockers = ZSE_SPEC.live_blockers()
    assert "session_open" in blockers and "session_close" in blockers and "stop_orders_supported" in blockers
    with pytest.raises(RuntimeError, match="unverified facts"):
        ZSE_SPEC.assert_live_ready()
    assert ZSE_SPEC.session_open.state is FactState.CONFLICTING
    assert len(ZSE_SPEC.session_open.sources) >= 3


def test_vfex_spec_is_mostly_unverified_and_says_so():
    assert VFEX_SPEC.currency.value == "USD"
    assert len(VFEX_SPEC.live_blockers()) >= 6


# ---------------------------------------------------------------------- costs
def test_zse_buy_side_matches_published_schedule():
    assert ZSE_EQUITY_COSTS.buy_pct() == Decimal("0.01693")


def test_zse_round_trip_is_punitive_for_short_holds():
    short = round_trip(ZSE_EQUITY_COSTS, holding_days=30)
    long = round_trip(ZSE_EQUITY_COSTS, holding_days=300)
    assert short.sell_pct == Decimal("0.05443")   # common 1.443% + 4% CGWT
    assert long.sell_pct == Decimal("0.02943")    # common 1.443% + 1.5% CGWT
    assert short.round_trip_pct > Decimal("0.07")
    assert breakeven_move(ZSE_EQUITY_COSTS, 30) > Decimal("0.075")
    assert breakeven_move(ZSE_EQUITY_COSTS, 300) < breakeven_move(ZSE_EQUITY_COSTS, 30)


def test_vfex_has_no_cgwt_and_lower_foreign_dividend_wht():
    assert round_trip(VFEX_EQUITY_COSTS, 1).sell_pct == VFEX_EQUITY_COSTS.common
    assert VFEX_EQUITY_COSTS.dividend_wht_non_resident == Decimal("0.05")


# ------------------------------------------------------------------- currency
@pytest.mark.parametrize("official,parallel,move,regime", [
    ("26.66", "27.5", "0", CurrencyRegime.ANCHORED),
    ("26.66", "32", "0", CurrencyRegime.ELEVATED),      # ~20% premium (Aug 2026 evidence)
    ("13.9987", "32", "0", CurrencyRegime.DISORDERLY),  # Sep 2024 pre-devaluation ≈ 128%
    ("24.8831", "32", "0", CurrencyRegime.ELEVATED),    # post-devaluation ≈ 29%
    ("24.8831", "32", "0.77", CurrencyRegime.DISORDERLY),  # the devaluation day itself
    ("26", "45", "0", CurrencyRegime.STRESSED),          # Jan 2025 reported parallel 45
])
def test_currency_regimes(official, parallel, move, regime):
    assert classify_currency_regime(RateSnapshot(Decimal(official), Decimal(parallel), Decimal(move))) is regime


def test_usd_equivalent_reports_both_rates_and_conservative():
    v = usd_equivalent(Decimal("26660"), RateSnapshot(Decimal("26.66"), Decimal("32")))
    assert v["usd_at_official"] == Decimal("1000")
    assert v["usd_conservative"] == v["usd_at_parallel"]


# ------------------------------------------------------------------ liquidity
def test_liquidity_haircut_grows_with_thinness_and_floors_at_band():
    liquid = LiquidityProfile(Decimal("500000"), Decimal("1000000"), 20, Decimal("0.01"), Decimal("0.15"))
    thin = LiquidityProfile(Decimal("2000"), Decimal("5000"), 6, Decimal("0.06"), Decimal("0.15"))
    assert liquidity_haircut(liquid) == Decimal("0.005")
    assert liquidity_haircut(thin) == Decimal("0.15")
    assert not liquidity_haircut(LiquidityProfile(Decimal("0"), Decimal("0"), 0, Decimal("0"), Decimal("0.15"))).is_finite()
    assert participation_cap(liquid, Decimal("100")) == Decimal("50000")
    assert participation_cap(thin, Decimal("100")) == Decimal("200")


# ---------------------------------------------------------- risk integration
def zse_contract(**over) -> SymbolContract:
    base = dict(
        symbol="DELTA", venue="zse", base_currency="DELTA", quote_currency="ZiG", account_currency="ZiG",
        contract_size=Decimal("1"), tick_size=Decimal("0.01"), tick_value=Decimal("0.01"),
        volume_min=Decimal("100"), volume_step=Decimal("100"), volume_max=Decimal("10000000"),
        min_stop_distance=Decimal("0"), trade_mode="LONG_ONLY", loss_model=LossModel.ILLIQUID_EQUITY,
        board_lot=Decimal("100"), adv_20d=Decimal("120000"), max_adv_participation=Decimal("0.10"),
        liquidity_haircut=Decimal("0.03"), round_trip_cost_pct=Decimal("0.0714"),
    )
    base.update(over)
    return SymbolContract(**base)


def test_illiquid_equity_sizing_reference():
    # equity 1,000,000 ZiG, 0.5% risk = 5,000; entry 25.00, stop 22.50 (10%) + 3% haircut → 3.25/share → 1538 → 1500 shares
    r = size_illiquid_equity(equity=Decimal("1000000"), allowed_risk_pct=Decimal("0.005"), entry=Decimal("25.00"), stop=Decimal("22.50"),
                             contract=zse_contract(), multipliers=Multipliers())
    assert r.size == Decimal("1500") and r.risk_amount == Decimal("4875.00")


def test_illiquid_equity_adv_cap_and_board_lot():
    r = size_illiquid_equity(equity=Decimal("100000000"), allowed_risk_pct=Decimal("0.005"), entry=Decimal("25"), stop=Decimal("22.5"),
                             contract=zse_contract(adv_20d=Decimal("12345")), multipliers=Multipliers())
    assert r.size == Decimal("1200")  # 10% of ADV rounded down to board lot
    with pytest.raises(SizingRejected) as exc:
        size_illiquid_equity(equity=Decimal("1000"), allowed_risk_pct=Decimal("0.005"), entry=Decimal("25"), stop=Decimal("22.5"),
                             contract=zse_contract(), multipliers=Multipliers())
    assert exc.value.code == "SIZE_BELOW_VENUE_MIN"
    with pytest.raises(SizingRejected) as exc:
        size_illiquid_equity(equity=Decimal("1000000"), allowed_risk_pct=Decimal("0.005"), entry=Decimal("25"), stop=Decimal("22.5"),
                             contract=zse_contract(adv_20d=Decimal("0")), multipliers=Multipliers())
    assert exc.value.code == "ADV_UNKNOWN"


def zse_mandate():
    return TradingMandate.from_mapping(mandate_dict(venue="zse", instruments=["DELTA", "CBZ"], allowed_strategies=["ZSE-VALUE-01"],
                                                    mode="LIMITED_LIVE", weekend_hold_allowed=True, max_currency_leg_exposure="0.04",
                                                    max_open_stop_risk="0.02", max_risk_per_trade="0.01"))


def zse_intent(**over):
    base = dict(venue="zse", symbol="DELTA", strategy_id="ZSE-VALUE-01", strategy_state=StrategyState.CERTIFIED_LIVE,
                entry=Decimal("25.00"), stop=Decimal("22.50"), requested_risk_pct=Decimal("0.005"), holds_over_weekend=True,
                expected_gross_move_pct=Decimal("0.20"))
    base.update(over)
    return intent(**base)


def test_authority_approves_zse_long_and_tracks_haircut_in_heat():
    snap = snapshot(zse_contract(), account_alias="fx_primary", equity=Decimal("1000000"), balance=Decimal("1000000"), peak_equity=Decimal("1000000"),
                    day_start_equity=Decimal("1000000"), week_start_equity=Decimal("1000000"))
    d = RiskAuthority(zse_mandate()).evaluate(zse_intent(), snap)
    assert d.decision is Decision.APPROVED, d
    assert d.approved_size == Decimal("1500") and d.portfolio_heat_after == Decimal("0.004875")


def test_authority_rejects_zse_short_and_edge_below_cost():
    snap = snapshot(zse_contract(), equity=Decimal("1000000"), balance=Decimal("1000000"), peak_equity=Decimal("1000000"),
                    day_start_equity=Decimal("1000000"), week_start_equity=Decimal("1000000"))
    d = RiskAuthority(zse_mandate()).evaluate(zse_intent(direction=Direction.SHORT, stop=Decimal("27.5")), snap)
    assert d.reason_code == "SYMBOL_TRADE_MODE"
    d = RiskAuthority(zse_mandate()).evaluate(zse_intent(expected_gross_move_pct=Decimal("0.05")), snap)
    assert d.reason_code == "EDGE_BELOW_COST"  # 5% expected < 2 × 7.14% round trip


def test_open_illiquid_position_counts_haircut_not_infinity():
    p = OpenPosition("CBZ", Direction.LONG, Decimal("1000"), Decimal("2.5"), Decimal("1"), "CBZ", "ZiG", has_broker_side_stop=False,
                     loss_model=LossModel.ILLIQUID_EQUITY, liquidity_haircut_per_unit=Decimal("0.75"))
    assert position_risk(p) == Decimal("3250")
    unprotected_fx = OpenPosition("EURUSD", Direction.LONG, Decimal("1"), Decimal("0.001"), Decimal("100000"), "EUR", "USD", has_broker_side_stop=False)
    assert not position_risk(unprotected_fx).is_finite()
