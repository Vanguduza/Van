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
        row = await self.store.fetchone(
            "SELECT idempotency_key, request_hash, status, response_json FROM idempotency WHERE idempotency_key = ?",
            (key,),
        )
        now = int(time.time())
        if row is None:
            await self.store.execute(
                "INSERT INTO idempotency(idempotency_key, request_hash, status, response_json, created_at_unix, updated_at_unix) VALUES (?, ?, ?, NULL, ?, ?)",
                (key, req_hash, IdempotencyStatus.IN_FLIGHT.value, now, now),
            )
            return None
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
