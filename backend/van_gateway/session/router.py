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


class SessionDelegateError(Exception):
    """A delegate refusing the payload, rather than failing.

    Distinct from an unexpected exception because the two need the same repair and for
    opposite reasons: a refusal is the final answer for this payload and a failure is not,
    but both must release the idempotency key. See [SessionRouter.route].
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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

        # Resolved *before* admission, and that order is the fix rather than a tidy-up.
        #
        # It used to be checked after, and the consequence was silent and permanent: an
        # envelope whose kind had no wired delegate was recorded in `van_session_messages`
        # as ADMITTED and then refused. Its idempotency key was now taken, so the phone's
        # retry — the correct thing for it to do — came back ALREADY_KNOWN with a null
        # result, which reads as success. The owner's "yes, cancel it" was acknowledged,
        # never performed, and could not be sent again for the life of the session.
        #
        # Nothing may be written down that this Gateway cannot carry out.
        delegate = self._delegate_for(envelope.kind)
        if delegate is None:
            return RoutedResult(False, envelope.kind, refusal=REJECT_UNKNOWN_KIND)

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

        try:
            result = await delegate(envelope.payload, session.device_id)
        except SessionDelegateError as exc:
            # The message is un-recorded, so the key is free again.
            #
            # §20.12's table answers a resubmission with what happened the first time, and
            # what happened here is nothing. Leaving the row means the owner's corrected
            # resend — a fixed mission id, the field that was missing — is answered
            # ALREADY_KNOWN with a null result, which the client reads as done. The record
            # exists to make a retry safe, not to make a refusal permanent.
            await self.sessions.forget_message(envelope)
            return RoutedResult(False, envelope.kind, refusal=exc.reason)
        except Exception:
            # A bug or a transient failure. The phone's retry is the right response to
            # both, and a burned key would turn something recoverable into a command that
            # can never be sent again. Re-raised: this is not a refusal and must not be
            # reported as one.
            await self.sessions.forget_message(envelope)
            raise
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
