"""ExecutionPolicyEngine (§22, TRD-ENH-051..053).

Extends the existing TCA path rather than replacing it. Today:

    ExecutionReceipt -> compute_tca -> LearningBroker -> BrokerExecutionProfile
        -> broker_liquidity -> MetaLabeler   (reduce-only)

That already changes future behaviour *defensively*. What is missing is the
choice dimension: nothing picks an order type or a wait from measured fill
quality, so "passive saves half a spread" stands in for the real trade-off.

Two boundaries make this safe:

* **It decides how, never whether.** The trade is already approved by the Risk
  Authority before a template is selected. This engine cannot cause an
  unapproved trade to exist.
* **Insufficient evidence falls back to the certified default**, which is what
  the router does today. A thin sample never produces an adventurous shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from statistics import median
from typing import Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash
from vati.execution.policy_templates import (
    CERTIFIED_DEFAULT,
    DEFAULT_TEMPLATES,
    DO_NOT_EXECUTE,
    LIMIT_AT_TOUCH,
    LIMIT_WITH_BOUNDED_CHASE,
    MARKET_WITH_SLIPPAGE_CAP,
    PASSIVE,
    PASSIVE_THEN_CROSS,
    ExecutionTemplate,
    template,
)

ZERO, ONE = Decimal("0"), Decimal("1")

#: Below this many observations for a bucket, the evidence is not evidence.
MIN_EVIDENCE_SAMPLE = 20

EVIDENCE_SUFFICIENT = "SUFFICIENT"
EVIDENCE_THIN = "THIN"
EVIDENCE_ABSENT = "ABSENT"

POLICY_VERSION = "execution-policy/1.0.0"


@dataclass(frozen=True)
class ExecutionBucket:
    """The dimensions execution quality actually varies along."""

    broker: str
    account_alias: str
    symbol: str
    session: str
    volatility_bucket: str
    event_proximity: str
    direction: str

    def key(self) -> str:
        return "|".join((self.broker, self.account_alias, self.symbol, self.session,
                         self.volatility_bucket, self.event_proximity, self.direction))


@dataclass
class ExecutionEvidence:
    """Measured outcomes for one bucket and one template."""

    samples: int = 0
    fills: int = 0
    partial_fills: int = 0
    cancels: int = 0
    slippage: list[Decimal] = field(default_factory=list)
    spread_captured: list[Decimal] = field(default_factory=list)
    post_fill_adverse: list[Decimal] = field(default_factory=list)
    time_to_fill_ms: list[int] = field(default_factory=list)
    non_fill_cost: list[Decimal] = field(default_factory=list)
    shortfall: list[Decimal] = field(default_factory=list)

    def observe(self, *, filled: bool, partial: bool = False, cancelled: bool = False,
                slippage: Decimal = ZERO, spread_captured: Decimal = ZERO,
                post_fill_adverse: Decimal = ZERO, time_to_fill_ms: int = 0,
                non_fill_cost: Decimal = ZERO, shortfall: Decimal = ZERO) -> None:
        self.samples += 1
        if filled:
            self.fills += 1
            self.slippage.append(slippage)
            self.spread_captured.append(spread_captured)
            self.post_fill_adverse.append(post_fill_adverse)
            self.time_to_fill_ms.append(time_to_fill_ms)
            self.shortfall.append(shortfall)
        else:
            self.non_fill_cost.append(non_fill_cost)
        if partial:
            self.partial_fills += 1
        if cancelled:
            self.cancels += 1

    @property
    def fill_probability(self) -> Optional[Decimal]:
        if self.samples == 0:
            return None
        return (Decimal(self.fills) / Decimal(self.samples)).quantize(Decimal("0.0001"))

    def _median(self, values: Sequence[Decimal]) -> Optional[Decimal]:
        return median(values) if values else None

    @property
    def median_slippage(self) -> Optional[Decimal]:
        return self._median(self.slippage)

    @property
    def median_adverse(self) -> Optional[Decimal]:
        return self._median(self.post_fill_adverse)

    @property
    def median_non_fill_cost(self) -> Optional[Decimal]:
        return self._median(self.non_fill_cost)

    def expected_shortfall_estimate(self) -> Optional[Decimal]:
        """Fill cost weighted by fill probability, plus the cost of not filling.

        The term the half-a-spread approximation omits: a passive order that
        never fills is not free.
        """
        p = self.fill_probability
        if p is None:
            return None
        fill_cost = self._median(self.shortfall) or ZERO
        miss_cost = self._median(self.non_fill_cost) or ZERO
        return (p * fill_cost + (ONE - p) * miss_cost).quantize(Decimal("0.00000001"))


@dataclass(frozen=True)
class ExecutionPolicyDecision:
    candidate_id: str
    bucket_key: str
    template_id: str
    template_version: str
    evidence_state: str
    evidence_sample_size: int
    estimated_fill_probability: Optional[Decimal] = None
    expected_slippage: Optional[Decimal] = None
    expected_adverse_selection: Optional[Decimal] = None
    expected_non_fill_cost: Optional[Decimal] = None
    expected_shortfall: Optional[Decimal] = None
    reason: str = ""
    policy_version: str = POLICY_VERSION
    decision_hash: str = ""

    def as_dict(self) -> dict:
        d = {k: (str(v) if isinstance(v, Decimal) else v)
             for k, v in self.__dict__.items() if k != "decision_hash"}
        return d

    def sealed(self) -> "ExecutionPolicyDecision":
        return ExecutionPolicyDecision(**{**self.__dict__, "decision_hash": canonical_hash(self.as_dict())})

    @property
    def entry_type(self) -> str:
        """What the router is actually handed."""
        allowed = template(self.template_id).allowed_entry_types
        return allowed[0] if allowed else "NONE"


class ExecutionPolicyEngine:
    def __init__(
        self,
        *,
        templates: Mapping[str, ExecutionTemplate] | None = None,
        min_sample: int = MIN_EVIDENCE_SAMPLE,
        default_template_id: str = CERTIFIED_DEFAULT,
    ) -> None:
        self.templates = dict(templates or DEFAULT_TEMPLATES)
        self.min_sample = min_sample
        self.default_template_id = default_template_id
        self._evidence: dict[tuple[str, str], ExecutionEvidence] = {}

    # -- evidence ----------------------------------------------------------

    def evidence(self, bucket: ExecutionBucket, template_id: str) -> ExecutionEvidence:
        return self._evidence.setdefault((bucket.key(), template_id), ExecutionEvidence())

    def observe(self, bucket: ExecutionBucket, template_id: str, **outcome) -> None:
        self.evidence(bucket, template_id).observe(**outcome)

    # -- selection ---------------------------------------------------------

    def select(
        self,
        *,
        candidate_id: str,
        bucket: ExecutionBucket,
        event_state: str = "NONE",
        urgent: bool = False,
    ) -> ExecutionPolicyDecision:
        """Pick a template from measured quality, or fall back safely."""
        # A blackout cancels regardless of evidence: the template's own bound.
        if event_state in ("PRE_BLACKOUT", "POST_BLACKOUT"):
            return self._decision(candidate_id, bucket, DO_NOT_EXECUTE, EVIDENCE_ABSENT, 0,
                                  reason=f"event_state:{event_state}")

        scored: list[tuple[Decimal, str, ExecutionEvidence]] = []
        for tid in self.templates:
            if tid == DO_NOT_EXECUTE:
                continue
            ev = self._evidence.get((bucket.key(), tid))
            if ev is None or ev.samples < self.min_sample:
                continue
            est = ev.expected_shortfall_estimate()
            if est is None:
                continue
            scored.append((est, tid, ev))

        if not scored:
            # Exactly what the router does today. An unlearned path is unchanged.
            total = sum(e.samples for (k, _t), e in self._evidence.items() if k == bucket.key())
            state = EVIDENCE_THIN if total else EVIDENCE_ABSENT
            return self._decision(candidate_id, bucket, self.default_template_id, state, total,
                                  reason=f"insufficient evidence (<{self.min_sample} per template)")

        if urgent:
            # Urgency narrows the field rather than widening the bounds.
            scored = [row for row in scored
                      if row[1] in (LIMIT_AT_TOUCH, LIMIT_WITH_BOUNDED_CHASE, MARKET_WITH_SLIPPAGE_CAP)] or scored

        scored.sort(key=lambda row: (row[0], row[1]))   # lowest cost, deterministic tie-break
        best_cost, best_id, ev = scored[0]
        return self._decision(candidate_id, bucket, best_id, EVIDENCE_SUFFICIENT, ev.samples,
                              fill_probability=ev.fill_probability,
                              slippage=ev.median_slippage, adverse=ev.median_adverse,
                              non_fill=ev.median_non_fill_cost, shortfall=best_cost,
                              reason="lowest measured expected shortfall")

    def _decision(self, candidate_id, bucket, template_id, state, samples, *,
                  fill_probability=None, slippage=None, adverse=None, non_fill=None,
                  shortfall=None, reason="") -> ExecutionPolicyDecision:
        t = template(template_id, self.templates)
        return ExecutionPolicyDecision(
            candidate_id=candidate_id, bucket_key=bucket.key(), template_id=t.template_id,
            template_version=t.version, evidence_state=state, evidence_sample_size=samples,
            estimated_fill_probability=fill_probability, expected_slippage=slippage,
            expected_adverse_selection=adverse, expected_non_fill_cost=non_fill,
            expected_shortfall=shortfall, reason=reason,
        ).sealed()


__all__ = [
    "EVIDENCE_ABSENT", "EVIDENCE_SUFFICIENT", "EVIDENCE_THIN", "MIN_EVIDENCE_SAMPLE",
    "POLICY_VERSION", "ExecutionBucket", "ExecutionEvidence", "ExecutionPolicyDecision",
    "ExecutionPolicyEngine",
]
