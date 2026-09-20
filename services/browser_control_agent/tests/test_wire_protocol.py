"""Rev 1.5 §13.2 — the encoding, and the four things it refuses to carry.

`wire.py` is the piece that lets the Stream Host's listener and whatever calls it be the
same protocol. It is pure, so all of it runs here; the socket it is eventually spoken over
is external and always will be.

Every test below is a refusal or a round trip. There is nothing in between, because an
encoder that "mostly" agrees with its decoder is a wire format that fails in production on
the one message shape nobody tried.
"""

from __future__ import annotations

import json

import pytest

from services.browser_control_agent.agent import Call
from services.browser_control_agent.authority import Operation, Refusal
from services.browser_control_agent.wire import (
    FRAME_DELIMITER,
    PROTOCOL_VERSION,
    WireError,
    decode_call,
    decode_response,
    encode_call,
    encode_refusal,
    encode_result,
    frame,
    unframe,
)


def _call(**overrides) -> Call:
    body = dict(
        operation=Operation.QUERY_DOM, session_id="ibs_1", target_id="tgt_1",
        lease_id="bctl_1", lease_generation=4, task_id="task_1",
        params={"selector": "h1"},
    )
    body.update(overrides)
    return Call(**body)


class TestRoundTrip:

    def test_a_call_survives_encoding_unchanged(self):
        request_id, decoded = decode_call(encode_call(_call(), request_id="req_1"))
        assert request_id == "req_1"
        assert decoded == _call()

    def test_every_operation_round_trips(self):
        """All eight, because a table that lists an operation the decoder cannot read is
        a surface that works until someone uses the eighth one."""
        for operation in Operation:
            _, decoded = decode_call(
                encode_call(_call(operation=operation), request_id="req_1")
            )
            assert decoded.operation is operation

    def test_a_result_round_trips(self):
        request_id, ok, payload = decode_response(
            encode_result("req_1", {"text": "Statements"})
        )
        assert (request_id, ok, payload) == ("req_1", True, {"text": "Statements"})

    def test_a_refusal_is_an_answer_rather_than_a_failure(self):
        """The second property in the module docstring.

        "You no longer hold the lease" is recoverable — the owner took control and the
        agent should stop. "The host is unreachable" is not. A transport that collapsed
        the two would make the recoverable case look like an outage.
        """
        request_id, ok, reason = decode_response(
            encode_refusal("req_1", Refusal.LEASE_SUPERSEDED)
        )
        assert request_id == "req_1"
        assert ok is False
        assert reason == Refusal.LEASE_SUPERSEDED.value

    def test_a_refusal_may_also_be_a_plain_string(self):
        """The wire errors below are not `Refusal` members and still have to be sayable."""
        _, ok, reason = decode_response(encode_refusal("req_1", "wire_not_json"))
        assert (ok, reason) == (False, "wire_not_json")


class TestWhatTheWireRefusesToCarry:

    def test_a_caller_cannot_name_itself(self):
        """The first property, and the reason `Call` has no caller field.

        `common_name_of` reads the identity from the verified peer certificate. A decoder
        that accepted `caller` in the body would let the transport layer's careful answer
        be overridden by a JSON key — and the override would look like ordinary data.
        """
        message = json.loads(encode_call(_call(), request_id="req_1"))
        message["caller"] = "trading-core"
        with pytest.raises(WireError) as raised:
            decode_call(json.dumps(message))
        assert raised.value.reason == "wire_caller_is_not_a_wire_field"

    @pytest.mark.parametrize("field", ["scope", "step_budget", "grant"])
    def test_a_caller_cannot_name_its_own_authority(self, field):
        """Rejected rather than ignored.

        Silently dropping the field would leave a caller believing it had asked for
        `browser.observe` and been granted it, when the scope actually applied is whatever
        the agent's own grant says. Being told is the difference between a bug and a
        misunderstanding that lasts.
        """
        message = json.loads(encode_call(_call(), request_id="req_1"))
        message[field] = "browser.actuate"
        with pytest.raises(WireError) as raised:
            decode_call(json.dumps(message))
        assert raised.value.reason == "wire_authority_is_not_a_wire_field"

    def test_an_unknown_operation_is_refused_not_approximated(self):
        message = json.loads(encode_call(_call(), request_id="req_1"))
        message["operation"] = "navigat"
        with pytest.raises(WireError) as raised:
            decode_call(json.dumps(message))
        assert raised.value.reason.startswith("wire_unknown_operation:")

    def test_a_version_mismatch_is_refused_rather_than_guessed(self):
        message = json.loads(encode_call(_call(), request_id="req_1"))
        message["protocol"] = PROTOCOL_VERSION + 1
        with pytest.raises(WireError) as raised:
            decode_call(json.dumps(message))
        assert raised.value.reason.startswith("wire_protocol_mismatch:")

    @pytest.mark.parametrize(
        "field", ["session_id", "target_id", "lease_id", "task_id"]
    )
    def test_a_missing_reference_is_refused(self, field):
        message = json.loads(encode_call(_call(), request_id="req_1"))
        del message[field]
        with pytest.raises(WireError) as raised:
            decode_call(json.dumps(message))
        assert raised.value.reason == f"wire_field_missing:{field}"

    def test_a_boolean_generation_is_not_a_generation(self):
        """`True` is an `int` in Python, and `lease_generation: true` compares greater
        than zero. The fencing check downstream would pass on it."""
        message = json.loads(encode_call(_call(), request_id="req_1"))
        message["lease_generation"] = True
        with pytest.raises(WireError) as raised:
            decode_call(json.dumps(message))
        assert raised.value.reason == "wire_field_missing:lease_generation"

    def test_generation_zero_is_a_generation(self):
        """The other side of the check above: a falsy value that is genuinely valid must
        not be swept up by an emptiness test."""
        _, decoded = decode_call(
            encode_call(_call(lease_generation=0), request_id="req_1")
        )
        assert decoded.lease_generation == 0

    @pytest.mark.parametrize("message", ["", "not json", "[]", '"a string"'])
    def test_something_that_is_not_a_call_is_refused(self, message):
        with pytest.raises(WireError):
            decode_call(message)

    def test_a_response_without_a_verdict_is_refused(self):
        """`ok` missing is not `ok: false`. A caller that read a malformed response as a
        refusal would report "the owner took control" for a corrupted frame."""
        with pytest.raises(WireError) as raised:
            decode_response(json.dumps({"protocol": PROTOCOL_VERSION, "request_id": "r"}))
        assert raised.value.reason == "wire_ok_not_a_boolean"

    def test_a_refusal_with_no_reason_is_refused(self):
        with pytest.raises(WireError) as raised:
            decode_response(
                json.dumps(
                    {"protocol": PROTOCOL_VERSION, "request_id": "r", "ok": False}
                )
            )
        assert raised.value.reason == "wire_refusal_missing"


class TestTheEncodingIsStable:

    def test_the_same_call_encodes_byte_identically(self):
        """Two implementations of this protocol have to produce the same bytes for the
        same call, or the first thing anyone does with a hash of a request breaks."""
        first = encode_call(_call(), request_id="req_1")
        second = encode_call(_call(), request_id="req_1")
        assert first == second
        assert first == json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))


class TestFraming:
    """Where one message ends, which is the other thing two implementations can disagree
    about while both looking right."""

    def test_no_encoded_message_can_contain_the_delimiter(self):
        """Newline framing is only safe while the encoder escapes control characters.

        A selector or a page title carrying a literal newline is the obvious way to break
        it, and `json.dumps` escapes those — but that is a property of the encoder, not a
        law, so it is asserted rather than assumed.
        """
        hostile = _call(params={"selector": "h1\nInput.dispatchKeyEvent", "note": "a\r\nb"})
        encoded = encode_call(hostile, request_id="req_1")
        assert FRAME_DELIMITER.decode() not in encoded
        assert frame(encoded).count(FRAME_DELIMITER) == 1

    def test_two_messages_in_one_read_are_both_delivered(self):
        """TCP does not promise one read is one message. A reader that assumed it would
        pass every test here and fail on a large accessibility tree."""
        first = frame(encode_call(_call(), request_id="req_1"))
        second = frame(encode_result("req_2", {"text": "ok"}))
        messages, remainder = unframe(first + second)
        assert len(messages) == 2
        assert remainder == b""
        assert decode_call(messages[0])[0] == "req_1"
        assert decode_response(messages[1])[0] == "req_2"

    def test_a_partial_message_is_kept_rather_than_decoded(self):
        whole = frame(encode_call(_call(), request_id="req_1"))
        messages, remainder = unframe(whole[:-5])
        assert messages == []
        assert remainder == whole[:-5]
        # And it completes when the rest arrives.
        messages, remainder = unframe(remainder + whole[-5:])
        assert len(messages) == 1
        assert remainder == b""
