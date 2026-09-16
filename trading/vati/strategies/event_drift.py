"""Post-event drift (Rev 3 A.5, C.3). Trades only inside the DRIFT window, in
the direction of the move since release, never the spike."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from vati.intelligence.events import EventWindowState
from vati.intelligence.market_state import MarketState
from vati.risk.contracts import Direction
from vati.strategies.base import Signal, StrategyContext


class EventDrift:
    def __init__(self, strategy_id: str = "FX-EVENT-DRIFT-01", version: str = "1.0.0", *, min_move_atr: Decimal = Decimal("1"), stop_atr: Decimal = Decimal("1.5"), target_atr: Decimal = Decimal("2.5")) -> None:
        self.strategy_id, self.version = strategy_id, version
        self.min_move_atr, self.stop_atr, self.target_atr = min_move_atr, stop_atr, target_atr

    def evaluate(self, state: MarketState, ctx: StrategyContext) -> Optional[Signal]:
        f = state.features
        if state.event_window is not EventWindowState.DRIFT or ctx.event_release_ref_price is None or f.atr is None or not f.complete:
            return None
        move = f.close - ctx.event_release_ref_price
        if abs(move) < f.atr * self.min_move_atr:
            return None
        if move > 0:
            entry, stop, target, d = f.close, f.close - f.atr * self.stop_atr, f.close + f.atr * self.target_atr, Direction.LONG
        else:
            entry, stop, target, d = f.close, f.close + f.atr * self.stop_atr, f.close - f.atr * self.target_atr, Direction.SHORT
        return Signal(self.strategy_id, self.version, state.symbol, d, entry, stop, (target,), abs(target - entry) / entry, "SESSION",
                      f"post-event drift {state.event_id}: move {move} since release", event_certified=True)
