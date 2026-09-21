"""Strategy Arbiter: which capsules may even look at this market state."""

from __future__ import annotations

from dataclasses import dataclass

from vati.intelligence.events import EventWindowState
from vati.intelligence.market_state import MarketState
from vati.risk.contracts import StrategyState
from vati.risk.mandate import TradingMandate
from vati.strategies.capsule import Capsule

ACTIVE_STATES = {StrategyState.DEMO, StrategyState.SHADOW, StrategyState.LIMITED_LIVE, StrategyState.CERTIFIED_LIVE}


@dataclass(frozen=True)
class EligibilityVerdict:
    strategy_id: str
    eligible: bool
    reasons: tuple[str, ...]


class StrategyArbiter:
    def evaluate(self, capsule: Capsule, state: MarketState, mandate: TradingMandate, *, regime_label: str, currency_regime_label: str | None = None) -> EligibilityVerdict:
        reasons = []
        if capsule.state not in ACTIVE_STATES:
            reasons.append(f"capsule state {capsule.state.value} is not active")
        if capsule.strategy_id not in mandate.allowed_strategies:
            reasons.append("not in mandate.allowed_strategies")
        if state.symbol.upper() not in capsule.instruments or state.symbol.upper() not in mandate.instruments:
            reasons.append("instrument not eligible for capsule/mandate")
        labels = {regime_label, state.regime.vol.value, state.regime.phase.value}
        if currency_regime_label:
            labels.add(currency_regime_label)
        if capsule.forbidden_regimes & labels:
            reasons.append(f"forbidden regime {sorted(capsule.forbidden_regimes & labels)}")
        if capsule.eligible_regimes and not (capsule.eligible_regimes & labels):
            reasons.append(f"no eligible regime among {sorted(labels)}")
        if state.event_window in (EventWindowState.PRE_BLACKOUT, EventWindowState.POST_BLACKOUT):
            reasons.append("inside Tier-1 blackout")
        elif state.event_window is EventWindowState.QUIET and not capsule.event_certified:
            reasons.append("quiet window: capsule not event-certified")
        if state.integrity.value in ("ABNORMAL", "HALTED"):
            reasons.append(f"market integrity {state.integrity.value}")
        return EligibilityVerdict(capsule.strategy_id, not reasons, tuple(reasons))
