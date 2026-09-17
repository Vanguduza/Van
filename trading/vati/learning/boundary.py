"""Learning boundary (Rev 4 improvement over integration doc §23).

The learning engine may change exactly three live-affecting quantities, all
reduce-only or demote-only: capsule health (→ multiplier ≤ 1 / demotion),
regime probabilities (→ multiplier ≤ 1), broker execution profile (→ liquidity
multiplier ≤ 1 / eligibility). Any other target raises. Promotion, mandates,
ceilings, capsule logic, instruments, credentials and leverage are outside."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

ONE, ZERO = Decimal(1), Decimal(0)


class LearningBoundaryError(RuntimeError):
    pass


class LiveTarget(str, Enum):
    CAPSULE_HEALTH = "CAPSULE_HEALTH"
    REGIME_PROBABILITY = "REGIME_PROBABILITY"
    BROKER_PROFILE = "BROKER_PROFILE"


FORBIDDEN_TARGETS = frozenset({"MANDATE", "PLATFORM_CEILINGS", "CAPSULE_LOGIC", "CAPSULE_STATE_PROMOTION", "INSTRUMENT_LIST", "BROKER_CREDENTIALS", "LEVERAGE", "RISK_POLICY", "EXECUTION_POLICY", "PRODUCTION_MODEL_ALIAS"})


@dataclass(frozen=True)
class LiveAdjustment:
    target: LiveTarget
    key: str                 # strategy_id / regime label / broker:symbol:session
    multiplier: Decimal      # ≤ 1
    demote_to: str | None = None   # DEGRADED | SHADOW | SUSPENDED (capsule health only)
    evidence_refs: tuple[str, ...] = ()
    environment_weighted_samples: Decimal = ZERO


class LearningBoundary:
    MIN_WEIGHTED_SAMPLES = Decimal("30")

    @classmethod
    def check(cls, adj: LiveAdjustment) -> LiveAdjustment:
        if str(adj.target) in FORBIDDEN_TARGETS or adj.target not in LiveTarget:
            raise LearningBoundaryError(f"learning may not touch {adj.target}")
        if adj.multiplier > ONE or adj.multiplier < ZERO:
            raise LearningBoundaryError("learning multipliers are reduce-only within [0, 1]")
        if adj.demote_to is not None and adj.target is not LiveTarget.CAPSULE_HEALTH:
            raise LearningBoundaryError("only capsule health may demote")
        if adj.demote_to is not None and adj.demote_to not in ("DEGRADED", "SHADOW", "SUSPENDED"):
            raise LearningBoundaryError("demotion targets are DEGRADED|SHADOW|SUSPENDED; promotion is never a learning output")
        if adj.environment_weighted_samples < cls.MIN_WEIGHTED_SAMPLES and adj.multiplier < ONE:
            raise LearningBoundaryError(f"insufficient environment-weighted samples ({adj.environment_weighted_samples} < {cls.MIN_WEIGHTED_SAMPLES}) for a live adjustment")
        if not adj.evidence_refs:
            raise LearningBoundaryError("a live adjustment must cite evidence artifact hashes")
        return adj

    @staticmethod
    def attempt(target: str, **_: object) -> None:
        """Explicit refusal path for anything outside the three live targets."""
        raise LearningBoundaryError(f"learning may not touch {target}; use the owner-signed promotion path")
