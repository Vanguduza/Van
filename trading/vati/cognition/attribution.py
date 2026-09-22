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
from typing import Any, Mapping, Optional

from vati.cognition.shadow_book import EntryStatus, ShadowEntry
from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.risk.contracts import Direction

PRODUCER = "vati-pnl-attribution"
ATTRIBUTION_VERSION = "pnl-attribution/5.1.0"

ZERO = Decimal("0")
ONE_MULT = Decimal("1")

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


# ===========================================================================
# Decision quality, outcome, and the quadrant between them (GAP-F-003)
# ===========================================================================
"""Separating "was that a good decision" from "did that make money".

The attribution engine above splits *result* into buckets. This splits the
judgement itself, along the one axis a P&L number can never carry: whether the
decision was sound at the moment it was made, given only what was known then.

Those two axes give four quadrants, and the two off-diagonal ones are the
whole point:

* `BAD_DECISION_GOOD_OUTCOME` — the lucky win. This is the most expensive
  trade a system can take, because reinforcing it teaches the strategy to do
  it again, and the next one will not be lucky. It **must** reduce capsule
  health.
* `GOOD_DECISION_BAD_OUTCOME` — the honest loss. Sound thesis, disciplined
  risk, policy followed, blackout respected; the market disagreed. It **must
  not** reduce capsule health, because degrading a strategy for variance is
  how a system talks itself out of a real edge.

So `capsule_health` is fed from the *decision-quality* axis alone. The R axis
is still recorded, still surfaced and still drives expectancy tracking — it
just does not get to decide whether a strategy is allowed to keep trading.

Decision quality is assessed from four deterministic, ex-ante facts:

1. **thesis validity at entry** — did the claim have a falsifiable invalidation
   condition and was it still intact when the position opened;
2. **risk discipline** — was the approved risk inside the mandate, was the
   position protected, did the stop never widen;
3. **execution policy adherence** — did the order go through the router with a
   policy decision and land inside its own slippage tolerance;
4. **event blackout compliance** — was the position opened outside a tier-1
   blackout, or was the strategy event-certified.

Every one of those is knowable at decision time. None of them consults the
outcome, which is what makes the axis independent — and an axis that quietly
peeked at the result would collapse into the R axis and tell us nothing.
"""



class DecisionQuality(str, Enum):
    GOOD = "GOOD_DECISION"
    BAD = "BAD_DECISION"


class OutcomeQuality(str, Enum):
    GOOD = "GOOD_OUTCOME"
    BAD = "BAD_OUTCOME"


class Quadrant(str, Enum):
    GOOD_DECISION_GOOD_OUTCOME = "GOOD_DECISION_GOOD_OUTCOME"
    GOOD_DECISION_BAD_OUTCOME = "GOOD_DECISION_BAD_OUTCOME"
    BAD_DECISION_GOOD_OUTCOME = "BAD_DECISION_GOOD_OUTCOME"
    BAD_DECISION_BAD_OUTCOME = "BAD_DECISION_BAD_OUTCOME"

    @property
    def decision(self) -> DecisionQuality:
        return DecisionQuality.GOOD if self.value.startswith("GOOD_DECISION") else DecisionQuality.BAD

    @property
    def outcome(self) -> OutcomeQuality:
        return OutcomeQuality.GOOD if self.value.endswith("GOOD_OUTCOME") else OutcomeQuality.BAD

    @property
    def is_lucky(self) -> bool:
        """A result the process did not earn. The most dangerous kind."""
        return self is Quadrant.BAD_DECISION_GOOD_OUTCOME

    @property
    def is_unlucky(self) -> bool:
        return self is Quadrant.GOOD_DECISION_BAD_OUTCOME


#: Process defects. Any one of these makes the decision BAD, whatever R did.
PROCESS_FAULTS: dict[str, str] = {
    "THESIS_ABSENT": "no falsifiable thesis was sealed for this position",
    "THESIS_INVALID_AT_ENTRY": "the thesis was already invalidated when the position opened",
    "RISK_ABOVE_MANDATE": "approved risk exceeded the mandate ceiling",
    "RISK_UNPROTECTED": "the position was carried without a confirmed protective stop",
    "STOP_WIDENED": "a protective stop was moved further away",
    "EXECUTION_POLICY_IGNORED": "the order did not carry an execution policy decision",
    "EXECUTION_OUT_OF_TOLERANCE": "realised cost was outside the policy's own tolerance",
    "EVENT_BLACKOUT_BREACHED": "the position opened inside a tier-1 blackout uncertified",
}

#: R at or above which the outcome axis reads GOOD. Zero, not a target: the
#: outcome axis is a fact about money, not about ambition.
OUTCOME_GOOD_R = ZERO

#: Health floor the decision-quality axis may drive a capsule to. It bottoms
#: out rather than reaching zero, because zero is the arbiter's SKIP threshold
#: and standing a capsule down is a demotion decision with its own gate.
QUALITY_HEALTH_FLOOR = Decimal("0.2")

#: Weighted observations before the quality multiplier is allowed to bite. One
#: lucky win is an anecdote.
MIN_QUALITY_SAMPLES = 3


@dataclass(frozen=True)
class DecisionQualityInputs:
    """The four ex-ante facts. Every one is knowable before the outcome is."""

    trade_intent_id: str
    strategy_id: str
    #: 1. thesis validity at entry
    thesis_sealed: bool = False
    thesis_falsifiable: bool = False
    thesis_intact_at_entry: bool = True
    #: 2. risk discipline
    approved_risk_pct: Decimal = ZERO
    mandate_max_risk_pct: Decimal = ZERO
    protective_stop_confirmed: bool = True
    stop_widened: bool = False
    #: 3. execution policy adherence
    execution_policy_applied: bool = True
    cost_ratio: Optional[Decimal] = None
    max_cost_ratio: Decimal = Decimal("2")
    #: 4. event blackout compliance
    opened_in_blackout: bool = False
    event_certified: bool = False

    def faults(self) -> tuple[str, ...]:
        out: list[str] = []
        if not self.thesis_sealed:
            out.append("THESIS_ABSENT")
        elif not self.thesis_falsifiable:
            out.append("THESIS_ABSENT")
        elif not self.thesis_intact_at_entry:
            out.append("THESIS_INVALID_AT_ENTRY")
        if self.mandate_max_risk_pct > ZERO and self.approved_risk_pct > self.mandate_max_risk_pct:
            out.append("RISK_ABOVE_MANDATE")
        if not self.protective_stop_confirmed:
            out.append("RISK_UNPROTECTED")
        if self.stop_widened:
            out.append("STOP_WIDENED")
        if not self.execution_policy_applied:
            out.append("EXECUTION_POLICY_IGNORED")
        if self.cost_ratio is not None and self.cost_ratio > self.max_cost_ratio:
            out.append("EXECUTION_OUT_OF_TOLERANCE")
        if self.opened_in_blackout and not self.event_certified:
            out.append("EVENT_BLACKOUT_BREACHED")
        return tuple(out)

    @property
    def quality(self) -> DecisionQuality:
        return DecisionQuality.BAD if self.faults() else DecisionQuality.GOOD

    def body(self) -> dict[str, Any]:
        return {
            "thesis_sealed": self.thesis_sealed,
            "thesis_falsifiable": self.thesis_falsifiable,
            "thesis_intact_at_entry": self.thesis_intact_at_entry,
            "approved_risk_pct": str(self.approved_risk_pct),
            "mandate_max_risk_pct": str(self.mandate_max_risk_pct),
            "protective_stop_confirmed": self.protective_stop_confirmed,
            "stop_widened": self.stop_widened,
            "execution_policy_applied": self.execution_policy_applied,
            "cost_ratio": None if self.cost_ratio is None else str(self.cost_ratio),
            "opened_in_blackout": self.opened_in_blackout,
            "event_certified": self.event_certified,
        }


@dataclass(frozen=True)
class QuadrantVerdict:
    """One closed trade placed on both axes, with the faults that put it there."""

    trade_intent_id: str
    strategy_id: str
    symbol: str
    quadrant: Quadrant
    faults: tuple[str, ...]
    r_multiple: Decimal
    inputs: Mapping[str, Any]
    evidence_refs: tuple[str, ...]
    assessed_ms: int
    version: str = "decision-quadrant/5.1.0"

    @property
    def decision_quality(self) -> DecisionQuality:
        return self.quadrant.decision

    def body(self) -> dict[str, Any]:
        return {
            "trade_intent_id": self.trade_intent_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "quadrant": self.quadrant.value,
            "decision_quality": self.quadrant.decision.value,
            "outcome_quality": self.quadrant.outcome.value,
            "faults": list(self.faults),
            "fault_detail": [PROCESS_FAULTS[f] for f in self.faults],
            "r_multiple": str(self.r_multiple),
            "is_lucky": self.quadrant.is_lucky,
            "is_unlucky": self.quadrant.is_unlucky,
            "inputs": dict(sorted(self.inputs.items())),
            "evidence_refs": list(self.evidence_refs),
            "assessed_ms": self.assessed_ms,
            "version": self.version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


def classify(inputs: DecisionQualityInputs, *, r_multiple: Decimal) -> Quadrant:
    """The quadrant, from process on one axis and money on the other."""
    decision = inputs.quality
    outcome = OutcomeQuality.GOOD if r_multiple > OUTCOME_GOOD_R else OutcomeQuality.BAD
    return Quadrant(f"{decision.value}_{outcome.value}")


class DecisionQualityLedger:
    """Quadrant verdicts per strategy, and the capsule-health view of them.

    `health_multiplier` reads **only** the decision axis. The two properties
    the caller can rely on, and which the tests assert directly:

    * a `BAD_DECISION_GOOD_OUTCOME` lowers the multiplier — the lucky win is
      punished, not rewarded;
    * a `GOOD_DECISION_BAD_OUTCOME` leaves it where it was — the honest loss
      costs the strategy nothing.
    """

    def __init__(self, *, ledger=None, producer: str = "vati-decision-quality",
                 window: int = 60) -> None:
        self._ledger = ledger
        self._producer = producer
        self.window = window
        self._by_strategy: dict[str, list[QuadrantVerdict]] = {}
        self._by_trade: dict[str, QuadrantVerdict] = {}

    def record(self, inputs: DecisionQualityInputs, *, symbol: str,
               r_multiple: Decimal, now_ms: int,
               evidence_refs: tuple[str, ...] = ()) -> QuadrantVerdict:
        verdict = QuadrantVerdict(
            trade_intent_id=inputs.trade_intent_id,
            strategy_id=inputs.strategy_id,
            symbol=symbol,
            quadrant=classify(inputs, r_multiple=r_multiple),
            faults=inputs.faults(),
            r_multiple=r_multiple,
            inputs=inputs.body(),
            evidence_refs=evidence_refs,
            assessed_ms=now_ms,
        )
        rows = self._by_strategy.setdefault(inputs.strategy_id, [])
        rows.append(verdict)
        del rows[:-self.window]
        self._by_trade[inputs.trade_intent_id] = verdict
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.DECISION_QUADRANT, self._producer,
                verdict.body() | {"verdict_hash": verdict.digest},
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=inputs.trade_intent_id))
        return verdict

    def get(self, trade_intent_id: str) -> Optional[QuadrantVerdict]:
        return self._by_trade.get(trade_intent_id)

    def verdicts_for(self, strategy_id: str) -> list[QuadrantVerdict]:
        return list(self._by_strategy.get(strategy_id, ()))

    def health_multiplier(self, strategy_id: str) -> Decimal:
        """Capsule health from the decision axis only, bounded [floor, 1].

        1 until there is enough evidence to say otherwise, so an unconfigured
        or brand-new strategy is never penalised for silence — and, because the
        value is a *multiplier* consumed by `min()` downstream, returning 1 can
        only ever leave the existing health where it already was.
        """
        rows = self._by_strategy.get(strategy_id, [])
        if len(rows) < MIN_QUALITY_SAMPLES:
            return ONE_MULT
        good = sum(1 for v in rows if v.decision_quality is DecisionQuality.GOOD)
        share = Decimal(good) / Decimal(len(rows))
        return max(QUALITY_HEALTH_FLOOR, min(ONE_MULT, share)).quantize(Decimal("0.001"))

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for rows in self._by_strategy.values():
            for v in rows:
                counts[v.quadrant.value] = counts.get(v.quadrant.value, 0) + 1
        return {
            "by_quadrant": dict(sorted(counts.items())),
            "strategies": {
                sid: {
                    "trades": len(rows),
                    "health_multiplier": str(self.health_multiplier(sid)),
                    "by_quadrant": _counts(v.quadrant.value for v in rows),
                }
                for sid, rows in sorted(self._by_strategy.items())
            },
            "axis": "capsule_health is fed from decision quality only; R is recorded, not used",
        }
