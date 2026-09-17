from __future__ import annotations

from decimal import Decimal

import pytest

from vati.risk import (
    AuthorizationMode,
    Direction,
    HARD_FORBIDDEN_BEHAVIOURS,
    LossModel,
    MarketIntegrityState,
    RiskSnapshot,
    StrategyState,
    SymbolContract,
    TradeIntent,
    TradingMandate,
)

NOW = 1_800_000_000


def mandate_dict(**overrides):
    base = {
        "mandate_id": "mandate-fx-primary",
        "version": "1.0.0",
        "account_alias": "fx_primary",
        "venue": "mt5",
        "mode": "LIMITED_LIVE",
        "instruments": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
        "allowed_strategies": ["FX-TREND-03", "FX-LONDON-BREAKOUT-04", "GOLD-NY-RECLAIM-04"],
        "max_risk_per_trade": "0.0050",
        "max_open_stop_risk": "0.0150",
        "max_daily_loss": "0.0200",
        "max_weekly_drawdown": "0.0400",
        "max_currency_leg_exposure": "0.0100",
        "max_consecutive_losses": 4,
        "max_positions_per_instrument": 1,
        "max_total_positions": 4,
        "tier1_event_policy": "strategy_specific",
        "weekend_hold_allowed": False,
        "forbidden": sorted(HARD_FORBIDDEN_BEHAVIOURS),
        "owner_signature_ref": "sig:owner-device:abc123",
        "signed_at_unix": NOW - 3600,
        "expires_at_unix": NOW + 30 * 86400,
    }
    base.update(overrides)
    return base


@pytest.fixture
def mandate() -> TradingMandate:
    return TradingMandate.from_mapping(mandate_dict())


@pytest.fixture
def eurusd() -> SymbolContract:
    # 1 standard lot EURUSD: tick 0.00001 worth 1.00 USD → 100,000 USD per price unit per lot
    return SymbolContract(
        symbol="EURUSD", venue="mt5", base_currency="EUR", quote_currency="USD", account_currency="USD",
        contract_size=Decimal("100000"), tick_size=Decimal("0.00001"), tick_value=Decimal("1.00"),
        volume_min=Decimal("0.01"), volume_step=Decimal("0.01"), volume_max=Decimal("100"),
        min_stop_distance=Decimal("0.00030"),
    )


@pytest.fixture
def deriv_synthetic() -> SymbolContract:
    return SymbolContract(
        symbol="R_75", venue="deriv", base_currency="R_75", quote_currency="USD", account_currency="USD",
        contract_size=Decimal("1"), tick_size=Decimal("0.01"), tick_value=Decimal("0.01"),
        volume_min=Decimal("0.35"), volume_step=Decimal("0.01"), volume_max=Decimal("50000"),
        min_stop_distance=Decimal("0"), loss_model=LossModel.FULL_STAKE, max_stake=Decimal("1000"),
        is_synthetic=True,
    )


def snapshot(contract: SymbolContract, **overrides) -> RiskSnapshot:
    base = dict(
        now_unix=NOW,
        account_alias="fx_primary",
        account_verified=True,
        equity=Decimal("10000"),
        balance=Decimal("10000"),
        peak_equity=Decimal("10000"),
        day_start_equity=Decimal("10000"),
        week_start_equity=Decimal("10000"),
        consecutive_losses=0,
        open_positions=(),
        symbol_contract=contract,
        quote_age_ms=120,
        max_quote_age_ms=1500,
        broker_connected=True,
        reconciliation_ok=True,
        clock_sync_ok=True,
        risk_store_ok=True,
        market_integrity=MarketIntegrityState.NORMAL,
        tier1_event_blackout_active=False,
    )
    base.update(overrides)
    return RiskSnapshot(**base)


def intent(**overrides) -> TradeIntent:
    base = dict(
        trade_intent_id="ti-1",
        idempotency_key="idem-1",
        account_alias="fx_primary",
        venue="mt5",
        symbol="EURUSD",
        direction=Direction.LONG,
        strategy_id="FX-LONDON-BREAKOUT-04",
        strategy_version="4.2.1",
        strategy_state=StrategyState.CERTIFIED_LIVE,
        entry=Decimal("1.10010"),
        stop=Decimal("1.09790"),
        requested_risk_pct=Decimal("0.0040"),
        decision_hash="dh",
        market_snapshot_hash="msh",
    )
    base.update(overrides)
    return TradeIntent(**base)
