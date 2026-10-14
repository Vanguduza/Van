"""Durable worker lease fencing for OMV-002/009."""

from __future__ import annotations

from dataclasses import dataclass
import time
import uuid

from van_gateway.storage.db import Store


class ComputerWorkerLeaseError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ComputerWorkerLease:
    surface: str
    lease_id: str
    generation: int
    holder_id: str
    expires_at_ms: int


class ComputerWorkerLeaseService:
    """A stale executor cannot publish a completion after lease loss/restart."""

    def __init__(self, store: Store, *, ttl_ms: int = 180_000) -> None:
        self.store = store
        self.ttl_ms = ttl_ms

    async def acquire(
        self, surface: str, holder_id: str, *, now_ms: int | None = None
    ) -> ComputerWorkerLease:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        lease_id = f"cwl_{uuid.uuid4().hex}"
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "SELECT * FROM computer_worker_leases WHERE surface = ?", (surface,)
            )
            row = await cur.fetchone()
            if (
                row is not None
                and row["released_at_ms"] is None
                and int(row["expires_at_ms"]) > now
            ):
                await db.rollback()
                raise ComputerWorkerLeaseError("COMPUTER_WORKER_BUSY")
            generation = 1 if row is None else int(row["generation"]) + 1
            expires = now + self.ttl_ms
            await db.execute(
                """
                INSERT INTO computer_worker_leases(
                  surface, lease_id, generation, holder_id, expires_at_ms,
                  released_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(surface) DO UPDATE SET
                  lease_id=excluded.lease_id,
                  generation=excluded.generation,
                  holder_id=excluded.holder_id,
                  expires_at_ms=excluded.expires_at_ms,
                  released_at_ms=NULL,
                  updated_at_ms=excluded.updated_at_ms
                """,
                (surface, lease_id, generation, holder_id, expires, now),
            )
            await db.commit()
        return ComputerWorkerLease(surface, lease_id, generation, holder_id, expires)

    async def renew(
        self, lease: ComputerWorkerLease, *, now_ms: int | None = None
    ) -> ComputerWorkerLease:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        current = await self.assert_active(lease, now_ms=now)
        expires = now + self.ttl_ms
        await self.store.execute(
            """
            UPDATE computer_worker_leases
               SET expires_at_ms = ?, updated_at_ms = ?
             WHERE surface = ? AND lease_id = ? AND generation = ? AND released_at_ms IS NULL
            """,
            (expires, now, lease.surface, lease.lease_id, lease.generation),
        )
        return ComputerWorkerLease(
            current.surface, current.lease_id, current.generation, current.holder_id, expires
        )

    async def assert_active(
        self, lease: ComputerWorkerLease, *, now_ms: int | None = None
    ) -> ComputerWorkerLease:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self.store.fetchone(
            "SELECT * FROM computer_worker_leases WHERE surface = ?", (lease.surface,)
        )
        if (
            row is None
            or row["lease_id"] != lease.lease_id
            or int(row["generation"]) != lease.generation
            or row["released_at_ms"] is not None
            or int(row["expires_at_ms"]) <= now
        ):
            raise ComputerWorkerLeaseError("COMPUTER_WORKER_LOST_LEASE")
        return ComputerWorkerLease(
            surface=row["surface"], lease_id=row["lease_id"],
            generation=int(row["generation"]), holder_id=row["holder_id"],
            expires_at_ms=int(row["expires_at_ms"]),
        )

    async def release(
        self, lease: ComputerWorkerLease, *, now_ms: int | None = None
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            UPDATE computer_worker_leases
               SET released_at_ms = ?, updated_at_ms = ?
             WHERE surface = ? AND lease_id = ? AND generation = ? AND released_at_ms IS NULL
            """,
            (now, now, lease.surface, lease.lease_id, lease.generation),
        )
