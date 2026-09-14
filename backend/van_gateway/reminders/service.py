from __future__ import annotations

import time
import uuid

from van_gateway.models import ReminderCreate
from van_gateway.storage.db import Store


class ReminderService:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def create(self, body: ReminderCreate) -> dict:
        existing = await self.store.fetchone(
            "SELECT id, text, due_at_unix, status, project_id, idempotency_key FROM reminders WHERE idempotency_key = ?",
            (body.idempotency_key,),
        )
        if existing:
            return {
                "id": existing["id"],
                "text": existing["text"],
                "due_at_unix": int(existing["due_at_unix"]),
                "status": existing["status"],
                "replayed": True,
            }
        now = int(time.time())
        reminder_id = str(uuid.uuid4())
        await self.store.execute(
            """
            INSERT INTO reminders(id, text, due_at_unix, status, project_id, idempotency_key, chain_follow_up_text, chain_follow_up_offset_seconds, created_at_unix, updated_at_unix)
            VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?)
            """,
            (
                reminder_id,
                body.text,
                body.due_at_unix,
                body.project_id,
                body.idempotency_key,
                body.chain_follow_up_text,
                body.chain_follow_up_offset_seconds,
                now,
                now,
            ),
        )
        return {"id": reminder_id, "text": body.text, "due_at_unix": body.due_at_unix, "status": "OPEN", "replayed": False}

    async def list_open(self) -> list[dict]:
        rows = await self.store.fetchall(
            "SELECT id, text, due_at_unix, status, project_id FROM reminders WHERE status = 'OPEN' ORDER BY due_at_unix ASC"
        )
        return [
            {
                "id": r["id"],
                "text": r["text"],
                "due_at_unix": int(r["due_at_unix"]),
                "status": r["status"],
                "project_id": r["project_id"],
            }
            for r in rows
        ]

    async def resolve(self, reminder_id: str) -> None:
        now = int(time.time())
        row = await self.store.fetchone(
            "SELECT id, chain_follow_up_text, chain_follow_up_offset_seconds FROM reminders WHERE id = ?",
            (reminder_id,),
        )
        if row is None:
            raise KeyError("reminder_not_found")
        await self.store.execute(
            "UPDATE reminders SET status = 'RESOLVED', updated_at_unix = ? WHERE id = ?",
            (now, reminder_id),
        )
        if row["chain_follow_up_text"] and row["chain_follow_up_offset_seconds"]:
            follow = ReminderCreate(
                text=row["chain_follow_up_text"],
                due_at_unix=now + int(row["chain_follow_up_offset_seconds"]),
                idempotency_key=f"chain:{reminder_id}",
            )
            await self.create(follow)

    async def cancel(self, reminder_id: str) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE reminders SET status = 'CANCELLED', updated_at_unix = ? WHERE id = ?",
            (now, reminder_id),
        )

    async def fire_due(self, now: int | None = None) -> list[dict]:
        now = now or int(time.time())
        rows = await self.store.fetchall(
            "SELECT id, text, due_at_unix FROM reminders WHERE status = 'OPEN' AND due_at_unix <= ?",
            (now,),
        )
        fired = []
        for row in rows:
            await self.store.execute(
                "UPDATE reminders SET status = 'FIRED', updated_at_unix = ? WHERE id = ?",
                (now, row["id"]),
            )
            fired.append({"id": row["id"], "text": row["text"], "due_at_unix": int(row["due_at_unix"])})
        return fired
