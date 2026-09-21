"""Rev 1.5 §8 — the owner-input wire format and the server pointer state machine.

Two channels carry input and they have different guarantees (§7.3, §7.4). FAST_INPUT is
unordered and unreliable, RELIABLE_INPUT is ordered and reliable, and §8.2 is explicit that
the canonical `DOWN -> MOVE* -> UP/CANCEL` invariant is enforced by a server state machine
rather than by arrival order — because there is no arrival order across two SCTP streams.

The edges are therefore sent twice (§8.3): immediately on FAST_INPUT so a tap feels
instant, and canonically on RELIABLE_INPUT so a lost edge heals. The server de-duplicates on
`(session_id, gesture_id, edge_id)`. Without that, the duplicate is not a safety net — it is
a second tap.

**Coordinates are normalized and mapped only against the acknowledged viewport revision**
(§8.6, §8.1). A packet carrying an old revision is refused rather than transformed, for the
reason §8.1 gives: after a reflow the old coordinates do not describe a scaled version of
the new page.

On the wire format: §8 asks for protobuf or explicitly-versioned CBOR and forbids ad-hoc
JSON for pointer motion. Neither protobuf nor cbor2 is a dependency of this gateway, and
admitting one would mean pinning and verifying a serialization library on both the Python
and the Kotlin side for a format with exactly two implementations. This is the third option
§8 leaves open: an explicitly-versioned binary schema, fixed field order, fixed widths,
`struct`-packed, with the version in the first byte so a mismatch is a refusal rather than a
misparse. The Kotlin encoder mirrors these constants and a contract test compares the two.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum

#: Bumped when the layout changes. A packet whose first byte is not this is refused: a
#: client that has been updated past the server must fail loudly, not send a shorter record
#: that happens to parse.
PROTOCOL_VERSION = 1

#: §8.6 — coordinates are normalized so the wire carries no device pixels. The server maps
#: them against the acknowledged viewport, which is the only place that knows both.
COORDINATE_MAX = 65535

#: §8.4 — how long a MOVE may wait for the DOWN it belongs to.
#:
#: The duplicate DOWN on FAST_INPUT usually arrives first, but "usually" is what a state
#: machine exists to not rely on. Eight milliseconds is half a frame at 60 FPS: long enough
#: to absorb reordering between two SCTP streams, short enough that a genuinely orphaned
#: MOVE is dropped before it could be drawn.
ORPHAN_MOVE_GRACE_MS = 8

#: §8.4 — a gesture with no input for this long is cancelled by the server.
#:
#: The failure this prevents is a pointer that is pressed forever: a phone that loses
#: signal mid-drag leaves the page thinking a finger is still down, which selects text,
#: drags images and never ends.
GESTURE_TIMEOUT_MS = 5_000


class InputKind(IntEnum):
    """The wire discriminator. Values are frozen; add, never renumber."""

    POINTER_DOWN = 1
    POINTER_MOVE = 2
    POINTER_UP = 3
    POINTER_CANCEL = 4
    SCROLL = 5
    KEY_DOWN = 6
    KEY_UP = 7
    TEXT_COMMIT = 8
    IME_COMPOSITION = 9

    # Rev 1.5 §17.2 — "send a navigation command through RELIABLE_INPUT". Navigation is
    # an actuation, so it travels on the same fenced path as a tap rather than through a
    # REST route: a URL bar that could navigate by calling the Gateway would be a way
    # round the control lease, and §6 keeps the Gateway off the actuation path entirely.
    #
    # They carry no coordinates. NAVIGATE and SEARCH carry their subject in `text`; the
    # history kinds carry nothing at all.
    NAVIGATE = 10
    SEARCH = 11
    HISTORY_BACK = 12
    HISTORY_FORWARD = 13
    RELOAD = 14
    STOP_LOADING = 15

    @property
    def is_navigation(self) -> bool:
        """Whether this kind moves the page rather than touching it.

        Separated because the host handles them differently — a navigation is one CDP
        call, not a gesture — and because the refusals differ: a navigation to a scheme
        the agent may not open is refused on its content, which no pointer event has.
        """
        return self in {
            InputKind.NAVIGATE,
            InputKind.SEARCH,
            InputKind.HISTORY_BACK,
            InputKind.HISTORY_FORWARD,
            InputKind.RELOAD,
            InputKind.STOP_LOADING,
        }

    @property
    def is_edge(self) -> bool:
        """DOWN/UP/CANCEL are duplicated across both channels (§8.3)."""
        return self in {
            InputKind.POINTER_DOWN,
            InputKind.POINTER_UP,
            InputKind.POINTER_CANCEL,
        }


class Channel(IntEnum):
    FAST = 1
    RELIABLE = 2


#: Refusal reasons, as plain strings. A caller on the other side of a socket compares a
#: string, not an enum identity, and the reason travels into a log and a metric unchanged.
REJECT_VERSION = "input_protocol_version"
REJECT_MALFORMED = "input_malformed"
REJECT_STALE_VIEWPORT = "input_viewport_revision_stale"
REJECT_STALE_EPOCH = "input_gesture_epoch_stale"
REJECT_ORPHAN_MOVE = "input_move_without_gesture"
REJECT_DUPLICATE_EDGE = "input_duplicate_edge"
REJECT_UNKNOWN_GESTURE = "input_unknown_gesture"

#: §17.2 / §9.14 — a navigation whose target VAN will not open.
#:
#: Refused here rather than on the host, because this is the last place that can tell the
#: owner why. A host that refused it would do so as a CDP error the phone cannot explain.
REJECT_NAVIGATION_SCHEME = "input_navigation_scheme_refused"
REJECT_NAVIGATION_EMPTY = "input_navigation_empty"


class InputProtocolError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class InputAuthority:
    """§8.1 — what every actuation packet must carry to be considered at all."""

    session_id: str
    control_lease_id: str
    control_generation: int
    viewport_revision: int


@dataclass(frozen=True)
class InputPacket:
    """One input event, as it crosses the wire."""

    authority: InputAuthority
    kind: InputKind
    channel: Channel
    #: §8.2 — identity of the gesture this belongs to.
    gesture_id: int = 0
    pointer_id: int = 0
    gesture_epoch: int = 0
    #: §8.3 — identifies an edge across its two copies.
    edge_id: int = 0
    #: §8.5 — three sequence spaces, never one.
    fast_seq: int = 0
    reliable_seq: int = 0
    motion_seq: int = 0
    x: int = 0
    y: int = 0
    #: Scroll deltas and key codes reuse these two, which is why they are named generically.
    value_a: int = 0
    value_b: int = 0
    text: str = ""
    sent_at_ms: int = 0


#: The header layout, field by field, in this exact order:
#:
#:   B  protocol version        B  kind                 B  channel
#:   H  motion_seq              I  control_generation   I  viewport_revision
#:   I  gesture_id              I  pointer_id           I  gesture_epoch
#:   I  edge_id                 I  fast_seq             I  reliable_seq
#:   H  x                       H  y                    i  value_a
#:   i  value_b                 Q  sent_at_ms
#:
#: `<` is little-endian with no padding, so the bytes are identical on every architecture.
#: Anything else and a phone and a server would agree about the schema and disagree about
#: the bytes. x and y are `H` because §8.6 bounds them at 65535 — the type enforces the
#: range rather than a comment asking for it.
_HEADER = struct.Struct("<BBBHIIIIIIIIHHiiQ")


def encode(packet: InputPacket) -> bytes:
    """Pack one input event. Session and lease ids travel as length-prefixed UTF-8."""
    if not 0 <= packet.x <= COORDINATE_MAX or not 0 <= packet.y <= COORDINATE_MAX:
        raise InputProtocolError(REJECT_MALFORMED)
    head = _HEADER.pack(
        PROTOCOL_VERSION,
        int(packet.kind),
        int(packet.channel),
        packet.motion_seq & 0xFFFF,
        packet.authority.control_generation,
        packet.authority.viewport_revision,
        packet.gesture_id,
        packet.pointer_id,
        packet.gesture_epoch,
        packet.edge_id,
        packet.fast_seq,
        packet.reliable_seq,
        packet.x,
        packet.y,
        packet.value_a,
        packet.value_b,
        packet.sent_at_ms,
    )
    parts = [head]
    for value in (packet.authority.session_id, packet.authority.control_lease_id, packet.text):
        raw = value.encode("utf-8")
        if len(raw) > 0xFFFF:
            raise InputProtocolError(REJECT_MALFORMED)
        parts.append(struct.pack("<H", len(raw)))
        parts.append(raw)
    return b"".join(parts)


def decode(raw: bytes) -> InputPacket:
    """Unpack, refusing anything that is not exactly this version's layout."""
    if len(raw) < _HEADER.size:
        raise InputProtocolError(REJECT_MALFORMED)
    if raw[0] != PROTOCOL_VERSION:
        # A version mismatch is a refusal, never a best-effort parse. The alternative is a
        # newer client's longer record being read as this version's fields, which produces
        # coordinates rather than an error.
        raise InputProtocolError(REJECT_VERSION)
    (
        _version, kind, channel, motion_seq, control_generation, viewport_revision,
        gesture_id, pointer_id, gesture_epoch, edge_id, fast_seq, reliable_seq,
        x, y, value_a, value_b, sent_at_ms,
    ) = _HEADER.unpack(raw[: _HEADER.size])

    offset = _HEADER.size
    strings = []
    for _ in range(3):
        if offset + 2 > len(raw):
            raise InputProtocolError(REJECT_MALFORMED)
        (length,) = struct.unpack_from("<H", raw, offset)
        offset += 2
        if offset + length > len(raw):
            raise InputProtocolError(REJECT_MALFORMED)
        strings.append(raw[offset : offset + length].decode("utf-8"))
        offset += length
    if offset != len(raw):
        raise InputProtocolError(REJECT_MALFORMED)

    try:
        parsed_kind = InputKind(kind)
        parsed_channel = Channel(channel)
    except ValueError as exc:
        raise InputProtocolError(REJECT_MALFORMED) from exc

    if not 0 <= x <= COORDINATE_MAX or not 0 <= y <= COORDINATE_MAX:
        raise InputProtocolError(REJECT_MALFORMED)

    if parsed_kind.is_navigation:
        # §17.2 — navigation travels on the reliable channel and nowhere else. A
        # navigate on the fast channel is a navigate that can be dropped, duplicated or
        # reordered against the tap that followed it, and the owner would end up
        # interacting with a page they had already left.
        if parsed_channel is not Channel.RELIABLE:
            raise InputProtocolError(REJECT_MALFORMED)
        _check_navigation(parsed_kind, strings[2])

    return InputPacket(
        authority=InputAuthority(
            session_id=strings[0],
            control_lease_id=strings[1],
            control_generation=control_generation,
            viewport_revision=viewport_revision,
        ),
        kind=parsed_kind,
        channel=parsed_channel,
        gesture_id=gesture_id,
        pointer_id=pointer_id,
        gesture_epoch=gesture_epoch,
        edge_id=edge_id,
        fast_seq=fast_seq,
        reliable_seq=reliable_seq,
        motion_seq=motion_seq,
        x=x,
        y=y,
        value_a=value_a,
        value_b=value_b,
        text=strings[2],
        sent_at_ms=sent_at_ms,
    )


#: §17.2 / §9.14 — the only schemes a navigation packet may carry.
#:
#: The same two the omnibox will produce and the same two an external link may use. A
#: third would have to be a decision, and there is no path here that could make it one
#: by accident.
NAVIGABLE_SCHEMES = ("http://", "https://")


def _check_navigation(kind: InputKind, text: str) -> None:
    """Refuse a navigation the Gateway will not carry, with a reason the owner can read.

    Checked here rather than on the host because this is the last place that knows who
    asked. A host refusing it produces a CDP error the phone cannot explain, and the
    owner sees a page that did not load for no stated reason.
    """
    if kind in {InputKind.NAVIGATE, InputKind.SEARCH}:
        if not text.strip():
            raise InputProtocolError(REJECT_NAVIGATION_EMPTY)
    if kind is InputKind.NAVIGATE:
        lowered = text.strip().lower()
        if not lowered.startswith(NAVIGABLE_SCHEMES):
            # `file://` reads the host's disk into a page the owner is watching and
            # `javascript:` is arbitrary execution in it. A phone should never send
            # either; one that does is not a phone this session should obey.
            raise InputProtocolError(REJECT_NAVIGATION_SCHEME)
    if kind in {InputKind.HISTORY_BACK, InputKind.HISTORY_FORWARD,
                InputKind.RELOAD, InputKind.STOP_LOADING} and text:
        # These carry nothing. Text in one of them is a caller using the field for
        # something the protocol does not define, which is how a format drifts.
        raise InputProtocolError(REJECT_MALFORMED)


def to_viewport_pixels(x: int, y: int, *, width: int, height: int) -> tuple[int, int]:
    """§8.6 — normalized to device pixels, against the viewport the server holds.

    The caller is responsible for having checked the revision first. This function cannot
    check it, which is exactly why the check lives in the actuation gate rather than here:
    a mapping function that silently accepts any revision is how a transform creeps back in.
    """
    return (
        round(x * (width - 1) / COORDINATE_MAX) if width > 1 else 0,
        round(y * (height - 1) / COORDINATE_MAX) if height > 1 else 0,
    )


class PointerPhase(IntEnum):
    CLOSED = 0
    OPEN = 1


@dataclass
class PointerState:
    phase: PointerPhase = PointerPhase.CLOSED
    epoch: int = 0
    gesture_id: int = 0
    last_motion_seq: int = -1
    last_seen_ms: int = 0
    #: MOVEs that arrived before their DOWN, held for at most ORPHAN_MOVE_GRACE_MS.
    pending: list[InputPacket] = field(default_factory=list)


@dataclass(frozen=True)
class Accepted:
    """What the router should actually dispatch, after ordering has been resolved."""

    packets: tuple[InputPacket, ...]
    synthesized_cancel: bool = False


class PointerStateMachine:
    """§8.4 — one per session. Enforces the gesture invariant without trusting arrival order.

    The rules, and what each is for:

    * a MOVE for an unknown gesture waits briefly for its duplicated DOWN, then is dropped.
      Dispatching it would mean a drag with no press;
    * a MOVE from an older epoch is dropped. The finger it described has lifted;
    * a newer DOWN epoch cancels the open gesture first. Two live gestures on one pointer is
      not a state any page can interpret;
    * UP/CANCEL for an unknown epoch is ignored idempotently, because the duplicate copy of
      an edge is *expected* to arrive twice;
    * a gesture with no input for GESTURE_TIMEOUT_MS is cancelled by the server, so a phone
      that vanishes mid-drag does not leave a finger pressed forever.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._pointers: dict[int, PointerState] = {}
        self._seen_edges: set[tuple[int, int]] = set()

    # ------------------------------------------------------------------ helpers

    def _state(self, pointer_id: int) -> PointerState:
        return self._pointers.setdefault(pointer_id, PointerState())

    def _edge_is_new(self, packet: InputPacket) -> bool:
        """§8.3 — de-duplicate by (gesture_id, edge_id) within this session."""
        key = (packet.gesture_id, packet.edge_id)
        if key in self._seen_edges:
            return False
        self._seen_edges.add(key)
        return True

    # ------------------------------------------------------------------ the machine

    def offer(self, packet: InputPacket, *, now_ms: int) -> Accepted:
        """Feed one decoded packet. Returns what may be dispatched, in order."""
        if packet.kind is InputKind.POINTER_DOWN:
            return self._on_down(packet, now_ms)
        if packet.kind is InputKind.POINTER_MOVE:
            return self._on_move(packet, now_ms)
        if packet.kind in {InputKind.POINTER_UP, InputKind.POINTER_CANCEL}:
            return self._on_edge_end(packet, now_ms)
        # Keys, text and scroll carry no gesture state; ordering for them is the reliable
        # channel's job and the protocol's sequence space, not this machine's.
        return Accepted(packets=(packet,))

    def _on_down(self, packet: InputPacket, now_ms: int) -> Accepted:
        if not self._edge_is_new(packet):
            return Accepted(packets=())
        state = self._state(packet.pointer_id)
        out: list[InputPacket] = []
        synthesized = False
        if state.phase is PointerPhase.OPEN and packet.gesture_epoch > state.epoch:
            out.append(self._cancel_for(state, now_ms))
            synthesized = True
        elif state.phase is PointerPhase.OPEN and packet.gesture_epoch <= state.epoch:
            # An old DOWN arriving late must not reopen a gesture that has moved on.
            return Accepted(packets=())

        state.phase = PointerPhase.OPEN
        state.epoch = packet.gesture_epoch
        state.gesture_id = packet.gesture_id
        state.last_motion_seq = -1
        state.last_seen_ms = now_ms
        out.append(packet)

        # Anything that was waiting for this DOWN is now deliverable, in motion order.
        pending = [p for p in state.pending if p.gesture_epoch == packet.gesture_epoch]
        state.pending = []
        for waiting in sorted(pending, key=lambda p: p.motion_seq):
            if waiting.motion_seq > state.last_motion_seq:
                state.last_motion_seq = waiting.motion_seq
                out.append(waiting)
        return Accepted(packets=tuple(out), synthesized_cancel=synthesized)

    def _on_move(self, packet: InputPacket, now_ms: int) -> Accepted:
        state = self._state(packet.pointer_id)
        if state.phase is PointerPhase.CLOSED or packet.gesture_epoch > state.epoch:
            # The DOWN may still be in flight on the other channel.
            state.pending = [
                p for p in state.pending if now_ms - p.sent_at_ms <= ORPHAN_MOVE_GRACE_MS
            ]
            state.pending.append(packet)
            return Accepted(packets=())
        if packet.gesture_epoch < state.epoch:
            raise InputProtocolError(REJECT_STALE_EPOCH)
        if packet.motion_seq <= state.last_motion_seq:
            # Unreliable channel: a reordered or duplicated MOVE is stale, not an error.
            return Accepted(packets=())
        state.last_motion_seq = packet.motion_seq
        state.last_seen_ms = now_ms
        return Accepted(packets=(packet,))

    def _on_edge_end(self, packet: InputPacket, now_ms: int) -> Accepted:
        if not self._edge_is_new(packet):
            return Accepted(packets=())
        state = self._state(packet.pointer_id)
        if state.phase is PointerPhase.CLOSED or packet.gesture_epoch != state.epoch:
            # Idempotent by design: this is the expected shape of a late duplicate.
            return Accepted(packets=())
        state.phase = PointerPhase.CLOSED
        state.pending = []
        state.last_seen_ms = now_ms
        return Accepted(packets=(packet,))

    def _cancel_for(self, state: PointerState, now_ms: int) -> InputPacket:
        return InputPacket(
            authority=InputAuthority(
                session_id=self.session_id, control_lease_id="", control_generation=0,
                viewport_revision=0,
            ),
            kind=InputKind.POINTER_CANCEL,
            channel=Channel.RELIABLE,
            gesture_id=state.gesture_id,
            gesture_epoch=state.epoch,
            sent_at_ms=now_ms,
        )

    def sweep(self, *, now_ms: int) -> list[InputPacket]:
        """Cancel gestures that have gone quiet. Called on a timer by the router."""
        cancels: list[InputPacket] = []
        for pointer_id, state in self._pointers.items():
            if state.phase is not PointerPhase.OPEN:
                continue
            if now_ms - state.last_seen_ms < GESTURE_TIMEOUT_MS:
                continue
            cancels.append(self._cancel_for(state, now_ms))
            state.phase = PointerPhase.CLOSED
            state.pending = []
        return cancels

    def open_pointers(self) -> list[int]:
        return [p for p, s in self._pointers.items() if s.phase is PointerPhase.OPEN]
