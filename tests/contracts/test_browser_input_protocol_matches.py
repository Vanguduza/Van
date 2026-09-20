"""Rev 1.5 §8 — the two implementations of one wire format, compared directly.

`backend/van_gateway/browser/input_protocol.py` and
`android/app/src/main/java/com/dial/van/browser/BrowserInputProtocol.kt` encode the same
packets. Nothing in either build can notice if they drift, because the only place they meet
is a running phone talking to a running stream host — and the symptom there is not an error,
it is a tap landing somewhere the owner did not touch.

So this reads both files and compares what has to match: the version, the coordinate bound,
the header size, the discriminator values, and the field order of the header itself. It is a
text comparison, which is a weaker check than a shared definition would be — and a shared
definition across Python and Kotlin means admitting a schema compiler on both sides, which
§32 would have to admit and pin. This is the honest middle: the drift that matters is the
kind this catches.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / "backend" / "van_gateway" / "browser" / "input_protocol.py"
KT = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van" / "browser" / "BrowserInputProtocol.kt"


def _python_constant(name: str) -> int:
    match = re.search(rf"^{name} = ([0-9_]+)", PY.read_text(), re.M)
    assert match, f"{name} not found in {PY.name}"
    return int(match.group(1).replace("_", ""))


def _kotlin_constant(name: str) -> int:
    match = re.search(rf"const val {name}:\s*\w+\s*=\s*([0-9_]+)", KT.read_text())
    assert match, f"{name} not found in {KT.name}"
    return int(match.group(1).replace("_", ""))


def _python_header_format() -> str:
    match = re.search(r'_HEADER = struct\.Struct\("([^"]+)"\)', PY.read_text())
    assert match, "the header format is not where this test expects it"
    return match.group(1)


def test_the_protocol_version_matches():
    assert _python_constant("PROTOCOL_VERSION") == _kotlin_constant("PROTOCOL_VERSION")


def test_the_coordinate_bound_matches():
    """A mismatch here scales every touch by a constant factor, silently."""
    assert _python_constant("COORDINATE_MAX") == _kotlin_constant("COORDINATE_MAX")


def test_the_header_size_matches():
    """The Kotlin side allocates a fixed buffer; the Python side unpacks a fixed struct."""
    assert struct.calcsize(_python_header_format()) == _kotlin_constant("HEADER_BYTES")


def test_the_header_is_little_endian_on_both_sides():
    """Otherwise the two agree about the schema and disagree about the bytes."""
    assert _python_header_format().startswith("<")
    assert "ByteOrder.LITTLE_ENDIAN" in KT.read_text()


#: Names the Python regex also picks up that are not input kinds. Listed rather than
#: filtered by a cleverer pattern, so adding a member to one of these enums is a visible
#: edit here rather than a silent exclusion from the comparison below.
NOT_AN_INPUT_KIND = {"CLOSED", "OPEN"}


def _kind_tables() -> tuple[dict[str, str], dict[str, str]]:
    python_kinds = {
        name: value
        for name, value in re.findall(r"^    ([A-Z_]+) = (\d+)$", PY.read_text(), re.M)
        if name not in NOT_AN_INPUT_KIND
    }
    kotlin_kinds = dict(
        re.findall(r"^        ([A-Z_]+)\((\d+)\),?;?$", KT.read_text(), re.M)
    )
    return python_kinds, kotlin_kinds


def test_the_kind_discriminators_match():
    """Renumbering one side turns a tap into a scroll, which no test on either side sees."""
    python_kinds, kotlin_kinds = _kind_tables()
    for name in sorted(set(python_kinds) & set(kotlin_kinds)):
        assert python_kinds[name] == kotlin_kinds[name], (
            f"{name} is {python_kinds[name]} in Python and {kotlin_kinds[name]} in Kotlin"
        )


def test_neither_side_has_a_kind_the_other_does_not():
    """The half the intersection above cannot see.

    A first version compared only the shared names and asserted there were at least nine
    of them, so a kind added to one implementation and not the other passed: the new name
    was simply not in the intersection. That is precisely the drift this file exists to
    catch — §17.2's navigation kinds were added to Python first, and nothing would have
    said the phone could not send one.
    """
    python_kinds, kotlin_kinds = _kind_tables()
    assert set(python_kinds) == set(kotlin_kinds), {
        "python_only": sorted(set(python_kinds) - set(kotlin_kinds)),
        "kotlin_only": sorted(set(kotlin_kinds) - set(python_kinds)),
    }


def test_the_navigation_kinds_are_on_both_sides():
    """§17.2 — navigation is an actuation and travels the input path.

    Named explicitly rather than left to the set comparison, because the set comparison
    is satisfied by both sides having none of them.
    """
    python_kinds, kotlin_kinds = _kind_tables()
    for name in ("NAVIGATE", "SEARCH", "HISTORY_BACK", "HISTORY_FORWARD", "RELOAD",
                 "STOP_LOADING"):
        assert name in python_kinds, name
        assert name in kotlin_kinds, name


def test_both_sides_refuse_a_navigation_on_the_fast_channel():
    """A navigate that can be dropped or reordered against the tap after it leaves the
    owner interacting with a page they had already left."""
    assert "navigation travels on the reliable channel" in KT.read_text()
    python_text = PY.read_text()
    assert "if parsed_channel is not Channel.RELIABLE:" in python_text


def test_both_sides_refuse_a_navigation_scheme_neither_will_open():
    """`file://` reads the host's disk into a page the owner is watching."""
    assert 'NAVIGABLE_SCHEMES = ("http://", "https://")' in PY.read_text()
    kotlin_text = KT.read_text()
    assert 'lowered.startsWith("http://") || lowered.startsWith("https://")' in kotlin_text


def test_the_channel_discriminators_match():
    python_text = PY.read_text()
    kotlin_text = KT.read_text()
    for name, expected in (("FAST", 1), ("RELIABLE", 2)):
        assert re.search(rf"^    {name} = {expected}$", python_text, re.M), name
        assert re.search(rf"{name}\({expected}\)", kotlin_text), name


def test_the_header_field_order_matches():
    """The comparison that actually protects the layout.

    Python's format string is the order of fields; the Kotlin encoder is a sequence of
    `put` calls. Reading both and comparing the widths in order catches a field inserted,
    removed or resized on one side — the change most likely to be made without noticing the
    other implementation exists.
    """
    widths = {"B": 1, "H": 2, "I": 4, "i": 4, "Q": 8}
    python_widths = [widths[c] for c in _python_header_format()[1:]]

    kotlin_puts = re.findall(
        r"buffer\.(put|putShort|putInt|putLong)\(", KT.read_text()
    )
    kotlin_widths = [
        {"put": 1, "putShort": 2, "putInt": 4, "putLong": 8}[call]
        for call in kotlin_puts
    ][: len(python_widths)]

    assert kotlin_widths == python_widths, (
        "the header layouts have diverged:\n"
        f"  python: {python_widths}\n"
        f"  kotlin: {kotlin_widths}"
    )


def test_both_sides_refuse_coordinates_outside_the_range():
    """Neither implementation may clamp silently: a clamped coordinate is a wrong tap."""
    assert "raise InputProtocolError(REJECT_MALFORMED)" in PY.read_text()
    assert "require(packet.x in 0..COORDINATE_MAX" in KT.read_text()


def test_the_device_never_restarts_a_pointer_epoch():
    """The invariant the server's state machine depends on, pinned in the sender.

    `PointerStateMachine._on_down` drops a DOWN whose epoch is at or below the gesture it
    still has open, and `_on_move` raises `REJECT_STALE_EPOCH` below it. Both are correct
    and both are silent from the phone's side: the owner's tap does nothing and the next one
    works. The only way the device can violate it is by resetting its epoch counter, so that
    is what this checks — `reset()` may forget a gesture's identity and must not forget how
    high the epoch has climbed.

    Read from the source rather than by running it, because the two halves never meet
    anywhere a test can put them: the sender is Kotlin and the receiver is Python.
    """
    text = KT.read_text()
    body = text[text.index("    fun reset() {"):]
    body = body[: body.index("\n    }")]
    assert "epochs.clear()" not in body, (
        "reset() clears the pointer epochs. The server fences on the epoch increasing, so "
        "restarting it means the first gesture after a control handover is dropped whenever "
        "a pointer was left open."
    )
    assert "gestures.clear()" in body, "reset() no longer drops the gesture identity"


def test_the_server_still_fences_on_a_non_increasing_epoch():
    """The other half of the pair above, so neither can be relaxed alone.

    If this rule were removed from the gateway, the device-side check would still pass while
    protecting nothing.
    """
    server = (ROOT / "backend" / "van_gateway" / "browser" / "input_protocol.py").read_text()
    assert "packet.gesture_epoch <= state.epoch" in server
    assert "REJECT_STALE_EPOCH" in server
