"""Learning boundary (Rev 4 improvement over integration doc §23; C5 evidence).

The learning engine may change exactly three live-affecting quantities, all
reduce-only or demote-only: capsule health (→ multiplier ≤ 1 / demotion),
regime probabilities (→ multiplier ≤ 1), broker execution profile (→ liquidity
multiplier ≤ 1 / eligibility). Any other target raises. Promotion, mandates,
ceilings, capsule logic, instruments, credentials and leverage are outside.

EXPERIENCE asks the question. EVIDENCE establishes what happened. AUTHORITY
decides what may change. Every adjustment cites typed, hashed VATI evidence
(`vati-evidence:<CLASS>:<64-hex>`, see `vati.learning.evidence`) that an
`EvidenceResolver` must resolve; the environment-weighted sample count is
recomputed from the resolved, de-duplicated evidence and never taken from the
caller. Hindsight/OpenViking/DEIL output is never live evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from vati.learning.evidence import EvidenceClass, EvidenceError, EvidenceResolver, EvidenceSet

ONE, ZERO = Decimal(1), Decimal(0)


class LearningBoundaryError(RuntimeError):
    pass


class LiveTarget(str, Enum):
    CAPSULE_HEALTH = "CAPSULE_HEALTH"
    REGIME_PROBABILITY = "REGIME_PROBABILITY"
    BROKER_PROFILE = "BROKER_PROFILE"


# A-MIN-VAN (reviewer D2): each live target admits only the evidence classes
# that are facts about it. The broker execution profile learns from execution
# facts (TCA) only; a shadow-book decision never carries execution weight.
TARGET_EVIDENCE_CLASSES: dict[LiveTarget, frozenset[EvidenceClass]] = {
    LiveTarget.BROKER_PROFILE: frozenset({EvidenceClass.TCA_RECORD}),
    LiveTarget.CAPSULE_HEALTH: frozenset({EvidenceClass.TRADE_REVIEW, EvidenceClass.VTIL_ARTIFACT,
                                          EvidenceClass.PNL_ATTRIBUTION, EvidenceClass.SHADOW_BOOK_OUTCOME}),
    LiveTarget.REGIME_PROBABILITY: frozenset({EvidenceClass.TRADE_REVIEW, EvidenceClass.VTIL_ARTIFACT,
                                              EvidenceClass.PNL_ATTRIBUTION, EvidenceClass.SHADOW_BOOK_OUTCOME}),
}
assert set(TARGET_EVIDENCE_CLASSES) == set(LiveTarget), "every live target needs an evidence-class allowlist"

FORBIDDEN_TARGETS = frozenset({"MANDATE", "PLATFORM_CEILINGS", "CAPSULE_LOGIC", "CAPSULE_STATE_PROMOTION", "INSTRUMENT_LIST", "BROKER_CREDENTIALS", "LEVERAGE", "RISK_POLICY", "EXECUTION_POLICY", "PRODUCTION_MODEL_ALIAS"})
DEMOTION_TARGETS = ("DEGRADED", "SHADOW", "SUSPENDED")


@dataclass(frozen=True)
class LiveAdjustmentProposal:
    """What learning would like to change, with the evidence it cites. It has
    no sample count: the boundary computes that from resolved evidence."""
    target: LiveTarget
    key: str
    multiplier: Decimal
    demote_to: Optional[str] = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class LiveAdjustment:
    """An adjustment the boundary has admitted (or is asked to re-check).

    `environment_weighted_samples` is DEPRECATED as caller authority: it is kept
    for compatibility with direct constructors, but `LearningBoundary.check`
    recomputes it from resolved evidence and rejects any mismatch. Build new
    adjustments with `LearningBoundary.admit(LiveAdjustmentProposal, resolver)`."""
    target: LiveTarget
    key: str                 # strategy_id / regime label / broker:symbol:session
    multiplier: Decimal      # ≤ 1
    demote_to: str | None = None   # DEGRADED | SHADOW | SUSPENDED (capsule health only)
    evidence_refs: tuple[str, ...] = ()   # vati-evidence:<CLASS>:<64-hex> only
    environment_weighted_samples: Decimal = ZERO


class LearningBoundary:
    MIN_WEIGHTED_SAMPLES = Decimal("30")

    @classmethod
    def _check_shape(cls, target: object, multiplier: Decimal, demote_to: Optional[str]) -> None:
        if str(target) in FORBIDDEN_TARGETS or target not in LiveTarget:
            raise LearningBoundaryError(f"learning may not touch {target}")
        if multiplier > ONE or multiplier < ZERO:
            raise LearningBoundaryError("learning multipliers are reduce-only within [0, 1]")
        if demote_to is not None and target is not LiveTarget.CAPSULE_HEALTH:
            raise LearningBoundaryError("only capsule health may demote")
        if demote_to is not None and demote_to not in DEMOTION_TARGETS:
            raise LearningBoundaryError("demotion targets are DEGRADED|SHADOW|SUSPENDED; promotion is never a learning output")

    @classmethod
    def _evidence(cls, target: LiveTarget, key: str, refs: tuple[str, ...], resolver: Optional[EvidenceResolver]) -> tuple[EvidenceSet, Decimal]:
        if not refs:
            raise LearningBoundaryError("a live adjustment must cite evidence artifact hashes")
        try:
            ev = EvidenceSet.resolve(refs, resolver, subject=key)
        except EvidenceError as e:
            raise LearningBoundaryError(f"live evidence rejected: {e}") from None
        allowed = TARGET_EVIDENCE_CLASSES[target]
        wrong = sorted({r.evidence_class.value for r in ev.records if r.evidence_class not in allowed})
        if wrong:
            raise LearningBoundaryError(f"live evidence rejected: {target.value} does not learn from {wrong} "
                                        f"(allowed: {sorted(c.value for c in allowed)})")
        # Execution facts from simulated environments weigh zero for the broker profile.
        return ev, ev.weighted_samples(execution_facts=target is LiveTarget.BROKER_PROFILE)

    @classmethod
    def _check_samples(cls, samples: Decimal, multiplier: Decimal) -> None:
        if samples < cls.MIN_WEIGHTED_SAMPLES and multiplier < ONE:
            raise LearningBoundaryError(f"insufficient environment-weighted samples ({samples} < {cls.MIN_WEIGHTED_SAMPLES}) for a live adjustment")

    @classmethod
    def admit(cls, proposal: LiveAdjustmentProposal, resolver: EvidenceResolver) -> LiveAdjustment:
        """Proposal → resolver → EvidenceSet → recomputed samples → boundary."""
        cls._check_shape(proposal.target, proposal.multiplier, proposal.demote_to)
        ev, samples = cls._evidence(proposal.target, proposal.key, tuple(proposal.evidence_refs), resolver)
        cls._check_samples(samples, proposal.multiplier)
        return LiveAdjustment(proposal.target, proposal.key, proposal.multiplier, proposal.demote_to, ev.refs, samples)

    @classmethod
    def check(cls, adj: LiveAdjustment, resolver: Optional[EvidenceResolver] = None) -> LiveAdjustment:
        """Re-check a directly constructed adjustment. Without a resolver there
        is no evidence authority, so the adjustment is refused."""
        cls._check_shape(adj.target, adj.multiplier, adj.demote_to)
        _, samples = cls._evidence(adj.target, adj.key, tuple(adj.evidence_refs), resolver)
        if adj.environment_weighted_samples != samples:
            raise LearningBoundaryError(f"caller-supplied environment_weighted_samples {adj.environment_weighted_samples} != {samples} recomputed from resolved evidence")
        cls._check_samples(samples, adj.multiplier)
        return adj

    @staticmethod
    def attempt(target: str, **_: object) -> None:
        """Explicit refusal path for anything outside the three live targets."""
        raise LearningBoundaryError(f"learning may not touch {target}; use the owner-signed promotion path")
