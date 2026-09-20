"""The two shapes the session socket carries, read from both sides.

The Gateway sends exactly two kinds of frame down `/v1/session/ws`: a downstream event,
and its answer to something the device sent. The client recognised neither. It read `seq`
from the top of the frame — it is nested under `event` — and switched on `kind` looking
for `"session.ack"`, while the Gateway's answer carries the *envelope's* kind, so the
comparison was against `"command.submit"`.

Silent in every direction. The event cursor never advanced from the socket, so a resume
asked to replay from zero. Nothing left `inFlight`, so every command stayed pending until
a resume reconciled it. And §20.1's "SHALL feed durable downstream pages/events into the
existing `EventStream.applyPage`" was not merely unmet: the events were parsed into
nothing and dropped.

This is the third time in this programme that two internally consistent halves of a wire
format have disagreed, so the frames are pinned here against the Gateway's own
construction sites rather than against anybody's reading of them.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend/van_gateway/session/api.py"
PARSER = ROOT / "android/app/src/main/java/com/dial/van/session/SessionDownstream.kt"
BUS = ROOT / "backend/van_gateway/events/bus.py"


def _gateway() -> str:
    return API.read_text(encoding="utf-8")


def _parser() -> str:
    return PARSER.read_text(encoding="utf-8")


def _parser_code() -> str:
    """The parser with its prose removed.

    The file's documentation names the string it used to match on, because saying what
    the defect was is the point of writing it down. A check that read the comments would
    therefore fail on the explanation of the thing it is checking for.
    """
    lines = []
    in_block = False
    for line in _parser().splitlines():
        stripped = line.strip()
        if stripped.startswith("/*"):
            in_block = True
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_the_gateway_still_sends_the_two_frames_this_parser_knows():
    """Guards the guard. A third shape, or a renamed field, and the rest is about nothing."""
    gateway = _gateway()
    assert '{"direction": "DOWNSTREAM", "event": event}' in gateway, (
        "the downstream frame changed shape and the device's parser has not"
    )
    assert '"message_id": body.message_id,' in gateway
    assert '"accepted": routed.accepted,' in gateway


def test_the_device_reads_the_event_where_the_gateway_puts_it():
    parser = _parser()
    assert 'optJSONObject("event")' in parser, (
        "the device reads the event from the top of the frame; it is nested"
    )
    assert 'optString("direction") == DIRECTION_DOWNSTREAM' in parser
    assert 'const val DIRECTION_DOWNSTREAM: String = "DOWNSTREAM"' in parser


def test_the_device_reads_every_field_the_event_row_projects_that_it_needs():
    """`seq`, `event_type`, `payload`, `created_at_unix` — spelled the Gateway's way."""
    projected = set(re.findall(r'^\s*"(\w+)":', BUS.read_text(encoding="utf-8"), re.M))
    assert {"seq", "event_type", "payload", "created_at_unix"} <= projected, (
        f"the event projection changed: {sorted(projected)}"
    )
    parser = _parser()
    for field in ("seq", "event_type", "payload", "created_at_unix"):
        assert f'"{field}"' in parser, f"the device never reads {field}"


def test_the_acknowledgement_is_not_matched_on_kind():
    """The defect, stated as a rule.

    `kind` in the answer is `routed.kind`, which is the envelope's kind — `command.submit`,
    `mission.cancel`. Matching a frame type on it is matching on the wrong thing, and it
    is how nothing was ever taken out of flight.
    """
    assert '"kind": routed.kind,' in _gateway(), "the answer no longer echoes the envelope kind"
    code = _parser_code()
    ack = code[code.index("val messageId = frame.optString"):]
    assert '"session.ack"' not in code, (
        "the device matches an acknowledgement on a kind the Gateway does not send"
    )
    assert 'has("accepted")' in ack and 'optString("message_id")' in ack


def test_the_session_manager_uses_the_parser_rather_than_its_own_reading():
    """Otherwise this file describes a parser nothing on the socket path calls."""
    manager = (
        ROOT / "android/app/src/main/java/com/dial/van/session/VanHermesSessionManager.kt"
    ).read_text(encoding="utf-8")
    assert "SessionDownstream.parse(" in manager, (
        "onMessage went back to reading the frame itself"
    )
