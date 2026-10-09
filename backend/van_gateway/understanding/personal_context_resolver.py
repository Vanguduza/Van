"""Personal-context resolver (Memory Fabric Programme A; owner decision 2026-09-29 §3).

`build_personal_capsule` *produces* a capsule fenced at the revision it was read at. This
module is the only thing that should *serve* one. Its single rule:

    requested owner revision == authoritative current ``owner_model_revision``,
    read from the authoritative Owner Model store at resolve time.

If that cannot be verified, the answer is ``PERSONAL_CONTEXT_UNAVAILABLE`` — never a
cached capsule, never a capsule built at a different revision. Concretely:

* the requested revision must be a non-negative integer (``bool`` is not an integer here);
* the authoritative revision is read live from ``owner_model_revisions``. A store error
  is ``AUTHORITATIVE_STORE_UNREACHABLE``; there is **no fallback to the cache on error**,
  because a warm cache is exactly the thing that cannot prove its own freshness;
* a missing revision row is ``AUTHORITATIVE_REVISION_MISSING``. `current_revision()` reads
  a missing row as 0 for display; the resolver does not, because "never written" and
  "reset" cannot be told apart from the requester's side;
* requested != authoritative is ``REVISION_MISMATCH``;
* the cache has **no TTL**. An entry is only a candidate: it is served only when its own
  revision equals the live authoritative read taken in the same resolve, and its content
  hash still verifies. Time never makes an entry valid;
* after a candidate is chosen, the authoritative revision is read **again**. A mutation
  that committed between the first read and serving (a correction racing the resolve)
  moves the revision, and the resolve fails with ``REVISION_CHANGED_DURING_RESOLVE``.

What this does not claim: a mutation that commits *after* the second read is not seen by
this resolve. That is the same fence the capsule carries — a consumer that holds a capsule
past the moment of use must re-resolve (or compare its ``owner_model_revision`` against a
live C2 read), which the outbox's PERSONAL_CONTEXT_CACHE target also forces for caches.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from van_gateway.understanding.owner_model import OwnerCognitiveModel
from van_gateway.understanding.owner_model_outbox import OutboxEvent
from van_gateway.understanding.personal_context import (
    build_personal_capsule,
    verify_content_hash,
)

PERSONAL_CONTEXT_UNAVAILABLE = "PERSONAL_CONTEXT_UNAVAILABLE"
FENCE_SCHEMA = "van.owner_model.personal_context_fence.v1"


class UnavailableReason(str, Enum):
    REQUESTED_REVISION_INVALID = "REQUESTED_REVISION_INVALID"
    AUTHORITATIVE_STORE_UNREACHABLE = "AUTHORITATIVE_STORE_UNREACHABLE"
    AUTHORITATIVE_REVISION_MISSING = "AUTHORITATIVE_REVISION_MISSING"
    REVISION_MISMATCH = "REVISION_MISMATCH"
    REVISION_CHANGED_DURING_RESOLVE = "REVISION_CHANGED_DURING_RESOLVE"
    CAPSULE_INTEGRITY_FAILED = "CAPSULE_INTEGRITY_FAILED"


class PersonalContextUnavailable(Exception):
    """The only failure a resolve raises. Carries revisions, never owner content."""

    code = PERSONAL_CONTEXT_UNAVAILABLE

    def __init__(
        self,
        reason: UnavailableReason,
        *,
        requested_revision: Any = None,
        authoritative_revision: int | None = None,
    ) -> None:
        super().__init__(f"{PERSONAL_CONTEXT_UNAVAILABLE}: {reason.value}")
        self.reason = reason
        self.requested_revision = requested_revision
        self.authoritative_revision = authoritative_revision

    def as_detail(self) -> dict[str, Any]:
        requested = self.requested_revision
        return {
            "code": self.code,
            "reason": self.reason.value,
            "requested_owner_model_revision": requested if isinstance(requested, int) else None,
            "authoritative_owner_model_revision": self.authoritative_revision,
        }


@dataclass(frozen=True)
class _CacheKey:
    owner_principal_id: str
    project_id: str | None
    purpose: str


class RevisionFencedCapsuleCache:
    """In-process capsule cache with no TTL: entries are candidates, not answers.

    `candidate()` returns an entry only when its revision equals the revision the caller
    has just read from the authoritative store; any other entry is evicted on sight.

    Entries are deep-copied in and out (A-MIN-VAN, reviewer D2): `content_hash` covers
    only `content`, so a consumer that mutated a nested envelope field of a served capsule
    (`provenance_refs`, `source_revisions`) would otherwise rewrite the cached entry every
    later consumer is served, without failing integrity.
    """

    def __init__(self) -> None:
        self._entries: dict[_CacheKey, dict[str, Any]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def candidate(self, key: _CacheKey, authoritative_revision: int) -> dict[str, Any] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.get("owner_model_revision") != authoritative_revision:
            del self._entries[key]
            return None
        return copy.deepcopy(entry)

    def put(self, key: _CacheKey, capsule: dict[str, Any]) -> None:
        self._entries[key] = copy.deepcopy(capsule)

    def evict(self, key: _CacheKey) -> None:
        self._entries.pop(key, None)

    def invalidate_owner(self, owner_principal_id: str) -> int:
        stale = [k for k in self._entries if k.owner_principal_id == owner_principal_id]
        for key in stale:
            del self._entries[key]
        return len(stale)

    async def outbox_handler(self, event: OutboxEvent) -> str:
        """Handler for the PERSONAL_CONTEXT_CACHE outbox target. Idempotent."""
        dropped = self.invalidate_owner(event.owner_principal_id)
        return f"personal-context-cache:{event.outbox_id}:dropped={dropped}"


class PersonalContextResolver:
    """Serves a personal context capsule only at the verified authoritative revision."""

    def __init__(
        self,
        model: OwnerCognitiveModel,
        *,
        cache: RevisionFencedCapsuleCache | None = None,
    ) -> None:
        self.model = model
        self.cache = cache

    async def authoritative_revision(self, owner_principal_id: str, *, requested: Any = None) -> int:
        """Live read of the authoritative revision row. Raises, never defaults."""
        try:
            row = await self.model.store.fetchone(
                "SELECT owner_model_revision FROM owner_model_revisions "
                "WHERE owner_principal_id = ?",
                (owner_principal_id,),
            )
        except Exception as exc:  # noqa: BLE001 — any read failure means "cannot verify"
            raise PersonalContextUnavailable(
                UnavailableReason.AUTHORITATIVE_STORE_UNREACHABLE, requested_revision=requested,
            ) from exc
        if row is None or row[0] is None:
            raise PersonalContextUnavailable(
                UnavailableReason.AUTHORITATIVE_REVISION_MISSING, requested_revision=requested,
            )
        return int(row[0])

    async def resolve(
        self,
        owner_principal_id: str,
        *,
        requested_revision: Any,
        purpose: str,
        project_id: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        if (not isinstance(requested_revision, int) or isinstance(requested_revision, bool)
                or requested_revision < 0):
            raise PersonalContextUnavailable(
                UnavailableReason.REQUESTED_REVISION_INVALID,
                requested_revision=requested_revision,
            )
        requested = requested_revision

        # Guard 1 — live authoritative read; no cache consulted before it succeeds.
        authoritative = await self.authoritative_revision(owner_principal_id, requested=requested)
        # Guard 2 — the requested revision is the authoritative one.
        if requested != authoritative:
            raise PersonalContextUnavailable(
                UnavailableReason.REVISION_MISMATCH,
                requested_revision=requested, authoritative_revision=authoritative,
            )

        key = _CacheKey(owner_principal_id, project_id, purpose)
        # Guard 3 — a cache entry is a candidate only at the live revision.
        capsule = self.cache.candidate(key, authoritative) if self.cache is not None else None
        if capsule is None:
            try:
                capsule = await build_personal_capsule(
                    self.model, owner_principal_id, purpose=purpose, project_id=project_id,
                    now_ms=now_ms,
                )
            except ValueError:
                raise  # caller error (e.g. empty purpose), not an availability question
            except Exception as exc:  # noqa: BLE001
                raise PersonalContextUnavailable(
                    UnavailableReason.AUTHORITATIVE_STORE_UNREACHABLE,
                    requested_revision=requested, authoritative_revision=authoritative,
                ) from exc
            if capsule["owner_model_revision"] != requested:
                raise PersonalContextUnavailable(
                    UnavailableReason.REVISION_CHANGED_DURING_RESOLVE,
                    requested_revision=requested,
                    authoritative_revision=int(capsule["owner_model_revision"]),
                )
            if self.cache is not None:
                self.cache.put(key, capsule)

        if not verify_content_hash(capsule):
            if self.cache is not None:
                self.cache.evict(key)
            raise PersonalContextUnavailable(
                UnavailableReason.CAPSULE_INTEGRITY_FAILED,
                requested_revision=requested, authoritative_revision=authoritative,
            )

        # Guard 4 — re-read at serve time: a commit since guard 1 moved the revision.
        confirmed = await self.authoritative_revision(owner_principal_id, requested=requested)
        if confirmed != requested:
            if self.cache is not None:
                self.cache.invalidate_owner(owner_principal_id)
            raise PersonalContextUnavailable(
                UnavailableReason.REVISION_CHANGED_DURING_RESOLVE,
                requested_revision=requested, authoritative_revision=confirmed,
            )

        now = int(time.time() * 1000) if now_ms is None else now_ms
        return {
            **capsule,
            "freshness": "FRESH",
            "fence": {
                "schema": FENCE_SCHEMA,
                "requested_owner_model_revision": requested,
                "authoritative_owner_model_revision": confirmed,
                "verified_at_ms": now,
            },
        }


__all__ = [
    "FENCE_SCHEMA",
    "PERSONAL_CONTEXT_UNAVAILABLE",
    "PersonalContextResolver",
    "PersonalContextUnavailable",
    "RevisionFencedCapsuleCache",
    "UnavailableReason",
]
