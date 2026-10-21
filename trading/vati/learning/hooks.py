"""Where learning attaches to the decision cycle (Rev 4 Part L §L.9).

The cycle calls two hooks: `on_tca` after an entry fill, `on_review` after a
trade closes. Each hook only *observes*; the only things it may push back into
the live path are the three LearningBoundary targets: a capsule-health
multiplier (≤ 1) with an optional demotion, and a per-symbol broker liquidity
multiplier (≤ 1). Every episode is written to the ledger as a
TRADE_EXPERIENCE_ARTIFACT so the evidence chain is replayable.

Evidence (C5): a hook learns only from an authoritative ledger event — the
TCA_RECORD or TRADE_REVIEW the runtime has just appended for that intent —
resolved through a LedgerEvidenceResolver bound to this runtime's environment.
No event, no learning: there is no fallback to an intent id or free text."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.core.events import Event, EventKind
from vati.core.ledger import Ledger
from vati.learning.boundary import LearningBoundary, LiveAdjustment, LiveTarget
from vati.learning.broker import EVENT_WINDOWS, BrokerLearner
from vati.learning.episodes import Environment, ExperienceEpisode, episode_from_ledger
from vati.learning.evidence import EvidenceClass, EvidenceError, LedgerEvidenceResolver, make_evidence_ref
from vati.learning.health import HealthObservation, StrategyHealthTracker

ONE, ZERO = Decimal(1), Decimal(0)


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
    # Observations the evidence refused (A-VATI M3): a value the ledger does not
    # record, or a caller value that disagrees with it. Refused means no learning
    # from that trade; the close/fill path itself is never interrupted.
    refusals: list[str] = field(default_factory=list)

    _resolvers: dict[int, LedgerEvidenceResolver] = field(default_factory=dict, repr=False)

    def resolver(self, ledger: Ledger) -> LedgerEvidenceResolver:
        r = self._resolvers.get(id(ledger))
        if r is None or r.ledger is not ledger:
            r = self._resolvers[id(ledger)] = LedgerEvidenceResolver(ledger, session_environment=self.environment)
        return r

    @staticmethod
    def _latest(ledger: Ledger, kind: EventKind, trade_intent_id: str, match: dict[str, str]) -> Optional[Event]:
        hit = None
        for ev in ledger.iter(kind, correlation_id=trade_intent_id):
            if all(str(ev.payload.get(k)) == v for k, v in match.items()):
                hit = ev
        return hit

    # ------------------------------------------------------------ observe
    def on_tca(self, ledger: Ledger, *, trade_intent_id: str, symbol: str, session: str, event_window: str, cost_ratio: Decimal, slippage: Decimal, rejected: bool = False) -> Optional[LiveAdjustment]:
        """Learn from the TCA_RECORD the runtime appended for `trade_intent_id`."""
        ev = self._latest(ledger, EventKind.TCA_RECORD, trade_intent_id, {"broker": self.broker, "symbol": symbol, "session": session})
        if ev is None:
            return None   # no authoritative execution fact, nothing to learn
        if cost_ratio.is_infinite():
            cost_ratio = Decimal("10")
        try:
            self.brokers.observe(broker=self.broker, symbol=symbol, session=session, environment=self.environment, cost_ratio=cost_ratio, slippage_pips=slippage,
                                 rejected=rejected, in_event_window=event_window in EVENT_WINDOWS,
                                 evidence_ref=make_evidence_ref(EvidenceClass.TCA_RECORD, ev.hash), resolver=self.resolver(ledger), correlation_hint=trade_intent_id)
        except EvidenceError as e:
            self.refusals.append(f"tca {trade_intent_id}: {e}")
            return None
        adj = self.brokers.live_adjustment(self.broker, symbol, session)
        if adj is not None:
            self.adjustments.append(adj)
        return adj

    def on_review(self, ledger: Ledger, *, trade_intent_id: str, strategy_id: str, r_multiple: Decimal, process_ok: bool, cost_ratio: Decimal, regime_fit: bool = True) -> tuple[Optional[ExperienceEpisode], Optional[LiveAdjustment]]:
        ep = episode_from_ledger(ledger, trade_intent_id, environment=self.environment)
        if ep is not None:
            self.episodes.append(ep)
        review = self._latest(ledger, EventKind.TRADE_REVIEW, trade_intent_id, {"strategy_id": strategy_id})
        if review is None:
            return ep, None   # no TRADE_REVIEW on the ledger: no health evidence (never the intent id)
        try:
            self.health.observe(HealthObservation(strategy_id, self.environment, r_multiple, process_ok, min(cost_ratio, Decimal("10")), regime_fit,
                                                  make_evidence_ref(EvidenceClass.TRADE_REVIEW, review.hash)),
                                resolver=self.resolver(ledger), correlation_hint=trade_intent_id)
        except EvidenceError as e:
            self.refusals.append(f"review {trade_intent_id}: {e}")
            return ep, None
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
