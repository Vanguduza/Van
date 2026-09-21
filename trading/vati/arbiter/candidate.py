"""CandidateOpportunity: an opportunity that cannot execute itself (§11, TRD-ENH-030).

`OpportunityEngine` builds a `TradeIntent` directly, so by the time an
opportunity exists it already carries a requested risk and a path to the Risk
Authority. That is fine when one symbol decides alone. It is the whole problem
when several symbols compete for one heat budget: whichever bar closes first
consumes capacity, and nothing ever compares the alternatives.

A candidate is deliberately **weaker** than an intent:

* no `requested_risk_pct`, no approved size, no stake;
* no `decision_hash` and no `idempotency_key`;
* no attribute the `ExecutionRouter` accepts.

Only `IntentFactory`, called by the account coordinator after allocation, turns
a selected candidate into a `TradeIntent`. The router's input contract does not
change, and nothing upstream of the Risk Authority gains reach it did not have.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional

from vati.core.canonical import canonical_hash
from vati.risk.contracts import Direction

#: Fields a candidate must never carry. Asserted by contract test, because the
#: guarantee is structural rather than conventional.
FORBIDDEN_CANDIDATE_FIELDS = (
    "requested_risk_pct", "approved_size", "approved_risk_pct",
    "decision_hash", "idempotency_key", "stake",
)


@dataclass(frozen=True)
class CandidateOpportunity:
    candidate_id: str
    account_alias: str
    venue: str
    symbol: str
    strategy_id: str
    strategy_version: str
    capsule_hash: str
    strategy_state: str

    generated_at_ms: int
    valid_from_ms: int
    valid_until_ms: int

    mtf_state_hash: str
    source_state_hashes: tuple[str, ...]
    feature_contract_hash: str

    direction: Direction
    entry: Decimal
    stop: Optional[Decimal]
    targets: tuple[Decimal, ...]
    horizon: str

    expected_gross_move_pct: Optional[Decimal] = None
    cost_multiple: Decimal = Decimal("0")
    #: Strategy-local ceiling from the signed/admitted capsule. This is evidence
    #: for IntentFactory; it is not a requested size and cannot reach execution
    #: without the account coordinator and Risk Authority.
    capsule_risk_ceiling: Decimal = Decimal("0.005")
    #: Carried for owner display only. Allocator V0 must not rank on it
    #: (blueprint Rev 1.1 §15 [OWNER-DEFAULT]); it is uncalibrated.
    confidence_score: Decimal = Decimal("0")
    regime_multiplier: Decimal = Decimal("1")
    confidence_multiplier: Decimal = Decimal("1")
    volatility_multiplier: Decimal = Decimal("1")
    liquidity_multiplier: Decimal = Decimal("1")
    event_risk_multiplier: Decimal = Decimal("1")

    edge_floor_R: Optional[Decimal] = None
    expected_R_per_risk_day: Optional[Decimal] = None
    regime_stability: Optional[Decimal] = None
    execution_quality: Optional[Decimal] = None
    estimated_fill_probability: Optional[Decimal] = None
    factor_exposures: tuple[str, ...] = ()

    holds_over_weekend: bool = False
    is_event_certified: bool = False
    meta_label: str = ""
    evidence_refs: tuple[str, ...] = ()
    candidate_hash: str = ""

    #: `account_alias + symbol + strategy_id + direction + setup identity`. A
    #: newer candidate for the same setup supersedes the older one rather than
    #: competing with it.
    @property
    def supersession_key(self) -> str:
        return "|".join((self.account_alias, self.symbol, self.strategy_id,
                         self.direction.value, str(self.entry), str(self.stop)))

    def fresh_at(self, now_ms: int) -> bool:
        return self.valid_from_ms <= now_ms < self.valid_until_ms

    def freshness(self, now_ms: int) -> Decimal:
        """1.0 at generation, 0.0 at expiry. Deterministic; no model involved."""
        span = self.valid_until_ms - self.valid_from_ms
        if span <= 0:
            return Decimal("0")
        remaining = max(0, min(span, self.valid_until_ms - now_ms))
        return (Decimal(remaining) / Decimal(span)).quantize(Decimal("0.0001"))

    def as_dict(self) -> dict:
        out: dict = {}
        for k, v in self.__dict__.items():
            if k == "candidate_hash":
                continue
            if isinstance(v, Decimal):
                out[k] = str(v)
            elif isinstance(v, Direction):
                out[k] = v.value
            elif isinstance(v, tuple):
                out[k] = [str(x) if isinstance(x, Decimal) else x for x in v]
            else:
                out[k] = v
        return out

    def sealed(self) -> "CandidateOpportunity":
        return CandidateOpportunity(**{**self.__dict__, "candidate_hash": canonical_hash(self.as_dict())})


def make_candidate_id(*, account_alias: str, symbol: str, strategy_id: str, state_hash: str, as_of_ms: int) -> str:
    """Deterministic across restart: the same economic decision keeps its id."""
    return "cand_" + uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"vati:candidate:{account_alias}:{symbol}:{strategy_id}:{state_hash}:{as_of_ms}",
    ).hex[:24]


__all__ = ["FORBIDDEN_CANDIDATE_FIELDS", "CandidateOpportunity", "make_candidate_id"]
