"""Capsule health with environment-weighted samples and hysteresis (Rev 2 §25,
integration doc §22). Demotion is automatic; recovery/promotion never is."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.learning.boundary import LearningBoundary, LiveAdjustment, LiveTarget
from vati.learning.episodes import ENVIRONMENT_WEIGHT, Environment

ONE, ZERO = Decimal(1), Decimal(0)


@dataclass(frozen=True)
class HealthObservation:
    strategy_id: str
    environment: Environment
    r_multiple: Decimal
    process_ok: bool
    cost_ratio: Decimal            # realised / modelled cost (1 = as modelled)
    regime_fit: bool               # traded inside an eligible regime
    evidence_ref: str


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

    def observe(self, o: HealthObservation) -> HealthVerdict:
        buf = self._obs.setdefault(o.strategy_id, [])
        buf.append(o)
        del buf[:-self.window]
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
        adj = LiveAdjustment(LiveTarget.CAPSULE_HEALTH, strategy_id, min(ONE, v.health), v.state_recommendation, tuple(o.evidence_ref for o in self._obs[strategy_id][-5:]), v.weighted_samples)
        return LearningBoundary.check(adj)
