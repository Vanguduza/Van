"""Allocator V0: selection, never sizing (§15, TRD-ENH-036).

The allocator answers "given the other opportunities and the risk already in
the book, is this the best use of the next unit of capacity?" — a question VATI
has never had a place to ask. It ranks; the Risk Authority sizes.

**V0 ranks on deterministic evidence only.** `confidence.py` states its score
"never sizes a trade, and it never feeds the Risk Authority", and calls itself
`RULES_V0_UNCALIBRATED`. Under the sequential procedure, ranking decides which
candidate *reaches* the Risk Authority and therefore which consumes capacity —
so ranking on an uncalibrated score would let it decide which trade happens.
That is the indirect authority path the blueprint's rule 9 exists to catch.

`confidence_score` is carried on the candidate for owner display and is excluded
here. Confidence-weighted ranking waits for V1, behind the calibration gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from vati.arbiter.candidate import CandidateOpportunity
from vati.core.canonical import canonical_hash

ALLOCATION_POLICY_V0 = "allocator/0.1.0-deterministic"
ALLOCATION_POLICY_V1 = "allocator/1.0.0-evidence-weighted"

#: Inputs V0 is permitted to read. Asserted by contract test, because the
#: exclusion is the point rather than an implementation detail.
V0_RANKING_INPUTS = ("cost_multiple", "freshness", "regime_multiplier", "dependency_penalty")
V0_FORBIDDEN_INPUTS = ("confidence_score", "confidence_multiplier")

SELECTED = "SELECTED"
NOT_SELECTED = "NOT_SELECTED"


@dataclass(frozen=True)
class AllocationDecision:
    candidate_id: str
    rank: int
    decision: str
    allocation_utility: Decimal
    score_components: Mapping[str, str]
    explanation: tuple[str, ...] = ()
    correlation_multiplier: Decimal = Decimal("1")
    incremental_expected_shortfall: Optional[Decimal] = None
    overlap_penalty: Optional[Decimal] = None
    policy_version: str = ALLOCATION_POLICY_V0
    decision_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id, "rank": self.rank, "decision": self.decision,
            "allocation_utility": str(self.allocation_utility),
            "score_components": dict(self.score_components),
            "explanation": list(self.explanation),
            "correlation_multiplier": str(self.correlation_multiplier),
            "incremental_expected_shortfall": (
                str(self.incremental_expected_shortfall)
                if self.incremental_expected_shortfall is not None else None),
            "overlap_penalty": str(self.overlap_penalty) if self.overlap_penalty is not None else None,
            "policy_version": self.policy_version,
        }

    def sealed(self) -> "AllocationDecision":
        return AllocationDecision(**{**self.__dict__, "decision_hash": canonical_hash(self.as_dict())})


@dataclass(frozen=True)
class AllocationEpoch:
    allocation_epoch_id: str
    account_alias: str
    started_at_ms: int
    portfolio_snapshot_hash: str
    candidate_hashes: tuple[str, ...]
    policy_version: str = ALLOCATION_POLICY_V0

    def as_dict(self) -> dict:
        return {
            "allocation_epoch_id": self.allocation_epoch_id, "account_alias": self.account_alias,
            "started_at_ms": self.started_at_ms,
            "portfolio_snapshot_hash": self.portfolio_snapshot_hash,
            "candidate_hashes": list(self.candidate_hashes), "policy_version": self.policy_version,
        }


class OpportunityPortfolioAllocator:
    """Deterministic ranking. No `reserve_heat`, `allocate_size` or `preapprove`."""

    def __init__(
        self,
        *,
        dependency_fn=None,
        policy_version: str = ALLOCATION_POLICY_V0,
    ) -> None:
        #: Phase 7 supplies this; until then dependency is unknown, not zero.
        self.dependency_fn = dependency_fn
        self.policy_version = policy_version

    def _utility(self, c: CandidateOpportunity, *, now_ms: int) -> tuple[Decimal, dict[str, str], Decimal]:
        """Higher is better. Every term is deterministic and reduce-only in spirit."""
        # Cost multiple is expected move over round-trip cost: bigger is better,
        # and it is already the horizon arbiter's own admission criterion.
        cost = c.cost_multiple if c.cost_multiple > 0 else Decimal("0")
        freshness = c.freshness(now_ms)
        regime = c.regime_multiplier

        correlation = Decimal("1")
        dependency_penalty = Decimal("1")
        if self.dependency_fn is not None:
            dep = self.dependency_fn(c)
            correlation = getattr(dep, "correlation_multiplier", Decimal("1"))
            dependency_penalty = correlation

        utility = (cost * freshness * regime * dependency_penalty).quantize(Decimal("0.000001"))
        components = {
            "cost_multiple": str(cost), "freshness": str(freshness),
            "regime_multiplier": str(regime), "dependency_penalty": str(dependency_penalty),
        }
        return utility, components, correlation

    def rank(self, candidates: Sequence[CandidateOpportunity], *, now_ms: int) -> tuple[AllocationDecision, ...]:
        scored = []
        for c in candidates:
            utility, components, correlation = self._utility(c, now_ms=now_ms)
            scored.append((utility, c, components, correlation))

        # Deterministic tie-break, so two equal utilities cannot reorder between
        # runs and make a replay diverge.
        scored.sort(key=lambda row: (-row[0], row[1].valid_until_ms, row[1].symbol,
                                     row[1].strategy_id, row[1].candidate_id))

        out: list[AllocationDecision] = []
        for i, (utility, c, components, correlation) in enumerate(scored):
            explanation = [
                f"cost_multiple={components['cost_multiple']}",
                f"freshness={components['freshness']}",
                f"regime_multiplier={components['regime_multiplier']}",
            ]
            if self.dependency_fn is not None:
                explanation.append(f"dependency_penalty={components['dependency_penalty']}")
            out.append(AllocationDecision(
                candidate_id=c.candidate_id, rank=i, decision=SELECTED if utility > 0 else NOT_SELECTED,
                allocation_utility=utility, score_components=components,
                explanation=tuple(explanation), correlation_multiplier=correlation,
                policy_version=self.policy_version,
            ).sealed())
        return tuple(out)


class AllocatorV1(OpportunityPortfolioAllocator):
    """V0 plus the evidence that had to be built first (TRD-ENH-066).

    Adds edge floor, capital efficiency and execution quality — each of which
    now exists and is validated. Confidence is *still* excluded: §28's
    calibration gate has not been passed, and until it is, an uncalibrated
    probability must not decide which trade happens.
    """

    def _utility(self, c: CandidateOpportunity, *, now_ms: int):
        base, components, correlation = super()._utility(c, now_ms=now_ms)

        # A candidate with no edge floor is not penalised into oblivion; it is
        # simply not credited for evidence it does not have.
        edge = c.edge_floor_R if c.edge_floor_R is not None else Decimal("0")
        efficiency = c.expected_R_per_risk_day if c.expected_R_per_risk_day is not None else Decimal("0")
        execution = c.execution_quality if c.execution_quality is not None else Decimal("1")
        stability = c.regime_stability if c.regime_stability is not None else Decimal("1")

        # Only a *positive* edge floor adds anything: a wide interval around a
        # good-looking mean is not evidence (see capital_promotion.edge_floor_R).
        edge_term = Decimal("1") + max(Decimal("0"), edge)
        efficiency_term = Decimal("1") + max(Decimal("0"), efficiency)

        utility = (base * edge_term * efficiency_term
                   * max(Decimal("0"), min(Decimal("1"), execution))
                   * max(Decimal("0"), min(Decimal("1"), stability))).quantize(Decimal("0.000001"))
        components = dict(components) | {
            "edge_floor_R": str(edge), "expected_R_per_risk_day": str(efficiency),
            "execution_quality": str(execution), "regime_stability": str(stability),
        }
        return utility, components, correlation


__all__ = [
    "ALLOCATION_POLICY_V0", "ALLOCATION_POLICY_V1", "NOT_SELECTED", "SELECTED",
    "AllocatorV1",
    "V0_FORBIDDEN_INPUTS", "V0_RANKING_INPUTS",
    "AllocationDecision", "AllocationEpoch", "OpportunityPortfolioAllocator",
]
