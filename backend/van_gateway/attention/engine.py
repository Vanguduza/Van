from __future__ import annotations

import time
import uuid
from typing import Any

from van_gateway.attention.scoring import AttentionCandidate, AttentionScorer, Disposition
from van_gateway.models import AttentionItem, AttentionSeverity, AttentionState
from van_gateway.storage.db import Store

#: How a severity maps onto the scorer's dimensions when a caller has not supplied its own
#: candidate. These are the numbers the old severity enum was standing in for, written out
#: so they can be argued with (§29 asks for exactly that).
SEVERITY_DIMENSIONS: dict[AttentionSeverity, dict[str, float]] = {
    AttentionSeverity.INFO: {"importance": 0.2, "urgency": 0.1, "actionability": 0.1},
    AttentionSeverity.FOLLOW_UP: {"importance": 0.5, "urgency": 0.3, "actionability": 0.6},
    AttentionSeverity.BLOCKER: {"importance": 0.8, "urgency": 0.7, "actionability": 0.8},
    AttentionSeverity.URGENT: {"importance": 0.95, "urgency": 0.95, "actionability": 0.9},
}


class AttentionEngine:
    """Deterministic owner attention system.

    P2-COH-002: this engine and `AttentionScorer` were two implementations of the same
    job. This one was live and decided nothing beyond a severity enum; the scorer had
    §29's five dispositions, real dedupe and a recorded reason for every decision, and was
    reached only by the understanding report's metrics.

    They are now one path rather than two implementations. The scorer makes the decision —
    it is the better of the two and retiring it in favour of the simpler one would have
    been a downgrade dressed as consolidation — and this engine remains what it always
    was: the durable owner-facing queue. Every upsert is scored, and the disposition is
    stored with the item, so what reaches the owner has a recorded reason.
    """

    def __init__(
        self,
        store: Store,
        budget_per_hour: int = 12,
        *,
        scorer: AttentionScorer | None = None,
    ) -> None:
        self.store = store
        self.budget_per_hour = budget_per_hour
        self.scorer = scorer or AttentionScorer(store)

    async def upsert(
        self,
        *,
        title: str,
        severity: AttentionSeverity,
        source: str,
        dedupe_key: str,
        project_id: str | None = None,
        payload: dict[str, Any] | None = None,
        state: AttentionState = AttentionState.OPEN,
        candidate: AttentionCandidate | None = None,
        quiet_hours: bool = False,
    ) -> AttentionItem:
        now = int(time.time())
        scored = await self.scorer.score(
            candidate or self.candidate_for(
                title=title, severity=severity, source=source, dedupe_key=dedupe_key
            ),
            quiet_hours=quiet_hours,
        )
        payload = {
            **(payload or {}),
            # The decision travels with the item, so "why did VAN interrupt me" and "why
            # did VAN stay quiet" are both answerable from the row.
            "attention_disposition": scored.disposition.value,
            "attention_score": scored.score,
            "attention_reason": scored.reason,
            "attention_candidate_id": scored.candidate_id,
        }
        existing = await self.store.fetchone(
            "SELECT id, title, severity, state, source, project_id, created_at_unix, updated_at_unix, dedupe_key, snooze_until_unix, payload_json FROM attention WHERE dedupe_key = ?",
            (dedupe_key,),
        )
        if existing:
            await self.store.execute(
                "UPDATE attention SET title = ?, severity = ?, state = ?, updated_at_unix = ?, payload_json = ? WHERE dedupe_key = ?",
                (title, severity.value, state.value, now, Store.dumps(payload or {}), dedupe_key),
            )
            return AttentionItem(
                id=existing["id"],
                title=title,
                severity=severity,
                state=state,
                source=source,
                project_id=project_id or existing["project_id"],
                created_at_unix=int(existing["created_at_unix"]),
                updated_at_unix=now,
                dedupe_key=dedupe_key,
                snooze_until_unix=existing["snooze_until_unix"],
                payload=payload or {},
            )
        item_id = str(uuid.uuid4())
        await self.store.execute(
            """
            INSERT INTO attention(id, title, severity, state, source, project_id, created_at_unix, updated_at_unix, dedupe_key, snooze_until_unix, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (item_id, title, severity.value, state.value, source, project_id, now, now, dedupe_key, Store.dumps(payload or {})),
        )
        return AttentionItem(
            id=item_id,
            title=title,
            severity=severity,
            state=state,
            source=source,
            project_id=project_id,
            created_at_unix=now,
            updated_at_unix=now,
            dedupe_key=dedupe_key,
            snooze_until_unix=None,
            payload=payload or {},
        )

    @staticmethod
    def candidate_for(
        *, title: str, severity: AttentionSeverity, source: str, dedupe_key: str
    ) -> AttentionCandidate:
        """The candidate a caller implied when it passed only a severity."""
        dimensions = SEVERITY_DIMENSIONS[severity]
        return AttentionCandidate(
            source=source, dedupe_key=dedupe_key, summary=title,
            owner_relevance=0.7, confidence=0.9, interruption_cost=0.3, **dimensions,
        )

    @staticmethod
    def interrupts(item: AttentionItem) -> bool:
        """Whether this item should reach the owner now, per its recorded disposition.

        An item whose disposition is missing — written before this was wired — is treated
        as interrupting, because under-notifying about something already in the queue is
        the worse failure and the honest reading of an absent decision is 'not decided'.
        """
        recorded = item.payload.get("attention_disposition")
        if not recorded:
            return True
        return Disposition(recorded).interrupts

    async def acknowledge(self, item_id: str) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE attention SET state = ?, updated_at_unix = ? WHERE id = ?",
            (AttentionState.ACKNOWLEDGED.value, now, item_id),
        )

    async def snooze(self, item_id: str, until_unix: int) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE attention SET state = ?, snooze_until_unix = ?, updated_at_unix = ? WHERE id = ?",
            (AttentionState.SNOOZED.value, until_unix, now, item_id),
        )

    async def mark_handled(self, item_id: str) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE attention SET state = ?, updated_at_unix = ? WHERE id = ?",
            (AttentionState.HANDLED.value, now, item_id),
        )

    async def list_open(self, *, now: int | None = None, quiet_hours: bool = False) -> list[AttentionItem]:
        now = now or int(time.time())
        rows = await self.store.fetchall(
            "SELECT id, title, severity, state, source, project_id, created_at_unix, updated_at_unix, dedupe_key, snooze_until_unix, payload_json FROM attention WHERE state NOT IN (?, ?)",
            (AttentionState.HANDLED.value, AttentionState.AUTO_RESOLVED.value),
        )
        items: list[AttentionItem] = []
        for row in rows:
            if row["state"] == AttentionState.SNOOZED.value and row["snooze_until_unix"] and int(row["snooze_until_unix"]) > now:
                continue
            # Mark stale if open > 7 days
            if now - int(row["created_at_unix"]) > 7 * 24 * 3600 and row["state"] == AttentionState.OPEN.value:
                await self.store.execute(
                    "UPDATE attention SET state = ?, updated_at_unix = ? WHERE id = ?",
                    (AttentionState.STALE.value, now, row["id"]),
                )
                state = AttentionState.STALE
            else:
                state = AttentionState(row["state"])
            severity = AttentionSeverity(row["severity"])
            if quiet_hours and severity not in (AttentionSeverity.URGENT, AttentionSeverity.BLOCKER):
                continue
            items.append(
                AttentionItem(
                    id=row["id"],
                    title=row["title"],
                    severity=severity,
                    state=state,
                    source=row["source"],
                    project_id=row["project_id"],
                    created_at_unix=int(row["created_at_unix"]),
                    updated_at_unix=int(row["updated_at_unix"]),
                    dedupe_key=row["dedupe_key"],
                    snooze_until_unix=row["snooze_until_unix"],
                    payload=__import__("json").loads(row["payload_json"]),
                )
            )
        items.sort(key=lambda i: ({"URGENT": 0, "BLOCKER": 1, "FOLLOW_UP": 2, "INFO": 3}[i.severity.value], -i.created_at_unix))
        # Attention budget: keep urgent/blocker always; truncate INFO beyond budget
        if len(items) > self.budget_per_hour:
            kept: list[AttentionItem] = []
            info_budget = max(0, self.budget_per_hour - sum(1 for i in items if i.severity != AttentionSeverity.INFO))
            info_seen = 0
            for item in items:
                if item.severity == AttentionSeverity.INFO:
                    if info_seen >= info_budget:
                        continue
                    info_seen += 1
                kept.append(item)
            items = kept
        return items
