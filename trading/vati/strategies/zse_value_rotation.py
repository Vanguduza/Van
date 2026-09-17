"""ZSE/VFEX value + currency-regime rotation (Rev 3 D.5 #1–2). Long only,
POSITION horizon, must clear the punitive round-trip cost, blocked in
DISORDERLY, reduced in STRESSED."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from vati.intelligence.market_state import MarketState
from vati.risk.contracts import Direction
from vati.strategies.base import Signal, StrategyContext
from vati.zse.currency import CurrencyRegime


class ZseValueRotation:
    def __init__(self, strategy_id: str = "ZSE-VALUE-ROTATION-01", version: str = "1.0.0", *, min_value_score: Decimal = Decimal("0.65"),
                 stop_fraction: Decimal = Decimal("0.12"), expected_move_multiple_of_cost: Decimal = Decimal("3")) -> None:
        self.strategy_id, self.version = strategy_id, version
        self.min_value_score, self.stop_fraction, self.k = min_value_score, stop_fraction, expected_move_multiple_of_cost

    def evaluate(self, state: MarketState, ctx: StrategyContext) -> Optional[Signal]:
        z = ctx.zse
        if z is None or z.currency_regime is CurrencyRegime.DISORDERLY:
            return None
        if z.value_score < self.min_value_score or z.trading_days_of_20 < 10:
            return None
        # expected move: value gap proxy scaled by regime, floored to clear cost by the required multiple
        gap = (z.value_score - Decimal("0.5")) * Decimal("0.8")  # 0.65 → 12%, 0.9 → 32%
        if z.currency_regime is CurrencyRegime.STRESSED:
            gap = gap / Decimal(2)
        if gap < z.round_trip_cost_pct * self.k:
            return None
        entry = z.last_price
        stop = entry * (Decimal(1) - self.stop_fraction)
        target = entry * (Decimal(1) + gap)
        conf = Decimal("1") if z.currency_regime is CurrencyRegime.ANCHORED else (Decimal("0.8") if z.currency_regime is CurrencyRegime.ELEVATED else Decimal("0.5"))
        return Signal(self.strategy_id, self.version, z.symbol, Direction.LONG, entry, stop, (target,), gap, "POSITION",
                      f"value score {z.value_score} in {z.currency_regime.value} regime; hold ≥ 270d for lower CGWT", entry_type="LIMIT",
                      holds_over_weekend=True, confidence_hint=conf)
