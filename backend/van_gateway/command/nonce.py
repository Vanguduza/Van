"""Single-use command nonces.

P1-SEC-005: `canonical_command_v2` covers the `nonce` field and the orchestrator passes it
through, but nothing ever stored or checked it. Replay was therefore defended only by the
idempotency key and three time windows — a 24-hour default, tightened to 60 seconds only
when the client itself opted in via `no_stale_replay`.

A signed command captured on the wire could be presented again inside its validity window
with a fresh idempotency key and would be accepted as a new owner instruction. Storing the
nonce closes that: the second presentation collides on a UNIQUE primary key.

Nonces are scoped per device so one device cannot exhaust or probe another's space.
"""

from __future__ import annotations

import time

from van_gateway.storage.db import Store


class NonceReplay(Exception):
    """This nonce was already consumed by an earlier command from this device."""

    def __init__(self, device_id: str, nonce: str, original_command_id: str) -> None:
        self.device_id = device_id
        self.nonce = nonce
        self.original_command_id = original_command_id
        super().__init__(
            f"nonce already consumed by command {original_command_id}"
        )


class CommandNonceService:
    """Consume-once storage for signed command nonces."""

    #: Nonces older than this are pruned. It must exceed the widest replay window the
    #: orchestrator will accept (`owner_intent_max_age_seconds`, 24h by default), or a
    #: pruned nonce would become replayable again while its command was still valid.
    RETENTION_SECONDS = 7 * 24 * 3600

    def __init__(self, store: Store) -> None:
        self.store = store

    async def consume(self, *, device_id: str, nonce: str, command_id: str, now: int | None = None) -> None:
        """Record a nonce as used, or raise if this device already used it.

        The insert itself is the check: a UNIQUE (device_id, nonce) primary key means the
        race between two concurrent replays is settled by SQLite, not by a read-then-write
        that both callers could win.
        """
        stamp = int(time.time()) if now is None else now
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cur = await db.execute(
                    "SELECT command_id FROM command_nonces WHERE device_id = ? AND nonce = ?",
                    (device_id, nonce),
                )
                existing = await cur.fetchone()
                if existing is not None:
                    await db.rollback()
                    raise NonceReplay(device_id, nonce, str(existing["command_id"]))
                await db.execute(
                    "INSERT INTO command_nonces(device_id, nonce, command_id, consumed_at_unix) "
                    "VALUES (?, ?, ?, ?)",
                    (device_id, nonce, command_id, stamp),
                )
            except NonceReplay:
                raise
            except BaseException:
                await db.rollback()
                raise
            await db.commit()

    async def prune(self, *, now: int | None = None) -> int:
        """Drop nonces older than the retention window. Returns rows removed."""
        stamp = int(time.time()) if now is None else now
        cutoff = stamp - self.RETENTION_SECONDS
        async with self.store.connection() as db:
            cur = await db.execute(
                "DELETE FROM command_nonces WHERE consumed_at_unix < ?", (cutoff,)
            )
            await db.commit()
            return cur.rowcount or 0
