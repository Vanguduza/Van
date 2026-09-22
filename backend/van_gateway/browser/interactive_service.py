"""Rev 1.5 §§5.1, 5.2, 6.2 — the interactive session lifecycle.

This is the Gateway's half of a remote browser: it authorises a session, holds the profile
lease on its behalf, tracks which tab is in front of the owner, records the durable events
and refuses actuation the moment any of that stops being true.

It does **not** touch pixels, WebRTC or CDP. §1 is explicit that the Gateway is not in the
pixel loop, and a service that both authorises and streams would put an encoder's latency
inside an authority decision.

Two rules from the audit are load-bearing here and are implemented rather than described:

* `INTERACTIVE` is not success. §5.2 forbids any surface inferring a completed browser task
  from a session state, which is `P0-EXEC-003`'s defect one layer out.
* An expired profile lease stops actuation **at the expiry instant** (§0E.1 D7). The
  30-second grace is for cleanup and reconnect only; video may stay frozen, nothing may act.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from van_gateway.automation.canonical import digest
from van_gateway.browser.control_lease import ControlLeaseError, ControlLeaseService
from van_gateway.browser.flood_bounds import (
    MAX_OPEN_TABS_PER_SESSION,
    REJECT_TAB_FLOOD,
)
from van_gateway.browser.interactive_models import (
    BrowserControlHolder,
    DURABLE_SESSION_EVENTS,
    InteractiveBrowserSession,
    InteractiveSessionState,
    ProfileLeaseHolderKind,
    Viewport,
    may_transition,
)
from van_gateway.browser.policy import BrowserPolicyError
from van_gateway.browser.service import BrowserSessionBroker
from van_gateway.observability import instruments
from van_gateway.storage.db import Store


class InteractiveSessionError(Exception):
    pass


#: §6.1 — the viewport a grant will authorise. A phone asking for a 16k viewport is asking
#: the stream host to allocate a surface nobody can see; the ceiling is enforced where the
#: session is created rather than trusted from the client.
MAX_VIEWPORT_WIDTH = 2400
MAX_VIEWPORT_HEIGHT = 2400
MAX_FPS = 60

#: How long a session may exist without the device being seen. §29's recovery path suspends
#: rather than terminates, so a phone that loses signal in a lift comes back to its tabs.
SESSION_TTL_MS = 30 * 60_000


class InteractiveSessionService:
    def __init__(
        self,
        store: Store,
        broker: BrowserSessionBroker,
        control: ControlLeaseService,
        events: Any | None = None,
    ) -> None:
        self.store = store
        self.broker = broker
        self.control = control
        self.events = events

    # ------------------------------------------------------------------ creation

    async def create(
        self,
        *,
        owner_device_id: str,
        profile_alias: str,
        viewport: Viewport,
        requested_fps: int = 60,
        mission_id: str | None = None,
        originating_command_id: str | None = None,
        idempotency_key: str | None = None,
        now_ms: int | None = None,
    ) -> InteractiveBrowserSession:
        """§6.2 — authorise, lease, record, and only then hand out a session.

        The profile lease is acquired *before* the session row exists. Doing it the other way
        round leaves a session that believes it owns a profile it never got, which is the
        state an owner sees as a browser that opens and then does nothing.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms

        if idempotency_key:
            existing = await self.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                # §6.1 sends an idempotency key precisely because the phone may retry after
                # an ambiguous failure. Returning the existing session is the only answer
                # that does not leak a second profile lease on every retry.
                return existing

        # §0A/B3 — the alias must exist in config/browser/profiles.yaml. The policy engine
        # owns that question; this service does not keep a second list.
        self.broker.policy.check_profile(profile_alias)

        if viewport.width > MAX_VIEWPORT_WIDTH or viewport.height > MAX_VIEWPORT_HEIGHT:
            raise InteractiveSessionError("interactive_viewport_too_large")
        fps = max(1, min(int(requested_fps), MAX_FPS))

        session_id = f"ibs_{uuid.uuid4().hex}"
        try:
            lease = await self.broker.acquire_lease(
                profile_alias=profile_alias,
                holder_kind=ProfileLeaseHolderKind.INTERACTIVE_SESSION,
                holder_id=session_id,
                now_ms=now,
            )
        except BrowserPolicyError as exc:
            raise InteractiveSessionError(str(exc)) from exc

        session = InteractiveBrowserSession(
            session_id=session_id,
            owner_device_id=owner_device_id,
            profile_alias=profile_alias,
            profile_lease_id=lease.lease_id,
            state=InteractiveSessionState.AUTHORIZED,
            viewport=viewport,
            requested_fps=fps,
            control_holder=BrowserControlHolder.OWNER,
            created_at_ms=now,
            expires_at_ms=now + SESSION_TTL_MS,
            mission_id=mission_id,
            originating_command_id=originating_command_id,
            idempotency_key=idempotency_key,
            last_profile_lease_renewed_at_ms=now,
        )
        await self._insert(session)
        await self._refresh_active_sessions_gauge()
        # The owner holds control from the first instant. A session that starts with NONE
        # would need a grant before the owner could touch their own browser.
        control = await self.control.issue(
            session_id=session_id,
            holder=BrowserControlHolder.OWNER,
            issued_for=owner_device_id,
            now_ms=now,
            revoke_reason="session_created",
        )
        session.control_lease_id = control.control_lease_id
        session.control_generation = control.generation
        await self.record_event(
            session_id=session_id, event_type="session.created", severity="INFO",
            summary=f"Interactive browser session on {profile_alias}", now_ms=now,
            payload={"profile_alias": profile_alias, "mission_id": mission_id},
            device_id=owner_device_id,
        )
        return session

    # ------------------------------------------------------------------ reads

    async def get(self, session_id: str) -> InteractiveBrowserSession | None:
        row = await self.store.fetchone(
            "SELECT * FROM browser_interactive_sessions WHERE session_id = ?", (session_id,)
        )
        return None if row is None else self._row_to_session(row)

    async def get_by_idempotency_key(self, key: str) -> InteractiveBrowserSession | None:
        row = await self.store.fetchone(
            "SELECT * FROM browser_interactive_sessions WHERE idempotency_key = ?", (key,)
        )
        return None if row is None else self._row_to_session(row)

    async def list_for_device(self, device_id: str) -> list[InteractiveBrowserSession]:
        rows = await self.store.fetchall(
            "SELECT * FROM browser_interactive_sessions WHERE owner_device_id = ? "
            "ORDER BY created_at_ms DESC",
            (device_id,),
        )
        return [self._row_to_session(r) for r in rows]

    # ------------------------------------------------------------------ transitions

    async def transition(
        self,
        *,
        session_id: str,
        target: InteractiveSessionState,
        reason: str | None = None,
        now_ms: int | None = None,
    ) -> InteractiveBrowserSession:
        """§5.2 — the ladder, enforced from the table rather than from scattered conditions."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        session = await self.get(session_id)
        if session is None:
            raise InteractiveSessionError("interactive_session_unknown")
        if session.state is target:
            return session
        if not may_transition(session.state, target):
            raise InteractiveSessionError(
                f"interactive_transition_forbidden:{session.state.value}->{target.value}"
            )

        fields: dict[str, Any] = {"state": target.value}
        if target is InteractiveSessionState.INTERACTIVE and session.connected_at_ms is None:
            fields["connected_at_ms"] = now
        if target is InteractiveSessionState.SUSPENDED:
            fields["suspended_at_ms"] = now
        if target in {InteractiveSessionState.TERMINATED, InteractiveSessionState.FAILED}:
            fields["terminated_at_ms"] = now
            fields["final_reason"] = reason
        await self._update(session_id, fields)

        await self.record_event(
            session_id=session_id, event_type="session.state_changed", severity="INFO",
            summary=f"{session.state.value} -> {target.value}", now_ms=now,
            payload={"from": session.state.value, "to": target.value, "reason": reason},
            device_id=session.owner_device_id,
        )

        if target in {InteractiveSessionState.TERMINATED, InteractiveSessionState.FAILED}:
            await self._release(session, reason or target.value, now)

        updated = await self.get(session_id)
        assert updated is not None
        return updated

    async def _release(self, session: InteractiveBrowserSession, reason: str, now: int) -> None:
        """Give the profile back and leave nobody holding control."""
        await self.control.revoke(session_id=session.session_id, reason=reason, now_ms=now)
        if session.profile_lease_id:
            await self.store.execute(
                "UPDATE browser_profiles SET lease_holder = NULL, lease_expires_at_ms = NULL, "
                "lease_holder_kind = NULL, lease_holder_id = NULL, updated_at_ms = ? "
                "WHERE lease_holder = ?",
                (now, session.profile_lease_id),
            )
        await self.record_event(
            session_id=session.session_id, event_type="session.ended", severity="INFO",
            summary=reason, now_ms=now, device_id=session.owner_device_id,
        )
        await self._refresh_active_sessions_gauge()

    async def _refresh_active_sessions_gauge(self) -> None:
        """Rev 1.5 §28.1 — `van_browser_session_active`, the one gauge the Gateway can
        report honestly about the Remote Browser without a Stream Host attached.

        Queried rather than kept as a running counter: a process restart would otherwise
        resume counting from zero while sessions a crash never released are still open in
        the store, and a gauge that lies about "how many" is worse than one that costs a
        cheap `COUNT(*)` on every create/release.
        """
        row = await self.store.fetchone(
            "SELECT COUNT(*) AS n FROM browser_interactive_sessions "
            "WHERE state NOT IN (?, ?)",
            (InteractiveSessionState.TERMINATED.value, InteractiveSessionState.FAILED.value),
        )
        instruments.set_browser_sessions_active(int(row["n"]) if row is not None else 0)

    # ------------------------------------------------------------------ the lease heartbeat

    async def heartbeat(
        self, *, session_id: str, now_ms: int | None = None
    ) -> InteractiveBrowserSession:
        """§5.3 — the device says it is still here, and the lease is renewed if it is due.

        Failure to renew is not survivable by ignoring it: the session goes to SUSPENDED and
        actuation stops. §5.3 step 6 — if reacquisition fails, the session terminates.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        session = await self.get(session_id)
        if session is None:
            raise InteractiveSessionError("interactive_session_unknown")
        await self._update(session_id, {"last_client_seen_at_ms": now})

        row = await self.store.fetchone(
            "SELECT lease_expires_at_ms, lease_generation FROM browser_profiles WHERE lease_holder = ?",
            (session.profile_lease_id,),
        )
        if row is None:
            await self._lease_lost(session, "browser_profile_lease_lost", now)
            raise InteractiveSessionError("browser_profile_lease_lost")

        remaining = int(row["lease_expires_at_ms"] or 0) - now
        if remaining <= 0:
            await self._lease_lost(session, "browser_profile_lease_expired", now)
            raise InteractiveSessionError("browser_profile_lease_expired")

        if remaining < self.broker.RENEW_WHEN_REMAINING_MS:
            try:
                await self.broker.renew_lease(
                    lease_id=session.profile_lease_id or "",
                    holder_id=session_id,
                    generation=int(row["lease_generation"]),
                    now_ms=now,
                )
            except BrowserPolicyError as exc:
                await self._lease_lost(session, str(exc), now)
                raise InteractiveSessionError(str(exc)) from exc
            await self._update(session_id, {"last_profile_lease_renewed_at_ms": now})

        updated = await self.get(session_id)
        assert updated is not None
        return updated

    async def _lease_lost(
        self, session: InteractiveBrowserSession, reason: str, now: int
    ) -> None:
        """Stop actuation first, then tell the owner. Not the other way round."""
        await self.control.revoke(session_id=session.session_id, reason=reason, now_ms=now)
        await self.record_event(
            session_id=session.session_id, event_type="session.lease_expired",
            severity="WARNING", summary=reason, now_ms=now,
            device_id=session.owner_device_id,
        )
        if may_transition(session.state, InteractiveSessionState.SUSPENDED):
            await self._update(
                session.session_id,
                {"state": InteractiveSessionState.SUSPENDED.value, "suspended_at_ms": now},
            )

    async def assert_may_actuate(
        self,
        *,
        session_id: str,
        control_lease_id: str,
        control_generation: int,
        viewport_revision: int,
        now_ms: int | None = None,
    ) -> InteractiveBrowserSession:
        """The whole gate, in the order the failures matter.

        Session state, then profile lease, then control lease, then viewport revision. The
        order is not cosmetic: a caller whose session has ended should be told that rather
        than being told its coordinates are stale.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        session = await self.get(session_id)
        if session is None:
            raise InteractiveSessionError("interactive_session_unknown")
        if not session.state.can_actuate:
            raise InteractiveSessionError(f"interactive_session_not_actuatable:{session.state.value}")

        row = await self.store.fetchone(
            "SELECT lease_expires_at_ms FROM browser_profiles WHERE lease_holder = ?",
            (session.profile_lease_id,),
        )
        if row is None or int(row["lease_expires_at_ms"] or 0) <= now:
            # §0E.1 D7 — at the expiry instant, not after a grace period.
            raise InteractiveSessionError("browser_profile_lease_expired")

        try:
            await self.control.assert_may_actuate(
                session_id=session_id,
                control_lease_id=control_lease_id,
                control_generation=control_generation,
                now_ms=now,
            )
        except ControlLeaseError as exc:
            raise InteractiveSessionError(str(exc)) from exc

        if int(viewport_revision) != session.viewport.revision:
            # §8.1 — refused, never transformed. After a reflow the old coordinates do not
            # describe a scaled version of the new page; they describe a different page.
            raise InteractiveSessionError("interactive_viewport_revision_stale")
        if session.acked_viewport_revision != session.viewport.revision:
            raise InteractiveSessionError("interactive_viewport_not_acknowledged")
        return session

    # ------------------------------------------------------------------ viewport

    async def propose_viewport(
        self, *, session_id: str, viewport: Viewport, now_ms: int | None = None
    ) -> int:
        """A resize bumps the revision and withholds actuation until the device acks it."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        session = await self.get(session_id)
        if session is None:
            raise InteractiveSessionError("interactive_session_unknown")
        if viewport.width > MAX_VIEWPORT_WIDTH or viewport.height > MAX_VIEWPORT_HEIGHT:
            raise InteractiveSessionError("interactive_viewport_too_large")
        revision = session.viewport.revision + 1
        await self._update(
            session_id,
            {
                "viewport_width": viewport.width,
                "viewport_height": viewport.height,
                "device_scale_factor": viewport.device_scale_factor,
                "viewport_revision": revision,
            },
        )
        return revision

    async def acknowledge_viewport(
        self, *, session_id: str, revision: int, now_ms: int | None = None
    ) -> None:
        session = await self.get(session_id)
        if session is None:
            raise InteractiveSessionError("interactive_session_unknown")
        if int(revision) != session.viewport.revision:
            # Acking an old revision would re-enable actuation against a layout that no
            # longer exists, which is the defect the revision was introduced to prevent.
            raise InteractiveSessionError("interactive_viewport_ack_stale")
        await self._update(session_id, {"acked_viewport_revision": int(revision)})

    # ------------------------------------------------------------------ targets, events

    async def record_active_url(
        self, *, session_id: str, target_id: str, url: str, title: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        """The URL is stored as a digest, like browser evidence (§5.1).

        A session's history is owner data. Keeping the plaintext here would put the owner's
        browsing in the Gateway's database as a byproduct of drawing a tab strip.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        url_digest = digest(url)
        # §38 item 17 — a tab flood. Checked before the insert and only for a target this
        # session has not seen: a page navigating in a tab it already owns is ordinary,
        # and refusing that would break the common case to bound the rare one.
        #
        # The new tab is refused rather than an old one closed. Closing loses whatever the
        # owner had open, which is the harm rather than the defence.
        known = await self.store.fetchone(
            "SELECT 1 FROM browser_session_targets WHERE session_id = ? AND target_id = ?",
            (session_id, target_id),
        )
        if known is None:
            open_tabs = await self.store.fetchone(
                "SELECT COUNT(*) AS n FROM browser_session_targets "
                "WHERE session_id = ? AND closed_at_ms IS NULL",
                (session_id,),
            )
            if int(open_tabs["n"]) >= MAX_OPEN_TABS_PER_SESSION:
                raise InteractiveSessionError(REJECT_TAB_FLOOD)
        await self.store.execute(
            """
            INSERT INTO browser_session_targets(
              session_id, target_id, title, url_digest, is_active, created_at_ms
            ) VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(session_id, target_id) DO UPDATE SET
              title=excluded.title, url_digest=excluded.url_digest, is_active=1
            """,
            (session_id, target_id, title, url_digest, now),
        )
        await self.store.execute(
            "UPDATE browser_session_targets SET is_active = 0 "
            "WHERE session_id = ? AND target_id != ?",
            (session_id, target_id),
        )
        await self._update(
            session_id, {"active_target_id": target_id, "active_url_digest": url_digest}
        )
        await self.record_event(
            session_id=session_id, event_type="session.url_changed", severity="INFO",
            summary=title or "page changed", now_ms=now,
            payload={"target_id": target_id, "url_digest": url_digest},
        )

    async def record_event(
        self,
        *,
        session_id: str,
        event_type: str,
        severity: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        evidence_ref: str | None = None,
        device_id: str | None = None,
        now_ms: int | None = None,
    ) -> str:
        """ADR-RB-008 — durable state changes only.

        The allowlist is enforced rather than documented. Without it the first person to
        want better telemetry writes pointer motion into the ledger, and the ledger stops
        being readable exactly when someone needs to read it.
        """
        if event_type not in DURABLE_SESSION_EVENTS:
            raise InteractiveSessionError(f"interactive_event_not_durable:{event_type}")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        event_id = f"bse_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO browser_session_events(
              event_id, session_id, event_type, severity, summary, payload_json,
              evidence_ref, occurred_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, session_id, event_type, severity, summary,
                Store.dumps(payload or {}), evidence_ref, now,
            ),
        )
        if self.events is not None and device_id is not None:
            await self.events.publish(
                event_type,
                {"session_id": session_id, "summary": summary, **(payload or {})},
                target_device_id=device_id,
                event_id=event_id,
                occurred_at_ms=now,
            )
        return event_id

    async def session_events(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.store.fetchall(
            "SELECT * FROM browser_session_events WHERE session_id = ? "
            "ORDER BY occurred_at_ms DESC LIMIT ?",
            (session_id, limit),
        )
        return [
            {
                "event_id": r["event_id"],
                "event_type": r["event_type"],
                "severity": r["severity"],
                "summary": r["summary"],
                "occurred_at_ms": int(r["occurred_at_ms"]),
                "evidence_ref": r["evidence_ref"],
            }
            for r in rows
        ]

    async def targets(self, session_id: str) -> list[dict[str, Any]]:
        rows = await self.store.fetchall(
            "SELECT * FROM browser_session_targets WHERE session_id = ? AND closed_at_ms IS NULL "
            "ORDER BY created_at_ms ASC",
            (session_id,),
        )
        return [
            {
                "target_id": r["target_id"],
                "title": r["title"],
                "url_digest": r["url_digest"],
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ persistence

    async def _insert(self, s: InteractiveBrowserSession) -> None:
        await self.store.execute(
            """
            INSERT INTO browser_interactive_sessions(
              session_id, owner_device_id, profile_alias, profile_lease_id, state,
              active_target_id, active_url_digest,
              viewport_width, viewport_height, device_scale_factor, viewport_revision,
              acked_viewport_revision, requested_fps, negotiated_codec, negotiated_transport,
              control_holder, control_lease_id, control_generation,
              created_at_ms, connected_at_ms, last_client_seen_at_ms,
              last_profile_lease_renewed_at_ms, suspended_at_ms, expires_at_ms,
              terminated_at_ms, final_reason, mission_id, originating_command_id, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s.session_id, s.owner_device_id, s.profile_alias, s.profile_lease_id, s.state.value,
                s.active_target_id, s.active_url_digest,
                s.viewport.width, s.viewport.height, s.viewport.device_scale_factor,
                s.viewport.revision, s.acked_viewport_revision, s.requested_fps,
                s.negotiated_codec, s.negotiated_transport,
                s.control_holder.value, s.control_lease_id, s.control_generation,
                s.created_at_ms, s.connected_at_ms, s.last_client_seen_at_ms,
                s.last_profile_lease_renewed_at_ms, s.suspended_at_ms, s.expires_at_ms,
                s.terminated_at_ms, s.final_reason, s.mission_id, s.originating_command_id,
                s.idempotency_key,
            ),
        )

    async def _update(self, session_id: str, fields: dict[str, Any]) -> None:
        assignments = ", ".join(f"{k} = ?" for k in fields)
        await self.store.execute(
            f"UPDATE browser_interactive_sessions SET {assignments} WHERE session_id = ?",
            (*fields.values(), session_id),
        )

    @staticmethod
    def _row_to_session(row: Any) -> InteractiveBrowserSession:
        return InteractiveBrowserSession(
            session_id=row["session_id"],
            owner_device_id=row["owner_device_id"],
            profile_alias=row["profile_alias"],
            profile_lease_id=row["profile_lease_id"],
            state=InteractiveSessionState(row["state"]),
            active_target_id=row["active_target_id"],
            active_url_digest=row["active_url_digest"],
            viewport=Viewport(
                width=int(row["viewport_width"]),
                height=int(row["viewport_height"]),
                device_scale_factor=float(row["device_scale_factor"]),
                revision=int(row["viewport_revision"]),
            ),
            acked_viewport_revision=(
                int(row["acked_viewport_revision"])
                if row["acked_viewport_revision"] is not None else None
            ),
            requested_fps=int(row["requested_fps"]),
            negotiated_codec=row["negotiated_codec"],
            negotiated_transport=row["negotiated_transport"],
            control_holder=BrowserControlHolder(row["control_holder"]),
            control_lease_id=row["control_lease_id"],
            control_generation=int(row["control_generation"]),
            created_at_ms=int(row["created_at_ms"]),
            connected_at_ms=_opt_int(row["connected_at_ms"]),
            last_client_seen_at_ms=_opt_int(row["last_client_seen_at_ms"]),
            last_profile_lease_renewed_at_ms=_opt_int(row["last_profile_lease_renewed_at_ms"]),
            suspended_at_ms=_opt_int(row["suspended_at_ms"]),
            expires_at_ms=int(row["expires_at_ms"]),
            terminated_at_ms=_opt_int(row["terminated_at_ms"]),
            final_reason=row["final_reason"],
            mission_id=row["mission_id"],
            originating_command_id=row["originating_command_id"],
            idempotency_key=row["idempotency_key"],
        )


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)
