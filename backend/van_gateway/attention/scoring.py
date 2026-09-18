"""Rev 1 §§10, 29 — Attention Engine 2.0 scoring.

The existing `AttentionEngine` is a good queue: it dedupes, it snoozes, it
respects quiet hours. What it cannot do is decide whether something deserved to
be in the queue at all, and §10's anti-noise requirements are entirely about
that decision.

So this is a scorer in front of the queue, not a replacement for it. It answers
one question — what should happen to this candidate — with one of five
dispositions, and records the answer either way. §29's *"suppress internally
recoverable transient errors"* only works if suppression is a recorded decision;
a candidate that silently never arrives is indistinguishable from a bug.

The scoring itself is arithmetic over declared fields, for the same reason the
capability router's is: a surprising notification should be explainable by
pointing at a number rather than by re-running a model.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.storage.db import Store


class Disposition(str, Enum):
    """§29's five outcomes."""

    SUPPRESS = "SUPPRESS"
    DIGEST = "DIGEST"
    PASSIVE_BADGE = "PASSIVE_BADGE"
    NORMAL_NOTIFICATION = "NORMAL_NOTIFICATION"
    URGENT_INTERRUPT = "URGENT_INTERRUPT"

    @property
    def interrupts(self) -> bool:
        return self in (
            Disposition.NORMAL_NOTIFICATION,
            Disposition.URGENT_INTERRUPT,
        )


class AttentionCandidate(BaseModel):
    """§29's candidate fields. Every one is a number the owner could argue with."""

    source: str
    dedupe_key: str
    summary: str = ""
    importance: float = 0.0
    urgency: float = 0.0
    actionability: float = 0.0
    novelty: float = 1.0
    owner_relevance: float = 0.5
    confidence: float = 0.5
    interruption_cost: float = 0.5
    expiry_ms: int | None = None
    related_mission_id: str | None = None
    #: §29 — an error VAN is already recovering from is not the owner's problem.
    internally_recoverable: bool = False

    @property
    def score(self) -> float:
        """Weighted, and interruption cost genuinely subtracts.

        A candidate that is important but cheap to raise should outrank one that
        is equally important and expensive; otherwise "important" becomes the
        only field that matters and everything claims it.
        """
        return round(
            self.importance * 0.30
            + self.urgency * 0.25
            + self.actionability * 0.20
            + self.owner_relevance * 0.15
            + self.novelty * 0.10
            - self.interruption_cost * 0.20,
            4,
        ) * self.confidence


#: DECISION (recorded, no owner input): these thresholds are a starting point,
#: not a measured optimum. §41's "nuisance alerts <5%" cannot be evaluated until
#: real candidates have been scored and the owner has reacted to them, so they
#: are deliberately conservative — it is easier to notice VAN being too quiet
#: than to undo having trained the owner to dismiss it.
URGENT_THRESHOLD = 0.75
NOTIFY_THRESHOLD = 0.55
BADGE_THRESHOLD = 0.35
DIGEST_THRESHOLD = 0.15


@dataclass(frozen=True)
class ScoredAttention:
    candidate_id: str
    disposition: Disposition
    score: float
    reason: str


class AttentionScorer:
    """Decides what reaches the owner, and records the decision either way."""

    #: DECISION (recorded): two notifications for the same dedupe key inside an
    #: hour is one notification. §29 asks for aggressive deduplication and
    #: "one decision request instead of repeated notifications".
    DEDUPE_WINDOW_MS = 60 * 60 * 1000

    def __init__(self, store: Store) -> None:
        self.store = store

    async def score(
        self,
        candidate: AttentionCandidate,
        *,
        quiet_hours: bool = False,
        now_ms: int | None = None,
    ) -> ScoredAttention:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        value = candidate.score

        disposition, reason = await self._decide(candidate, value, quiet_hours, now)
        candidate_id = f"attc_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO attention_candidates(
              candidate_id, source, dedupe_key, importance, urgency, actionability, novelty,
              owner_relevance, confidence, interruption_cost, score, disposition, reason,
              related_mission_id, summary, expiry_ms, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id, candidate.source, candidate.dedupe_key, candidate.importance,
                candidate.urgency, candidate.actionability, candidate.novelty,
                candidate.owner_relevance, candidate.confidence, candidate.interruption_cost,
                value, disposition.value, reason, candidate.related_mission_id,
                candidate.summary, candidate.expiry_ms, now,
            ),
        )
        return ScoredAttention(
            candidate_id=candidate_id, disposition=disposition, score=value, reason=reason
        )

    async def _decide(
        self, candidate: AttentionCandidate, value: float, quiet_hours: bool, now: int
    ) -> tuple[Disposition, str]:
        if candidate.internally_recoverable:
            # §29 — VAN handling its own transient failure is not news.
            return Disposition.SUPPRESS, "internally_recoverable"

        if candidate.expiry_ms is not None and candidate.expiry_ms <= now:
            return Disposition.SUPPRESS, "expired_before_delivery"

        recent = await self.store.fetchone(
            "SELECT COUNT(*) AS n FROM attention_candidates WHERE dedupe_key = ? "
            "AND created_at_ms >= ? AND disposition NOT IN ('SUPPRESS','DIGEST')",
            (candidate.dedupe_key, now - self.DEDUPE_WINDOW_MS),
        )
        if recent is not None and int(recent["n"]) > 0:
            # §29 — one decision request, not a stream of reminders about it.
            return Disposition.DIGEST, "duplicate_within_window"

        if value >= URGENT_THRESHOLD:
            return Disposition.URGENT_INTERRUPT, "score_above_urgent_threshold"

        if quiet_hours:
            # §29 — quiet hours hold everything except a genuine urgent
            # interrupt, which has already returned above.
            return Disposition.DIGEST, "quiet_hours"

        if value >= NOTIFY_THRESHOLD:
            return Disposition.NORMAL_NOTIFICATION, "score_above_notify_threshold"
        if value >= BADGE_THRESHOLD:
            return Disposition.PASSIVE_BADGE, "score_above_badge_threshold"
        if value >= DIGEST_THRESHOLD:
            return Disposition.DIGEST, "score_above_digest_threshold"
        return Disposition.SUPPRESS, "below_digest_threshold"

    async def metrics(
        self, *, window_ms: int | None = None, now_ms: int | None = None
    ) -> dict[str, Any]:
        """§41's proactive targets, computed rather than claimed.

        `measured` is False with a zero denominator: a system that has never
        scored a candidate has not achieved a 0% nuisance rate.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        since = now - (window_ms or 7 * 24 * 60 * 60 * 1000)
        rows = await self.store.fetchall(
            "SELECT disposition, dedupe_key FROM attention_candidates WHERE created_at_ms >= ?",
            (since,),
        )
        total = len(rows)
        interrupts = sum(
            1 for r in rows if Disposition(str(r["disposition"])).interrupts
        )
        duplicates = total - len({str(r["dedupe_key"]) for r in rows})
        suppressed = sum(1 for r in rows if str(r["disposition"]) == "SUPPRESS")
        return {
            "measured": total > 0,
            "candidates_scored": total,
            "interrupt_rate": (interrupts / total) if total else None,
            "duplicate_rate": (duplicates / total) if total else None,
            "suppression_rate": (suppressed / total) if total else None,
            "targets": {"duplicate_alerts": 0.01, "nuisance_alerts": 0.05},
            # §55 — nuisance rate needs owner reaction data that does not exist
            # yet, so it is reported as unmeasurable rather than as a pass.
            "nuisance_rate": None,
            "nuisance_rate_note": (
                "requires owner dismissal feedback; not yet collected"
            ),
        }


__all__ = [
    "BADGE_THRESHOLD",
    "DIGEST_THRESHOLD",
    "NOTIFY_THRESHOLD",
    "URGENT_THRESHOLD",
    "AttentionCandidate",
    "AttentionScorer",
    "Disposition",
    "ScoredAttention",
]
