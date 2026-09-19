"""The wire vocabulary the device sees, projected onto the owner-facing status.

P0-EXEC-003: the Android controller mapped gateway statuses with a `when` whose final
branch was `else -> ACCEPTED`. Any status it did not recognise — including every status
added to the gateway after the controller was written — read to the owner as "under way".
It also collapsed `unverifiable`, `verification_failed` and `partial_success` into FAILED,
which is three different situations answered with one wrong word.

The device now maps through the same table this module defines. Keeping the table here,
beside the mission projection, is what lets a test assert the two languages agree rather
than hoping they do; `backend/tests/test_owner_status_kotlin_contract.py` parses the Kotlin
and compares it to this.

Two vocabularies reach the device and both are covered:

  * `COMMAND_RESULT` — the synchronous answer to POST /v1/commands;
  * mission states, which arrive later over the event stream, and which reuse the mission
    projection directly rather than restating it.
"""

from __future__ import annotations

from van_gateway.coherence.owner_status import MISSION, OwnerWorkStatus

_W = OwnerWorkStatus

#: Every status CommandResult.status can carry, and what it means to the owner.
COMMAND_RESULT: dict[str, OwnerWorkStatus] = {
    # The gateway took it and dispatched it. Not success — the audit's central confusion.
    "accepted": _W.WORKING,
    "in_flight": _W.WORKING,
    # A4 needs a biometric proof before anything executes.
    "approval_required": _W.WAITING_ON_YOU,
    # A capability is down; the command did not run and the owner may want to retry.
    "degraded": _W.WAITING_ON_SOMETHING_ELSE,
    "denied": _W.REFUSED,
    "rejected_untrusted": _W.REFUSED,
    "expired": _W.STOPPED,
    # Two different commands claimed one idempotency key. The owner must look.
    "conflict": _W.WAITING_ON_YOU,
}

#: Mission states as they appear on the wire, derived from the mission projection rather
#: than written out again, so the two cannot disagree.
MISSION_STATE: dict[str, OwnerWorkStatus] = {
    state.value: projected for state, projected in MISSION.items()
}


def from_command_result(status: str | None) -> OwnerWorkStatus:
    """No benign default: an unrecognised status is UNKNOWN, never WORKING."""
    if not status:
        return OwnerWorkStatus.UNKNOWN
    return COMMAND_RESULT.get(status.strip().lower(), OwnerWorkStatus.UNKNOWN)


def from_mission_state(state: str | None) -> OwnerWorkStatus:
    if not state:
        return OwnerWorkStatus.UNKNOWN
    return MISSION_STATE.get(state.strip().upper(), OwnerWorkStatus.UNKNOWN)


__all__ = ["COMMAND_RESULT", "MISSION_STATE", "from_command_result", "from_mission_state"]
