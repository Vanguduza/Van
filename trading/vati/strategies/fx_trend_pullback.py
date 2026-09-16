"""FX/gold trend pullback (Rev 3 D3a). BULL/BEAR regime, price pulls back to the
fast EMA, RSI not stretched, structure stop beyond the swing, target 3 ATR."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from vati.intelligence.market_state import MarketState
from vati.intelligence.regimes import TransitionPhase, TrendRegime, VolRegime
from vati.risk.contracts import Direction
from vati.strategies.base import Signal, Strategy, StrategyContext


class FxTrendPullback:
    def __init__(self, strategy_id: str = "FX-TREND-PULLBACK-01", version: str = "1.0.0", *, pullback_atr: Decimal = Decimal("0.75"),
                 stop_atr: Decimal = Decimal("2"), target_atr: Decimal = Decimal("3"), horizon: str = "SWING") -> None:
        self.strategy_id, self.version = strategy_id, version
        self.pullback_atr, self.stop_atr, self.target_atr, self.horizon = pullback_atr, stop_atr, target_atr, horizon

    def evaluate(self, state: MarketState, ctx: StrategyContext) -> Optional[Signal]:
        f, r = state.features, state.regime
        if not f.complete or f.atr is None or f.ema_fast is None or r.phase is TransitionPhase.TRANSITION or r.vol is VolRegime.EXTREME:
            return None
        if state.in_event_window():
            return None
        band = f.atr * self.pullback_atr
        if r.trend is TrendRegime.BULL and f.rsi is not None and f.rsi < 65:
            pulled_back = f.swing_high is not None and (f.swing_high - f.close) >= f.atr * Decimal("0.5")
            if pulled_back and abs(f.close - f.ema_fast) <= band:
                entry = f.close
                stop = min(f.swing_low or entry, entry - f.atr * self.stop_atr)
                target = entry + f.atr * self.target_atr
                return Signal(self.strategy_id, self.version, state.symbol, Direction.LONG, entry, stop, (target,), (target - entry) / entry, self.horizon,
                              f"BULL regime pullback to EMA{20} within {self.pullback_atr} ATR; RSI {f.rsi:.1f}", confidence_hint=r.confidence)
        if r.trend is TrendRegime.BEAR and f.rsi is not None and f.rsi > 35:
            pulled_back = f.swing_low is not None and (f.close - f.swing_low) >= f.atr * Decimal("0.5")
            if pulled_back and abs(f.close - f.ema_fast) <= band:
                entry = f.close
                stop = max(f.swing_high or entry, entry + f.atr * self.stop_atr)
                target = entry - f.atr * self.target_atr
                return Signal(self.strategy_id, self.version, state.symbol, Direction.SHORT, entry, stop, (target,), (entry - target) / entry, self.horizon,
                              f"BEAR regime pullback to EMA within {self.pullback_atr} ATR; RSI {f.rsi:.1f}", confidence_hint=r.confidence)
        return None
