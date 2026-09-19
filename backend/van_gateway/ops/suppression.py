"""Dedupe and suppression that survive a restart.

P3-OPS-005: `NotificationIntelligence._seen` was a `set()` on the instance and
`DegradedRegistry._active` was a `set()` on the instance. Both are decisions with
owner-visible consequences — this notification has already been shown, this
subsystem's degradation has already been announced — and both were erased by any
restart. Restarting the gateway re-showed notifications the owner had already
seen, which is the specific behaviour that teaches someone to stop reading their
notifications.

A suppression has three parts and the table holds all three: the **channel** it
applies to, the **subject** it is about, and **how long it lasts**. The third is
the one an in-memory set cannot express at all: a set entry is forever or gone,
so "suppress this for an hour" had nowhere to live.

`suppressed_until_unix IS NULL` means permanent — the owner said never again.
That is deliberately distinguishable from a long expiry: a permanent suppression
should not quietly come back after the longest interval anyone thought to write.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from van_gateway.storage.db import Store


class SuppressionChannel(str, Enum):
    NOTIFICATION = "NOTIFICATION"
    ATTENTION = "ATTENTION"
    DEGRADED = "DEGRADED"
    REMINDER = "REMINDER"


@dataclass(frozen=True)
class Suppression:
    key: str
    channel: SuppressionChannel
    subject_ref: str
    reason: str
    suppressed_until_unix: int | None
    created_at_unix: int
    updated_at_unix: int

    def active_at(self, now_unix: int) -> bool:
        if self.suppressed_until_unix is None:
            return True
        return now_unix < self.suppressed_until_unix

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "channel": self.channel.value,
            "subject_ref": self.subject_ref,
            "reason": self.reason,
            "suppressed_until_unix": self.suppressed_until_unix,
            "created_at_unix": self.created_at_unix,
            "updated_at_unix": self.updated_at_unix,
        }


def suppression_key(channel: SuppressionChannel, subject_ref: str) -> str:
    return f"{channel.value}:{subject_ref}"


class SuppressionStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def suppress(
        self,
        channel: SuppressionChannel,
        subject_ref: str,
        *,
        reason: str,
        ttl_seconds: int | None = None,
        now_unix: int | None = None,
    ) -> Suppression:
        """Record a suppression. `ttl_seconds=None` means permanent."""
        now = now_unix if now_unix is not None else int(time.time())
        until = None if ttl_seconds is None else now + int(ttl_seconds)
        key = suppression_key(channel, subject_ref)
        await self.store.execute(
            """
            INSERT INTO notification_suppressions(
              suppression_key, channel, subject_ref, reason, suppressed_until_unix,
              created_at_unix, updated_at_unix
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(suppression_key) DO UPDATE SET
              reason = excluded.reason,
              suppressed_until_unix = excluded.suppressed_until_unix,
              updated_at_unix = excluded.updated_at_unix
            """,
            (key, channel.value, subject_ref, reason, until, now, now),
        )
        stored = await self.get(channel, subject_ref)
        assert stored is not None  # just written in the same connection pool
        return stored

    async def get(self, channel: SuppressionChannel, subject_ref: str) -> Suppression | None:
        rows = await self.store.fetchall(
            "SELECT suppression_key, channel, subject_ref, reason, suppressed_until_unix, "
            "created_at_unix, updated_at_unix FROM notification_suppressions "
            "WHERE suppression_key = ?",
            (suppression_key(channel, subject_ref),),
        )
        if not rows:
            return None
        row = rows[0]
        return Suppression(
            key=str(row["suppression_key"]),
            channel=SuppressionChannel(str(row["channel"])),
            subject_ref=str(row["subject_ref"]),
            reason=str(row["reason"]),
            suppressed_until_unix=(
                None if row["suppressed_until_unix"] is None
                else int(row["suppressed_until_unix"])
            ),
            created_at_unix=int(row["created_at_unix"]),
            updated_at_unix=int(row["updated_at_unix"]),
        )

    async def is_suppressed(
        self, channel: SuppressionChannel, subject_ref: str, *, now_unix: int | None = None
    ) -> Suppression | None:
        """The suppression in force right now, or None. Expired rows return None
        but are left in place: that they existed is how "I already told you about
        this yesterday" stays answerable."""
        now = now_unix if now_unix is not None else int(time.time())
        found = await self.get(channel, subject_ref)
        if found is None or not found.active_at(now):
            return None
        return found

    async def release(self, channel: SuppressionChannel, subject_ref: str) -> bool:
        """Lift a suppression. Returns whether one was in the table."""
        async with self.store.connection() as db:
            cursor = await db.execute(
                "DELETE FROM notification_suppressions WHERE suppression_key = ?",
                (suppression_key(channel, subject_ref),),
            )
            await db.commit()
            return bool(cursor.rowcount)

    async def active(
        self, channel: SuppressionChannel | None = None, *, now_unix: int | None = None
    ) -> list[Suppression]:
        now = now_unix if now_unix is not None else int(time.time())
        sql = (
            "SELECT suppression_key, channel, subject_ref, reason, suppressed_until_unix, "
            "created_at_unix, updated_at_unix FROM notification_suppressions"
        )
        params: tuple = ()
        if channel is not None:
            sql += " WHERE channel = ?"
            params = (channel.value,)
        rows = await self.store.fetchall(sql + " ORDER BY created_at_unix", params)
        found = [
            Suppression(
                key=str(row["suppression_key"]),
                channel=SuppressionChannel(str(row["channel"])),
                subject_ref=str(row["subject_ref"]),
                reason=str(row["reason"]),
                suppressed_until_unix=(
                    None if row["suppressed_until_unix"] is None
                    else int(row["suppressed_until_unix"])
                ),
                created_at_unix=int(row["created_at_unix"]),
                updated_at_unix=int(row["updated_at_unix"]),
            )
            for row in rows
        ]
        return [item for item in found if item.active_at(now)]


__all__ = ["Suppression", "SuppressionChannel", "SuppressionStore", "suppression_key"]
