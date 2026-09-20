"""Rev 1.5 §§8.1, 8.6 — from an admitted input packet to a CDP call.

The packets arrive over the WebRTC data channels, are ordered and de-duplicated by
`PointerStateMachine` (RB-018), and end here. This module is the last step and it does
exactly two things: it checks that the packet is still entitled to actuate, and it maps
normalized coordinates into the viewport's device pixels.

Both halves have a specific failure behind them.

The entitlement check is the viewport revision. §8.6 withholds actuation between a resize
being proposed and the device acknowledging it, and the revision travels *in the packet* so
that a packet built against revision 4 cannot be applied to revision 5. A router that
transformed a stale packet instead of refusing it would be the exact bug the revision
exists to prevent: a tap landing where the page used to be.

The mapping is deliberately not in the protocol module's `normalize`. That function turns
pixels into the wire's fixed range on the device, where the viewport is the phone's; this
one turns the wire's range into the *host's* viewport. They look symmetric and are not: the
phone's screen and the browser's viewport are different sizes, which is the whole reason the
wire carries a normalized coordinate rather than a pixel.

Nothing here talks to a browser. `CdpCall` is a description of what to send, so this module
can be executed and a real host's transport can be the thing that cannot.

One deployment consequence, stated because it is easy to get wrong: this imports the
Gateway's `input_protocol` rather than reimplementing the decoder, so the Stream Host's
package has to carry that module. Vendoring a copy would give the wire format a *third*
implementation, and the two it already has needed a shared vectors file and two contract
tests to stop them drifting.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from van_gateway.browser.flood_bounds import (
    REJECT_INPUT_FLOOD,
    InputRateLimiter,
)
from van_gateway.browser.input_protocol import (
    InputKind,
    InputPacket,
    to_viewport_pixels,
)

#: §8.6 — a packet whose revision is not the current one is refused, never transformed.
REJECT_STALE_VIEWPORT = "input_router_stale_viewport_revision"
#: §8.1 — the control generation fences an agent that has been preempted.
REJECT_STALE_GENERATION = "input_router_stale_control_generation"
REJECT_UNMAPPED_KIND = "input_router_kind_has_no_mapping"

#: Rev 1.5 §17.2 — navigation travels the input path and is not translated here.
#:
#: Its own reason rather than REJECT_UNMAPPED_KIND, because the two mean opposite things:
#: an unmapped kind is a gap and this is a boundary. A navigation packet is fenced by the
#: same control generation and viewport revision as a tap — that is why it travels the
#: input path at all — but turning one into `Page.navigate` here would put a second CDP
#: surface behind a router whose whole claim is that it emits `Input.*` and nothing else.
#: It is handed to the Browser Control Agent's `navigate` operation instead (§13.2), which
#: is the component that owns the scheme allowlist and the step budget.
REJECT_NOT_INPUT = "input_router_navigation_belongs_to_the_control_agent"


class InputRouterRefused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CdpCall:
    """One CDP message, described rather than sent."""

    method: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int
    revision: int


#: Chromium's own modifier bits, which the wire carries in `value_b` for key events.
ALT, CONTROL, META, SHIFT = 1, 2, 4, 8


class CdpInputRouter:
    """RB-017. One per session; holds the viewport the host is actually rendering."""

    def __init__(
        self, *, viewport: Viewport, control_generation: int,
        rate_limiter: InputRateLimiter | None = None,
    ) -> None:
        self.viewport = viewport
        self.control_generation = control_generation
        # §38 item 12 — the input flood, bounded where the packets are translated.
        #
        # Here rather than at the Gateway because the Gateway is not in this path: §8's
        # input travels device → Stream Host, and a bound anywhere else would be counting
        # something it cannot see. Optional so a caller can share one limiter across the
        # host's sessions or supply a clock-controlled one in a test; a router with none
        # translates everything, which is the behaviour every existing caller had.
        self.rate_limiter = rate_limiter

    def adopt_viewport(self, viewport: Viewport, *, control_generation: int | None = None) -> None:
        """A resize the device has acknowledged, and optionally a control handover."""
        self.viewport = viewport
        if control_generation is not None:
            self.control_generation = control_generation

    def route(self, packet: InputPacket, *, now_ms: int | None = None) -> list[CdpCall]:
        """Translate, or refuse with a named reason.

        Returns a list because one input event is sometimes two CDP calls: a pointer down
        that also moves the mouse there first, which Chromium needs for hover state to be
        right before the press.
        """
        if packet.authority.viewport_revision != self.viewport.revision:
            raise InputRouterRefused(REJECT_STALE_VIEWPORT)
        if packet.authority.control_generation != self.control_generation:
            raise InputRouterRefused(REJECT_STALE_GENERATION)
        # Checked after the fencing, not before: a navigation naming a superseded
        # generation is refused as stale, which is the more specific truth and the one an
        # agent that has just been preempted needs to hear.
        if packet.kind.is_navigation:
            raise InputRouterRefused(REJECT_NOT_INPUT)
        # Last of the refusals, and deliberately so. A flood of packets that are *also*
        # stale or preempted should be reported as stale or preempted: those say the
        # sender has lost authority, which is what whoever reads the log needs to act on,
        # and a rate refusal would hide it behind a symptom.
        if self.rate_limiter is not None:
            when = int(time.time() * 1000) if now_ms is None else now_ms
            if not self.rate_limiter.admit(packet.authority.session_id, when):
                raise InputRouterRefused(REJECT_INPUT_FLOOD)

        handler = _ROUTES.get(packet.kind)
        if handler is None:
            raise InputRouterRefused(REJECT_UNMAPPED_KIND)
        return handler(self, packet)

    # ------------------------------------------------------------------ mappings

    def _pixels(self, packet: InputPacket) -> tuple[int, int]:
        return to_viewport_pixels(
            packet.x, packet.y, width=self.viewport.width, height=self.viewport.height
        )

    def _pointer(self, packet: InputPacket, event_type: str) -> CdpCall:
        x, y = self._pixels(packet)
        return CdpCall(
            "Input.dispatchMouseEvent",
            {
                "type": event_type,
                "x": x,
                "y": y,
                "button": "left",
                # Chromium treats buttons=0 on a move as "no button held", which cancels a
                # drag. A press and a drag must both report the button as down.
                "buttons": 0 if event_type == "mouseReleased" else 1,
                "clickCount": 1 if event_type in {"mousePressed", "mouseReleased"} else 0,
                "timestamp": packet.sent_at_ms / 1000.0,
            },
        )

    def _down(self, packet: InputPacket) -> list[CdpCall]:
        # Moved first. Without it Chromium presses at wherever the pointer was last, and
        # hover-dependent pages see the press on the wrong element.
        return [self._pointer(packet, "mouseMoved"), self._pointer(packet, "mousePressed")]

    def _move(self, packet: InputPacket) -> list[CdpCall]:
        return [self._pointer(packet, "mouseMoved")]

    def _up(self, packet: InputPacket) -> list[CdpCall]:
        return [self._pointer(packet, "mouseReleased")]

    def _cancel(self, packet: InputPacket) -> list[CdpCall]:
        # A cancel is a release, not a nothing. Dropping it leaves the page holding a press
        # that the owner's finger has already left — which is the gesture-machine's
        # synthesized cancel arriving here and being discarded.
        return [self._pointer(packet, "mouseReleased")]

    def _scroll(self, packet: InputPacket) -> list[CdpCall]:
        x, y = self._pixels(packet)
        return [
            CdpCall(
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseWheel",
                    "x": x,
                    "y": y,
                    # The wire carries whole wheel detents; the host scales them against its
                    # own viewport, because the phone must not decide how far a desktop-
                    # sized page scrolls.
                    "deltaX": _scroll_pixels(packet.value_a, self.viewport.width),
                    "deltaY": _scroll_pixels(packet.value_b, self.viewport.height),
                    "timestamp": packet.sent_at_ms / 1000.0,
                },
            )
        ]

    def _key(self, packet: InputPacket, event_type: str) -> list[CdpCall]:
        params: dict[str, Any] = {
            "type": event_type,
            "windowsVirtualKeyCode": packet.value_a,
            "nativeVirtualKeyCode": packet.value_a,
            "modifiers": packet.value_b,
            "timestamp": packet.sent_at_ms / 1000.0,
        }
        if packet.text:
            # `keyDown` without text produces a key event the page sees but no character;
            # `char` is what actually types. Chromium wants both fields on a printable key.
            params["text"] = packet.text
            params["unmodifiedText"] = packet.text
        return [CdpCall("Input.dispatchKeyEvent", params)]

    def _text_commit(self, packet: InputPacket) -> list[CdpCall]:
        # `insertText` rather than synthesized key events. An IME that produced one word
        # from five keystrokes did not produce five keys, and replaying it as keys is how
        # non-Latin input arrives in the page as nonsense.
        return [CdpCall("Input.insertText", {"text": packet.text})]

    def _composition(self, packet: InputPacket) -> list[CdpCall]:
        return [
            CdpCall(
                "Input.imeSetComposition",
                {
                    "text": packet.text,
                    "selectionStart": len(packet.text),
                    "selectionEnd": len(packet.text),
                },
            )
        ]


def _scroll_pixels(detents: int, extent: int) -> float:
    """One detent is a proportion of the viewport, not a fixed number of pixels.

    A constant would scroll a phone-sized viewport off the end and barely move a desktop
    one. `SCROLL_UNITS` on the device is 120 per detent, matching Android's own reporting.
    """
    return (detents / 120.0) * (extent * 0.2)


_ROUTES = {
    InputKind.POINTER_DOWN: CdpInputRouter._down,
    InputKind.POINTER_MOVE: CdpInputRouter._move,
    InputKind.POINTER_UP: CdpInputRouter._up,
    InputKind.POINTER_CANCEL: CdpInputRouter._cancel,
    InputKind.SCROLL: CdpInputRouter._scroll,
    InputKind.KEY_DOWN: lambda self, packet: self._key(packet, "keyDown"),
    InputKind.KEY_UP: lambda self, packet: self._key(packet, "keyUp"),
    InputKind.TEXT_COMMIT: CdpInputRouter._text_commit,
    InputKind.IME_COMPOSITION: CdpInputRouter._composition,
}

#: Every CDP method this router will ever emit. Compared against what it actually produces
#: by its tests, for the same reason the control agent's allowlist is: "narrow" is a claim
#: until something checks it.
PERMITTED_CDP_METHODS = frozenset(
    {
        "Input.dispatchMouseEvent",
        "Input.dispatchKeyEvent",
        "Input.insertText",
        "Input.imeSetComposition",
    }
)
