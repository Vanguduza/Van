from vati.strategies.base import Signal, Strategy, StrategyContext, ZseSnapshot
from vati.strategies.capsule import Capsule, CapsuleRegistry, CapsuleError
from vati.strategies.fx_trend_pullback import FxTrendPullback
from vati.strategies.session_breakout import LondonSessionBreakout
from vati.strategies.event_drift import EventDrift
from vati.strategies.zse_value_rotation import ZseValueRotation
from vati.strategies.zse_liquidity_provision import ZseLiquidityProvision

STRATEGY_IMPLEMENTATIONS = {
    "FX-TREND-PULLBACK": FxTrendPullback,
    "FX-LONDON-BREAKOUT": LondonSessionBreakout,
    "FX-EVENT-DRIFT": EventDrift,
    "GOLD-TREND-POSITION": FxTrendPullback,
    "ZSE-VALUE-ROTATION": ZseValueRotation,
    "ZSE-LIQUIDITY-PROVISION": ZseLiquidityProvision,
}

__all__ = ["Signal", "Strategy", "StrategyContext", "ZseSnapshot", "Capsule", "CapsuleRegistry", "CapsuleError", "FxTrendPullback",
           "LondonSessionBreakout", "EventDrift", "ZseValueRotation", "ZseLiquidityProvision", "STRATEGY_IMPLEMENTATIONS"]
