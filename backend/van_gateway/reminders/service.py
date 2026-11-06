from __future__ import annotations

import time
import uuid

from van_gateway.models import ReminderCreate, AttentionSeverity
from van_gateway.storage.db import Store


class ReminderConflict(ValueError):
    """The original request or current state conflicts with this mutation."""


class ReminderService:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    async def _create_in_transaction(db, body: ReminderCreate, now: int) -> dict:
        source = (body.source or "owner_device").strip() or "owner_device"
        fields = (body.text, body.due_at_unix, body.project_id,
                  body.chain_follow_up_text, body.chain_follow_up_offset_seconds, source)
        existing = await (await db.execute(
            "SELECT * FROM reminders WHERE idempotency_key=?", (body.idempotency_key,)
        )).fetchone()
        if existing is not None:
            original = tuple(existing[k] for k in (
                "text", "due_at_unix", "project_id", "chain_follow_up_text",
                "chain_follow_up_offset_seconds", "source"))
            if original != fields:
                raise ReminderConflict("reminder_idempotency_conflict")
            return {"id": existing["id"], "text": existing["text"],
                    "due_at_unix": int(existing["due_at_unix"]), "status": existing["status"],
                    "source": existing["source"], "replayed": True}
        reminder_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO reminders(id,text,due_at_unix,status,project_id,idempotency_key,"
            "chain_follow_up_text,chain_follow_up_offset_seconds,source,created_at_unix,updated_at_unix) "
            "VALUES(?,?,?,'OPEN',?,?,?,?,?,?,?)",
            (reminder_id,body.text,body.due_at_unix,body.project_id,body.idempotency_key,
             body.chain_follow_up_text,body.chain_follow_up_offset_seconds,source,now,now),
        )
        return {"id": reminder_id, "text": body.text, "due_at_unix": body.due_at_unix,
                "status": "OPEN", "source": source, "replayed": False}

    async def create(self, body: ReminderCreate) -> dict:
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            result = await self._create_in_transaction(db, body, int(time.time()))
            await db.commit()
            return result

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
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,))).fetchone()
            if row is None:
                raise KeyError("reminder_not_found")
            if row["status"] == "RESOLVED":
                return
            if row["status"] not in {"OPEN", "FIRED"}:
                raise ReminderConflict("reminder_state_conflict")
            await db.execute("UPDATE reminders SET status='RESOLVED',updated_at_unix=? WHERE id=?", (now,reminder_id))
            if row["chain_follow_up_text"] and row["chain_follow_up_offset_seconds"]:
                follow = ReminderCreate(text=row["chain_follow_up_text"],
                    due_at_unix=now+int(row["chain_follow_up_offset_seconds"]),
                    idempotency_key=f"chain:{reminder_id}",project_id=row["project_id"],source=row["source"])
                await self._create_in_transaction(db,follow,now)
            await db.commit()

    async def cancel(self, reminder_id: str) -> None:
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute("SELECT status FROM reminders WHERE id=?", (reminder_id,))).fetchone()
            if row is None:
                raise KeyError("reminder_not_found")
            if row["status"] == "CANCELLED":
                return
            if row["status"] not in {"OPEN", "FIRED"}:
                raise ReminderConflict("reminder_state_conflict")
            await db.execute("UPDATE reminders SET status='CANCELLED',updated_at_unix=? WHERE id=?", (int(time.time()),reminder_id))
            await db.commit()

    async def fire_due(self, now: int | None = None) -> list[dict]:
        now = int(time.time()) if now is None else now
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            rows = await (await db.execute(
                "SELECT id,text,due_at_unix FROM reminders WHERE status='OPEN' AND due_at_unix<=? ORDER BY due_at_unix,id",(now,)
            )).fetchall()
            fired = []
            for row in rows:
                changed = await db.execute("UPDATE reminders SET status='FIRED',updated_at_unix=? WHERE id=? AND status='OPEN'",(now,row['id']))
                if changed.rowcount == 1:
                    fired.append({"id":row['id'],"text":row['text'],"due_at_unix":int(row['due_at_unix'])})
            await db.commit()
            return fired

    async def publish_pending(self, events, attention) -> int:
        """FIRED is pending work until both server publications are committed.

        This receipt does not claim handset delivery or owner acknowledgement.
        Stable event identity and attention dedupe make a lost storage reply
        retryable. A delivery error never changes FIRED back to OPEN or runs the
        reminder again. Legacy published events are reused, not rebroadcast.
        """
        rows = await self.store.fetchall(
            "SELECT r.id,r.text,r.due_at_unix,r.project_id FROM reminders r "
            "LEFT JOIN runtime_meta m ON m.key='reminder_publication_receipt:'||r.id "
            "WHERE r.status='FIRED' AND m.key IS NULL ORDER BY r.due_at_unix,r.id"
        )
        published = 0
        for row in rows:
            existing = await self.store.fetchone(
                "SELECT seq FROM events WHERE event_type='reminder.fired' "
                "AND json_extract(payload_json,'$.reminder_id')=? ORDER BY seq LIMIT 1", (row['id'],)
            )
            if existing is None:
                await events.publish('reminder.fired',
                    {'reminder_id':row['id'],'text':row['text'],'due_at_unix':int(row['due_at_unix'])},
                    event_id='reminder-fired:'+row['id'],correlation_id=row['id'])
            await attention.upsert(title=row['text'],severity=AttentionSeverity.FOLLOW_UP,
                source='reminder',dedupe_key='reminder:'+row['id'],project_id=row['project_id'],
                payload={'reminder_id':row['id'],'due_at_unix':int(row['due_at_unix'])})
            await self.store.execute(
                "INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) ON CONFLICT(key) DO NOTHING",
                ('reminder_publication_receipt:'+row['id'],Store.dumps({'schema':'van.reminder-publication/1','reminder_id':row['id']}),int(time.time()*1000)))
            published += 1
        return published
