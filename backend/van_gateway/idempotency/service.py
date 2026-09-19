from __future__ import annotations

import hashlib
import json
import time
from enum import Enum
from typing import Any

from van_gateway.storage.db import Store


class IdempotencyStatus(str, Enum):
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


class IdempotencyConflict(Exception):
    pass


class IdempotencyInFlight(Exception):
    pass


#: P0-OPS-011 — how long a claim may be held before it is treated as abandoned.
#:
#: An IN_FLIGHT claim had no lease at all. A gateway that died between claiming a key and
#: completing it left the row IN_FLIGHT forever, and every later retry raised "still in
#: flight". The idempotency key is part of the signed request, so the owner could not work
#: around it by changing it: that command became permanently unrepeatable and the only cure
#: was editing the database.
#:
#: Chosen against the execution deadline rather than against how long a request takes. A
#: command handed to Hermes carries a deadline measured in minutes, and a claim released
#: before that deadline would let a second attempt run beside the first. Fifteen minutes is
#: comfortably past it, and the cost of waiting is a retry that is refused for a while
#: rather than one that duplicates work.
STALE_CLAIM_SECONDS = 15 * 60


class IdempotencyService:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def request_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def begin(self, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Start idempotent work.

        Returns prior response if same key+hash completed.
        Raises conflict if same key different hash.
        Raises in-flight if ambiguous reuse while running.
        """
        req_hash = self.request_hash(payload)
        now = int(time.time())

        # The claim must be atomic. The previous implementation did a SELECT on one
        # connection and an INSERT on another with no transaction, so two concurrent
        # identical signed commands could both observe no row and both proceed to execute
        # (finding P1-SEC-005). auth/service.py already used BEGIN IMMEDIATE for exactly
        # this reason; the pattern was known and simply not applied here.
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cur = await db.execute(
                    "SELECT idempotency_key, request_hash, status, response_json, "
                    "updated_at_unix FROM idempotency WHERE idempotency_key = ?",
                    (key,),
                )
                row = await cur.fetchone()
                if row is None:
                    await db.execute(
                        "INSERT INTO idempotency(idempotency_key, request_hash, status, "
                        "response_json, created_at_unix, updated_at_unix, claim_count) "
                        "VALUES (?, ?, ?, NULL, ?, ?, 1)",
                        (key, req_hash, IdempotencyStatus.IN_FLIGHT.value, now, now),
                    )
                    await db.commit()
                    return None
                # Materialise before the transaction closes.
                row = dict(row)

                # P0-OPS-011 — recover a claim whose holder is gone. Inside the same
                # BEGIN IMMEDIATE as the read, because two retries arriving together must
                # not both conclude the claim is theirs; that is the defect P1-SEC-005
                # closed, and releasing a claim would reopen it if done outside.
                #
                # Only an IN_FLIGHT claim with a matching hash is recoverable. COMPLETED
                # and CONFLICT are answers, not claims, and a different hash under the same
                # key is the conflict this table exists to detect.
                if (
                    row["status"] == IdempotencyStatus.IN_FLIGHT.value
                    and row["request_hash"] == req_hash
                    and now - int(row["updated_at_unix"]) >= STALE_CLAIM_SECONDS
                ):
                    await db.execute(
                        "UPDATE idempotency SET updated_at_unix = ?, "
                        "claim_count = claim_count + 1 WHERE idempotency_key = ?",
                        (now, key),
                    )
                    await db.commit()
                    # The caller now re-executes. That is safe because the work it would
                    # repeat is itself idempotent at the layer that matters:
                    # `CommandMissionLink.existing_for_command` returns the mission already
                    # opened for this command rather than opening a second one. Retaking a
                    # claim is not a promise that nothing happened; it is a statement that
                    # whoever held it is not coming back.
                    return None
            except BaseException:
                await db.rollback()
                raise
            await db.commit()

        if row["request_hash"] != req_hash:
            await self.store.execute(
                "UPDATE idempotency SET status = ?, updated_at_unix = ? WHERE idempotency_key = ?",
                (IdempotencyStatus.CONFLICT.value, now, key),
            )
            raise IdempotencyConflict("Same idempotency key with different request")
        if row["status"] == IdempotencyStatus.COMPLETED.value:
            return json.loads(row["response_json"]) if row["response_json"] else {}
        if row["status"] == IdempotencyStatus.IN_FLIGHT.value:
            raise IdempotencyInFlight("Idempotency key still in flight")
        if row["status"] == IdempotencyStatus.CONFLICT.value:
            raise IdempotencyConflict("Idempotency key previously conflicted")
        # FAILED with same hash: allow retry by moving back to IN_FLIGHT
        await self.store.execute(
            "UPDATE idempotency SET status = ?, response_json = NULL, updated_at_unix = ? WHERE idempotency_key = ?",
            (IdempotencyStatus.IN_FLIGHT.value, now, key),
        )
        return None

    async def complete(self, key: str, response: dict[str, Any]) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE idempotency SET status = ?, response_json = ?, updated_at_unix = ? WHERE idempotency_key = ?",
            (IdempotencyStatus.COMPLETED.value, Store.dumps(response), now, key),
        )

    async def fail(self, key: str, response: dict[str, Any]) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE idempotency SET status = ?, response_json = ?, updated_at_unix = ? WHERE idempotency_key = ?",
            (IdempotencyStatus.FAILED.value, Store.dumps(response), now, key),
        )
