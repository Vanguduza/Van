"""Where learning attaches to the decision cycle (Rev 4 Part L §L.9).

The cycle calls two hooks: `on_tca` after an entry fill, `on_review` after a
trade closes. Each hook only *observes*; the only things it may push back into
the live path are the three LearningBoundary targets: a capsule-health
multiplier (≤ 1) with an optional demotion, and a per-symbol broker liquidity
multiplier (≤ 1). Every episode is written to the ledger as a
TRADE_EXPERIENCE_ARTIFACT so the evidence chain is replayable."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.core.ledger import Ledger
from vati.learning.boundary import LearningBoundary, LiveAdjustment, LiveTarget
from vati.learning.broker import BrokerLearner
from vati.learning.episodes import Environment, ExperienceEpisode, episode_from_ledger
from vati.learning.health import HealthObservation, StrategyHealthTracker

ONE, ZERO = Decimal(1), Decimal(0)
EVENT_WINDOWS = {"QUIET", "DRIFT", "PRE_BLACKOUT", "POST_BLACKOUT"}


def to_payload(obj: Any) -> Any:
    """Ledger payloads are plain JSON: Decimal → str, Enum → value, tuple → list."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_payload(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, dict):
        return {str(k): to_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_payload(v) for v in obj]
    return obj


@dataclass
class LearningHooks:
    environment: Environment
    broker: str = "paper"
    health: StrategyHealthTracker = field(default_factory=StrategyHealthTracker)
    brokers: BrokerLearner = field(default_factory=BrokerLearner)
    episodes: list[ExperienceEpisode] = field(default_factory=list)
    adjustments: list[LiveAdjustment] = field(default_factory=list)
    demotions: list[tuple[str, str]] = field(default_factory=list)

    # ------------------------------------------------------------ observe
    def on_tca(self, *, symbol: str, session: str, event_window: str, cost_ratio: Decimal, slippage: Decimal, rejected: bool = False) -> Optional[LiveAdjustment]:
        if cost_ratio.is_infinite():
            cost_ratio = Decimal("10")
        self.brokers.observe(broker=self.broker, symbol=symbol, session=session, environment=self.environment, cost_ratio=cost_ratio, slippage_pips=slippage,
                             rejected=rejected, in_event_window=event_window in EVENT_WINDOWS)
        adj = self.brokers.live_adjustment(self.broker, symbol, session)
        if adj is not None:
            self.adjustments.append(adj)
        return adj

    def on_review(self, ledger: Ledger, *, trade_intent_id: str, strategy_id: str, r_multiple: Decimal, process_ok: bool, cost_ratio: Decimal, regime_fit: bool = True) -> tuple[Optional[ExperienceEpisode], Optional[LiveAdjustment]]:
        ep = episode_from_ledger(ledger, trade_intent_id, environment=self.environment)
        if ep is not None:
            self.episodes.append(ep)
        self.health.observe(HealthObservation(strategy_id, self.environment, r_multiple, process_ok, min(cost_ratio, Decimal("10")), regime_fit, ep.artifact_hash if ep else trade_intent_id))
        adj = self.health.live_adjustment(strategy_id)
        if adj is not None:
            self.adjustments.append(adj)
        return ep, adj

    # ---------------------------------------------------------- read-only
    def broker_liquidity(self, symbol: str) -> Decimal:
        """Minimum liquidity multiplier across sessions for this broker/symbol; 1 when unknown."""
        ms = [p.liquidity_multiplier() for (b, s, _), p in self.brokers.profiles.items() if b == self.broker and s == symbol and p._w() >= LearningBoundary.MIN_WEIGHTED_SAMPLES]
        return min(ms) if ms else ONE

    def capsule_health(self) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for sid in list(self.health._obs):
            adj = self.health.live_adjustment(sid)
            if adj is not None and adj.target is LiveTarget.CAPSULE_HEALTH:
                out[sid] = adj.multiplier
        return out
