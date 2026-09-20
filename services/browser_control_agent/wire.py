"""Rev 1.5 §13.2 — the encoding a call and its answer travel in.

`agent.py` deliberately says nothing about transport and `server.py` deliberately starts no
listener, which left a gap: two implementations of the same protocol, one in the Stream
Host package and one in whatever calls it, with nothing in between to disagree with. This
module is that missing middle. It is pure — it encodes and decodes, it opens no socket —
so it can be tested here and used by the host implementation that cannot be.

Four properties it has to have, each of which is a failure it prevents:

* **the caller's name is not in the wire format.** `Call` already leaves it out; a decoder
  that accepted one would hand the agent an identity the caller chose, and the whole point
  of reading the common name from the verified certificate would be undone by a JSON key;
* **neither is its authority.** A message carries `task_id`, `lease_id` and
  `lease_generation` — references the agent resolves against its own `ControlAuthority` —
  and never a scope or a step budget. A caller that could send those would be answering
  the question `authorize` exists to ask;
* **a refusal is a successful response, not an error.** A refusal carries a reason the
  caller can act on. Encoding it as a transport failure would make "you do not hold the
  control lease" indistinguishable from "the host is unreachable", and the first is
  recoverable by asking the owner while the second is not;
* **an unknown operation decodes to a refusal, never to a default.** A decoder that fell
  back to the nearest match would let a typo actuate.
"""

from __future__ import annotations

import json
from typing import Any

from services.browser_control_agent.agent import Call
from services.browser_control_agent.authority import Operation, Refusal

#: Bumped when the shape below changes incompatibly. The host and the caller both send it
#: and both check it, because a silent mismatch is the failure mode this exists to avoid.
PROTOCOL_VERSION = 1

#: How one message is separated from the next on a stream.
#:
#: Framing belongs here for the same reason the encoding does: it is the other thing two
#: implementations can disagree about while both looking correct. A newline is safe because
#: `json.dumps` escapes every control character, so no encoded message can contain a raw
#: one — `test_no_encoded_message_can_contain_the_delimiter` is what holds that true
#: against a future encoder that stops escaping.
FRAME_DELIMITER = b"\n"


def frame(message: str) -> bytes:
    """One encoded message, ready to send."""
    return message.encode("utf-8") + FRAME_DELIMITER


def unframe(buffer: bytes) -> tuple[list[str], bytes]:
    """Split a received buffer into complete messages and whatever is left over.

    Returning the remainder rather than assuming one read is one message: TCP does not
    promise that, and a reader that assumed it would work in every test and fail on a
    large accessibility tree.
    """
    parts = buffer.split(FRAME_DELIMITER)
    remainder = parts.pop()
    return [part.decode("utf-8") for part in parts if part.strip()], remainder


class WireError(Exception):
    """The message could not be understood at all, as opposed to being refused."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def encode_call(call: Call, *, request_id: str) -> str:
    """One call, as the caller sends it.

    `request_id` is the caller's, echoed back untouched, so a response can be matched to a
    request on a multiplexed connection without the agent having to hold any state.
    """
    return json.dumps(
        {
            "protocol": PROTOCOL_VERSION,
            "request_id": request_id,
            "operation": call.operation.value,
            "session_id": call.session_id,
            "target_id": call.target_id,
            "lease_id": call.lease_id,
            "lease_generation": call.lease_generation,
            "task_id": call.task_id,
            "params": call.params,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_call(message: str | bytes) -> tuple[str, Call]:
    """The agent's side. Returns the request id and the call.

    Everything that is not a well-formed call of a known operation raises `WireError`, and
    the server turns that into a refusal with the request id it managed to read — or, when
    it could not read one, closes the connection. What it must never do is guess.
    """
    try:
        payload = json.loads(message)
    except (TypeError, ValueError) as exc:
        raise WireError("wire_not_json") from exc
    if not isinstance(payload, dict):
        raise WireError("wire_not_an_object")
    if payload.get("protocol") != PROTOCOL_VERSION:
        raise WireError(f"wire_protocol_mismatch:{payload.get('protocol')!r}")

    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise WireError("wire_request_id_missing")

    # The refusal the module docstring's first property is about. `caller` is not a field
    # of this protocol, and a message carrying one is rejected rather than having it
    # ignored: a caller that believes it is naming itself should be told it is not.
    if "caller" in payload or "caller_common_name" in payload:
        raise WireError("wire_caller_is_not_a_wire_field")

    # The same rule one level in. A caller that sent its own scope or step budget would
    # be naming its own authority; those live in the agent's `ControlAuthority` and are
    # looked up from `task_id`.
    if "scope" in payload or "step_budget" in payload or "grant" in payload:
        raise WireError("wire_authority_is_not_a_wire_field")

    try:
        operation = Operation(payload.get("operation"))
    except ValueError as exc:
        raise WireError(f"wire_unknown_operation:{payload.get('operation')!r}") from exc

    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise WireError("wire_params_not_an_object")

    # The grant itself is never on the wire. `lease_id`, `lease_generation` and
    # `task_id` are *references* the agent resolves against its own `ControlAuthority`;
    # a caller that could send the grant would be sending its own step budget and its
    # own scope, which is the authority check answering to the thing it checks.
    try:
        return request_id, Call(
            operation=operation,
            session_id=_text(payload, "session_id"),
            target_id=_text(payload, "target_id"),
            lease_id=_text(payload, "lease_id"),
            lease_generation=_integer(payload, "lease_generation"),
            task_id=_text(payload, "task_id"),
            params=params,
        )
    except KeyError as exc:
        raise WireError(f"wire_field_missing:{exc.args[0]}") from exc


def encode_result(request_id: str, result: dict[str, Any]) -> str:
    return json.dumps(
        {
            "protocol": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def encode_refusal(request_id: str, refusal: Refusal | str) -> str:
    """A refusal is `ok: false` with a reason, and it is still a 200-shaped answer.

    The caller distinguishes "refused" from "unreachable" by whether it got one of these at
    all, which is the second property in the module docstring.
    """
    reason = refusal.value if isinstance(refusal, Refusal) else str(refusal)
    return json.dumps(
        {
            "protocol": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": False,
            "refusal": reason,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_response(message: str | bytes) -> tuple[str, bool, Any]:
    """Returns `(request_id, ok, payload)` where payload is the result or the reason."""
    try:
        payload = json.loads(message)
    except (TypeError, ValueError) as exc:
        raise WireError("wire_not_json") from exc
    if not isinstance(payload, dict):
        raise WireError("wire_not_an_object")
    if payload.get("protocol") != PROTOCOL_VERSION:
        raise WireError(f"wire_protocol_mismatch:{payload.get('protocol')!r}")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise WireError("wire_request_id_missing")
    ok = payload.get("ok")
    if ok is True:
        result = payload.get("result")
        if not isinstance(result, dict):
            raise WireError("wire_result_not_an_object")
        return request_id, True, result
    if ok is False:
        refusal = payload.get("refusal")
        if not isinstance(refusal, str) or not refusal:
            raise WireError("wire_refusal_missing")
        return request_id, False, refusal
    raise WireError("wire_ok_not_a_boolean")


def _text(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise WireError(f"wire_field_missing:{key}")
    return value


def _integer(payload: dict, key: str) -> int:
    value = payload.get(key)
    # `bool` is an `int` in Python and `True` is not a generation.
    if isinstance(value, bool) or not isinstance(value, int):
        raise WireError(f"wire_field_missing:{key}")
    return value
