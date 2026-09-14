from __future__ import annotations

import time
import uuid
from enum import Enum

from pydantic import BaseModel, Field

from van_gateway.attention.engine import AttentionEngine
from van_gateway.models import AttentionSeverity, AttentionState
from van_gateway.storage.db import Store


class DecisionStatus(str, Enum):
    OPEN = "OPEN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class DecisionCreate(BaseModel):
    title: str
    body: str
    source: str = "hermes"
    hermes_ref: str | None = None
    blocking: bool = True


class DecisionRecord(BaseModel):
    id: str
    title: str
    body: str
    status: DecisionStatus
    source: str
    hermes_ref: str | None = None
    created_at_unix: int
    updated_at_unix: int


class DecisionService:
    """Owner escalations from Hermes (@user / blocking judgments) become first-class decisions."""

    def __init__(self, store: Store, attention: AttentionEngine) -> None:
        self.store = store
        self.attention = attention

    async def escalate(self, body: DecisionCreate) -> DecisionRecord:
        now = int(time.time())
        decision_id = str(uuid.uuid4())
        await self.store.execute(
            """
            INSERT INTO decisions(id, title, body, status, source, hermes_ref, created_at_unix, updated_at_unix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (decision_id, body.title, body.body, DecisionStatus.OPEN.value, body.source, body.hermes_ref, now, now),
        )
        await self.attention.upsert(
            title=body.title,
            severity=AttentionSeverity.BLOCKER if body.blocking else AttentionSeverity.FOLLOW_UP,
            source=f"escalation:{body.source}",
            dedupe_key=f"decision:{decision_id}",
            payload={"decision_id": decision_id, "hermes_ref": body.hermes_ref, "body": body.body},
            state=AttentionState.OPEN,
        )
        return DecisionRecord(
            id=decision_id,
            title=body.title,
            body=body.body,
            status=DecisionStatus.OPEN,
            source=body.source,
            hermes_ref=body.hermes_ref,
            created_at_unix=now,
            updated_at_unix=now,
        )

    async def list_open(self) -> list[DecisionRecord]:
        rows = await self.store.fetchall(
            "SELECT id, title, body, status, source, hermes_ref, created_at_unix, updated_at_unix FROM decisions WHERE status = ? ORDER BY created_at_unix DESC",
            (DecisionStatus.OPEN.value,),
        )
        return [
            DecisionRecord(
                id=r["id"],
                title=r["title"],
                body=r["body"],
                status=DecisionStatus(r["status"]),
                source=r["source"],
                hermes_ref=r["hermes_ref"],
                created_at_unix=int(r["created_at_unix"]),
                updated_at_unix=int(r["updated_at_unix"]),
            )
            for r in rows
        ]

    async def resolve(self, decision_id: str, *, approved: bool) -> DecisionRecord:
        now = int(time.time())
        row = await self.store.fetchone(
            "SELECT id, title, body, status, source, hermes_ref, created_at_unix FROM decisions WHERE id = ?",
            (decision_id,),
        )
        if row is None:
            raise KeyError("decision_not_found")
        status = DecisionStatus.APPROVED if approved else DecisionStatus.REJECTED
        await self.store.execute(
            "UPDATE decisions SET status = ?, updated_at_unix = ? WHERE id = ?",
            (status.value, now, decision_id),
        )
        attention = await self.store.fetchone(
            "SELECT id FROM attention WHERE dedupe_key = ?",
            (f"decision:{decision_id}",),
        )
        if attention:
            await self.attention.mark_handled(attention["id"])
        return DecisionRecord(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            status=status,
            source=row["source"],
            hermes_ref=row["hermes_ref"],
            created_at_unix=int(row["created_at_unix"]),
            updated_at_unix=now,
        )
