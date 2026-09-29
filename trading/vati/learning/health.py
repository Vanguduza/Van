"""Capsule health with environment-weighted samples and hysteresis (Rev 2 §25,
integration doc §22). Demotion is automatic; recovery/promotion never is."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Optional

from vati.learning.boundary import LearningBoundary, LiveAdjustment, LiveAdjustmentProposal, LiveTarget
from vati.learning.episodes import ENVIRONMENT_WEIGHT, Environment
from vati.learning.evidence import EvidenceClass, EvidenceError, EvidenceRecord, LedgerEvidenceResolver, ResolvedEvidenceCache, parse_evidence_ref

# Authoritative ledger events a health observation may stand on. A health
# observation is derived; its evidence is the source event it cites, and its
# values are read from that evidence (A-VATI M3). Only classes that record the
# trade's R multiple and process verdict qualify: a PnL attribution or a shadow
# outcome records neither, so it cannot stand behind a health sample.
HEALTH_SOURCE_CLASSES = frozenset({EvidenceClass.TRADE_REVIEW, EvidenceClass.VTIL_ARTIFACT})

ONE, ZERO = Decimal(1), Decimal(0)
COST_RATIO_CAP = Decimal("10")


def _decimal(v: Any, what: str, rec: EvidenceRecord) -> Decimal:
    if v is None or isinstance(v, bool):
        raise EvidenceError(f"evidence {rec.ref} records no {what}")
    try:
        d = Decimal(str(v))
    except (ArithmeticError, ValueError):
        raise EvidenceError(f"evidence {rec.ref} records a malformed {what} {v!r}") from None
    if d.is_nan():
        raise EvidenceError(f"evidence {rec.ref} records a malformed {what} {v!r}")
    return d


def cap_cost_ratio(c: Decimal) -> Decimal:
    """Realised/modelled cost with no model (Infinity) or runaway values caps at 10."""
    return COST_RATIO_CAP if c.is_infinite() else min(c, COST_RATIO_CAP)


def health_facts(rec: EvidenceRecord, resolver: LedgerEvidenceResolver) -> tuple[Decimal, bool, Decimal]:
    """(r_multiple, process_ok, cost_ratio) of one trade, read from the ledger.

    * r_multiple — the cited TRADE_REVIEW payload, or the experience artifact's outcome;
    * process_ok — the trade's decision-quality verdict (GAP-F-003, no faults) when the
      ledger holds one, else the cited record's own process flag;
    * cost_ratio — the experience artifact's TCA, or for a review the trade's TCA_RECORD
      (same trade, same environment).
    A value the evidence does not record is refused, never defaulted."""
    p = rec.content["payload"]
    if rec.evidence_class is EvidenceClass.TRADE_REVIEW:
        r_raw, proc = p.get("r_multiple"), p.get("process_ok")
        tca = resolver.trade_fact(EvidenceClass.TCA_RECORD, rec.trade_id)
        if tca is None:
            raise EvidenceError(f"evidence {rec.ref} has no TCA_RECORD for trade {rec.trade_id!r}: its cost ratio is not recorded")
        if tca.environment is not rec.environment:
            raise EvidenceError(f"TCA_RECORD of trade {rec.trade_id!r} is {tca.environment.value}, its review is {rec.environment.value}")
        cost_raw = tca.content["payload"].get("cost_ratio")
    elif rec.evidence_class is EvidenceClass.VTIL_ARTIFACT:
        outcome, review, execution = p.get("outcome"), p.get("review"), p.get("execution")
        r_raw = outcome.get("r_multiple") if isinstance(outcome, Mapping) else None
        proc = review.get("process_ok") if isinstance(review, Mapping) else None
        tca = execution.get("tca") if isinstance(execution, Mapping) else None
        cost_raw = tca.get("cost_ratio") if isinstance(tca, Mapping) else None
    else:
        raise EvidenceError(f"{rec.evidence_class.value} is not a source event for strategy health")
    r = _decimal(r_raw, "r_multiple", rec)
    if r.is_infinite():
        raise EvidenceError(f"evidence {rec.ref} records a malformed r_multiple {r_raw!r}")
    cost = cap_cost_ratio(_decimal(cost_raw, "cost_ratio", rec))
    dq = resolver.decision_quality(rec.trade_id)
    if dq is not None:
        faults = dq.get("faults")
        if not isinstance(faults, list):
            raise EvidenceError(f"decision-quality verdict of trade {rec.trade_id!r} records no faults list")
        proc = not faults
    if not isinstance(proc, bool):
        raise EvidenceError(f"evidence {rec.ref} records no process_ok")
    return r, proc, cost


@dataclass(frozen=True)
class HealthObservation:
    strategy_id: str
    environment: Environment
    r_multiple: Decimal
    process_ok: bool
    cost_ratio: Decimal            # realised / modelled cost (1 = as modelled)
    regime_fit: bool               # traded inside an eligible regime
    evidence_ref: str              # vati-evidence:<TRADE_REVIEW|VTIL_ARTIFACT|...>:<ledger Event.hash>


@dataclass(frozen=True)
class HealthVerdict:
    strategy_id: str
    health: Decimal
    weighted_samples: Decimal
    state_recommendation: Optional[str]   # None | DEGRADED | SHADOW
    reasons: tuple[str, ...]


@dataclass
class StrategyHealthTracker:
    certified_expectancy_r: dict[str, Decimal] = field(default_factory=dict)
    window: int = 60
    degrade_below: Decimal = Decimal("0.55")
    shadow_below: Decimal = Decimal("0.40")
    sustain: int = 20
    _obs: dict[str, list[HealthObservation]] = field(default_factory=dict)
    _below_count: dict[str, int] = field(default_factory=dict)
    _state: dict[str, str] = field(default_factory=dict)
    # Each observation must cite an authoritative ledger event, resolved through a
    # LedgerEvidenceResolver. Identity is that event's hash, so re-observing the
    # same fact is a no-op and the boundary recomputes the weighted count itself.
    evidence: ResolvedEvidenceCache = field(default_factory=ResolvedEvidenceCache)
    _refs: dict[str, list[str]] = field(default_factory=dict)
    # One trade is one sample (A-VATI M2), and once counted it is never counted
    # again (A-VATI minor): the trades a strategy's health has consumed are
    # remembered for the tracker's lifetime, not just while they sit in the
    # 60-item window, because ledger evidence never stops being admissible. A
    # trade that ages out of the window is not re-admitted as a new sample. One
    # id per closed trade; a restart rebuilds it by replaying each trade once.
    _consumed: dict[str, set[str]] = field(default_factory=dict)

    def observe(self, o: HealthObservation, *, resolver: LedgerEvidenceResolver, correlation_hint: str | None = None) -> HealthVerdict:
        ref = parse_evidence_ref(o.evidence_ref)
        if ref.evidence_class not in HEALTH_SOURCE_CLASSES:
            raise EvidenceError(f"{ref.evidence_class.value} is not a source event for strategy health")
        # Checked before it is cached: a refused observation leaves nothing behind.
        rec = ResolvedEvidenceCache.resolve_from_ledger(ref, resolver, correlation_hint=correlation_hint)
        if o.strategy_id not in rec.subjects:
            raise EvidenceError(f"evidence {ref} is not about {o.strategy_id!r}")
        if Environment(o.environment) is not rec.environment:
            raise EvidenceError(f"observation environment {o.environment.value} != evidence environment {rec.environment.value}")
        # A-VATI M3: the observed values are the evidence's, not the caller's.
        r, proc, cost = health_facts(rec, resolver)
        if o.r_multiple != r or bool(o.process_ok) is not proc or cap_cost_ratio(Decimal(o.cost_ratio)) != cost:
            raise EvidenceError(f"observation (r={o.r_multiple}, process_ok={o.process_ok}, cost_ratio={o.cost_ratio}) disagrees with "
                                f"its evidence {ref} (r={r}, process_ok={proc}, cost_ratio={cost})")
        o = HealthObservation(o.strategy_id, rec.environment, r, proc, cost, bool(o.regime_fit), o.evidence_ref)
        refs = self._refs.setdefault(o.strategy_id, [])
        consumed = self._consumed.setdefault(o.strategy_id, set())
        canonical = str(ref)
        if rec.trade_id in consumed:
            return self.verdict(o.strategy_id)   # the same trade (evicted or not, any artifact) is not a new sample
        self.evidence.admit(ref, resolver, correlation_hint=correlation_hint)
        consumed.add(rec.trade_id)
        buf = self._obs.setdefault(o.strategy_id, [])
        buf.append(o)
        refs.append(canonical)
        del buf[:-self.window]
        for old in refs[:-self.window]:
            self.evidence.discard(old)
        del refs[:-self.window]
        return self.verdict(o.strategy_id)

    def observe_evidence(self, strategy_id: str, evidence_ref: str, *, resolver: LedgerEvidenceResolver,
                         correlation_hint: str | None = None, regime_fit: bool = True) -> HealthVerdict:
        """Observe a trade whose every value is read from its ledger evidence."""
        rec = ResolvedEvidenceCache.resolve_from_ledger(evidence_ref, resolver, correlation_hint=correlation_hint)
        r, proc, cost = health_facts(rec, resolver)
        return self.observe(HealthObservation(strategy_id, rec.environment, r, proc, cost, regime_fit, evidence_ref),
                            resolver=resolver, correlation_hint=correlation_hint)

    def verdict(self, strategy_id: str) -> HealthVerdict:
        buf = self._obs.get(strategy_id, [])
        if not buf:
            return HealthVerdict(strategy_id, ONE, ZERO, None, ("no observations",))
        w = [ENVIRONMENT_WEIGHT[o.environment] for o in buf]
        W = sum(w, ZERO)
        exp_r = sum((o.r_multiple * wi for o, wi in zip(buf, w)), ZERO) / W
        cert = self.certified_expectancy_r.get(strategy_id, Decimal("0.3"))
        c_exp = min(ONE, max(ZERO, (exp_r / cert) if cert > ZERO else ZERO))
        c_proc = sum((wi for o, wi in zip(buf, w) if o.process_ok), ZERO) / W
        c_cost = min(ONE, max(ZERO, Decimal(2) - sum((o.cost_ratio * wi for o, wi in zip(buf, w)), ZERO) / W))   # cost ratio 1 → 1.0, 2 → 0
        c_fit = sum((wi for o, wi in zip(buf, w) if o.regime_fit), ZERO) / W
        health = (c_exp + c_proc + c_cost + c_fit) / Decimal(4)
        reasons = []
        if c_exp < Decimal("0.5"): reasons.append(f"expectancy {exp_r:.2f}R vs certified {cert}R")
        if c_cost < Decimal("0.7"): reasons.append("cost drift")
        if c_fit < Decimal("0.7"): reasons.append("trading outside eligible regimes")
        rec = None
        below = health < self.degrade_below
        self._below_count[strategy_id] = self._below_count.get(strategy_id, 0) + 1 if below else 0
        if health < self.shadow_below and self._below_count[strategy_id] >= self.sustain:
            rec = "SHADOW"
        elif below and self._below_count[strategy_id] >= self.sustain:
            rec = "DEGRADED"
        return HealthVerdict(strategy_id, health.quantize(Decimal("0.001")), W, rec, tuple(reasons))

    def live_adjustment(self, strategy_id: str) -> Optional[LiveAdjustment]:
        v = self.verdict(strategy_id)
        if v.weighted_samples < LearningBoundary.MIN_WEIGHTED_SAMPLES:
            return None
        proposal = LiveAdjustmentProposal(LiveTarget.CAPSULE_HEALTH, strategy_id, min(ONE, v.health), v.state_recommendation, tuple(self._refs[strategy_id]))
        return LearningBoundary.admit(proposal, self.evidence)
