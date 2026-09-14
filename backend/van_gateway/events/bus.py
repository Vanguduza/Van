from __future__ import annotations

import time
from typing import Any

from van_gateway.storage.db import Store


class EventBus:
    def __init__(self, store: Store, page_size: int = 100) -> None:
        self.store = store
        self.page_size = page_size

    async def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        async with self.store.connection() as db:
            cur = await db.execute(
                "INSERT INTO events(event_type, payload_json, created_at_unix) VALUES (?, ?, ?)",
                (event_type, Store.dumps(payload), int(time.time())),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def replay(self, device_id: str, after_seq: int) -> dict[str, Any]:
        rows = await self.store.fetchall(
            "SELECT seq, event_type, payload_json, created_at_unix FROM events WHERE seq > ? ORDER BY seq ASC LIMIT ?",
            (after_seq, self.page_size),
        )
        events = [
            {
                "seq": int(r["seq"]),
                "event_type": r["event_type"],
                "payload": __import__("json").loads(r["payload_json"]),
                "created_at_unix": int(r["created_at_unix"]),
            }
            for r in rows
        ]
        last = events[-1]["seq"] if events else after_seq
        now = int(time.time())
        await self.store.execute(
            """
            INSERT INTO event_cursors(device_id, last_seq, updated_at_unix) VALUES (?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET last_seq=excluded.last_seq, updated_at_unix=excluded.updated_at_unix
            """,
            (device_id, last, now),
        )
        return {"events": events, "next_cursor": last, "page_size": self.page_size, "truncated": len(events) == self.page_size}

    async def reset_cursor(self, device_id: str) -> None:
        now = int(time.time())
        await self.store.execute(
            """
            INSERT INTO event_cursors(device_id, last_seq, updated_at_unix) VALUES (?, 0, ?)
            ON CONFLICT(device_id) DO UPDATE SET last_seq=0, updated_at_unix=excluded.updated_at_unix
            """,
            (device_id, now),
        )
