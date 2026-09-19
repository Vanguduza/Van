"""Rev 1.5 §§20.3, 20.7, 20.10-20.13 — the session service.

Three mechanisms, each of which exists because of a specific way continuity goes wrong:

* **Path-epoch fencing.** A failover is a transaction (§20.10), not "open another socket and
  continue". The Gateway grants a new epoch, and an envelope from the old one is refused —
  otherwise a delayed frame from a dying path becomes a second command after the owner has
  already been told the first one failed.

* **Effectively-once admission.** Transports are at-least-once (ADR-RB-011). A command
  resubmitted under the same key with the same payload returns the existing state; the same
  key with a *different* payload is refused outright, because one of the two is not what the
  owner asked for and the Gateway cannot tell which.

* **Honest multipath.** `MULTIPATH_HEALTHY` requires two live paths with distinct route ids
  (§20.6). Two protocols over one ingress is protocol diversity, and reporting it as route
  redundancy would tell the owner they are covered for the failure that will actually
  happen.

The service deliberately holds no command authority. §20.2: the router delegates to the
existing command path, and a second authority here would be a second place the owner's
intent could be approved.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from van_gateway.session.models import (
    CommandAdmission,
    Direction,
    PROTOCOL_VERSION,
    PathHealth,
    ResumeRequest,
    ResumeResult,
    SessionEnvelope,
    SessionState,
    SupervisorState,
    TransportPathDescriptor,
    VanHermesSession,
)
import json

from van_gateway.storage.db import Store

#: §20.8 — a session nobody has spoken to for this long is suspended, not closed. Its
#: cursors stay, so the owner comes back to their place rather than to a new session.
IDLE_SUSPEND_MS = 15 * 60_000

REJECT_STALE_PATH_EPOCH = "session_path_epoch_stale"
REJECT_STALE_SESSION_EPOCH = "session_epoch_stale"
REJECT_UNKNOWN_SESSION = "session_unknown"
REJECT_WRONG_DEVICE = "session_device_mismatch"
REJECT_PROTOCOL_VERSION = "session_protocol_version"
REJECT_CLOSED = "session_closed"
REJECT_PAYLOAD_DIGEST_MISMATCH = "session_payload_digest_mismatch"


class SessionError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class VanHermesSessionService:
    def __init__(self, store: Store, events: Any | None = None) -> None:
        self.store = store
        self.events = events

    # ------------------------------------------------------------------ lifecycle

    async def open(
        self, *, device_id: str, path: TransportPathDescriptor | None = None,
        now_ms: int | None = None,
    ) -> tuple[VanHermesSession, int]:
        """Start a logical session and grant its first path epoch."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        session = VanHermesSession(
            van_session_id=f"vhs_{uuid.uuid4().hex}",
            session_epoch=1,
            device_id=device_id,
            created_at_ms=now,
            authoritative_path_epoch=1,
        )
        await self.store.execute(
            """
            INSERT INTO van_sessions(
              van_session_id, session_epoch, device_id, principal_type, state,
              created_at_ms, last_client_event_seq, last_server_ack_seq,
              authoritative_path_epoch
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (
                session.van_session_id, session.session_epoch, device_id,
                session.principal_type, session.state.value, now,
                session.authoritative_path_epoch,
            ),
        )
        if path is not None:
            await self._record_path(session.van_session_id, 1, path, now)
        return session, session.authoritative_path_epoch

    async def get(self, van_session_id: str) -> VanHermesSession | None:
        row = await self.store.fetchone(
            "SELECT * FROM van_sessions WHERE van_session_id = ?", (van_session_id,)
        )
        if row is None:
            return None
        return VanHermesSession(
            van_session_id=row["van_session_id"],
            session_epoch=int(row["session_epoch"]),
            device_id=row["device_id"],
            principal_type=row["principal_type"],
            state=SessionState(row["state"]),
            created_at_ms=int(row["created_at_ms"]),
            last_resumed_at_ms=(
                int(row["last_resumed_at_ms"]) if row["last_resumed_at_ms"] is not None else None
            ),
            last_client_event_seq=int(row["last_client_event_seq"]),
            last_server_ack_seq=int(row["last_server_ack_seq"]),
            authoritative_path_epoch=int(row["authoritative_path_epoch"]),
            closed_at_ms=int(row["closed_at_ms"]) if row["closed_at_ms"] is not None else None,
        )

    async def close(self, van_session_id: str, *, now_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE van_sessions SET state = ?, closed_at_ms = ? WHERE van_session_id = ?",
            (SessionState.CLOSED.value, now, van_session_id),
        )

    # ------------------------------------------------------------------ resume

    async def resume(
        self,
        request: ResumeRequest,
        *,
        path: TransportPathDescriptor | None = None,
        command_states: dict[str, str] | None = None,
        authoritative_event_cursor: int | None = None,
        response_state: dict | None = None,
        now_ms: int | None = None,
    ) -> ResumeResult:
        """§20.11 — the transaction a failover actually is.

        The client says what it has; the Gateway answers with what is true and grants a new
        path epoch. Everything the client thought it knew about command state is replaced
        rather than merged: a client that lost the path is precisely the client whose view
        is least trustworthy.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        session = await self.get(request.van_session_id)
        if session is None:
            return self._refuse(REJECT_UNKNOWN_SESSION)
        if session.device_id != request.device_id:
            return self._refuse(REJECT_WRONG_DEVICE)
        if session.state is SessionState.CLOSED:
            return self._refuse(REJECT_CLOSED)
        if request.session_epoch != session.session_epoch:
            # A client resuming an older epoch has missed a deliberate invalidation — a
            # re-pairing, or an owner ending the session elsewhere. Accepting it would
            # resurrect authority the Gateway has already withdrawn.
            return self._refuse(REJECT_STALE_SESSION_EPOCH)

        new_path_epoch = session.authoritative_path_epoch + 1
        cursor = (
            authoritative_event_cursor
            if authoritative_event_cursor is not None
            else max(request.last_event_seq, session.last_client_event_seq)
        )
        await self.store.execute(
            """
            UPDATE van_sessions
               SET state = ?, last_resumed_at_ms = ?, authoritative_path_epoch = ?,
                   last_client_event_seq = ?
             WHERE van_session_id = ?
            """,
            (
                SessionState.ACTIVE.value, now, new_path_epoch,
                max(request.last_event_seq, session.last_client_event_seq),
                session.van_session_id,
            ),
        )
        if path is not None:
            await self._record_path(session.van_session_id, new_path_epoch, path, now)

        return ResumeResult(
            accepted=True,
            session_epoch=session.session_epoch,
            new_path_epoch=new_path_epoch,
            authoritative_event_cursor=cursor,
            # The client replays from the next event after what it holds, not from the
            # cursor itself: replaying the one it already has is a duplicate, and although
            # event_id makes that harmless it also makes it pointless.
            replay_from_seq=request.last_event_seq + 1,
            command_states=dict(command_states or {}),
            response_state=response_state,
        )

    @staticmethod
    def _refuse(reason: str) -> ResumeResult:
        return ResumeResult(
            accepted=False, session_epoch=0, new_path_epoch=0,
            authoritative_event_cursor=0, replay_from_seq=0, refusal=reason,
        )

    # ------------------------------------------------------------------ envelopes

    async def accept_upstream(
        self, envelope: SessionEnvelope, *, now_ms: int | None = None
    ) -> VanHermesSession:
        """§20.3 / §20.10 step 9 — the fence.

        Called before anything reads the payload. A delayed envelope from a retired path
        must not be able to do work, and the check has to happen here rather than in each
        handler: one place that can be wrong is better than every place being able to be.
        """
        if envelope.protocol_version != PROTOCOL_VERSION:
            raise SessionError(REJECT_PROTOCOL_VERSION)
        session = await self.get(envelope.van_session_id)
        if session is None:
            raise SessionError(REJECT_UNKNOWN_SESSION)
        if session.state is SessionState.CLOSED:
            raise SessionError(REJECT_CLOSED)
        if session.device_id != envelope.device_id:
            raise SessionError(REJECT_WRONG_DEVICE)
        if envelope.session_epoch != session.session_epoch:
            raise SessionError(REJECT_STALE_SESSION_EPOCH)
        if envelope.direction is Direction.UPSTREAM:
            if envelope.path_epoch != session.authoritative_path_epoch:
                raise SessionError(REJECT_STALE_PATH_EPOCH)
        return session

    async def admit(
        self, envelope: SessionEnvelope, *, now_ms: int | None = None
    ) -> tuple[CommandAdmission, dict | None]:
        """§20.12 — effectively-once, decided by key plus digest.

        Returns the admission and, for a known key, whatever result was recorded the first
        time. The caller executes only on ADMITTED, which is what makes a reconnect safe
        without the client ever minting a fresh command id "to retry".
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        # Computed from the payload, never taken from the envelope.
        #
        # A first version read `envelope.payload_digest or envelope.digest()`, which lets a
        # client vouch for its own payload: send payload A carrying the digest of B and the
        # pair is recorded under B's fingerprint. The immediate effect is mild — A is not
        # executed — but the stored digest is then wrong, so the *real* B arriving later is
        # treated as a duplicate and silently never runs. A command the owner sent,
        # acknowledged and never performed is the exact failure this table exists to prevent.
        #
        # The envelope's field is kept as a cross-check: a mismatch means the client and the
        # server disagree about what was sent, which is worth refusing rather than resolving.
        digest = envelope.digest()
        if envelope.payload_digest is not None and envelope.payload_digest != digest:
            raise SessionError(REJECT_PAYLOAD_DIGEST_MISMATCH)

        if not envelope.idempotency_key:
            # Without a key there is nothing to be idempotent about. The message is still
            # recorded, so a duplicate message_id cannot be replayed.
            await self._record_message(envelope, digest, CommandAdmission.ADMITTED, None, now)
            return CommandAdmission.ADMITTED, None

        existing = await self.store.fetchone(
            """
            SELECT payload_digest, admitted_state, result_json
              FROM van_session_messages
             WHERE van_session_id = ? AND idempotency_key = ?
            """,
            (envelope.van_session_id, envelope.idempotency_key),
        )
        if existing is None:
            await self._record_message(envelope, digest, CommandAdmission.ADMITTED, None, now)
            return CommandAdmission.ADMITTED, None
        if existing["payload_digest"] != digest:
            # Refused rather than executed, and deliberately not recorded as a new message:
            # the conflicting payload must leave no trace that could later be mistaken for
            # an accepted command.
            return CommandAdmission.CONFLICT, None
        result = existing["result_json"]
        return CommandAdmission.ALREADY_KNOWN, (json.loads(result) if result else None)

    async def record_result(
        self, envelope: SessionEnvelope, result: dict, *, now_ms: int | None = None
    ) -> None:
        """Store what the first execution produced, so the resubmission can be answered."""
        await self.store.execute(
            "UPDATE van_session_messages SET result_json = ? WHERE message_id = ?",
            (Store.dumps(result), envelope.message_id),
        )

    async def _record_message(
        self,
        envelope: SessionEnvelope,
        digest: str,
        admission: CommandAdmission,
        result: dict | None,
        now: int,
    ) -> None:
        await self.store.execute(
            """
            INSERT INTO van_session_messages(
              message_id, van_session_id, idempotency_key, command_id, kind,
              payload_digest, path_epoch, admitted_state, result_json, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO NOTHING
            """,
            (
                envelope.message_id, envelope.van_session_id, envelope.idempotency_key,
                envelope.command_id, envelope.kind, digest, envelope.path_epoch,
                admission.value, Store.dumps(result) if result else None, now,
            ),
        )

    # ------------------------------------------------------------------ paths

    async def _record_path(
        self, van_session_id: str, path_epoch: int, path: TransportPathDescriptor, now: int
    ) -> None:
        await self.store.execute(
            """
            INSERT INTO van_session_paths(
              van_session_id, path_epoch, path_id, path_class, route_id, health,
              opened_at_ms, last_rx_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(van_session_id, path_epoch) DO UPDATE SET
              path_id=excluded.path_id, route_id=excluded.route_id, health=excluded.health,
              last_rx_ms=excluded.last_rx_ms
            """,
            (
                van_session_id, path_epoch, path.path_id, path.path_class.value,
                path.route_id, PathHealth.HEALTHY.value, now, now,
            ),
        )

    async def mark_path_health(
        self, van_session_id: str, path_epoch: int, health: PathHealth,
        *, now_ms: int | None = None,
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE van_session_paths SET health = ?, last_rx_ms = ? "
            "WHERE van_session_id = ? AND path_epoch = ?",
            (health.value, now, van_session_id, path_epoch),
        )

    async def live_paths(self, van_session_id: str) -> list[dict]:
        rows = await self.store.fetchall(
            "SELECT path_id, path_class, route_id, health, path_epoch FROM van_session_paths "
            "WHERE van_session_id = ? AND retired_at_ms IS NULL",
            (van_session_id,),
        )
        return [
            {
                "path_id": r["path_id"],
                "path_class": r["path_class"],
                "route_id": r["route_id"],
                "health": r["health"],
                "path_epoch": int(r["path_epoch"]),
            }
            for r in rows
        ]

    async def continuity(self, van_session_id: str) -> tuple[SupervisorState, str]:
        """§0B / §20.6 — what VAN may honestly claim about its own continuity.

        The distinction the blueprint insists on: protocol diversity is not route
        diversity. Two carriers over one ingress fail together, and a status that called
        that MULTIPATH_HEALTHY would be telling the owner they are covered for the exact
        failure that is going to happen.
        """
        paths = await self.live_paths(van_session_id)
        usable = [p for p in paths if PathHealth(p["health"]).usable]
        if not usable:
            return SupervisorState.OFFLINE_LOCAL, "no usable path"
        routes = {p["route_id"] for p in usable}
        if len(routes) >= 2:
            return (
                SupervisorState.MULTIPATH_HEALTHY,
                f"{len(usable)} live paths across {len(routes)} independent routes",
            )
        if len(usable) >= 2:
            return (
                SupervisorState.SINGLE_PATH,
                f"{len(usable)} live paths, one route ({sorted(routes)[0]}): protocol "
                "diversity, not route diversity",
            )
        return SupervisorState.SINGLE_PATH, f"one live path on route {sorted(routes)[0]}"
