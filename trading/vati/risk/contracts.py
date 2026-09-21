"""Typed inputs to the Risk Authority (Rev 2 §27, §29, §41)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class LossModel(str, Enum):
    """How the maximum loss of a position is defined.

    STOP_DISTANCE — loss bounded by a broker-side protective stop (MT5 FX/CFD).
    FULL_STAKE    — loss bounded by the stake (Deriv fixed-payout / multipliers
                    with built-in stop-out). Sizing is stake-based, not lot-based.
    """

    STOP_DISTANCE = "STOP_DISTANCE"
    FULL_STAKE = "FULL_STAKE"
    # ILLIQUID_EQUITY — order-driven exchange with no broker-side stop orders
    # (Zimbabwe Stock Exchange / VFEX). Exit is software-managed; maximum loss is
    # stop fraction PLUS a liquidity haircut for gap-through and impact, sized in
    # board lots and capped by average daily volume participation (Rev 3 Part D).
    ILLIQUID_EQUITY = "ILLIQUID_EQUITY"


class StrategyState(str, Enum):
    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    VALIDATION = "VALIDATION"
    DEMO = "DEMO"
    SHADOW = "SHADOW"
    LIMITED_LIVE = "LIMITED_LIVE"
    CERTIFIED_LIVE = "CERTIFIED_LIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class MarketIntegrityState(str, Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    ABNORMAL = "ABNORMAL"
    HALTED = "HALTED"


class KillSwitchTrigger(str, Enum):
    MAX_DAILY_LOSS = "MAX_DAILY_LOSS"
    MAX_WEEKLY_DRAWDOWN = "MAX_WEEKLY_DRAWDOWN"
    EQUITY_DRAWDOWN = "EQUITY_DRAWDOWN"
    STALE_DATA = "STALE_DATA"
    RECONCILIATION_FAILURE = "RECONCILIATION_FAILURE"
    ABNORMAL_SPREAD = "ABNORMAL_SPREAD"
    REJECT_STORM = "REJECT_STORM"
    DUPLICATE_ORDER_RISK = "DUPLICATE_ORDER_RISK"
    TIME_SYNC_FAULT = "TIME_SYNC_FAULT"
    CORRUPT_STATE = "CORRUPT_STATE"
    UNAUTHORIZED_ACCOUNT = "UNAUTHORIZED_ACCOUNT"
    VENUE_DISCONNECT = "VENUE_DISCONNECT"
    RISK_STORE_UNAVAILABLE = "RISK_STORE_UNAVAILABLE"
    OWNER_HALT = "OWNER_HALT"
    STOP_REJECTED = "STOP_REJECTED"


@dataclass(frozen=True)
class SymbolContract:
    """Venue-truth symbol specification. Every field comes from the venue's
    symbol info at sync time; none may be assumed (Rev 2 §5.2)."""

    symbol: str
    venue: str
    base_currency: str
    quote_currency: str
    account_currency: str
    contract_size: Decimal
    tick_size: Decimal
    tick_value: Decimal  # account currency per lot per tick
    volume_min: Decimal
    volume_step: Decimal
    volume_max: Decimal
    min_stop_distance: Decimal  # price units (stops_level + spread already applied by adapter)
    trade_mode: str = "FULL"  # FULL | LONG_ONLY | SHORT_ONLY | CLOSE_ONLY | DISABLED
    loss_model: LossModel = LossModel.STOP_DISTANCE
    max_stake: Optional[Decimal] = None  # FULL_STAKE contracts only
    is_synthetic: bool = False
    # ILLIQUID_EQUITY only
    board_lot: Decimal = Decimal("1")
    adv_20d: Decimal = Decimal("0")  # average daily volume, shares, trailing 20 sessions
    max_adv_participation: Decimal = Decimal("0.10")  # fraction of ADV one order may take
    liquidity_haircut: Decimal = Decimal("0")  # fraction of price added to the stop as gap/impact loss
    round_trip_cost_pct: Decimal = Decimal("0")  # all-in buy+sell cost as fraction of notional

    @property
    def value_per_price_unit_per_lot(self) -> Decimal:
        return self.tick_value / self.tick_size

    def allows(self, direction: Direction) -> bool:
        if self.trade_mode == "FULL":
            return True
        if self.trade_mode == "LONG_ONLY":
            return direction is Direction.LONG
        if self.trade_mode == "SHORT_ONLY":
            return direction is Direction.SHORT
        return False


@dataclass(frozen=True)
class OpenPosition:
    symbol: str
    direction: Direction
    lots: Decimal
    stop_distance: Decimal  # price units between current protective stop and entry
    value_per_price_unit_per_lot: Decimal
    base_currency: str
    quote_currency: str
    strategy_id: str = ""
    has_broker_side_stop: bool = True
    loss_model: LossModel = LossModel.STOP_DISTANCE
    stake: Decimal = Decimal("0")
    liquidity_haircut_per_unit: Decimal = Decimal("0")  # ILLIQUID_EQUITY: price × haircut, per share


@dataclass(frozen=True)
class TradeIntent:
    trade_intent_id: str
    idempotency_key: str
    account_alias: str
    venue: str
    symbol: str
    direction: Direction
    strategy_id: str
    strategy_version: str
    strategy_state: StrategyState
    entry: Decimal
    stop: Optional[Decimal]
    requested_risk_pct: Decimal
    decision_hash: str
    market_snapshot_hash: str
    owner_authority: str = "MANDATE"
    is_event_certified: bool = False
    holds_over_weekend: bool = False
    stake: Optional[Decimal] = None  # FULL_STAKE contracts
    expected_gross_move_pct: Optional[Decimal] = None  # optional: strategy's expected favourable move as fraction of entry
    # Bounded multipliers proposed by upstream intelligence; the authority clamps them.
    regime_multiplier: Decimal = Decimal("1")
    confidence_multiplier: Decimal = Decimal("1")
    volatility_multiplier: Decimal = Decimal("1")
    liquidity_multiplier: Decimal = Decimal("1")
    event_risk_multiplier: Decimal = Decimal("1")
    correlation_multiplier: Decimal = Decimal("1")


@dataclass(frozen=True)
class RiskSnapshot:
    """Everything the authority needs, captured at decision time. Any field the
    caller cannot prove must be supplied as its fail-closed value."""

    now_unix: int
    account_alias: str
    account_verified: bool
    equity: Decimal
    balance: Decimal
    peak_equity: Decimal
    day_start_equity: Decimal
    week_start_equity: Decimal
    consecutive_losses: int
    open_positions: tuple[OpenPosition, ...]
    symbol_contract: SymbolContract
    quote_age_ms: int
    max_quote_age_ms: int
    broker_connected: bool
    reconciliation_ok: bool
    clock_sync_ok: bool
    risk_store_ok: bool
    market_integrity: MarketIntegrityState
    tier1_event_blackout_active: bool
    kill_switch_triggers: frozenset[KillSwitchTrigger] = frozenset()
    #: P0-TRADE-006 — broker margin, which the authority could not see at all. None means
    #: the venue did not report it, which the margin gate treats as unknown rather than as
    #: healthy; a paper or owner-ticket venue has no margin and legitimately reports None.
    margin_level_pct: Optional[Decimal] = None
    free_margin: Optional[Decimal] = None

    @property
    def data_fresh(self) -> bool:
        return 0 <= self.quote_age_ms <= self.max_quote_age_ms
