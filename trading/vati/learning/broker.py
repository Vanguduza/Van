"""Broker execution learning (integration doc §24, §43) from TCA records.
Outputs are reduce-only: a liquidity multiplier and a per-(symbol, session)
state that the arbiter may use to exclude capsules. Execution facts from
BACKTEST/REPLAY/COUNTERFACTUAL carry zero weight."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from vati.learning.boundary import LearningBoundary, LiveAdjustment, LiveTarget
from vati.learning.episodes import EXECUTION_FACT_WEIGHT, Environment

ONE, ZERO = Decimal(1), Decimal(0)


class BrokerState(str, Enum):
    CERTIFIED = "CERTIFIED"
    DEGRADED = "DEGRADED"
    EVENT_LIMITED = "EVENT_LIMITED"
    NO_SCALPING = "NO_SCALPING"
    SUSPENDED = "SUSPENDED"


@dataclass
class BrokerExecutionProfile:
    broker: str
    symbol: str
    session: str
    samples: list = field(default_factory=list)   # (weight, cost_ratio, slippage_pips, rejected:bool, in_event:bool)

    def _w(self) -> Decimal:
        return sum((s[0] for s in self.samples), ZERO)

    def median(self, idx: int) -> Decimal:
        xs = sorted(s[idx] for s in self.samples if s[0] > ZERO)
        return xs[len(xs) // 2] if xs else ZERO

    def p95(self, idx: int) -> Decimal:
        xs = sorted(s[idx] for s in self.samples if s[0] > ZERO)
        return xs[min(len(xs) - 1, int(len(xs) * 0.95))] if xs else ZERO

    def rejection_rate(self) -> Decimal:
        w = self._w()
        return sum((s[0] for s in self.samples if s[3]), ZERO) / w if w > ZERO else ZERO

    def event_cost_ratio(self) -> Decimal:
        ev = [s for s in self.samples if s[4] and s[0] > ZERO]
        return (sum((s[1] * s[0] for s in ev), ZERO) / sum((s[0] for s in ev), ZERO)) if ev else ZERO

    def state(self) -> BrokerState:
        if self._w() < Decimal("10"):
            return BrokerState.CERTIFIED   # not enough real evidence to downgrade; sizing still capped by multiplier
        if self.rejection_rate() > Decimal("0.10") or self.median(1) > Decimal("2.0"):
            return BrokerState.SUSPENDED
        if self.event_cost_ratio() > Decimal("2.0"):
            return BrokerState.EVENT_LIMITED
        if self.p95(1) > Decimal("3.0"):
            return BrokerState.NO_SCALPING
        if self.median(1) > Decimal("1.3"):
            return BrokerState.DEGRADED
        return BrokerState.CERTIFIED

    def liquidity_multiplier(self) -> Decimal:
        s = self.state()
        return {BrokerState.CERTIFIED: ONE, BrokerState.DEGRADED: Decimal("0.7"), BrokerState.EVENT_LIMITED: Decimal("0.8"), BrokerState.NO_SCALPING: Decimal("0.8"), BrokerState.SUSPENDED: ZERO}[s]


@dataclass
class BrokerLearner:
    profiles: dict[tuple[str, str, str], BrokerExecutionProfile] = field(default_factory=dict)

    def observe(self, *, broker: str, symbol: str, session: str, environment: Environment, cost_ratio: Decimal, slippage_pips: Decimal, rejected: bool, in_event_window: bool) -> BrokerExecutionProfile:
        p = self.profiles.setdefault((broker, symbol, session), BrokerExecutionProfile(broker, symbol, session))
        p.samples.append((EXECUTION_FACT_WEIGHT[environment], cost_ratio, slippage_pips, rejected, in_event_window))
        return p

    def live_adjustment(self, broker: str, symbol: str, session: str) -> Optional[LiveAdjustment]:
        p = self.profiles.get((broker, symbol, session))
        if p is None or p._w() < LearningBoundary.MIN_WEIGHTED_SAMPLES:
            return None
        return LearningBoundary.check(LiveAdjustment(LiveTarget.BROKER_PROFILE, f"{broker}:{symbol}:{session}", p.liquidity_multiplier(), None, (f"broker-profile:{broker}:{symbol}:{session}",), p._w()))
