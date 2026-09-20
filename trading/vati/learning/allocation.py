"""AllocationEpisode (§16, TRD-ENH-038).

Selection policy is a hypothesis, so it has to be falsifiable. Without this,
VAN could spend a year taking +0.3R setups while rejecting +1.8R alternatives
and never find out.

The hindsight guard is the same one `missed.py` applies: ex-ante validity is
frozen at decision time, and the later path only scores the outcome, over the
setup's own horizon window. In particular — **a Risk Authority rejection is not
allocator regret**, even if price later moved favourably. The gate was right;
recording it as a miss would teach the system to route around its own risk
controls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash

ZERO = Decimal("0")

#: Counterfactual outcomes are simulated, so they carry reduced weight in any
#: aggregate, exactly like `counterfactual.py`.
SIMULATED_EVIDENCE_WEIGHT = Decimal("0.2")

#: Why a candidate did not trade. Only the first is the allocator's business.
NOT_SELECTED = "NOT_SELECTED"
RISK_REJECTED = "RISK_REJECTED"
ROUTER_REFUSED = "ROUTER_REFUSED"
EXPIRED = "EXPIRED"
SUPERSEDED = "SUPERSEDED"

#: Rejections that are *not* allocator regret, whatever the price did next.
NOT_ALLOCATOR_REGRET = frozenset({RISK_REJECTED, ROUTER_REFUSED, SUPERSEDED})


@dataclass(frozen=True)
class RejectedOutcome:
    candidate_id: str
    rejection_reason: str
    #: R the setup would have produced, scored over its own horizon window.
    counterfactual_r: Optional[Decimal] = None
    ex_ante_valid: bool = True
    horizon_window_ms: int = 0

    def as_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "rejection_reason": self.rejection_reason,
                "counterfactual_r": str(self.counterfactual_r) if self.counterfactual_r is not None else None,
                "ex_ante_valid": self.ex_ante_valid, "horizon_window_ms": self.horizon_window_ms}


@dataclass(frozen=True)
class AllocationEpisode:
    allocation_epoch_id: str
    account_alias: str
    as_of_ms: int
    portfolio_snapshot_hash: str
    ranking_policy_version: str
    selected_candidate_ids: tuple[str, ...]
    rejected: tuple[RejectedOutcome, ...]
    ranking_features: Mapping[str, object] = field(default_factory=dict)
    realised_selected_outcomes: Mapping[str, str] = field(default_factory=dict)
    environment: str = "BACKTEST"
    evidence_weight: Decimal = SIMULATED_EVIDENCE_WEIGHT
    episode_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "allocation_epoch_id": self.allocation_epoch_id, "account_alias": self.account_alias,
            "as_of_ms": self.as_of_ms, "portfolio_snapshot_hash": self.portfolio_snapshot_hash,
            "ranking_policy_version": self.ranking_policy_version,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "rejected": [r.as_dict() for r in self.rejected],
            "ranking_features": dict(self.ranking_features),
            "realised_selected_outcomes": dict(self.realised_selected_outcomes),
            "environment": self.environment, "evidence_weight": str(self.evidence_weight),
        }

    def sealed(self) -> "AllocationEpisode":
        return AllocationEpisode(**{**self.__dict__, "episode_hash": canonical_hash(self.as_dict())})

    # -- the question this exists to answer --------------------------------

    def regret_R(self, selected_r: Mapping[str, Decimal]) -> Decimal:
        """How much better the best *legitimately* passed-over alternative was.

        Only `NOT_SELECTED` counts. A candidate the Risk Authority refused is
        excluded however well it would have done — otherwise the metric teaches
        the allocator to prefer candidates the risk gate would have stopped.
        """
        taken = max((selected_r.get(cid, ZERO) for cid in self.selected_candidate_ids), default=ZERO)
        passed = [r.counterfactual_r for r in self.rejected
                  if r.rejection_reason == NOT_SELECTED
                  and r.ex_ante_valid
                  and r.counterfactual_r is not None]
        if not passed:
            return ZERO
        best_passed = max(passed)
        return max(ZERO, best_passed - taken)

    def excluded_from_regret(self) -> tuple[str, ...]:
        return tuple(r.candidate_id for r in self.rejected
                     if r.rejection_reason in NOT_ALLOCATOR_REGRET)


__all__ = [
    "EXPIRED", "NOT_ALLOCATOR_REGRET", "NOT_SELECTED", "RISK_REJECTED",
    "ROUTER_REFUSED", "SIMULATED_EVIDENCE_WEIGHT", "SUPERSEDED",
    "AllocationEpisode", "RejectedOutcome",
]
