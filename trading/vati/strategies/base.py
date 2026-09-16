"""Strategy protocol. A strategy proposes; it never sizes, never sends."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Protocol

from vati.intelligence.market_state import MarketState
from vati.risk.contracts import Direction
from vati.zse.currency import CurrencyRegime


@dataclass(frozen=True)
class ZseSnapshot:
    """Fundamental and liquidity context for a ZSE/VFEX counter (end-of-day)."""
    symbol: str
    exchange: str
    last_price: Decimal
    adv_20d_shares: Decimal
    trading_days_of_20: int
    median_spread_pct: Decimal
    value_score: Decimal            # 0..1 composite from USD-IFRS screen (higher = cheaper/better quality)
    days_since_results: Optional[int]
    post_results_drift_pct: Optional[Decimal]
    currency_regime: CurrencyRegime
    round_trip_cost_pct: Decimal
    liquidity_haircut: Decimal
    board_lot: Decimal = Decimal("100")
    dividend_yield_after_wht: Decimal = Decimal("0")


@dataclass(frozen=True)
class StrategyContext:
    """Everything a strategy may look at beyond MarketState. All optional so a
    strategy that needs a missing input returns None (no signal)."""
    round_trip_cost_pct: Decimal
    event_release_ref_price: Optional[Decimal] = None   # price at the event release, for drift strategies
    zse: Optional[ZseSnapshot] = None


@dataclass(frozen=True)
class Signal:
    strategy_id: str
    strategy_version: str
    symbol: str
    direction: Direction
    entry: Decimal
    stop: Decimal
    targets: tuple[Decimal, ...]
    expected_gross_move_pct: Decimal
    horizon: str                       # SCALP | INTRADAY | SESSION | OVERNIGHT | SWING | POSITION
    rationale: str
    entry_type: str = "LIMIT"          # LIMIT | STOP | MARKET | PASSIVE_LIMIT
    event_certified: bool = False
    holds_over_weekend: bool = False
    stake: Optional[Decimal] = None
    confidence_hint: Decimal = Decimal("1")   # strategy's own view, clamped downstream

    @property
    def stop_fraction(self) -> Decimal:
        return abs(self.entry - self.stop) / self.entry


class Strategy(Protocol):
    strategy_id: str
    version: str

    def evaluate(self, state: MarketState, ctx: StrategyContext) -> Optional[Signal]: ...
