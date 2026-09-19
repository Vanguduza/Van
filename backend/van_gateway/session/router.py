"""Rev 1.5 §20.2 — the session router.

The router turns a transport-independent envelope into a call on an authority that already
exists. §20.2 is explicit that it "does not create a second command authority", and that is
the whole design constraint: every kind this router knows about is delegated, and a kind it
does not know is refused rather than interpreted.

That refusal matters more than it looks. A router with a permissive default becomes a second
ingress: whatever a future kind means, it would arrive here with a device token and be
handled by whatever code happened to be nearest.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from van_gateway.session.models import (
    CommandAdmission,
    Direction,
    SessionEnvelope,
)
from van_gateway.session.service import SessionError, VanHermesSessionService

REJECT_UNKNOWN_KIND = "session_kind_unknown"
REJECT_WRONG_DIRECTION = "session_direction_invalid"
REJECT_EXPIRED = "session_message_expired"
REJECT_CONFLICT = "session_idempotency_conflict"

#: The kinds an upstream envelope may carry. Adding one means adding a delegate; there is
#: deliberately no fallback branch.
UPSTREAM_KINDS = frozenset({
    "command.submit",
    "decision.answer",
    "mission.cancel",
    "mission.message",
    "session.heartbeat",
    "session.ack",
})


@dataclass
class SessionDelegates:
    """The authorities the router calls. Each is the existing production path.

    They are injected rather than imported so that this module cannot accidentally grow its
    own implementation of one: there is nothing here to call except what was handed in.
    """

    submit_command: Callable[[dict, str], Awaitable[dict]]
    answer_decision: Callable[[dict, str], Awaitable[dict]] | None = None
    cancel_mission: Callable[[dict, str], Awaitable[dict]] | None = None
    message_mission: Callable[[dict, str], Awaitable[dict]] | None = None


@dataclass(frozen=True)
class RoutedResult:
    accepted: bool
    kind: str
    result: dict | None = None
    refusal: str | None = None
    admission: CommandAdmission | None = None


class SessionRouter:
    def __init__(self, sessions: VanHermesSessionService, delegates: SessionDelegates) -> None:
        self.sessions = sessions
        self.delegates = delegates

    async def route(
        self, envelope: SessionEnvelope, *, now_ms: int | None = None
    ) -> RoutedResult:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        if envelope.direction is not Direction.UPSTREAM:
            return RoutedResult(False, envelope.kind, refusal=REJECT_WRONG_DIRECTION)
        if envelope.kind not in UPSTREAM_KINDS:
            return RoutedResult(False, envelope.kind, refusal=REJECT_UNKNOWN_KIND)
        if envelope.expires_at_ms is not None and envelope.expires_at_ms <= now:
            # §20.14's freshness policy, enforced at the door. A command that was worth
            # doing twenty minutes ago is not automatically worth doing now, and the outbox
            # cannot be the only thing deciding that.
            return RoutedResult(False, envelope.kind, refusal=REJECT_EXPIRED)

        try:
            session = await self.sessions.accept_upstream(envelope, now_ms=now)
        except SessionError as exc:
            return RoutedResult(False, envelope.kind, refusal=exc.reason)

        if envelope.kind in {"session.heartbeat", "session.ack"}:
            # Liveness, not work. Deliberately not passed through admission: a heartbeat
            # under an idempotency key would occupy one for no reason.
            return RoutedResult(True, envelope.kind, result={"ok": True})

        admission, existing = await self.sessions.admit(envelope, now_ms=now)
        if admission is CommandAdmission.CONFLICT:
            return RoutedResult(
                False, envelope.kind, refusal=REJECT_CONFLICT, admission=admission
            )
        if admission is CommandAdmission.ALREADY_KNOWN:
            # §20.12 — the client lost the acknowledgement, not the command. Returning the
            # first result is the whole point: re-executing would be the duplicate the
            # idempotency key exists to prevent.
            return RoutedResult(True, envelope.kind, result=existing, admission=admission)

        delegate = self._delegate_for(envelope.kind)
        if delegate is None:
            return RoutedResult(False, envelope.kind, refusal=REJECT_UNKNOWN_KIND)
        result = await delegate(envelope.payload, session.device_id)
        await self.sessions.record_result(envelope, result, now_ms=now)
        return RoutedResult(True, envelope.kind, result=result, admission=admission)

    def _delegate_for(
        self, kind: str
    ) -> Callable[[dict, str], Awaitable[dict]] | None:
        return {
            "command.submit": self.delegates.submit_command,
            "decision.answer": self.delegates.answer_decision,
            "mission.cancel": self.delegates.cancel_mission,
            "mission.message": self.delegates.message_mission,
        }.get(kind)
