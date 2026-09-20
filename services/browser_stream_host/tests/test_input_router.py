"""Rev 1.5 §§8.1, 8.6 — RB-017, the last step before the owner's tap becomes a click.

This is the point where a wrong answer is invisible and wrong in the worst way: the packet
is well-formed, the session is live, the gesture machine has admitted it, and the click
lands somewhere the owner did not touch. So the tests are about the two things that decide
where it lands — the revision it was built against, and the arithmetic that maps it — plus
the handful of CDP details that look like plumbing and are not.

The full path from a phone to a page is not tested here and cannot be: it needs a Chromium.
What this pins is that the translation is right, so that when a host exists the remaining
question is whether the host works rather than whether the mapping was ever correct.
"""

from __future__ import annotations

import pytest

from services.browser_stream_host.input_router import (
    PERMITTED_CDP_METHODS,
    REJECT_NOT_INPUT,
    REJECT_STALE_GENERATION,
    REJECT_STALE_VIEWPORT,
    REJECT_UNMAPPED_KIND,
    CdpInputRouter,
    InputRouterRefused,
    Viewport,
)
from van_gateway.browser.input_protocol import (
    COORDINATE_MAX,
    Channel,
    InputAuthority,
    InputKind,
    InputPacket,
)

GENERATION = 3
REVISION = 4


def _router(width: int = 1280, height: int = 720) -> CdpInputRouter:
    return CdpInputRouter(
        viewport=Viewport(width, height, REVISION), control_generation=GENERATION
    )


def _packet(
    kind: InputKind = InputKind.POINTER_DOWN,
    *,
    x: int = 0,
    y: int = 0,
    revision: int = REVISION,
    generation: int = GENERATION,
    **fields,
) -> InputPacket:
    return InputPacket(
        authority=InputAuthority(
            session_id="ibs_1",
            control_lease_id="bctl_1",
            control_generation=generation,
            viewport_revision=revision,
        ),
        kind=kind,
        channel=Channel.RELIABLE,
        x=x,
        y=y,
        **fields,
    )


class TestTheRevisionDecidesWhetherItActuates:

    def test_a_packet_from_the_previous_layout_is_refused_not_transformed(self):
        """§8.6's whole purpose.

        The device built this packet while the page was one size and it arrived after a
        resize. Transforming it would put the tap where the page used to be, and nothing
        downstream could tell.
        """
        with pytest.raises(InputRouterRefused) as caught:
            _router().route(_packet(revision=REVISION - 1))
        assert caught.value.reason == REJECT_STALE_VIEWPORT

    def test_a_packet_from_a_newer_revision_is_refused_too(self):
        """Not "older is stale, newer is fine": the host renders one layout, and a packet
        for a layout it has not adopted is as unusable as one for a layout it has left."""
        with pytest.raises(InputRouterRefused) as caught:
            _router().route(_packet(revision=REVISION + 1))
        assert caught.value.reason == REJECT_STALE_VIEWPORT

    def test_adopting_the_new_viewport_admits_the_packet(self):
        """The other half — a router that refused everything would pass both tests above."""
        router = _router()
        router.adopt_viewport(Viewport(800, 600, REVISION + 1))
        assert router.route(_packet(revision=REVISION + 1))

    def test_a_preempted_control_generation_is_refused(self):
        """ADR-RB-007 at the last possible moment. An agent that has been preempted still
        holds a valid-looking packet; only the generation says otherwise."""
        with pytest.raises(InputRouterRefused) as caught:
            _router().route(_packet(generation=GENERATION - 1))
        assert caught.value.reason == REJECT_STALE_GENERATION

    def test_the_revision_is_checked_before_the_generation(self):
        """Both wrong should report the revision, because a resize is the ordinary case and
        a preemption is the exceptional one; reporting the rare cause for the common event
        sends whoever reads the log to the wrong place."""
        with pytest.raises(InputRouterRefused) as caught:
            _router().route(_packet(revision=99, generation=99))
        assert caught.value.reason == REJECT_STALE_VIEWPORT


class TestTheCoordinateMapping:

    def test_the_extremes_map_to_the_extremes(self):
        """Off by one at either end is a row of pixels the owner can never reach."""
        router = _router(1280, 720)
        top_left = router.route(_packet(InputKind.POINTER_MOVE, x=0, y=0))[0]
        assert (top_left.params["x"], top_left.params["y"]) == (0, 0)

        bottom_right = router.route(
            _packet(InputKind.POINTER_MOVE, x=COORDINATE_MAX, y=COORDINATE_MAX)
        )[0]
        assert (bottom_right.params["x"], bottom_right.params["y"]) == (1279, 719)

    def test_the_middle_lands_in_the_middle(self):
        router = _router(1000, 500)
        middle = router.route(
            _packet(InputKind.POINTER_MOVE, x=COORDINATE_MAX // 2, y=COORDINATE_MAX // 2)
        )[0]
        assert middle.params["x"] == pytest.approx(499, abs=1)
        assert middle.params["y"] == pytest.approx(249, abs=1)

    def test_the_phone_s_screen_size_never_enters_the_calculation(self):
        """The wire carries a normalized coordinate precisely so that the same packet maps
        differently on two viewports. If it carried pixels, this test could not exist."""
        packet = _packet(InputKind.POINTER_MOVE, x=COORDINATE_MAX, y=0)
        wide = _router(1920, 1080).route(packet)[0]
        narrow = _router(800, 600).route(packet)[0]
        assert wide.params["x"] == 1919
        assert narrow.params["x"] == 799

    def test_a_one_pixel_viewport_does_not_divide_by_zero(self):
        result = _router(1, 1).route(_packet(InputKind.POINTER_MOVE, x=COORDINATE_MAX))[0]
        assert result.params["x"] == 0


class TestTheCdpDetailsThatLookLikePlumbing:

    def test_a_press_moves_first(self):
        """Without the move, Chromium presses wherever the pointer last was, and a page
        whose button only appears on hover gets the press on the wrong element."""
        calls = _router().route(_packet(InputKind.POINTER_DOWN, x=100, y=100))
        assert [call.params["type"] for call in calls] == ["mouseMoved", "mousePressed"]
        assert calls[0].params["x"] == calls[1].params["x"]

    def test_a_drag_reports_the_button_as_held(self):
        """`buttons: 0` on a move tells Chromium no button is down, which ends the drag
        halfway through it."""
        move = _router().route(_packet(InputKind.POINTER_MOVE, x=50, y=50))[0]
        assert move.params["buttons"] == 1

    def test_a_release_reports_no_button_held(self):
        release = _router().route(_packet(InputKind.POINTER_UP))[0]
        assert release.params["buttons"] == 0
        assert release.params["clickCount"] == 1

    def test_a_cancel_releases_rather_than_disappearing(self):
        """The gesture machine synthesizes a cancel when a gesture is superseded. Dropping
        it here leaves the page holding a press the owner's finger has already left."""
        calls = _router().route(_packet(InputKind.POINTER_CANCEL))
        assert [call.params["type"] for call in calls] == ["mouseReleased"]

    def test_text_is_inserted_rather_than_typed(self):
        """An IME that produced one word from five keystrokes did not produce five keys."""
        call = _router().route(_packet(InputKind.TEXT_COMMIT, text="東京"))[0]
        assert call.method == "Input.insertText"
        assert call.params["text"] == "東京"

    def test_a_composition_is_set_rather_than_committed(self):
        call = _router().route(_packet(InputKind.IME_COMPOSITION, text="kon"))[0]
        assert call.method == "Input.imeSetComposition"
        assert call.params["selectionStart"] == 3

    def test_a_printable_key_carries_its_text(self):
        """`keyDown` without `text` fires a key event the page sees and types nothing."""
        call = _router().route(_packet(InputKind.KEY_DOWN, value_a=65, text="a"))[0]
        assert call.params["text"] == "a"
        assert call.params["unmodifiedText"] == "a"
        assert call.params["windowsVirtualKeyCode"] == 65

    def test_a_non_printable_key_carries_no_text_field(self):
        """Sending `text: ""` for Backspace makes Chromium insert an empty string instead
        of deleting."""
        call = _router().route(_packet(InputKind.KEY_UP, value_a=8))[0]
        assert "text" not in call.params
        assert call.params["type"] == "keyUp"

    def test_modifiers_are_passed_through(self):
        call = _router().route(_packet(InputKind.KEY_DOWN, value_a=67, value_b=2))[0]
        assert call.params["modifiers"] == 2

    def test_a_scroll_is_proportional_to_the_viewport(self):
        """A fixed pixel delta scrolls a small viewport off the end and barely moves a
        large one; the device sends detents for exactly this reason."""
        packet = _packet(InputKind.SCROLL, value_b=120)
        tall = _router(1280, 1000).route(packet)[0]
        short = _router(1280, 400).route(packet)[0]
        assert tall.params["deltaY"] > short.params["deltaY"]
        assert tall.params["deltaY"] == pytest.approx(200.0)

    def test_a_scroll_in_the_other_direction_is_negative(self):
        up = _router().route(_packet(InputKind.SCROLL, value_b=-120))[0]
        assert up.params["deltaY"] < 0


class TestTheRouterIsNarrow:

    def test_every_input_kind_has_a_mapping(self):
        """A kind with no route is an input the owner can send and the page never sees."""
        router = _router()
        for kind in InputKind:
            if kind.is_navigation:
                continue
            assert router.route(_packet(kind, text="x")), kind

    def test_a_navigation_is_refused_as_a_boundary_rather_than_as_a_gap(self):
        """§17.2 — navigation travels the input path and is not translated here.

        The distinction is the whole reason this has its own reason string. An unmapped
        kind is a gap in the router; a navigation is a packet that belongs to a different
        component. Collapsing them into `kind_has_no_mapping` would make the boundary read
        as an omission, and the next person to see it would close it by adding
        `Page.navigate` to the table — which is precisely what this router must not emit.
        """
        router = _router()
        for kind in InputKind:
            if not kind.is_navigation:
                continue
            with pytest.raises(InputRouterRefused) as caught:
                router.route(_packet(kind, text="https://example.com/"))
            assert caught.value.reason == REJECT_NOT_INPUT, kind

    def test_a_stale_navigation_is_refused_as_stale_first(self):
        """The more specific truth, and the one a preempted agent needs to hear.

        "You no longer hold the lease" tells the agent to stop. "That is not an input"
        tells it to send the same thing somewhere else, which is the wrong action when the
        owner has just taken control.
        """
        router = _router()
        packet = _packet(InputKind.NAVIGATE, text="https://example.com/", generation=99)
        with pytest.raises(InputRouterRefused) as caught:
            router.route(packet)
        assert caught.value.reason == REJECT_STALE_GENERATION

    def test_an_unmapped_kind_is_refused_rather_than_ignored(self):
        from services.browser_stream_host import input_router as module

        router = _router()
        original = module._ROUTES.pop(InputKind.SCROLL)
        try:
            with pytest.raises(InputRouterRefused) as caught:
                router.route(_packet(InputKind.SCROLL))
            assert caught.value.reason == REJECT_UNMAPPED_KIND
        finally:
            module._ROUTES[InputKind.SCROLL] = original

    def test_it_emits_nothing_outside_the_allowlist(self):
        router = _router()
        emitted = set()
        for kind in InputKind:
            if kind.is_navigation:
                continue
            emitted.update(call.method for call in router.route(_packet(kind, text="x")))
        assert emitted <= PERMITTED_CDP_METHODS, sorted(emitted - PERMITTED_CDP_METHODS)

    def test_it_never_emits_a_navigation_or_an_evaluation(self):
        """Input is input. A router that could navigate would be a second actuation path
        with no control lease behind it."""
        router = _router()
        for kind in InputKind:
            if kind.is_navigation:
                # Refused above, by name. The property here is about what the router
                # *emits*, and a kind it refuses emits nothing.
                continue
            for call in router.route(_packet(kind, text="x")):
                assert call.method.startswith("Input."), call.method


class TestTheInputFloodBound:
    """Rev 1.5 §38 item 12 — the flood where every packet is well-formed.

    Bounded here rather than at the Gateway because the Gateway is not in this path: §8's
    input travels device → Stream Host, and a bound anywhere else would be counting
    something it cannot see.
    """

    def _limited(self, limit: int = 3):
        from van_gateway.browser.flood_bounds import InputRateLimiter

        return CdpInputRouter(
            viewport=Viewport(1280, 720, REVISION),
            control_generation=GENERATION,
            rate_limiter=InputRateLimiter(limit=limit, window_ms=1_000),
        )

    def test_a_router_with_no_limiter_translates_everything(self):
        """Every caller that existed before this bound keeps working unchanged."""
        router = _router()
        for _ in range(1_000):
            assert router.route(_packet(InputKind.POINTER_MOVE))

    def test_packets_past_the_bound_are_refused_by_name(self):
        from services.browser_stream_host.input_router import REJECT_INPUT_FLOOD

        router = self._limited()
        for _ in range(3):
            assert router.route(_packet(InputKind.POINTER_MOVE), now_ms=1_000)
        with pytest.raises(InputRouterRefused) as caught:
            router.route(_packet(InputKind.POINTER_MOVE), now_ms=1_000)
        assert caught.value.reason == REJECT_INPUT_FLOOD

    def test_the_session_recovers_once_the_window_passes(self):
        router = self._limited()
        for _ in range(3):
            router.route(_packet(InputKind.POINTER_MOVE), now_ms=1_000)
        assert router.route(_packet(InputKind.POINTER_MOVE), now_ms=2_100)

    def test_a_stale_packet_is_reported_as_stale_rather_than_as_a_flood(self):
        """The ordering that makes the log usable.

        A flood of packets that are *also* preempted should say preempted: that is the
        fact an agent needs to act on, and a rate refusal would hide it behind a symptom.
        """
        router = self._limited(limit=0)
        with pytest.raises(InputRouterRefused) as caught:
            router.route(_packet(generation=GENERATION - 1), now_ms=1_000)
        assert caught.value.reason == REJECT_STALE_GENERATION

    def test_a_navigation_is_still_a_boundary_rather_than_a_flood(self):
        router = self._limited(limit=0)
        with pytest.raises(InputRouterRefused) as caught:
            router.route(
                _packet(InputKind.NAVIGATE, text="https://example.com/"), now_ms=1_000,
            )
        assert caught.value.reason == REJECT_NOT_INPUT
