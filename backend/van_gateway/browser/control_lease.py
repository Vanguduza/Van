"""Rev 1.5 §5.4 and ADR-RB-006/007 — who may actuate inside an open session.

The profile lease answers "whose browser profile is this". This answers "whose hands are on
it right now", and the two are separate on purpose: an owner handing the keyboard to Hermes
must not have to give up their tabs, and Hermes finishing a task must not evict the owner
from the profile.

There may be many observers. There is exactly one control holder, and the fence that makes
that true under concurrency is the generation: `UNIQUE (session_id, generation)` in migration
27 means a generation is issued once, ever. An actuation packet naming an older one is not
merely out of date — it names an authority that no longer exists, and is refused.

**Owner touch wins** (ADR-RB-007). A first intentional owner event preempts the agent, and
the preemption is not a request the agent may decline: the generation moves, and every packet
the agent has in flight becomes invalid at the same instant.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from van_gateway.browser.interactive_models import BrowserControlHolder, BrowserControlLease
from van_gateway.storage.db import Store


class ControlLeaseError(Exception):
    """Refusals carry a code, because the owner and the agent are sent to different places."""


#: §5.4 — how long a control lease lives without being renewed.
#:
#: Deliberately short for an agent and long for the owner. An agent that stops responding
#: mid-task must not keep the keyboard; an owner reading a page is not doing anything wrong
#: by not touching it for a minute.
DEFAULT_TTL_MS = {
    BrowserControlHolder.OWNER: 15 * 60_000,
    BrowserControlHolder.HERMES_DETERMINISTIC: 120_000,
    BrowserControlHolder.HERMES_STAGEHAND: 120_000,
    BrowserControlHolder.SYSTEM_RECOVERY: 60_000,
    BrowserControlHolder.NONE: 0,
}


class ControlLeaseService:
    def __init__(self, store: Store) -> None:
        self.store = store

    # ------------------------------------------------------------------ reads

    async def current(self, session_id: str) -> BrowserControlLease | None:
        row = await self.store.fetchone(
            """
            SELECT * FROM browser_control_leases
             WHERE session_id = ?
             ORDER BY generation DESC LIMIT 1
            """,
            (session_id,),
        )
        return None if row is None else self._row_to_lease(row)

    @staticmethod
    def _row_to_lease(row: Any) -> BrowserControlLease:
        return BrowserControlLease(
            control_lease_id=row["control_lease_id"],
            session_id=row["session_id"],
            holder=BrowserControlHolder(row["holder"]),
            issued_for=row["issued_for"],
            issued_at_ms=int(row["issued_at_ms"]),
            expires_at_ms=int(row["expires_at_ms"]),
            generation=int(row["generation"]),
            revoked_at_ms=int(row["revoked_at_ms"]) if row["revoked_at_ms"] is not None else None,
            revoke_reason=row["revoke_reason"],
        )

    # ------------------------------------------------------------------ writes

    async def issue(
        self,
        *,
        session_id: str,
        holder: BrowserControlHolder,
        issued_for: str,
        ttl_ms: int | None = None,
        now_ms: int | None = None,
        revoke_reason: str = "superseded",
    ) -> BrowserControlLease:
        """Take control, revoking whoever held it.

        The generation is read and written inside one transaction. Two callers racing here
        both compute the same next generation, and the second insert fails on the unique
        index rather than silently producing two leases that each believe they are current —
        which is precisely the "exactly one control holder" claim being false while both
        rows look fine individually.
        """
        if holder is BrowserControlHolder.NONE:
            raise ControlLeaseError("control_lease_requires_a_holder")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        ttl = int(ttl_ms if ttl_ms is not None else DEFAULT_TTL_MS[holder])
        lease_id = f"bctl_{uuid.uuid4().hex}"

        async with self.store.connection() as db:
            cur = await db.execute(
                "SELECT COALESCE(MAX(generation), 0) AS g FROM browser_control_leases WHERE session_id = ?",
                (session_id,),
            )
            generation = int((await cur.fetchone())["g"]) + 1

            await db.execute(
                """
                UPDATE browser_control_leases
                   SET revoked_at_ms = ?, revoke_reason = ?
                 WHERE session_id = ? AND revoked_at_ms IS NULL
                """,
                (now, revoke_reason, session_id),
            )
            await db.execute(
                """
                INSERT INTO browser_control_leases(
                  control_lease_id, session_id, holder, issued_for,
                  issued_at_ms, expires_at_ms, generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (lease_id, session_id, holder.value, issued_for, now, now + ttl, generation),
            )
            await db.execute(
                """
                UPDATE browser_interactive_sessions
                   SET control_holder = ?, control_lease_id = ?, control_generation = ?
                 WHERE session_id = ?
                """,
                (holder.value, lease_id, generation, session_id),
            )
            await db.commit()

        return BrowserControlLease(
            control_lease_id=lease_id, session_id=session_id, holder=holder,
            issued_for=issued_for, issued_at_ms=now, expires_at_ms=now + ttl,
            generation=generation,
        )

    async def owner_preempt(
        self, *, session_id: str, device_id: str, now_ms: int | None = None
    ) -> BrowserControlLease:
        """ADR-RB-007 — the owner touched the viewport.

        This is not a negotiation. The agent's lease is revoked in the same transaction that
        issues the owner's, so there is no window in which both are live and no way for the
        agent to "finish the current action first". Its queued input is invalidated by the
        generation moving, rather than by anyone remembering to drop it.
        """
        return await self.issue(
            session_id=session_id,
            holder=BrowserControlHolder.OWNER,
            issued_for=device_id,
            now_ms=now_ms,
            revoke_reason="owner_preempt",
        )

    async def delegate(
        self,
        *,
        session_id: str,
        holder: BrowserControlHolder,
        issued_for: str,
        now_ms: int | None = None,
    ) -> BrowserControlLease:
        """Hand actuation to an agent. Only the owner may do this.

        An agent may not delegate to another agent, and SYSTEM_RECOVERY may not delegate at
        all: recovery exists to put a session back into a state the owner can use, and a
        recovery path that can hand control onward is a path that can launder authority.
        """
        if not holder.is_agent:
            raise ControlLeaseError("control_delegation_requires_an_agent_holder")
        existing = await self.current(session_id)
        if existing is not None and existing.holder is not BrowserControlHolder.OWNER:
            raise ControlLeaseError("control_delegation_requires_owner_control")
        return await self.issue(
            session_id=session_id, holder=holder, issued_for=issued_for,
            now_ms=now_ms, revoke_reason="delegated",
        )

    async def revoke(
        self, *, session_id: str, reason: str, now_ms: int | None = None
    ) -> None:
        """Leave the session with no control holder. Actuation then fails closed."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            await db.execute(
                """
                UPDATE browser_control_leases
                   SET revoked_at_ms = ?, revoke_reason = ?
                 WHERE session_id = ? AND revoked_at_ms IS NULL
                """,
                (now, reason, session_id),
            )
            await db.execute(
                """
                UPDATE browser_interactive_sessions
                   SET control_holder = ?, control_lease_id = NULL
                 WHERE session_id = ?
                """,
                (BrowserControlHolder.NONE.value, session_id),
            )
            await db.commit()

    # ------------------------------------------------------------------ the check

    async def assert_may_actuate(
        self,
        *,
        session_id: str,
        control_lease_id: str,
        control_generation: int,
        now_ms: int | None = None,
    ) -> BrowserControlLease:
        """§8.1 — every actuation packet is checked against the live lease.

        Four separate refusals rather than one, because they mean different things to
        whoever is holding the other end: unknown, superseded, revoked, expired.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        lease = await self.current(session_id)
        if lease is None:
            raise ControlLeaseError("control_lease_absent")
        if lease.control_lease_id != control_lease_id:
            raise ControlLeaseError("control_lease_superseded")
        if lease.generation != int(control_generation):
            raise ControlLeaseError("control_generation_stale")
        if lease.revoked_at_ms is not None:
            raise ControlLeaseError("control_lease_revoked")
        if now >= lease.expires_at_ms:
            raise ControlLeaseError("control_lease_expired")
        return lease
