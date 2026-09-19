"""Owner-facing deletion for everything VAN holds about the owner.

P2-MEM-002: only `owner_facts` and `owner_context_edges` had an erase path. The owner
cognitive model, the reasoning assessments, the symbiotic growth ledger, strategic memory,
decision fingerprints, the shared vocabulary and the intent continuity graph all accumulate
owner-derived material and none of them could be cleared. A system that learns about
somebody and cannot forget is not a system they control.

Two decisions shape this, and both are arguable, so both are stated:

**Forget means delete, not tombstone.** A row the owner asked to be gone, kept with a flag,
is still there — and the flag is one query away from being ignored. The audit ledger is the
exception and stays: it records what VAN *did*, not what it concluded about the owner, and
erasing it would destroy the evidence trail that makes everything else checkable. The
report says so rather than quietly leaving it out.

**Nothing is forgotten by inference.** Each store is named, with the column that scopes it
to an owner. A store added later is absent from this list and therefore not erased — so the
inventory test asserts that every table holding owner-derived material appears here, and
fails when one does not.
"""

from __future__ import annotations

from dataclasses import dataclass

from van_gateway.storage.db import Store


@dataclass(frozen=True)
class ForgettableStore:
    """A table the owner may clear, and how it is scoped to them."""

    table: str
    owner_column: str | None
    description: str


#: Every store holding owner-derived material, and how to scope a deletion to one owner.
#: `owner_column` of None means the table is entirely owner-derived and is cleared wholesale.
FORGETTABLE: tuple[ForgettableStore, ...] = (
    ForgettableStore("owner_facts", None, "what VAN believes about the owner"),
    ForgettableStore("owner_context_edges", None, "how VAN connects the owner's world"),
    ForgettableStore("owner_cognitive_model", "owner_principal_id",
                     "how VAN thinks the owner prefers to work"),
    ForgettableStore("reasoning_assessments", None, "VAN's recorded reasoning about the owner's decisions"),
    ForgettableStore("symbiotic_growth", None, "what VAN thinks it has learned from the owner"),
    ForgettableStore("strategic_memory", None, "long-running context about the owner's direction"),
    ForgettableStore("decision_fingerprints", None, "patterns VAN has noticed in the owner's decisions"),
    ForgettableStore("shared_vocabulary", None, "words VAN has learned the owner's meaning for"),
    ForgettableStore("intent_edges", None, "how VAN links the owner's intents over time"),
    ForgettableStore("intent_nodes", None, "the owner's intents as VAN recorded them"),
    ForgettableStore("intent_missions", None, "which missions VAN attached to which intent"),
)

#: Named, with the reason, rather than silently omitted. Someone auditing this list should
#: be able to see that the omission was decided rather than forgotten.
DELIBERATELY_KEPT: dict[str, str] = {
    "audit": (
        "records what VAN did on the owner's authority, not what it concluded about them. "
        "Erasing it would destroy the hash-chained evidence trail that makes every other "
        "claim checkable, including the claim that this deletion happened."
    ),
    "missions": (
        "the owner's own work. Forgetting what they asked for is not a privacy control, "
        "and mission cancellation is the owner control that belongs here."
    ),
}


class OwnerMemory:
    """What VAN holds about the owner, and the owner's ability to end it."""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def inventory(self, owner_principal_id: str = "owner") -> dict:
        """What is held, per store, before deciding to clear it."""
        held = {}
        for entry in FORGETTABLE:
            if entry.owner_column:
                row = await self.store.fetchone(
                    f"SELECT COUNT(*) AS n FROM {entry.table} WHERE {entry.owner_column} = ?",  # noqa: S608
                    (owner_principal_id,),
                )
            else:
                row = await self.store.fetchone(f"SELECT COUNT(*) AS n FROM {entry.table}", ())  # noqa: S608
            held[entry.table] = {"rows": int(row["n"]) if row else 0, "holds": entry.description}
        return {
            "owner_principal_id": owner_principal_id,
            "stores": held,
            "kept_deliberately": DELIBERATELY_KEPT,
        }

    async def forget_all(self, owner_principal_id: str = "owner") -> dict:
        """Delete everything VAN has concluded about the owner.

        Returns what was removed per store, so the owner sees the effect rather than a
        confirmation message. A store that was already empty reports zero rather than
        being left out, because "nothing was there" and "this was not touched" are
        different answers.
        """
        removed = {}
        # One connection and one transaction: a partial forget is worse than none, because
        # the owner is told it happened.
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                for entry in FORGETTABLE:
                    if entry.owner_column:
                        cursor = await db.execute(
                            f"DELETE FROM {entry.table} WHERE {entry.owner_column} = ?",  # noqa: S608
                            (owner_principal_id,),
                        )
                    else:
                        cursor = await db.execute(f"DELETE FROM {entry.table}", ())  # noqa: S608
                    removed[entry.table] = int(cursor.rowcount or 0)
            except BaseException:
                await db.rollback()
                raise
            await db.commit()
        return {
            "owner_principal_id": owner_principal_id,
            "removed": removed,
            "kept_deliberately": DELIBERATELY_KEPT,
        }

    async def forget_store(self, table: str, owner_principal_id: str = "owner") -> int:
        """Clear one store. Refuses a table that is not on the list."""
        entry = next((e for e in FORGETTABLE if e.table == table), None)
        if entry is None:
            raise ValueError(
                f"{table!r} is not an owner-derived store; "
                f"known stores are {sorted(e.table for e in FORGETTABLE)}"
            )
        async with self.store.connection() as db:
            if entry.owner_column:
                cursor = await db.execute(
                    f"DELETE FROM {entry.table} WHERE {entry.owner_column} = ?",  # noqa: S608
                    (owner_principal_id,),
                )
            else:
                cursor = await db.execute(f"DELETE FROM {entry.table}", ())  # noqa: S608
            await db.commit()
            return int(cursor.rowcount or 0)


__all__ = ["DELIBERATELY_KEPT", "FORGETTABLE", "ForgettableStore", "OwnerMemory"]
