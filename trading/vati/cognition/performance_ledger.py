"""Cognitive performance ledger (TRD-REV51-103, G3b).

What a model says about itself is worth nothing here. INV-EVID-001 is the
whole design constraint: every number in this ledger is computed from shadow
entries that were sealed at T0 and resolved against outcomes the model never
saw. Confidence appears only as an input to calibration — never as a score in
its own right, because a model that is confidently wrong should be punished by
this ledger, not flattered by it.

Three things are measured, and they are deliberately different questions.

* **Divergence value.** Over the entries where cognition would have done
  something different, did the difference help? That is `mean_delta_r`, and it
  is the only number that speaks to whether cognition is worth having.
* **Calibration.** When the model said 0.9, was it right nine times in ten?
  Reported as a Brier score and as per-decile buckets, because one number
  hides which end of the range is broken.
* **Reliability.** How often did it refuse, abstain, or leave a comparison
  unresolved? A model that never diverges is cheap and useless, and looks
  perfect on delta alone.

`qualified` is evidence, not permission. It says a model has cleared a sample
threshold with a positive measured contribution. Promotion past SHADOW_LIVE is
gated elsewhere and by an owner; nothing in this module may be read as consent
(INV-LIVE-001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

from vati.cognition.contracts import Verdict
from vati.cognition.shadow_book import EntryStatus, ShadowEntry
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

PRODUCER = "vati-cognitive-performance"
LEDGER_VERSION = "cognitive-performance/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: Below this many resolved divergences, no qualification verdict is offered
#: at all. A run of six good calls is a run, not a record.
MIN_DIVERGENCES_FOR_QUALIFICATION = 50

#: The measured contribution a model must clear, in R per divergence. Above
#: zero by a margin on purpose: a contribution indistinguishable from noise is
#: not a reason to let a model near anything.
MIN_MEAN_DELTA_R = Decimal("0.02")

#: Worse than this and the model is miscalibrated regardless of its delta.
#: 0.25 is the Brier score of always saying 0.5, i.e. of claiming nothing.
MAX_BRIER_SCORE = Decimal("0.25")

CONFIDENCE_BUCKETS = (
    (Decimal("0.0"), Decimal("0.2")), (Decimal("0.2"), Decimal("0.4")),
    (Decimal("0.4"), Decimal("0.6")), (Decimal("0.6"), Decimal("0.8")),
    (Decimal("0.8"), Decimal("1.0")),
)


@dataclass(frozen=True)
class CalibrationBucket:
    low: Decimal
    high: Decimal
    n: int
    mean_confidence: Optional[Decimal]
    realised_hit_rate: Optional[Decimal]

    @property
    def gap(self) -> Optional[Decimal]:
        """Claimed minus realised. Positive means overconfident."""
        if self.mean_confidence is None or self.realised_hit_rate is None:
            return None
        return self.mean_confidence - self.realised_hit_rate

    def body(self) -> dict[str, Any]:
        return {
            "range": [str(self.low), str(self.high)], "n": self.n,
            "mean_confidence": None if self.mean_confidence is None else str(self.mean_confidence),
            "realised_hit_rate": None if self.realised_hit_rate is None else str(self.realised_hit_rate),
            "gap": None if self.gap is None else str(self.gap),
        }


@dataclass(frozen=True)
class ModelRecord:
    """One model's measured record. Nothing here is self-reported."""

    model_id: str
    assessments: int
    refusals: int
    abstentions: int
    concurrences: int
    divergences: int
    resolved_divergences: int
    expired: int
    total_delta_r: Decimal
    mean_delta_r: Optional[Decimal]
    hit_rate: Optional[Decimal]
    brier_score: Optional[Decimal]
    calibration: tuple[CalibrationBucket, ...]
    window_start_ms: int
    window_end_ms: int
    ledger_version: str = LEDGER_VERSION

    @property
    def divergence_rate(self) -> Optional[Decimal]:
        """A model that never diverges is cheap, useless, and perfect on delta."""
        if self.assessments == 0:
            return None
        return Decimal(self.divergences) / Decimal(self.assessments)

    @property
    def sample_sufficient(self) -> bool:
        return self.resolved_divergences >= MIN_DIVERGENCES_FOR_QUALIFICATION

    @property
    def qualified(self) -> bool:
        """Evidence of a positive measured contribution. Never permission."""
        if not self.sample_sufficient:
            return False
        if self.mean_delta_r is None or self.mean_delta_r < MIN_MEAN_DELTA_R:
            return False
        if self.brier_score is not None and self.brier_score > MAX_BRIER_SCORE:
            return False
        return True

    def qualification_detail(self) -> dict[str, Any]:
        reasons: list[str] = []
        if not self.sample_sufficient:
            reasons.append(
                f"sample {self.resolved_divergences} < {MIN_DIVERGENCES_FOR_QUALIFICATION}")
        if self.mean_delta_r is not None and self.mean_delta_r < MIN_MEAN_DELTA_R:
            reasons.append(f"mean_delta_r {self.mean_delta_r} < {MIN_MEAN_DELTA_R}")
        if self.mean_delta_r is None:
            reasons.append("no resolved divergence to measure")
        if self.brier_score is not None and self.brier_score > MAX_BRIER_SCORE:
            reasons.append(f"brier {self.brier_score} > {MAX_BRIER_SCORE}")
        return {
            "qualified": self.qualified,
            "means": "measured contribution only; promotion is owner-gated (INV-LIVE-001)",
            "blocking": reasons,
        }

    def body(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "ledger_version": self.ledger_version,
            "window": [self.window_start_ms, self.window_end_ms],
            "assessments": self.assessments,
            "refusals": self.refusals,
            "abstentions": self.abstentions,
            "concurrences": self.concurrences,
            "divergences": self.divergences,
            "resolved_divergences": self.resolved_divergences,
            "expired": self.expired,
            "divergence_rate": None if self.divergence_rate is None else str(self.divergence_rate),
            "total_delta_r": str(self.total_delta_r),
            "mean_delta_r": None if self.mean_delta_r is None else str(self.mean_delta_r),
            "hit_rate": None if self.hit_rate is None else str(self.hit_rate),
            "brier_score": None if self.brier_score is None else str(self.brier_score),
            "calibration": [b.body() for b in self.calibration],
            "qualification": self.qualification_detail(),
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class CognitivePerformanceLedger:
    """Scores models from resolved shadow entries and recorded refusals."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer
        self._refusals: dict[str, int] = {}

    def record_refusal(self, model_id: str, *, count: int = 1) -> None:
        """A result the normaliser rejected. Counted against the model, since
        an unparseable answer is a failure to answer."""
        self._refusals[model_id] = self._refusals.get(model_id, 0) + count

    def compile(self, entries: Sequence[ShadowEntry], *, model_id: str,
                now_ms: int) -> ModelRecord:
        mine = [e for e in entries if e.assessment.model_id == model_id]
        resolved = [e for e in mine if e.status is EntryStatus.RESOLVED]
        diverged_resolved = [e for e in resolved if e.diverged]
        deltas = [e.delta_r for e in diverged_resolved if e.delta_r is not None]

        total = sum(deltas, ZERO)
        mean = (total / Decimal(len(deltas))) if deltas else None
        wins = sum(1 for d in deltas if d > ZERO)
        hit_rate = (Decimal(wins) / Decimal(len(deltas))) if deltas else None

        brier, buckets = self._calibration(diverged_resolved)

        rec = ModelRecord(
            model_id=model_id,
            assessments=len(mine),
            refusals=self._refusals.get(model_id, 0),
            abstentions=sum(1 for e in mine if e.assessment.verdict is Verdict.ABSTAIN),
            concurrences=sum(1 for e in mine if e.assessment.verdict is Verdict.CONCUR),
            divergences=sum(1 for e in mine if e.diverged),
            resolved_divergences=len(diverged_resolved),
            expired=sum(1 for e in mine if e.status is EntryStatus.EXPIRED),
            total_delta_r=total,
            mean_delta_r=mean,
            hit_rate=hit_rate,
            brier_score=brier,
            calibration=buckets,
            window_start_ms=min((e.opened_ms for e in mine), default=0),
            window_end_ms=max((e.resolved_ms or e.opened_ms for e in mine), default=0),
        )
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.COGNITIVE_PERFORMANCE, self._producer, rec.body(),
                event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=model_id))
        return rec

    def compile_all(self, entries: Sequence[ShadowEntry], *, now_ms: int) -> list[ModelRecord]:
        models = sorted({e.assessment.model_id for e in entries} | set(self._refusals))
        return [self.compile(entries, model_id=m, now_ms=now_ms) for m in models]

    # ----------------------------------------------------------- calibration
    @staticmethod
    def _calibration(entries: Sequence[ShadowEntry]) -> tuple[Optional[Decimal],
                                                              tuple[CalibrationBucket, ...]]:
        """Brier score over divergences, plus per-bucket detail.

        The outcome being predicted is 'this divergence helps', scored 1 or 0
        against the confidence the model attached to the assessment. One number
        hides which end of the range is broken, so the buckets come too.
        """
        scored = [(e.assessment.confidence, ONE if (e.delta_r or ZERO) > ZERO else ZERO)
                  for e in entries if e.delta_r is not None]
        if not scored:
            return None, tuple(
                CalibrationBucket(lo, hi, 0, None, None) for lo, hi in CONFIDENCE_BUCKETS)

        brier = sum(((c - o) * (c - o) for c, o in scored), ZERO) / Decimal(len(scored))

        buckets: list[CalibrationBucket] = []
        for lo, hi in CONFIDENCE_BUCKETS:
            inside = [(c, o) for c, o in scored if lo <= c < hi or (hi == ONE and c == ONE)]
            if not inside:
                buckets.append(CalibrationBucket(lo, hi, 0, None, None))
                continue
            n = Decimal(len(inside))
            buckets.append(CalibrationBucket(
                lo, hi, len(inside),
                sum((c for c, _ in inside), ZERO) / n,
                sum((o for _, o in inside), ZERO) / n))
        return brier, tuple(buckets)
