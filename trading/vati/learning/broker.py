"""Broker execution learning (integration doc §24, §43) from TCA records.
Outputs are reduce-only: a liquidity multiplier and a per-(symbol, session)
state that the arbiter may use to exclude capsules. Execution facts from
BACKTEST/REPLAY/COUNTERFACTUAL carry zero weight."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from vati.learning.boundary import LearningBoundary, LiveAdjustment, LiveAdjustmentProposal, LiveTarget
from vati.learning.episodes import EXECUTION_FACT_WEIGHT, Environment
from vati.learning.evidence import EvidenceClass, EvidenceError, LedgerEvidenceResolver, ResolvedEvidenceCache, parse_evidence_ref

ONE, ZERO = Decimal(1), Decimal(0)
EVENT_WINDOWS = frozenset({"QUIET", "DRIFT", "PRE_BLACKOUT", "POST_BLACKOUT"})


def _tca_decimal(p, key: str, ref) -> Decimal:
    v = p.get(key)
    if v is None or isinstance(v, bool):
        raise EvidenceError(f"TCA evidence {ref} records no {key}")
    try:
        d = Decimal(str(v))
    except (ArithmeticError, ValueError):
        raise EvidenceError(f"TCA evidence {ref} records a malformed {key} {v!r}") from None
    if d.is_nan():
        raise EvidenceError(f"TCA evidence {ref} records a malformed {key} {v!r}")
    return d


def tca_facts(rec) -> tuple[Decimal, Decimal, bool, bool]:
    """(cost_ratio, slippage, rejected, in_event_window) read from a TCA_RECORD (A-VATI M3).
    A value the record does not carry is refused, never defaulted."""
    p = rec.content["payload"]
    cost = _tca_decimal(p, "cost_ratio", rec.ref)
    if cost.is_infinite():
        cost = Decimal("10")   # no modelled cost: the runtime's own cap (hooks.on_tca, replay)
    slippage = _tca_decimal(p, "slippage", rec.ref)
    if slippage.is_infinite():
        raise EvidenceError(f"TCA evidence {rec.ref} records a malformed slippage")
    rejected, window = p.get("rejected"), p.get("event_window")
    if not isinstance(rejected, bool):
        raise EvidenceError(f"TCA evidence {rec.ref} records no rejected flag")
    if not isinstance(window, str):
        raise EvidenceError(f"TCA evidence {rec.ref} records no event_window")
    return cost, slippage, rejected, window in EVENT_WINDOWS


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
    evidence_refs: list = field(default_factory=list)   # one TCA_RECORD ledger evidence ref per sample
    trade_ids: list = field(default_factory=list)       # one trade per sample (A-VATI M2)

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
    evidence: ResolvedEvidenceCache = field(default_factory=ResolvedEvidenceCache)

    def observe(self, *, broker: str, symbol: str, session: str, environment: Environment, cost_ratio: Decimal, slippage_pips: Decimal, rejected: bool, in_event_window: bool,
                evidence_ref: str, resolver: LedgerEvidenceResolver, correlation_hint: str | None = None) -> BrokerExecutionProfile:
        """Each execution fact must cite the TCA_RECORD ledger event it came from."""
        ref = parse_evidence_ref(evidence_ref)
        if ref.evidence_class is not EvidenceClass.TCA_RECORD:
            raise EvidenceError(f"broker execution facts must cite a TCA_RECORD, not {ref.evidence_class.value}")
        rec = self.evidence.admit(ref, resolver, correlation_hint=correlation_hint)
        key = f"{broker}:{symbol}:{session}"
        if key not in rec.subjects:
            raise EvidenceError(f"evidence {ref} is not about {key!r}")
        if Environment(environment) is not rec.environment:
            raise EvidenceError(f"fact environment {environment.value} != evidence environment {rec.environment.value}")
        # A-VATI M3: the execution facts are the TCA record's, not the caller's.
        cost, slip, rej, in_ev = tca_facts(rec)
        if cost_ratio.is_infinite():
            cost_ratio = Decimal("10")
        if cost_ratio != cost or slippage_pips != slip or bool(rejected) is not rej or bool(in_event_window) is not in_ev:
            raise EvidenceError(f"execution fact (cost_ratio={cost_ratio}, slippage={slippage_pips}, rejected={rejected}, in_event_window={in_event_window}) "
                                f"disagrees with its evidence {ref} (cost_ratio={cost}, slippage={slip}, rejected={rej}, in_event_window={in_ev})")
        cost_ratio, slippage_pips, rejected, in_event_window = cost, slip, rej, in_ev
        p = self.profiles.setdefault((broker, symbol, session), BrokerExecutionProfile(broker, symbol, session))
        if str(ref) in p.evidence_refs or rec.trade_id in p.trade_ids:
            return p   # the same TCA record (or another record of the same trade) is not a new sample
        p.evidence_refs.append(str(ref))
        p.trade_ids.append(rec.trade_id)
        p.samples.append((EXECUTION_FACT_WEIGHT[environment], cost_ratio, slippage_pips, rejected, in_event_window))
        return p

    def live_adjustment(self, broker: str, symbol: str, session: str) -> Optional[LiveAdjustment]:
        p = self.profiles.get((broker, symbol, session))
        if p is None or p._w() < LearningBoundary.MIN_WEIGHTED_SAMPLES:
            return None
        return LearningBoundary.admit(LiveAdjustmentProposal(LiveTarget.BROKER_PROFILE, f"{broker}:{symbol}:{session}", p.liquidity_multiplier(), None, tuple(p.evidence_refs)), self.evidence)
