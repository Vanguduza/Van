"""Capsule health with environment-weighted samples and hysteresis (Rev 2 §25,
integration doc §22). Demotion is automatic; recovery/promotion never is."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.learning.boundary import LearningBoundary, LiveAdjustment, LiveAdjustmentProposal, LiveTarget
from vati.learning.episodes import ENVIRONMENT_WEIGHT, Environment
from vati.learning.evidence import EvidenceClass, EvidenceError, LedgerEvidenceResolver, ResolvedEvidenceCache, parse_evidence_ref

# Authoritative ledger events a health observation may stand on. A health
# observation is derived; its evidence is the source event it cites.
HEALTH_SOURCE_CLASSES = frozenset({EvidenceClass.TRADE_REVIEW, EvidenceClass.VTIL_ARTIFACT, EvidenceClass.PNL_ATTRIBUTION, EvidenceClass.SHADOW_BOOK_OUTCOME})

ONE, ZERO = Decimal(1), Decimal(0)


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

    def observe(self, o: HealthObservation, *, resolver: LedgerEvidenceResolver, correlation_hint: str | None = None) -> HealthVerdict:
        ref = parse_evidence_ref(o.evidence_ref)
        if ref.evidence_class not in HEALTH_SOURCE_CLASSES:
            raise EvidenceError(f"{ref.evidence_class.value} is not a source event for strategy health")
        rec = self.evidence.admit(ref, resolver, correlation_hint=correlation_hint)
        if o.strategy_id not in rec.subjects:
            raise EvidenceError(f"evidence {ref} is not about {o.strategy_id!r}")
        if Environment(o.environment) is not rec.environment:
            raise EvidenceError(f"observation environment {o.environment.value} != evidence environment {rec.environment.value}")
        refs = self._refs.setdefault(o.strategy_id, [])
        canonical = str(ref)
        if canonical in refs:
            return self.verdict(o.strategy_id)   # the same fact observed again is not a new sample
        buf = self._obs.setdefault(o.strategy_id, [])
        buf.append(o)
        refs.append(canonical)
        del buf[:-self.window]
        for old in refs[:-self.window]:
            self.evidence.discard(old)
        del refs[:-self.window]
        return self.verdict(o.strategy_id)

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
