from __future__ import annotations

import time
import uuid
from typing import Any

from van_gateway.models import AttentionItem, AttentionSeverity, AttentionState
from van_gateway.storage.db import Store


class AttentionEngine:
    """Deterministic owner attention system."""

    def __init__(self, store: Store, budget_per_hour: int = 12) -> None:
        self.store = store
        self.budget_per_hour = budget_per_hour

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
    ) -> AttentionItem:
        now = int(time.time())
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
