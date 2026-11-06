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
* **One row cannot block the others.** A drain reads only rows for targets that have a
  handler, and only rows that are due: a failure schedules the row's next attempt with
  exponential backoff, and after ``max_attempts`` failures the row is dead-lettered
  (``dead_lettered_at_ms`` set, still ``PENDING``) and never selected again. Before this,
  the oldest 100 PENDING rows of *any* target filled every batch, so unhandled or poison
  rows starved handled targets indefinitely.
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

#: Failures a row may accumulate before it is dead-lettered.
DEFAULT_MAX_ATTEMPTS = 8
#: Backoff after the n-th failure: base * 2**(n-1), capped.
DEFAULT_BACKOFF_BASE_MS = 1_000
DEFAULT_BACKOFF_CAP_MS = 15 * 60 * 1_000


def backoff_ms(failures: int, *, base_ms: int = DEFAULT_BACKOFF_BASE_MS,
               cap_ms: int = DEFAULT_BACKOFF_CAP_MS) -> int:
    """Delay before the next attempt after `failures` consecutive failures (>= 1)."""
    return min(cap_ms, base_ms * (2 ** max(failures - 1, 0)))


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
    #: PENDING rows whose target has no handler registered. Not attempted, not counted,
    #: and — since they are read separately — never taking a handled row's place.
    unhandled: list[tuple[str, str]] = field(default_factory=list)
    #: Rows that failed for the last permitted time in this drain and are now parked.
    dead_lettered: list[tuple[str, str, str]] = field(default_factory=list)


async def drain_outbox(
    store: Store,
    handlers: Mapping[OutboxTarget, OutboxHandler],
    *,
    limit: int = 100,
    now_ms: int | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base_ms: int = DEFAULT_BACKOFF_BASE_MS,
    backoff_cap_ms: int = DEFAULT_BACKOFF_CAP_MS,
) -> DrainReport:
    """Deliver due PENDING rows to their target handlers, oldest first.

    Idempotent: only PENDING rows are selected, and the DELIVERED mark is conditional on
    the row still being PENDING, so re-running a drain never re-delivers a delivered row.
    One target failing does not block the others; each (event, target) is independent.

    The batch is drawn only from targets in `handlers`, and only from rows that are due
    (not backing off, not dead-lettered), so neither a target nobody serves nor a row
    that always fails can occupy the batch a handled row needs.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    report = DrainReport()
    handled = sorted(t.value for t in handlers)
    unhandled_targets = sorted(t.value for t in OutboxTarget if t.value not in handled)
    if unhandled_targets:
        marks = ",".join("?" for _ in unhandled_targets)
        for row in await store.fetchall(
            "SELECT outbox_id, target FROM owner_model_outbox WHERE status = 'PENDING' "
            f"AND dead_lettered_at_ms IS NULL AND target IN ({marks}) "  # noqa: S608
            "ORDER BY created_at_ms, outbox_id, target LIMIT ?",
            (*unhandled_targets, limit),
        ):
            report.unhandled.append((str(row["outbox_id"]), str(row["target"])))
    if not handled:
        return report
    marks = ",".join("?" for _ in handled)
    rows = await store.fetchall(
        "SELECT * FROM owner_model_outbox WHERE status = 'PENDING' "
        f"AND dead_lettered_at_ms IS NULL AND target IN ({marks}) "  # noqa: S608
        "AND (next_attempt_at_ms IS NULL OR next_attempt_at_ms <= ?) "
        "ORDER BY created_at_ms, outbox_id, target LIMIT ?",
        (*handled, now, limit),
    )
    for row in rows:
        target = OutboxTarget(str(row["target"]))
        key = (str(row["outbox_id"]), target.value)
        handler = handlers[target]
        try:
            # Decoded inside the try (A-MIN-VAN, reviewer D2): a row whose stored payload
            # cannot be decoded is that row's failed attempt and ends in dead-letter; it
            # must never abort the drain and starve every row behind it.
            try:
                payload = json.loads(str(row["payload_json"]))
            except ValueError:
                raise OutboxDeliveryError("OUTBOX_PAYLOAD_UNDECODABLE") from None
            event = OutboxEvent(
                outbox_id=key[0], target=target,
                owner_principal_id=str(row["owner_principal_id"]),
                owner_model_revision=int(row["owner_model_revision"]),
                event_kind=str(row["event_kind"]),
                payload=payload,
                attempts=int(row["attempts"]),
            )
            receipt = await handler(event)
            if not isinstance(receipt, str) or not receipt.strip():
                raise OutboxDeliveryError("OUTBOX_HANDLER_NO_RECEIPT")
        except Exception as exc:  # noqa: BLE001 — any handler failure keeps the row pending
            # The error *type/code* only: a handler's message could echo owner content.
            error = exc.code if isinstance(exc, OutboxDeliveryError) else type(exc).__name__
            failures = int(row["attempts"]) + 1
            dead = failures >= max_attempts
            await store.execute(
                "UPDATE owner_model_outbox SET attempts = attempts + 1, last_error = ?, "
                "last_attempt_at_ms = ?, next_attempt_at_ms = ?, dead_lettered_at_ms = ? "
                "WHERE outbox_id = ? AND target = ? AND status = 'PENDING'",
                (error, now,
                 now + backoff_ms(failures, base_ms=backoff_base_ms, cap_ms=backoff_cap_ms),
                 now if dead else None, *key),
            )
            report.failed.append((*key, error))
            if dead:
                report.dead_lettered.append((*key, error))
            continue
        await store.execute(
            "UPDATE owner_model_outbox SET status = 'DELIVERED', receipt = ?, "
            "attempts = attempts + 1, last_error = NULL, last_attempt_at_ms = ?, "
            "next_attempt_at_ms = NULL, "
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
    "DEFAULT_BACKOFF_BASE_MS",
    "DEFAULT_BACKOFF_CAP_MS",
    "DEFAULT_MAX_ATTEMPTS",
    "DrainReport",
    "OutboxDeliveryError",
    "OutboxEvent",
    "OutboxEventKind",
    "OutboxHandler",
    "OutboxTarget",
    "backoff_ms",
    "drain_outbox",
    "write_outbox",
]
