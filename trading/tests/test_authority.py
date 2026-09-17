from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import NOW, intent, mandate_dict, snapshot
from vati.risk import (
    Decision,
    Direction,
    KillSwitchTrigger,
    MarketIntegrityState,
    OpenPosition,
    RiskAuthority,
    StrategyState,
    TradingMandate,
)


def test_reference_approval(mandate, eurusd):
    d = RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd))
    assert d.decision is Decision.APPROVED, d
    assert d.approved_size == Decimal("0.18")
    assert d.approved_risk_pct == Decimal("0.00396")
    assert d.portfolio_heat_after == Decimal("0.00396")
    assert d.decision_hash and d.risk_snapshot_hash


def test_decision_is_deterministic(mandate, eurusd):
    a = RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd))
    b = RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd))
    assert a == b


def test_duplicate_intent_rejected(mandate, eurusd):
    auth = RiskAuthority(mandate)
    assert auth.evaluate(intent(), snapshot(eurusd)).decision is Decision.APPROVED
    d = auth.evaluate(intent(trade_intent_id="ti-2"), snapshot(eurusd))
    assert d.decision is Decision.REJECTED and d.reason_code == "DUPLICATE_INTENT"


def test_rejected_intent_does_not_consume_key(mandate, eurusd):
    auth = RiskAuthority(mandate)
    bad = auth.evaluate(intent(stop=None), snapshot(eurusd))
    assert bad.reason_code == "STOP_REQUIRED"
    assert auth.evaluate(intent(), snapshot(eurusd)).decision is Decision.APPROVED


def test_requested_risk_clamped_to_mandate(mandate, eurusd):
    d = RiskAuthority(mandate).evaluate(intent(requested_risk_pct=Decimal("0.02")), snapshot(eurusd))
    assert d.decision is Decision.REDUCED
    assert "RISK_CLAMPED_TO_MANDATE" in d.constraints
    assert d.approved_risk_pct <= mandate.max_risk_per_trade


@pytest.mark.parametrize(
    "snap_override,code",
    [
        ({"kill_switch_triggers": frozenset({KillSwitchTrigger.OWNER_HALT})}, "KILL_SWITCH"),
        ({"account_verified": False}, "ACCOUNT_UNVERIFIED"),
        ({"account_alias": "other"}, "ACCOUNT_MISMATCH"),
        ({"quote_age_ms": 5000}, "STALE_DATA"),
        ({"quote_age_ms": -1}, "STALE_DATA"),
        ({"broker_connected": False}, "VENUE_DISCONNECTED"),
        ({"reconciliation_ok": False}, "RECONCILIATION_FAILED"),
        ({"clock_sync_ok": False}, "TIME_SYNC_FAULT"),
        ({"risk_store_ok": False}, "RISK_STORE_UNAVAILABLE"),
        ({"market_integrity": MarketIntegrityState.ABNORMAL}, "MARKET_INTEGRITY"),
        ({"market_integrity": MarketIntegrityState.HALTED}, "MARKET_INTEGRITY"),
        ({"tier1_event_blackout_active": True}, "EVENT_BLACKOUT"),
        ({"consecutive_losses": 4}, "CONSECUTIVE_LOSSES"),
        ({"equity": Decimal("9790")}, "MAX_DAILY_LOSS"),
        ({"day_start_equity": Decimal("0")}, "EQUITY_BASELINE_MISSING"),
        ({"equity": Decimal("9500"), "day_start_equity": Decimal("9500"), "peak_equity": Decimal("9500")}, "MAX_WEEKLY_DRAWDOWN"),
        ({"equity": Decimal("9350"), "day_start_equity": Decimal("9350"), "week_start_equity": Decimal("9350")}, "DRAWDOWN_SUSPENDED"),
        ({"now_unix": NOW + 100 * 86400}, "MANDATE_EXPIRED"),
    ],
)
def test_fail_closed_paths(mandate, eurusd, snap_override, code):
    d = RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd, **snap_override))
    assert d.decision is Decision.REJECTED and d.reason_code == code, d
    assert d.approved_size == 0 and d.approved_risk_pct == 0


@pytest.mark.parametrize(
    "intent_override,code",
    [
        ({"symbol": "AUDUSD"}, "INSTRUMENT_NOT_MANDATED"),
        ({"strategy_id": "ROGUE-01"}, "STRATEGY_NOT_MANDATED"),
        ({"strategy_state": StrategyState.SHADOW}, "STRATEGY_STATE_INELIGIBLE"),
        ({"strategy_state": StrategyState.RESEARCH}, "STRATEGY_STATE_INELIGIBLE"),
        ({"owner_authority": "MODEL_OPINION"}, "AUTHORITY_UNKNOWN"),
        ({"holds_over_weekend": True}, "WEEKEND_HOLD_FORBIDDEN"),
        ({"stop": None}, "STOP_REQUIRED"),
        ({"stop": Decimal("1.10005")}, "STOP_TOO_TIGHT"),
        ({"stop": Decimal("1.20000")}, "STOP_WRONG_SIDE"),
        ({"requested_risk_pct": Decimal("0")}, "RISK_NON_POSITIVE"),
        ({"venue": "deriv"}, "VENUE_MISMATCH"),
        ({"account_alias": "other"}, "ACCOUNT_MISMATCH"),
    ],
)
def test_intent_rejections(mandate, eurusd, intent_override, code):
    d = RiskAuthority(mandate).evaluate(intent(**intent_override), snapshot(eurusd))
    assert d.decision is Decision.REJECTED and d.reason_code == code, d


def test_autonomous_mode_requires_certified_live(eurusd):
    m = TradingMandate.from_mapping(mandate_dict(mode="AUTONOMOUS_LIVE"))
    d = RiskAuthority(m).evaluate(intent(strategy_state=StrategyState.LIMITED_LIVE), snapshot(eurusd))
    assert d.reason_code == "STRATEGY_STATE_INELIGIBLE"
    assert RiskAuthority(m).evaluate(intent(), snapshot(eurusd)).decision is Decision.APPROVED


@pytest.mark.parametrize("mode", ["OBSERVE", "ADVISOR", "SHADOW_TRADER", "HALTED"])
def test_non_order_modes_never_approve(eurusd, mode):
    m = TradingMandate.from_mapping(mandate_dict(mode=mode))
    d = RiskAuthority(m).evaluate(intent(strategy_state=StrategyState.CERTIFIED_LIVE), snapshot(eurusd))
    assert d.decision is Decision.REJECTED and d.reason_code == "MODE_NOT_ORDER_SENDING"


def test_event_certified_strategy_may_trade_in_blackout(mandate, eurusd):
    d = RiskAuthority(mandate).evaluate(intent(is_event_certified=True), snapshot(eurusd, tier1_event_blackout_active=True))
    assert d.decision is Decision.APPROVED
    flat = TradingMandate.from_mapping(mandate_dict(tier1_event_policy="flat"))
    d = RiskAuthority(flat).evaluate(intent(is_event_certified=True), snapshot(eurusd, tier1_event_blackout_active=True))
    assert d.reason_code == "EVENT_BLACKOUT"


def test_elevated_market_halves_size(mandate, eurusd):
    d = RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd, market_integrity=MarketIntegrityState.ELEVATED))
    assert d.decision is Decision.REDUCED and d.approved_size == Decimal("0.09")
    assert "MARKET_ELEVATED_HALF_SIZE" in d.constraints


def test_drawdown_tier_reduces_and_restricts(mandate, eurusd):
    snap = snapshot(eurusd, equity=Decimal("9750"), day_start_equity=Decimal("9750"), week_start_equity=Decimal("9750"))
    d = RiskAuthority(mandate).evaluate(intent(), snap)
    assert d.decision is Decision.REDUCED and "DRAWDOWN_TIER_0" in d.constraints
    assert d.approved_size == Decimal("0.13")  # 0.1818 × 0.75 × (9750/10000) → 0.1329 → 0.13
    snap = snapshot(eurusd, equity=Decimal("9550"), day_start_equity=Decimal("9550"), week_start_equity=Decimal("9550"))
    d = RiskAuthority(mandate).evaluate(intent(strategy_state=StrategyState.LIMITED_LIVE), snap)
    assert d.reason_code == "DRAWDOWN_TOP_TIER_ONLY"


def test_portfolio_heat_and_currency_leg(mandate, eurusd):
    vppu = eurusd.value_per_price_unit_per_lot
    # existing USD short exposure via USDJPY short worth 0.7% of equity
    open_pos = (OpenPosition("USDJPY", Direction.SHORT, Decimal("0.35"), Decimal("0.00200"), vppu, "USD", "JPY", "FX-TREND-03"),)
    d = RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd, open_positions=open_pos))
    # new EURUSD long adds ~0.396% USD short → 1.096% > 1.0% leg cap
    assert d.decision is Decision.REJECTED and d.reason_code == "CURRENCY_LEG_EXPOSURE", d
    # opposite direction nets the leg instead
    d = RiskAuthority(mandate).evaluate(intent(direction=Direction.SHORT, stop=Decimal("1.10230")), snapshot(eurusd, open_positions=open_pos))
    assert d.decision is Decision.APPROVED, d


def test_portfolio_heat_cap(mandate, eurusd):
    vppu = eurusd.value_per_price_unit_per_lot
    # three positions each 0.4% on non-USD legs → heat 1.2%; a 0.396% add breaches 1.5%
    open_pos = tuple(
        OpenPosition(s, Direction.LONG, Decimal("0.20"), Decimal("0.00200"), vppu, b, q, "FX-TREND-03")
        for s, b, q in (("EURGBP", "EUR", "GBP"), ("EURCHF", "EUR", "CHF"), ("GBPCHF", "GBP", "CHF"))
    )
    d = RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd, open_positions=open_pos))
    assert d.reason_code == "PORTFOLIO_HEAT", d


def test_unprotected_open_position_blocks_new_risk(mandate, eurusd):
    open_pos = (OpenPosition("GBPUSD", Direction.LONG, Decimal("0.01"), Decimal("0.001"), Decimal("100000"), "GBP", "USD", has_broker_side_stop=False),)
    d = RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd, open_positions=open_pos))
    assert d.reason_code == "UNPROTECTED_POSITION"


def test_position_count_limits(mandate, eurusd):
    vppu = eurusd.value_per_price_unit_per_lot
    same = (OpenPosition("EURUSD", Direction.LONG, Decimal("0.01"), Decimal("0.001"), vppu, "EUR", "USD"),)
    assert RiskAuthority(mandate).evaluate(intent(), snapshot(eurusd, open_positions=same)).reason_code == "MAX_POSITIONS_PER_INSTRUMENT"


def test_deriv_stake_path(deriv_synthetic):
    m = TradingMandate.from_mapping(mandate_dict(venue="deriv", instruments=["R_75"], allowed_strategies=["DERIV-SYN-01"], mode="DEMO_TRADER"))
    it = intent(venue="deriv", symbol="R_75", strategy_id="DERIV-SYN-01", strategy_state=StrategyState.DEMO, stop=None, stake=Decimal("25"))
    d = RiskAuthority(m).evaluate(it, snapshot(deriv_synthetic))
    assert d.decision is Decision.APPROVED and d.approved_size == Decimal("25.00")
    it = intent(venue="deriv", symbol="R_75", strategy_id="DERIV-SYN-01", strategy_state=StrategyState.DEMO, stop=None, stake=Decimal("500"))
    d = RiskAuthority(m).evaluate(it, snapshot(deriv_synthetic))
    assert d.decision is Decision.APPROVED and d.approved_size == Decimal("40.00")  # capped at 0.4% of 10k


def test_evaluate_safe_turns_faults_into_rejections(mandate, eurusd):
    auth = RiskAuthority(mandate)
    broken = intent(stop="not-a-decimal")  # type: ignore[arg-type]
    d = auth.evaluate_safe(broken, snapshot(eurusd))
    assert d.decision is Decision.REJECTED and d.reason_code == "AUTHORITY_FAULT" and d.approved_size == 0
    assert auth.evaluate_safe(intent(), snapshot(eurusd)).decision is Decision.APPROVED
