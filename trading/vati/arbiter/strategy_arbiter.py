"""Strategy Arbiter: which capsules may even look at this market state."""

from __future__ import annotations

from dataclasses import dataclass

from vati.intelligence.events import EventWindowState
from vati.intelligence.feature_contract import (
    FEATURE_CONTRACT_UNSATISFIED,
    FeatureContractValidator,
    FeatureContractVerdict,
    availability_from_context,
    availability_from_feature_vector,
    requirements_from_capsule,
)
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
    #: TRD-ENH-003. Present when the feature contract ran; the capsule abstains
    #: on an unsatisfied contract rather than trading on whatever remains.
    feature_contract: FeatureContractVerdict | None = None


class StrategyArbiter:
    def __init__(self, *, feature_validator: FeatureContractValidator | None = None) -> None:
        self.feature_validator = feature_validator or FeatureContractValidator()

    def evaluate(self, capsule: Capsule, state: MarketState, mandate: TradingMandate, *, regime_label: str, currency_regime_label: str | None = None,
                 venue_class: str | None = None, history_bars: int | None = None, context: object | None = None) -> EligibilityVerdict:
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
        # TRD-ENH-003 — the declared feature dependencies, checked at evaluation
        # time. A contract satisfied at startup can be unsatisfied an hour later.
        available = availability_from_feature_vector(state.features, venue_class=venue_class, history_bars=history_bars)
        available.update(availability_from_context(context, as_of_ms=state.as_of_ms, venue_class=venue_class,
                                                   timeframe=getattr(state, "timeframe", "UNKNOWN")))
        contract = self.feature_validator.validate(
            requirements=requirements_from_capsule(capsule, timeframe=getattr(state, "timeframe", None) if getattr(state, "timeframe", "UNKNOWN") != "UNKNOWN" else None),
            available=available,
            now_ms=state.as_of_ms,
            venue_class=venue_class,
        )
        if not contract.satisfied:
            reasons.append(f"{FEATURE_CONTRACT_UNSATISFIED}:{','.join(contract.reasons)}")
        return EligibilityVerdict(capsule.strategy_id, not reasons, tuple(reasons), contract)
