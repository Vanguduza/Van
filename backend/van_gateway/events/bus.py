from __future__ import annotations

import json
import time
import uuid
from typing import Any

from van_gateway.observability import instruments
from van_gateway.storage.db import Store


class EventBus:
    """The device event stream, and — since migration 27 — its realtime envelope.

    Rev 1.5 §5.6 is deliberate about what this does not become. Rev 1.2 proposed a second
    realtime store; the existing table already has an Android reducer, a per-device cursor
    and months of rows on the other end of it, so the envelope is additive columns on the
    same table and the globally monotonic ``seq`` stays the cursor.

    **Per-device sequences are not introduced.** One global sequence with device-scoped
    *visibility* means a client can always tell "I have seen everything up to N". Two
    sequence spaces is how a replay gap becomes invisible: each space looks continuous while
    the join between them loses rows.
    """

    def __init__(self, store: Store, page_size: int = 100) -> None:
        self.store = store
        self.page_size = page_size

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        target_device_id: str | None = None,
        event_id: str | None = None,
        mission_id: str | None = None,
        command_id: str | None = None,
        correlation_id: str | None = None,
        occurred_at_ms: int | None = None,
    ) -> int:
        """§5.6 — additive. Existing callers passing ``(event_type, payload)`` are unchanged.

        ``target_device_id=None`` means broadcast, which is what every row written before
        migration 27 meant and still means.

        ``event_id`` is generated when the caller does not supply one, so de-duplication
        downstream never has to fall back to "this looks like the other one". A caller that
        supplies its own gets idempotency: publishing the same event twice after an ambiguous
        failure writes one row, because the unique index refuses the second.
        """
        now_ms = int(time.time() * 1000) if occurred_at_ms is None else int(occurred_at_ms)
        generated = event_id or f"evt_{uuid.uuid4().hex}"
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                INSERT INTO events(
                  event_type, payload_json, created_at_unix,
                  event_id, target_device_id, occurred_at_ms, mission_id, command_id, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                -- The unique index on event_id is partial (`WHERE event_id IS NOT NULL`),
                -- and SQLite matches a conflict target to a partial index only when the
                -- predicate is repeated here. Without it this raises
                -- "ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint"
                -- at runtime, which is what three existing tests said the first time.
                ON CONFLICT(event_id) WHERE event_id IS NOT NULL DO NOTHING
                """,
                (
                    event_type, Store.dumps(payload), now_ms // 1000,
                    generated, target_device_id, now_ms, mission_id, command_id, correlation_id,
                ),
            )
            await db.commit()
            if cur.rowcount == 0:
                existing = await db.execute(
                    "SELECT seq FROM events WHERE event_id = ?", (generated,)
                )
                row = await existing.fetchone()
                if row is not None:
                    return int(row["seq"])
            return int(cur.lastrowid)

    async def replay(self, device_id: str, after_seq: int) -> dict[str, Any]:
        # P3-OBS-002 — event-bus lag is Gate 11's name for the thing an owner
        # experiences as "VAN already did it but my phone still says pending".
        # Measured where it is actually observable: the gap between an event being
        # written and the device fetching it. Recorded below, once the rows are read.
        #
        # §5.6 — the visibility filter. A row addressed to another device is not this
        # device's business, and a row addressed to nobody is everyone's.
        async with self.store.connection() as db:
            # The ceiling is taken before the read rather than after. Reading first and then
            # advancing the cursor to whatever the table's maximum had become would skip any
            # row inserted in between — silently, and only for the device that happened to
            # poll at that moment.
            cur = await db.execute("SELECT COALESCE(MAX(seq), 0) AS ceiling FROM events")
            ceiling = int((await cur.fetchone())["ceiling"])
            cur = await db.execute(
                """
                SELECT seq, event_type, payload_json, created_at_unix,
                       event_id, target_device_id, occurred_at_ms, mission_id, command_id,
                       correlation_id
                  FROM events
                 WHERE seq > ? AND seq <= ?
                   AND (target_device_id IS NULL OR target_device_id = ?)
                 ORDER BY seq ASC
                 LIMIT ?
                """,
                (after_seq, ceiling, device_id, self.page_size),
            )
            rows = await cur.fetchall()

        events = [
            {
                "seq": int(r["seq"]),
                "event_type": r["event_type"],
                "payload": json.loads(r["payload_json"]),
                "created_at_unix": int(r["created_at_unix"]),
                "event_id": r["event_id"],
                "occurred_at_ms": int(r["occurred_at_ms"]) if r["occurred_at_ms"] is not None else None,
                "mission_id": r["mission_id"],
                "command_id": r["command_id"],
                "correlation_id": r["correlation_id"],
            }
            for r in rows
        ]
        truncated = len(events) == self.page_size
        # A partial page means everything up to the ceiling has been considered, including
        # the rows addressed to other devices. Leaving the cursor at the last *visible* row
        # would make this device rescan those forever.
        last = events[-1]["seq"] if truncated else max(ceiling, after_seq)
        now = int(time.time())
        for event in events:
            instruments.record_event_lag(
                event["event_type"], max(now - event["created_at_unix"], 0) * 1000.0
            )
        instruments.set_queue_depth("event_backlog", 0 if not events else len(events))
        await self.store.execute(
            """
            INSERT INTO event_cursors(device_id, last_seq, updated_at_unix) VALUES (?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET last_seq=excluded.last_seq, updated_at_unix=excluded.updated_at_unix
            """,
            (device_id, last, now),
        )
        return {
            "events": events,
            "next_cursor": last,
            "page_size": self.page_size,
            "truncated": truncated,
        }

    async def reset_cursor(self, device_id: str) -> None:
        now = int(time.time())
        await self.store.execute(
            """
            INSERT INTO event_cursors(device_id, last_seq, updated_at_unix) VALUES (?, 0, ?)
            ON CONFLICT(device_id) DO UPDATE SET last_seq=0, updated_at_unix=excluded.updated_at_unix
            """,
            (device_id, now),
        )
