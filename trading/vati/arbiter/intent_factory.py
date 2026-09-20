"""The only path from a candidate to a TradeIntent (§11, TRD-ENH-031).

A candidate cannot reach the router. This is where it gains the ability to, and
it is called by the account coordinator *after* allocation — so the decision
about which opportunity gets scarce capacity has already been made and recorded.

The target-precedence rule here is the P1-TRADE-007 regression, restated as
code: the decision cycle used to discard a strategy's own targets and re-derive
one price from `expected_gross_move_pct`, silently replacing a scaled exit plan.
The candidate carries both fields, so the precedence has to be law rather than
a comment.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional, Sequence

from vati.arbiter.candidate import CandidateOpportunity
from vati.core.canonical import canonical_hash
from vati.risk.contracts import StrategyState, TradeIntent


class IntentFactoryError(ValueError):
    """A candidate that must not become an intent."""


def resolve_targets(candidate: CandidateOpportunity) -> tuple[Decimal, ...]:
    """Explicit targets win, always.

    `expected_gross_move_pct` is a fallback for a strategy that expressed no
    exit plan — never a replacement for one that did.
    """
    if candidate.targets:
        return tuple(candidate.targets)
    return ()


class IntentFactory:
    """Constructs the sealed `TradeIntent` for one selected candidate."""

    def __init__(self, *, producer: str = "vati-intent-factory") -> None:
        self.producer = producer

    def from_selected_candidate(
        self,
        candidate: CandidateOpportunity,
        *,
        requested_risk_pct: Decimal,
        idempotency_seed: str,
        allocation_decision_hash: str = "",
        correlation_multiplier: Decimal = Decimal("1"),
        now_ms: Optional[int] = None,
    ) -> TradeIntent:
        if candidate.stop is None and candidate.targets:
            # A candidate with targets but no stop has no risk denominator; the
            # Risk Authority would have to invent one.
            raise IntentFactoryError(f"{candidate.candidate_id}: targets without a stop")
        if not candidate.candidate_hash:
            raise IntentFactoryError(f"{candidate.candidate_id}: unsealed candidate")

        decision_body = {
            "candidate_hash": candidate.candidate_hash,
            "mtf_state_hash": candidate.mtf_state_hash,
            "allocation_decision_hash": allocation_decision_hash,
            "strategy_id": candidate.strategy_id,
            "capsule_hash": candidate.capsule_hash,
            "requested_risk_pct": str(requested_risk_pct),
        }
        decision_hash = canonical_hash(decision_body)

        return TradeIntent(
            trade_intent_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"vati:{decision_hash}")),
            idempotency_key=canonical_hash({"seed": idempotency_seed, "decision": decision_hash})[:32],
            account_alias=candidate.account_alias,
            venue=candidate.venue,
            symbol=candidate.symbol,
            direction=candidate.direction,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            strategy_state=StrategyState(candidate.strategy_state),
            entry=candidate.entry,
            stop=candidate.stop,
            requested_risk_pct=requested_risk_pct,
            decision_hash=decision_hash,
            market_snapshot_hash=candidate.mtf_state_hash,
            owner_authority="MANDATE",
            is_event_certified=candidate.is_event_certified,
            holds_over_weekend=candidate.holds_over_weekend,
            expected_gross_move_pct=candidate.expected_gross_move_pct,
            regime_multiplier=candidate.regime_multiplier,
            confidence_multiplier=candidate.confidence_multiplier,
            volatility_multiplier=candidate.volatility_multiplier,
            liquidity_multiplier=candidate.liquidity_multiplier,
            event_risk_multiplier=candidate.event_risk_multiplier,
            correlation_multiplier=correlation_multiplier,
        )


__all__ = ["IntentFactory", "IntentFactoryError", "resolve_targets"]
