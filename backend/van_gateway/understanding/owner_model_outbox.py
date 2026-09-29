"""Durable correction/invalidation outbox for the Owner Model (Memory Fabric Programme A).

When the owner corrects, rejects or contests what VAN believes about them — or a
correction supersedes an assertion, or the owner forgets it — every *derived* copy of
that belief (Hindsight's owner bank, the OpenViking owner projection, any cached personal
context capsule) is now wrong. This module is how those stores are told.

What is guaranteed, and what is not:

* The outbox row is written **in the same SQLite transaction** as the Owner Model commit
  and the ``owner_model_revision`` bump. Either all three persist or none does.
* Delivery to each target is **at-least-once**, recorded per target with a receipt.
  A handler may be called again for an event it already applied (a crash between the
  handler returning and the DELIVERED mark committing), so handlers must be idempotent on
  ``(outbox_id, target)``.
* **No distributed atomicity is claimed.** Between the commit and a successful delivery a
  derived store can still hold the old belief. The synchronous guarantee is the revision
  fence: every consumer of personal context must compare the capsule's
  ``owner_model_revision`` with a live read of the current one (contract C2/C3), so a
  stale derived copy is refused before the outbox has even been drained.

There are no real Hindsight/OpenViking clients here on purpose. Targets are served by
pluggable handlers; tests use fakes.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping

import aiosqlite

from van_gateway.storage.db import Store


class OutboxTarget(str, Enum):
    HINDSIGHT_OWNER = "HINDSIGHT_OWNER"
    OPENVIKING_OWNER_PROJECTION = "OPENVIKING_OWNER_PROJECTION"
    PERSONAL_CONTEXT_CACHE = "PERSONAL_CONTEXT_CACHE"


class OutboxEventKind(str, Enum):
    CORRECTED = "CORRECTED"  # a correction: the old assertion is SUPERSEDED by a new one
    REJECTED = "REJECTED"
    CONTESTED = "CONTESTED"
    FORGOTTEN = "FORGOTTEN"  # written by the SQL trigger on owner forget, not by Python


ALL_TARGETS: tuple[OutboxTarget, ...] = tuple(OutboxTarget)


@dataclass(frozen=True)
class OutboxEvent:
    """What a handler receives. Ids and field names only — never the owner's values."""

    outbox_id: str
    target: OutboxTarget
    owner_principal_id: str
    owner_model_revision: int
    event_kind: str
    payload: dict[str, Any]
    attempts: int


#: A handler applies one event to one target and returns a non-empty receipt string.
#: Raising, or returning an empty receipt, leaves the row PENDING with attempts+1.
OutboxHandler = Callable[[OutboxEvent], Awaitable[str]]


async def write_outbox(
    db: aiosqlite.Connection,
    *,
    owner_principal_id: str,
    owner_model_revision: int,
    event_kind: OutboxEventKind,
    payload: Mapping[str, Any],
    now_ms: int,
    targets: tuple[OutboxTarget, ...] = ALL_TARGETS,
) -> str:
    """Insert one PENDING row per target on the caller's open transaction.

    Takes the connection rather than the store so it cannot be called outside the
    Owner Model's transaction by accident.
    """
    outbox_id = f"omo_{uuid.uuid4().hex}"
    payload_json = Store.dumps(dict(payload))
    for target in targets:
        await db.execute(
            "INSERT INTO owner_model_outbox(outbox_id, target, owner_principal_id, "
            "owner_model_revision, event_kind, payload_json, status, attempts, created_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0, ?)",
            (outbox_id, target.value, owner_principal_id, owner_model_revision,
             event_kind.value, payload_json, now_ms),
        )
    return outbox_id


@dataclass
class DrainReport:
    delivered: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str, str]] = field(default_factory=list)
    #: PENDING rows whose target has no handler registered. Not attempted, not counted.
    unhandled: list[tuple[str, str]] = field(default_factory=list)


async def drain_outbox(
    store: Store,
    handlers: Mapping[OutboxTarget, OutboxHandler],
    *,
    limit: int = 100,
    now_ms: int | None = None,
) -> DrainReport:
    """Deliver PENDING rows to their target handlers, oldest first.

    Idempotent: only PENDING rows are selected, and the DELIVERED mark is conditional on
    the row still being PENDING, so re-running a drain never re-delivers a delivered row.
    One target failing does not block the others; each (event, target) is independent.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    report = DrainReport()
    rows = await store.fetchall(
        "SELECT * FROM owner_model_outbox WHERE status = 'PENDING' "
        "ORDER BY created_at_ms, outbox_id, target LIMIT ?",
        (limit,),
    )
    for row in rows:
        target = OutboxTarget(str(row["target"]))
        key = (str(row["outbox_id"]), target.value)
        handler = handlers.get(target)
        if handler is None:
            report.unhandled.append(key)
            continue
        event = OutboxEvent(
            outbox_id=key[0], target=target,
            owner_principal_id=str(row["owner_principal_id"]),
            owner_model_revision=int(row["owner_model_revision"]),
            event_kind=str(row["event_kind"]),
            payload=json.loads(str(row["payload_json"])),
            attempts=int(row["attempts"]),
        )
        try:
            receipt = await handler(event)
            if not isinstance(receipt, str) or not receipt.strip():
                raise OutboxDeliveryError("OUTBOX_HANDLER_NO_RECEIPT")
        except Exception as exc:  # noqa: BLE001 — any handler failure keeps the row pending
            # The error *type/code* only: a handler's message could echo owner content.
            error = exc.code if isinstance(exc, OutboxDeliveryError) else type(exc).__name__
            await store.execute(
                "UPDATE owner_model_outbox SET attempts = attempts + 1, last_error = ?, "
                "last_attempt_at_ms = ? WHERE outbox_id = ? AND target = ? "
                "AND status = 'PENDING'",
                (error, now, *key),
            )
            report.failed.append((*key, error))
            continue
        await store.execute(
            "UPDATE owner_model_outbox SET status = 'DELIVERED', receipt = ?, "
            "attempts = attempts + 1, last_error = NULL, last_attempt_at_ms = ?, "
            "delivered_at_ms = ? WHERE outbox_id = ? AND target = ? AND status = 'PENDING'",
            (receipt, now, now, *key),
        )
        report.delivered.append(key)
    return report


class OutboxDeliveryError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


__all__ = [
    "ALL_TARGETS",
    "DrainReport",
    "OutboxDeliveryError",
    "OutboxEvent",
    "OutboxEventKind",
    "OutboxHandler",
    "OutboxTarget",
    "drain_outbox",
    "write_outbox",
]
