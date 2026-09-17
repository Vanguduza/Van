"""ZSE liquidity-premium provision (Rev 3 D.5 #3): patient bid-side GTC limit
below last when the counter is thin and spreads wide. Never chases."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from vati.intelligence.market_state import MarketState
from vati.risk.contracts import Direction
from vati.strategies.base import Signal, StrategyContext
from vati.zse.currency import CurrencyRegime


class ZseLiquidityProvision:
    def __init__(self, strategy_id: str = "ZSE-LIQUIDITY-PROVISION-01", version: str = "1.0.0", *, min_spread_pct: Decimal = Decimal("0.04"),
                 discount_of_spread: Decimal = Decimal("0.75"), stop_fraction: Decimal = Decimal("0.15")) -> None:
        self.strategy_id, self.version = strategy_id, version
        self.min_spread_pct, self.discount, self.stop_fraction = min_spread_pct, discount_of_spread, stop_fraction

    def evaluate(self, state: MarketState, ctx: StrategyContext) -> Optional[Signal]:
        z = ctx.zse
        if z is None or z.currency_regime in (CurrencyRegime.STRESSED, CurrencyRegime.DISORDERLY):
            return None
        if z.median_spread_pct < self.min_spread_pct or z.value_score < Decimal("0.5") or z.trading_days_of_20 < 8:
            return None
        entry = z.last_price * (Decimal(1) - z.median_spread_pct * self.discount)
        stop = entry * (Decimal(1) - self.stop_fraction)
        target = z.last_price * (Decimal(1) + z.median_spread_pct / Decimal(2))
        gap = (target - entry) / entry
        if gap < z.round_trip_cost_pct * Decimal(2):
            return None
        return Signal(self.strategy_id, self.version, z.symbol, Direction.LONG, entry, stop, (target,), gap, "SWING",
                      f"bid-side provision: spread {z.median_spread_pct} wide, thin {z.trading_days_of_20}/20 sessions", entry_type="PASSIVE_LIMIT", holds_over_weekend=True)
