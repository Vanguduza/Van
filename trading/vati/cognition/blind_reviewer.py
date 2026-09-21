"""Blind reviewer and reviewer canary (TRD-REV51-095, G4).

High-impact offline evaluations get a second opinion. The obvious way to do
that — hand model B model A's answer and ask if it agrees — has two failure
modes that make it worse than no review at all.

**Deference.** A reviewer that knows the author defers to it, or to the house
style, or to whichever model it believes is better. So the packet handed to a
reviewer carries the reasoning and nothing about its origin: no model id, no
role, no seal, no narrative tell. Reviewers see an argument, not a colleague.

**Rubber-stamping.** A reviewer that concurs with everything looks like a
reviewer and costs the same. The canary is the answer: at a deterministic
rate, the reviewer is handed a packet that has been deliberately broken in a
way any reading reviewer must catch — a REDUCE with no reduction, an ABSTAIN
citing nothing, a conclusion contradicting its own evidence. Missing one is
not a scoring event, it is a statement about the reviewer, and while its
canary health is bad *every* verdict it produced is marked UNTRUSTED
(INV-EVID-001).

Canary selection is hashed from the context, not sampled randomly. Replaying
the same month gives the same canaries in the same places, which is the only
way the reviewer's record is itself reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Sequence

from vati.cognition.contracts import (
    REASON_VOCABULARY,
    AssessmentRejected,
    CognitiveAssessment,
    Verdict,
)
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

PRODUCER = "vati-blind-reviewer"
REVIEWER_VERSION = "blind-reviewer/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: One packet in this many is a canary. High enough to build a record in a
#: reasonable number of reviews, low enough that review stays mostly real work.
CANARY_RATE_DENOMINATOR = 8

#: A reviewer must catch at least this fraction of canaries for its verdicts
#: to count. Not 1.0: a single miss over a long record is a bad day, not a
#: broken reviewer. Anything below it and the record is discarded wholesale.
MIN_CANARY_CATCH_RATE = Decimal("0.9")

#: Below this many canaries seen, canary health is UNPROVEN rather than good.
MIN_CANARIES_FOR_HEALTH = 10


class ReviewVerdict(str, Enum):
    CONCUR = "CONCUR"              # the reasoning supports the conclusion
    DISSENT = "DISSENT"            # it does not
    CANNOT_ASSESS = "CANNOT_ASSESS"  # the packet does not contain enough to judge


class CanaryHealth(str, Enum):
    HEALTHY = "HEALTHY"
    UNPROVEN = "UNPROVEN"          # too few canaries seen to say
    FAILING = "FAILING"            # verdicts from this reviewer are untrusted


class ReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class BlindPacket:
    """What a reviewer is allowed to see. Authorship is absent by construction."""

    packet_id: str
    context: Mapping[str, Any]
    verdict: str
    reason_codes: tuple[str, ...]
    risk_multiplier: str
    #: Present so a reviewer can judge the argument, with any authorship tell
    #: already removed by `blind_packet`.
    reasoning: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id, "context": dict(self.context),
            "verdict": self.verdict, "reason_codes": list(self.reason_codes),
            "risk_multiplier": self.risk_multiplier, "reasoning": self.reasoning,
        }


#: Fields that would tell a reviewer who wrote the thing.
_AUTHORSHIP_FIELDS = ("model_id", "role", "assessment_id", "seal", "produced_ms",
                      "contract_version", "confidence")


def blind_packet(assessment: CognitiveAssessment, context: Mapping[str, Any],
                 *, reasoning: str = "") -> BlindPacket:
    """Strip an assessment down to its argument.

    `confidence` is removed with the authorship fields. It is not identifying
    on its own, but it invites the reviewer to score the author's certainty
    instead of the reasoning, which is the same deference failure wearing a
    number.
    """
    return BlindPacket(
        packet_id=canonical_hash({"a": assessment.seal, "c": canonical_hash(dict(context))})[:32],
        context=dict(context),
        verdict=assessment.verdict.value,
        reason_codes=tuple(assessment.reason_codes),
        risk_multiplier=str(assessment.risk_multiplier),
        reasoning=reasoning or assessment.narrative,
    )


@dataclass(frozen=True)
class CanaryFlaw:
    """A defect planted in a packet, and what catching it looks like."""

    flaw_id: str
    description: str

    def body(self) -> dict[str, str]:
        return {"flaw_id": self.flaw_id, "description": self.description}


#: Flaws any reviewer that is reading must catch. Each is an internal
#: contradiction, not a market opinion, so dissent is not a matter of taste.
CANARY_FLAWS: tuple[CanaryFlaw, ...] = (
    CanaryFlaw("REDUCE_WITHOUT_REDUCTION",
               "the verdict says reduce and the multiplier is 1"),
    CanaryFlaw("ABSTAIN_WITH_SIZE",
               "the verdict says stand down and the multiplier is not zero"),
    CanaryFlaw("REASON_CONTRADICTS_VERDICT",
               "the reasons describe abundant, fresh evidence and the verdict cites thinness"),
    CanaryFlaw("UNSUPPORTED_CONCUR",
               "the context reports a tier-1 release inside the horizon and the verdict concurs"),
)


def plant_canary(packet: BlindPacket, flaw: CanaryFlaw) -> BlindPacket:
    """Break a packet in one named, catchable way."""
    if flaw.flaw_id == "REDUCE_WITHOUT_REDUCTION":
        return BlindPacket(**{**packet.__dict__, "verdict": Verdict.REDUCE.value,
                              "risk_multiplier": "1"})
    if flaw.flaw_id == "ABSTAIN_WITH_SIZE":
        return BlindPacket(**{**packet.__dict__, "verdict": Verdict.ABSTAIN.value,
                              "risk_multiplier": "0.6"})
    if flaw.flaw_id == "REASON_CONTRADICTS_VERDICT":
        return BlindPacket(**{**packet.__dict__, "verdict": Verdict.REDUCE.value,
                              "risk_multiplier": "0.5",
                              "reason_codes": ("EVIDENCE_THIN",),
                              "reasoning": "four hundred comparable episodes, all recent"})
    if flaw.flaw_id == "UNSUPPORTED_CONCUR":
        return BlindPacket(**{**packet.__dict__, "verdict": Verdict.CONCUR.value,
                              "risk_multiplier": "1", "reason_codes": (),
                              "context": {**dict(packet.context),
                                          "event_minutes_to_release": 20,
                                          "holding_horizon_minutes": 240}})
    raise ReviewError(f"unknown flaw {flaw.flaw_id}")


def select_canary(packet_id: str, *, salt: str = "rev51") -> Optional[CanaryFlaw]:
    """Deterministically decide whether this packet is a canary, and which.

    Hashed rather than sampled so replaying a month puts the canaries back in
    exactly the same places.
    """
    h = int(canonical_hash({"p": packet_id, "s": salt})[:16], 16)
    if h % CANARY_RATE_DENOMINATOR != 0:
        return None
    return CANARY_FLAWS[(h // CANARY_RATE_DENOMINATOR) % len(CANARY_FLAWS)]


@dataclass(frozen=True)
class Review:
    review_id: str
    packet_id: str
    reviewer_id: str
    verdict: ReviewVerdict
    reason_codes: tuple[str, ...]
    note: str
    was_canary: bool
    canary_flaw_id: str
    caught: Optional[bool]        # canaries only
    reviewed_ms: int
    trusted: bool = True
    reviewer_version: str = REVIEWER_VERSION

    def body(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id, "packet_id": self.packet_id,
            "reviewer_id": self.reviewer_id, "verdict": self.verdict.value,
            "reason_codes": list(self.reason_codes), "note": self.note,
            "was_canary": self.was_canary, "canary_flaw_id": self.canary_flaw_id,
            "caught": self.caught, "reviewed_ms": self.reviewed_ms,
            "trusted": self.trusted, "reviewer_version": self.reviewer_version,
        }


ReviewFn = Callable[[BlindPacket], Mapping[str, Any]]


class BlindReviewer:
    """Runs blind reviews, plants canaries, and tracks whether to believe them."""

    def __init__(self, *, reviewer_id: str, review_fn: ReviewFn, ledger=None,
                 salt: str = "rev51", producer: str = PRODUCER) -> None:
        self.reviewer_id = reviewer_id
        self._review_fn = review_fn
        self._ledger = ledger
        self._salt = salt
        self._producer = producer
        self._reviews: list[Review] = []
        self._seq = 0

    # ----------------------------------------------------------------- review
    def review(self, assessment: CognitiveAssessment, context: Mapping[str, Any],
               *, now_ms: int) -> Review:
        packet = blind_packet(assessment, context)
        flaw = select_canary(packet.packet_id, salt=self._salt)
        presented = plant_canary(packet, flaw) if flaw else packet

        try:
            raw = self._review_fn(presented)
        except Exception as exc:  # noqa: BLE001 — a reviewer outage is not an approval
            raw = {"verdict": ReviewVerdict.CANNOT_ASSESS.value,
                   "note": f"reviewer error: {exc}"[:200]}

        verdict = self._parse_verdict(raw)
        reasons = tuple(str(r).upper() for r in (raw.get("reason_codes") or ())
                        if str(r).upper() in REASON_VOCABULARY)
        caught = (verdict is ReviewVerdict.DISSENT) if flaw else None

        self._seq += 1
        review = Review(
            review_id=f"review-{now_ms}-{self._seq}",
            packet_id=presented.packet_id,
            reviewer_id=self.reviewer_id,
            verdict=verdict,
            reason_codes=reasons,
            note=str(raw.get("note", ""))[:500],
            was_canary=flaw is not None,
            canary_flaw_id=flaw.flaw_id if flaw else "",
            caught=caught,
            reviewed_ms=now_ms,
            trusted=self.canary_health() is not CanaryHealth.FAILING,
        )
        self._reviews.append(review)
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.BLIND_REVIEW, self._producer, review.body(),
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=assessment.context_hash))
        return review

    @staticmethod
    def _parse_verdict(raw: Mapping[str, Any]) -> ReviewVerdict:
        try:
            return ReviewVerdict(str(raw.get("verdict", "")).strip().upper())
        except ValueError:
            # An unreadable review is not agreement.
            return ReviewVerdict.CANNOT_ASSESS

    # ----------------------------------------------------------------- health
    @property
    def canaries_seen(self) -> int:
        return sum(1 for r in self._reviews if r.was_canary)

    @property
    def canaries_caught(self) -> int:
        return sum(1 for r in self._reviews if r.was_canary and r.caught)

    def catch_rate(self) -> Optional[Decimal]:
        if not self.canaries_seen:
            return None
        return Decimal(self.canaries_caught) / Decimal(self.canaries_seen)

    def canary_health(self) -> CanaryHealth:
        rate = self.catch_rate()
        if rate is None or self.canaries_seen < MIN_CANARIES_FOR_HEALTH:
            return CanaryHealth.UNPROVEN
        return CanaryHealth.HEALTHY if rate >= MIN_CANARY_CATCH_RATE else CanaryHealth.FAILING

    def trusted_reviews(self) -> list[Review]:
        """Real reviews, from a reviewer currently worth believing.

        When health is FAILING this is empty — not filtered down to the good
        ones. A reviewer that missed planted contradictions has told you
        nothing about the packets it passed.
        """
        if self.canary_health() is CanaryHealth.FAILING:
            return []
        return [r for r in self._reviews if not r.was_canary]

    def dissents(self) -> list[Review]:
        return [r for r in self.trusted_reviews() if r.verdict is ReviewVerdict.DISSENT]

    def report(self) -> dict[str, Any]:
        rate = self.catch_rate()
        return {
            "reviewer_version": REVIEWER_VERSION,
            "reviewer_id": self.reviewer_id,
            "reviews": len(self._reviews),
            "real_reviews": sum(1 for r in self._reviews if not r.was_canary),
            "canaries_seen": self.canaries_seen,
            "canaries_caught": self.canaries_caught,
            "catch_rate": None if rate is None else str(rate),
            "canary_health": self.canary_health().value,
            "verdicts_trusted": self.canary_health() is not CanaryHealth.FAILING,
            "dissents": len(self.dissents()),
        }
