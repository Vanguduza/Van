"""Capital Promotion Plane (§20, TRD-ENH-061..065).

The fast safety loop shrinks immediately and needs nobody's permission. This is
the slow loop, and it is deliberately not symmetric: it can *propose* a larger
ceiling and it can do nothing else. The proposal object has no mutation method,
no reference to a mandate, and no way to become one.

Two things make a proposal honest:

* **Edge floor, not mean R.** `+0.34R [-0.02, +0.70]` and `+0.34R [+0.22, +0.46]`
  are not the same proposition, and allocating capital from the mean treats them
  as if they were. The lower confidence bound is what gets proposed against.
* **Capital efficiency.** Two strategies at +0.3R are not equivalent if one ties
  up risk for two hours and the other for four days. `expected_R_per_risk_day`
  is what a portfolio actually compounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash

ZERO = Decimal("0")

#: A proposal is stale after this long: the evidence described a market.
DEFAULT_PROPOSAL_TTL_MS = 14 * 24 * 3_600_000

#: Below this many *live* trades a strategy has not earned a larger ceiling,
#: however good the backtest. Shadow evidence supports but never substitutes.
MIN_LIVE_SAMPLE = 30

#: No single amendment may more than double a ceiling. Compounding through
#: repeated small raises is visible in the ledger; one large jump is not.
MAX_INCREASE_FACTOR = Decimal("2")

PROPOSAL_POLICY_VERSION = "capital-promotion/1.0.0"


def edge_floor_R(r_multiples: Sequence[Decimal], *, confidence: float = 0.95) -> Optional[Decimal]:
    """Lower confidence bound on mean R.

    Normal-approximation one-sided bound. Deliberately simple and deterministic:
    a replay must reproduce it, and a conformal method that has not been
    calibrated out of sample does not belong in a capital decision.
    """
    n = len(r_multiples)
    if n < 2:
        return None
    xs = [float(r) for r in r_multiples]
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    se = math.sqrt(var / n)
    z = {0.90: 1.2816, 0.95: 1.6449, 0.99: 2.3263}.get(confidence, 1.6449)
    return Decimal(str(round(mean - z * se, 6)))


@dataclass(frozen=True)
class CapitalEfficiency:
    """What a unit of risk actually earns per unit of time it is occupied."""

    expected_R: Decimal
    mean_risk_days: Decimal
    fill_probability: Decimal = Decimal("1")
    financing_cost_R: Decimal = ZERO
    rollover_cost_R: Decimal = ZERO

    @property
    def expected_R_per_risk_day(self) -> Decimal:
        if self.mean_risk_days <= ZERO:
            return ZERO
        net = (self.expected_R * self.fill_probability
               - self.financing_cost_R - self.rollover_cost_R)
        return (net / self.mean_risk_days).quantize(Decimal("0.000001"))

    def as_dict(self) -> dict:
        return {k: str(v) for k, v in self.__dict__.items()} | {
            "expected_R_per_risk_day": str(self.expected_R_per_risk_day)}


@dataclass(frozen=True)
class CapitalBudgetProposal:
    """Evidence for a larger ceiling. It cannot apply itself."""

    proposal_id: str
    account_alias: str
    strategy_id: str
    strategy_version: str
    current_budget: Decimal
    proposed_budget: Decimal
    validation_hash: str
    live_sample: int
    shadow_sample: int
    expectancy_R: Decimal
    edge_floor_R: Decimal
    max_drawdown: Decimal
    tail_risk: Decimal
    capital_efficiency: Decimal
    execution_quality: Decimal = Decimal("1")
    strategy_return_correlation: Mapping[str, str] = field(default_factory=dict)
    regime_stability: Mapping[str, str] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    created_at_ms: int = 0
    expires_at_ms: int = 0
    policy_version: str = PROPOSAL_POLICY_VERSION
    proposal_hash: str = ""

    def as_dict(self) -> dict:
        out = {}
        for k, v in self.__dict__.items():
            if k == "proposal_hash":
                continue
            if isinstance(v, Decimal):
                out[k] = str(v)
            elif isinstance(v, tuple):
                out[k] = list(v)
            elif isinstance(v, Mapping):
                out[k] = dict(v)
            else:
                out[k] = v
        return out

    def sealed(self) -> "CapitalBudgetProposal":
        return CapitalBudgetProposal(**{**self.__dict__, "proposal_hash": canonical_hash(self.as_dict())})

    def live_at(self, now_ms: int) -> bool:
        return self.expires_at_ms == 0 or now_ms < self.expires_at_ms


@dataclass(frozen=True)
class ProposalVerdict:
    admissible: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"admissible": self.admissible, "reasons": list(self.reasons)}


def evaluate_proposal(
    p: CapitalBudgetProposal,
    *,
    now_ms: int,
    mandate_max_risk_per_trade: Decimal,
    platform_max_risk_per_trade: Decimal,
    min_live_sample: int = MIN_LIVE_SAMPLE,
    max_increase_factor: Decimal = MAX_INCREASE_FACTOR,
) -> ProposalVerdict:
    """Whether this is worth putting in front of the owner. Never applies it."""
    reasons: list[str] = []

    if p.proposal_hash != canonical_hash(p.as_dict()):
        reasons.append("proposal_seal_invalid")
    if not p.live_at(now_ms):
        reasons.append(f"proposal_expired_at:{p.expires_at_ms}")
    if not p.validation_hash:
        reasons.append("no_validation_certificate")
    if p.live_sample < min_live_sample:
        reasons.append(f"insufficient_live_sample:{p.live_sample}<{min_live_sample}")
    # The point of the edge floor: a wide interval is not evidence.
    if p.edge_floor_R <= ZERO:
        reasons.append(f"edge_floor_not_positive:{p.edge_floor_R}")
    if p.proposed_budget <= ZERO:
        reasons.append("proposed_budget_not_positive")
    if p.proposed_budget > mandate_max_risk_per_trade:
        reasons.append(
            f"proposed_budget_exceeds_mandate:{p.proposed_budget}>{mandate_max_risk_per_trade}")
    if p.proposed_budget > platform_max_risk_per_trade:
        reasons.append(
            f"proposed_budget_exceeds_platform:{p.proposed_budget}>{platform_max_risk_per_trade}")
    if p.current_budget > ZERO and p.proposed_budget > p.current_budget * max_increase_factor:
        reasons.append(
            f"increase_factor:{(p.proposed_budget / p.current_budget):.2f}>{max_increase_factor}")
    if p.capital_efficiency <= ZERO:
        reasons.append(f"capital_efficiency_not_positive:{p.capital_efficiency}")
    negative = sorted(k for k, v in p.regime_stability.items() if Decimal(str(v)) < 0)
    if negative:
        reasons.append("regime_instability:" + ",".join(negative))

    return ProposalVerdict(not reasons, tuple(reasons))


__all__ = [
    "DEFAULT_PROPOSAL_TTL_MS", "MAX_INCREASE_FACTOR", "MIN_LIVE_SAMPLE",
    "PROPOSAL_POLICY_VERSION",
    "CapitalBudgetProposal", "CapitalEfficiency", "ProposalVerdict",
    "edge_floor_R", "evaluate_proposal",
]
