"""Deterministic Risk Authority (Rev 2 §27).

Everything in this package is pure, synchronous and dependency-free. It is the
only component permitted to turn a TradeIntent into an approved size. Nothing
here consults a model, a broker or the network.
"""

from vati.risk.mandate import (
    AuthorizationMode,
    DrawdownTier,
    HARD_FORBIDDEN_BEHAVIOURS,
    MandateError,
    PlatformCeilings,
    TradingMandate,
)
from vati.risk.contracts import (
    Direction,
    KillSwitchTrigger,
    LossModel,
    MarketIntegrityState,
    OpenPosition,
    RiskSnapshot,
    StrategyState,
    SymbolContract,
    TradeIntent,
)
from vati.risk.sizing import (
    Multipliers,
    SizingRejected,
    SizingResult,
    clamp_multiplier,
    size_stake_contract,
    size_stop_contract,
)
from vati.risk.heat import currency_leg_exposure, open_stop_risk, position_risk
from vati.risk.governor import DrawdownVerdict, KillSwitch, drawdown_verdict
from vati.risk.authority import Decision, RiskAuthority, RiskDecision

__all__ = [
    "AuthorizationMode",
    "Decision",
    "Direction",
    "DrawdownTier",
    "DrawdownVerdict",
    "HARD_FORBIDDEN_BEHAVIOURS",
    "KillSwitch",
    "KillSwitchTrigger",
    "LossModel",
    "MandateError",
    "MarketIntegrityState",
    "Multipliers",
    "OpenPosition",
    "PlatformCeilings",
    "RiskAuthority",
    "RiskDecision",
    "RiskSnapshot",
    "SizingRejected",
    "SizingResult",
    "StrategyState",
    "SymbolContract",
    "TradeIntent",
    "TradingMandate",
    "clamp_multiplier",
    "currency_leg_exposure",
    "drawdown_verdict",
    "open_stop_risk",
    "position_risk",
    "size_stake_contract",
    "size_stop_contract",
]
