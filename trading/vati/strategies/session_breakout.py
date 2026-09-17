"""London session breakout with compression and spread gates (Rev 3 D3b).
Evidence: highs/lows cluster around the London open; spreads are 3–10× wider
in Asia, so the spread percentile gate matters more than the pattern."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from vati.intelligence.market_state import MarketState
from vati.intelligence.regimes import VolRegime
from vati.market_data.calendars import Session
from vati.risk.contracts import Direction
from vati.strategies.base import Signal, StrategyContext


class LondonSessionBreakout:
    def __init__(self, strategy_id: str = "FX-LONDON-BREAKOUT-01", version: str = "1.0.0", *, max_compression: Decimal = Decimal("0.6"),
                 max_spread_pct: Decimal = Decimal("0.6"), target_atr: Decimal = Decimal("2")) -> None:
        self.strategy_id, self.version = strategy_id, version
        self.max_compression, self.max_spread_pct, self.target_atr = max_compression, max_spread_pct, target_atr

    def evaluate(self, state: MarketState, ctx: StrategyContext) -> Optional[Signal]:
        f = state.features
        if state.session not in (Session.LONDON, Session.LONDON_NY_OVERLAP) or not f.complete or f.atr is None:
            return None
        if state.in_event_window() or state.regime.vol is VolRegime.EXTREME:
            return None
        if f.range_compression is None or f.range_compression > self.max_compression or f.spread_percentile > self.max_spread_pct:
            return None
        if f.swing_high is None or f.swing_low is None:
            return None
        rng = f.swing_high - f.swing_low
        if rng <= 0:
            return None
        # stop-entry above the range, stop below it; target 2 ATR beyond
        entry = f.swing_high + f.atr * Decimal("0.1")
        stop = f.swing_low
        target = entry + f.atr * self.target_atr
        return Signal(self.strategy_id, self.version, state.symbol, Direction.LONG, entry, stop, (target,), (target - entry) / entry, "INTRADAY",
                      f"London compression {f.range_compression:.2f} breakout; spread pct {f.spread_percentile:.2f}", entry_type="STOP")
