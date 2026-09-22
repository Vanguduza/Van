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
            "SELECT id, text, due_at_unix, status, project_id, idempotency_key, source FROM reminders WHERE idempotency_key = ?",
            (body.idempotency_key,),
        )
        if existing:
            return {
                "id": existing["id"],
                "text": existing["text"],
                "due_at_unix": int(existing["due_at_unix"]),
                "status": existing["status"],
                "source": existing["source"],
                "replayed": True,
            }
        now = int(time.time())
        reminder_id = str(uuid.uuid4())
        source = (body.source or "owner_device").strip() or "owner_device"
        await self.store.execute(
            """
            INSERT INTO reminders(id, text, due_at_unix, status, project_id, idempotency_key, chain_follow_up_text, chain_follow_up_offset_seconds, source, created_at_unix, updated_at_unix)
            VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reminder_id,
                body.text,
                body.due_at_unix,
                body.project_id,
                body.idempotency_key,
                body.chain_follow_up_text,
                body.chain_follow_up_offset_seconds,
                source,
                now,
                now,
            ),
        )
        return {
            "id": reminder_id, "text": body.text, "due_at_unix": body.due_at_unix,
            "status": "OPEN", "source": source, "replayed": False,
        }

    async def list_open(self) -> list[dict]:
        rows = await self.store.fetchall(
            "SELECT id, text, due_at_unix, status, project_id, source FROM reminders WHERE status = 'OPEN' ORDER BY due_at_unix ASC"
        )
        return [
            {
                "id": r["id"],
                "text": r["text"],
                "due_at_unix": int(r["due_at_unix"]),
                "status": r["status"],
                "project_id": r["project_id"],
                "source": r["source"],
            }
            for r in rows
        ]

    async def get_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        """The row a caller who already knows its own idempotency key would find.

        GAP-F-001/002/005's mission-level readback (`verification/production.py`'s
        "reminder-readback" strategy) uses this to independently confirm a
        `reminder.create` execution without trusting the executor's own report: the
        mission's authority envelope carries the source command id, from which the same
        deterministic idempotency key (`f"reminder:{command_id}"`) the executor used can be
        reconstructed and looked up here, a plain read with no side effect.
        """
        row = await self.store.fetchone(
            "SELECT id, text, due_at_unix, status, project_id, source FROM reminders WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "text": row["text"],
            "due_at_unix": int(row["due_at_unix"]),
            "status": row["status"],
            "project_id": row["project_id"],
            "source": row["source"],
        }

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
