"""P&L attribution engine (TRD-REV51-101, G3b).

"Did that trade work" is not one question. A trade can be a good decision that
executed badly, a bad decision rescued by a fill, or a fine decision eaten by
costs, and a single P&L number tells you none of that. Worse, when a model is
being evaluated, an undecomposed result lets any story be told afterwards.

So the engine splits realised result into four buckets that sum *exactly* to
it, with no residual and no smoothing:

* **edge** — what the decision itself was worth: decision price to exit.
* **execution** — what the fill gave away or won against the decision price.
* **cost** — commissions, spread and fees, as charged.
* **carry** — swap and funding, as credited or debited.

The sum identity is checked, not assumed. If the four do not reconstruct the
realised figure the engine raises rather than quietly parking the difference
in a residual bucket, because a residual is where attribution errors go to be
forgotten.

The counterfactual bucket is kept strictly apart from those four. The shadow
book (100) can only evaluate a size change on the same entry and exit, so the
cognition delta is reported with `basis = SIZE_ONLY`, is labelled
counterfactual, and is never added into the realised sum. A number that mixes
a measurement with an estimate is a measurement no longer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.cognition.shadow_book import EntryStatus, ShadowEntry
from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.risk.contracts import Direction

PRODUCER = "vati-pnl-attribution"
ATTRIBUTION_VERSION = "pnl-attribution/5.1.0"

ZERO = Decimal("0")

#: Absolute money tolerance when checking that the buckets reconstruct the
#: realised figure. Non-zero only to absorb Decimal quantisation in the
#: caller's own inputs; anything larger is a real defect.
SUM_TOLERANCE = Decimal("0.000001")


class AttributionError(RuntimeError):
    pass


class CounterfactualBasis(str, Enum):
    """What a counterfactual number is actually entitled to claim."""

    SIZE_ONLY = "SIZE_ONLY"        # same entry, same exit, different size
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class TradeFacts:
    """Everything needed to decompose one closed trade. All venue-reported."""

    trade_intent_id: str
    symbol: str
    strategy_id: str
    direction: Direction
    quantity: Decimal
    decision_price: Decimal        # the price the decision was made against
    fill_price: Decimal            # where it actually filled
    exit_price: Decimal            # where it actually closed
    money_risk: Decimal            # initial risk in account currency; the R unit
    costs: Decimal = ZERO          # commissions + spread paid, positive number
    carry: Decimal = ZERO          # swap/funding, signed
    opened_ms: int = 0
    closed_ms: int = 0

    def __post_init__(self) -> None:
        if self.money_risk <= ZERO:
            raise AttributionError(
                f"{self.trade_intent_id} has money_risk {self.money_risk}; R is undefined")
        if self.quantity <= ZERO:
            raise AttributionError(f"{self.trade_intent_id} has quantity {self.quantity}")

    @property
    def sign(self) -> Decimal:
        return Decimal("1") if self.direction is Direction.LONG else Decimal("-1")


@dataclass(frozen=True)
class Attribution:
    """One trade, decomposed. The four realised buckets sum to realised."""

    trade_intent_id: str
    symbol: str
    strategy_id: str
    edge_money: Decimal
    execution_money: Decimal
    cost_money: Decimal
    carry_money: Decimal
    realised_money: Decimal
    money_risk: Decimal
    #: Counterfactual, kept out of the sum on purpose.
    cognition_delta_r: Optional[Decimal]
    counterfactual_basis: CounterfactualBasis
    model_id: str = ""
    attribution_version: str = ATTRIBUTION_VERSION

    def _r(self, money: Decimal) -> Decimal:
        return money / self.money_risk

    @property
    def edge_r(self) -> Decimal:
        return self._r(self.edge_money)

    @property
    def execution_r(self) -> Decimal:
        return self._r(self.execution_money)

    @property
    def cost_r(self) -> Decimal:
        return self._r(self.cost_money)

    @property
    def carry_r(self) -> Decimal:
        return self._r(self.carry_money)

    @property
    def realised_r(self) -> Decimal:
        return self._r(self.realised_money)

    @property
    def dominant_bucket(self) -> str:
        """Which bucket explains most of the result, by absolute size."""
        buckets = {
            "edge": abs(self.edge_money), "execution": abs(self.execution_money),
            "cost": abs(self.cost_money), "carry": abs(self.carry_money),
        }
        return max(sorted(buckets), key=lambda k: buckets[k])

    def body(self) -> dict[str, Any]:
        return {
            "trade_intent_id": self.trade_intent_id,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "money_risk": str(self.money_risk),
            "realised": {"money": str(self.realised_money), "r": str(self.realised_r)},
            "buckets": {
                "edge": {"money": str(self.edge_money), "r": str(self.edge_r)},
                "execution": {"money": str(self.execution_money), "r": str(self.execution_r)},
                "cost": {"money": str(self.cost_money), "r": str(self.cost_r)},
                "carry": {"money": str(self.carry_money), "r": str(self.carry_r)},
            },
            "dominant_bucket": self.dominant_bucket,
            "counterfactual": {
                "cognition_delta_r": None if self.cognition_delta_r is None else str(self.cognition_delta_r),
                "basis": self.counterfactual_basis.value,
                "is_realised": False,
                "model_id": self.model_id,
            },
            "attribution_version": self.attribution_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class AttributionEngine:
    """Decomposes closed trades; optionally joins the shadow counterfactual."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer
        self._by_trade: dict[str, Attribution] = {}

    def attribute(self, facts: TradeFacts, *,
                  shadow_entry: Optional[ShadowEntry] = None,
                  now_ms: Optional[int] = None) -> Attribution:
        s, q = facts.sign, facts.quantity

        # What the decision was worth, independent of how it filled.
        edge = s * (facts.exit_price - facts.decision_price) * q
        # What execution gave away (negative) or won (positive) against it.
        execution = s * (facts.decision_price - facts.fill_price) * q
        cost = -facts.costs
        carry = facts.carry

        realised = s * (facts.exit_price - facts.fill_price) * q - facts.costs + facts.carry
        if abs((edge + execution + cost + carry) - realised) > SUM_TOLERANCE:
            # A residual bucket is where attribution errors go to be forgotten.
            raise AttributionError(
                f"{facts.trade_intent_id}: buckets sum to "
                f"{edge + execution + cost + carry} but realised is {realised}")

        delta_r: Optional[Decimal] = None
        basis = CounterfactualBasis.NOT_APPLICABLE
        model_id = ""
        if shadow_entry is not None:
            if shadow_entry.status is not EntryStatus.RESOLVED:
                raise AttributionError(
                    f"shadow entry {shadow_entry.entry_id} is {shadow_entry.status.value}; "
                    "only a resolved comparison may be attributed")
            delta_r = shadow_entry.delta_r
            basis = CounterfactualBasis.SIZE_ONLY
            model_id = shadow_entry.assessment.model_id

        att = Attribution(
            trade_intent_id=facts.trade_intent_id, symbol=facts.symbol,
            strategy_id=facts.strategy_id, edge_money=edge, execution_money=execution,
            cost_money=cost, carry_money=carry, realised_money=realised,
            money_risk=facts.money_risk, cognition_delta_r=delta_r,
            counterfactual_basis=basis, model_id=model_id)
        self._by_trade[facts.trade_intent_id] = att

        if self._ledger is not None:
            t = now_ms if now_ms is not None else facts.closed_ms
            self._ledger.append(make_event(
                EventKind.PNL_ATTRIBUTION, self._producer, att.body(),
                event_time_ms=t, received_time_ms=t,
                correlation_id=facts.trade_intent_id))
        return att

    def get(self, trade_intent_id: str) -> Optional[Attribution]:
        return self._by_trade.get(trade_intent_id)

    def portfolio_summary(self) -> dict[str, Any]:
        """Totals by bucket. The counterfactual is reported separately and is
        never folded into the realised total."""
        atts = list(self._by_trade.values())
        if not atts:
            return {"trades": 0, "attribution_version": ATTRIBUTION_VERSION}
        totals = {
            "edge_r": sum((a.edge_r for a in atts), ZERO),
            "execution_r": sum((a.execution_r for a in atts), ZERO),
            "cost_r": sum((a.cost_r for a in atts), ZERO),
            "carry_r": sum((a.carry_r for a in atts), ZERO),
        }
        cf = [a.cognition_delta_r for a in atts if a.cognition_delta_r is not None]
        return {
            "attribution_version": ATTRIBUTION_VERSION,
            "trades": len(atts),
            "realised_r": str(sum((a.realised_r for a in atts), ZERO)),
            "buckets_r": {k: str(v) for k, v in sorted(totals.items())},
            "dominant_bucket_counts": _counts(a.dominant_bucket for a in atts),
            "counterfactual": {
                "compared": len(cf),
                "cognition_delta_r": str(sum(cf, ZERO)) if cf else None,
                "basis": CounterfactualBasis.SIZE_ONLY.value if cf else CounterfactualBasis.NOT_APPLICABLE.value,
                "is_realised": False,
            },
        }


def _counts(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))
