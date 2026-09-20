"""Rev 1.5 §§8, 26, 27 — the input wire format, the gesture machine and quality adaptation.

The gesture machine is the piece that cannot be checked by reading it. Its whole job is to
be correct when packets arrive in an order nobody planned, so the tests deliver them in the
orders that actually happen: the duplicate before the original, the MOVE before its DOWN,
the UP twice, the DOWN from a gesture that has already been superseded.

The quality tests are mostly about one sentence in §26.2 — a metered session is not failed
merely because it does not reach the unmetered target — and about §27.2's "must not silently
consume 4–12 Mbps for hours", which is a rule about what the default is, not about what is
possible.
"""

from __future__ import annotations

import pytest

from van_gateway.browser import input_protocol as ip
from van_gateway.browser.quality import (
    BrowserQualityController,
    LinkSample,
    METERED_LADDER,
    METERED_SLO,
    QualityMode,
    SessionQualityStatus,
    UNMETERED_LADDER,
    UNMETERED_SLO,
)

AUTH = ip.InputAuthority(
    session_id="ibs_1", control_lease_id="bctl_1", control_generation=2, viewport_revision=3
)


def _packet(kind: ip.InputKind, **kwargs) -> ip.InputPacket:
    base = dict(authority=AUTH, kind=kind, channel=ip.Channel.RELIABLE, pointer_id=1)
    base.update(kwargs)
    return ip.InputPacket(**base)


# --------------------------------------------------------------------------- the codec


class TestWireFormat:
    def test_a_packet_survives_a_round_trip_unchanged(self):
        packet = _packet(
            ip.InputKind.POINTER_DOWN, gesture_id=7, gesture_epoch=2, edge_id=9,
            x=12345, y=54321, fast_seq=3, reliable_seq=4, motion_seq=5, sent_at_ms=99,
        )
        assert ip.decode(ip.encode(packet)) == packet

    def test_text_survives_beyond_ascii(self):
        packet = _packet(ip.InputKind.TEXT_COMMIT, text="naïve — 東京")
        assert ip.decode(ip.encode(packet)).text == "naïve — 東京"

    def test_a_different_protocol_version_is_refused_rather_than_reinterpreted(self):
        """A newer client's longer record must not be read as this version's fields."""
        raw = bytearray(ip.encode(_packet(ip.InputKind.POINTER_MOVE, x=1, y=1)))
        raw[0] = ip.PROTOCOL_VERSION + 1
        with pytest.raises(ip.InputProtocolError) as caught:
            ip.decode(bytes(raw))
        assert caught.value.reason == ip.REJECT_VERSION

    def test_a_truncated_packet_is_refused(self):
        raw = ip.encode(_packet(ip.InputKind.POINTER_MOVE, x=1, y=1))
        with pytest.raises(ip.InputProtocolError):
            ip.decode(raw[:-3])

    def test_trailing_bytes_are_refused(self):
        """Silently ignoring a tail means two different packets decode identically."""
        raw = ip.encode(_packet(ip.InputKind.POINTER_MOVE, x=1, y=1))
        with pytest.raises(ip.InputProtocolError):
            ip.decode(raw + b"\x00")

    def test_an_unknown_kind_is_refused(self):
        raw = bytearray(ip.encode(_packet(ip.InputKind.POINTER_MOVE, x=1, y=1)))
        raw[1] = 200
        with pytest.raises(ip.InputProtocolError):
            ip.decode(bytes(raw))

    def test_coordinates_outside_the_normalized_range_cannot_be_encoded(self):
        with pytest.raises(ip.InputProtocolError):
            ip.encode(_packet(ip.InputKind.POINTER_DOWN, x=ip.COORDINATE_MAX + 1, y=0))

    def test_the_wire_carries_no_device_pixels(self):
        """§8.6 — normalized, so a packet means the same thing at any viewport."""
        packet = _packet(ip.InputKind.POINTER_DOWN, x=ip.COORDINATE_MAX, y=0)
        assert ip.to_viewport_pixels(packet.x, packet.y, width=1080, height=2016) == (1079, 0)
        assert ip.to_viewport_pixels(packet.x, packet.y, width=2016, height=1080) == (2015, 0)


# --------------------------------------------------------------------------- the machine


class TestPointerStateMachine:
    def _machine(self):
        return ip.PointerStateMachine("ibs_1")

    def test_a_normal_gesture_passes_through_in_order(self):
        m = self._machine()
        down = _packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1)
        move = _packet(ip.InputKind.POINTER_MOVE, gesture_id=1, gesture_epoch=1, motion_seq=1)
        up = _packet(ip.InputKind.POINTER_UP, gesture_id=1, gesture_epoch=1, edge_id=2)
        assert m.offer(down, now_ms=0).packets == (down,)
        assert m.offer(move, now_ms=1).packets == (move,)
        assert m.offer(up, now_ms=2).packets == (up,)
        assert m.open_pointers() == []

    def test_the_duplicate_edge_is_not_a_second_tap(self):
        """§8.3 — the same edge arrives on both channels, by design."""
        m = self._machine()
        fast = _packet(
            ip.InputKind.POINTER_DOWN, channel=ip.Channel.FAST,
            gesture_id=1, gesture_epoch=1, edge_id=1,
        )
        reliable = _packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1)
        assert m.offer(fast, now_ms=0).packets == (fast,)
        assert m.offer(reliable, now_ms=1).packets == ()

    def test_a_late_duplicate_down_does_not_press_the_page_again(self):
        """The case the edge de-duplication uniquely prevents.

        A first version of this suite tested the duplicate arriving while the gesture was
        still open, where the epoch guard also refuses it — so deleting the de-duplication
        changed nothing and the mutation survived. The distinguishing order is the one that
        actually happens on a lossy link: DOWN on the fast channel, UP, and then the
        reliable copy of the DOWN arriving after the gesture has already ended. Without
        de-duplication the pointer is pressed a second time, on a page the owner has
        already finished tapping.
        """
        m = self._machine()
        down = _packet(
            ip.InputKind.POINTER_DOWN, channel=ip.Channel.FAST,
            gesture_id=1, gesture_epoch=1, edge_id=1,
        )
        up = _packet(ip.InputKind.POINTER_UP, gesture_id=1, gesture_epoch=1, edge_id=2)
        m.offer(down, now_ms=0)
        m.offer(up, now_ms=5)

        late_copy = _packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1)
        assert m.offer(late_copy, now_ms=9).packets == ()
        assert m.open_pointers() == [], "the gesture was re-opened by its own duplicate"

    def test_a_move_that_overtakes_its_down_is_held_and_then_delivered(self):
        """The reordering §8.4 exists for: two SCTP streams, no ordering between them."""
        m = self._machine()
        move = _packet(
            ip.InputKind.POINTER_MOVE, channel=ip.Channel.FAST,
            gesture_id=1, gesture_epoch=1, motion_seq=1, sent_at_ms=0,
        )
        down = _packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1)
        assert m.offer(move, now_ms=0).packets == (), "a drag with no press must not dispatch"
        accepted = m.offer(down, now_ms=2)
        assert accepted.packets == (down, move), "the held move must follow its own press"

    def test_an_orphaned_move_is_dropped_once_the_grace_has_passed(self):
        m = self._machine()
        first = _packet(
            ip.InputKind.POINTER_MOVE, gesture_id=1, gesture_epoch=1, motion_seq=1, sent_at_ms=0
        )
        m.offer(first, now_ms=0)
        later = _packet(
            ip.InputKind.POINTER_MOVE, gesture_id=1, gesture_epoch=1, motion_seq=2,
            sent_at_ms=ip.ORPHAN_MOVE_GRACE_MS + 1,
        )
        m.offer(later, now_ms=ip.ORPHAN_MOVE_GRACE_MS + 1)
        down = _packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1)
        delivered = m.offer(down, now_ms=ip.ORPHAN_MOVE_GRACE_MS + 2).packets
        assert first not in delivered, "a move older than the grace must not resurface"
        assert later in delivered

    def test_a_move_from_a_finished_gesture_is_refused(self):
        m = self._machine()
        m.offer(_packet(ip.InputKind.POINTER_DOWN, gesture_id=2, gesture_epoch=2, edge_id=1), now_ms=0)
        with pytest.raises(ip.InputProtocolError) as caught:
            m.offer(
                _packet(ip.InputKind.POINTER_MOVE, gesture_id=1, gesture_epoch=1, motion_seq=9),
                now_ms=1,
            )
        assert caught.value.reason == ip.REJECT_STALE_EPOCH

    def test_a_reordered_move_within_a_gesture_is_dropped_not_applied(self):
        """The unreliable channel reorders; applying an old position would jump the page."""
        m = self._machine()
        m.offer(_packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1), now_ms=0)
        newer = _packet(ip.InputKind.POINTER_MOVE, gesture_id=1, gesture_epoch=1, motion_seq=5, x=500)
        older = _packet(ip.InputKind.POINTER_MOVE, gesture_id=1, gesture_epoch=1, motion_seq=4, x=100)
        assert m.offer(newer, now_ms=1).packets == (newer,)
        assert m.offer(older, now_ms=2).packets == ()

    def test_a_new_gesture_cancels_the_one_it_replaces(self):
        """Two live gestures on one pointer is not a state any page can interpret."""
        m = self._machine()
        m.offer(_packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1), now_ms=0)
        second = _packet(ip.InputKind.POINTER_DOWN, gesture_id=2, gesture_epoch=2, edge_id=2)
        accepted = m.offer(second, now_ms=5)
        assert accepted.synthesized_cancel is True
        assert accepted.packets[0].kind is ip.InputKind.POINTER_CANCEL
        assert accepted.packets[0].gesture_id == 1
        assert accepted.packets[-1] == second

    def test_a_late_down_does_not_reopen_a_superseded_gesture(self):
        m = self._machine()
        m.offer(_packet(ip.InputKind.POINTER_DOWN, gesture_id=2, gesture_epoch=2, edge_id=2), now_ms=0)
        late = _packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1)
        assert m.offer(late, now_ms=1).packets == ()

    def test_an_up_for_an_unknown_gesture_is_ignored_idempotently(self):
        m = self._machine()
        up = _packet(ip.InputKind.POINTER_UP, gesture_id=99, gesture_epoch=9, edge_id=99)
        assert m.offer(up, now_ms=0).packets == ()

    def test_a_gesture_that_goes_quiet_is_cancelled_by_the_server(self):
        """The failure this prevents: a finger pressed forever after the phone vanishes."""
        m = self._machine()
        m.offer(_packet(ip.InputKind.POINTER_DOWN, gesture_id=1, gesture_epoch=1, edge_id=1), now_ms=0)
        assert m.sweep(now_ms=ip.GESTURE_TIMEOUT_MS - 1) == []
        cancels = m.sweep(now_ms=ip.GESTURE_TIMEOUT_MS)
        assert [c.kind for c in cancels] == [ip.InputKind.POINTER_CANCEL]
        assert m.open_pointers() == []
        assert m.sweep(now_ms=ip.GESTURE_TIMEOUT_MS * 3) == [], "cancelled once, not repeatedly"

    def test_two_pointers_do_not_interfere(self):
        m = self._machine()
        a = _packet(ip.InputKind.POINTER_DOWN, pointer_id=1, gesture_id=1, gesture_epoch=1, edge_id=1)
        b = _packet(ip.InputKind.POINTER_DOWN, pointer_id=2, gesture_id=2, gesture_epoch=1, edge_id=2)
        m.offer(a, now_ms=0)
        accepted = m.offer(b, now_ms=0)
        assert accepted.synthesized_cancel is False
        assert sorted(m.open_pointers()) == [1, 2]

    def test_keys_and_text_pass_through_without_gesture_state(self):
        m = self._machine()
        key = _packet(ip.InputKind.KEY_DOWN, value_a=65)
        text = _packet(ip.InputKind.TEXT_COMMIT, text="hello")
        assert m.offer(key, now_ms=0).packets == (key,)
        assert m.offer(text, now_ms=1).packets == (text,)


# --------------------------------------------------------------------------- quality


def _sample(**kwargs) -> LinkSample:
    base = dict(
        rtt_ms=40.0, jitter_ms=5.0, packet_loss=0.0, available_bitrate_kbps=9_000.0,
        encode_ms=8.0, capture_ms=3.0, rendered_fps=60.0, metered=False,
    )
    base.update(kwargs)
    return LinkSample(**base)


class TestQualityAdaptation:
    def test_a_healthy_unmetered_link_reaches_the_top_of_the_ladder(self):
        """ULTRA asks for 8 Mbps, and the upgrade margin asks for headroom on top of it.

        A first version of this test offered 9 Mbps and expected ULTRA. It got NORMAL,
        which is correct: 9 Mbps is enough to send an 8 Mbps stream and not enough to
        promise one. Demanding the margin is the difference between a link that can carry
        the mode and a link that is about to drop back out of it.
        """
        c = BrowserQualityController()
        for _ in range(5):
            verdict = c.observe(_sample(available_bitrate_kbps=12_000))
        assert verdict.mode is QualityMode.ULTRA
        assert verdict.status is SessionQualityStatus.OK
        assert verdict.certified_high_quality is True

    def test_metered_data_is_capped_by_default_and_the_owner_can_lift_it(self):
        """§27.2 — VAN must not silently spend hours of someone's mobile data at 8 Mbps."""
        capped = BrowserQualityController()
        for _ in range(6):
            verdict = capped.observe(_sample(metered=True))
        assert verdict.mode in METERED_LADDER
        assert verdict.target.bitrate_kbps <= 3_000
        assert verdict.target.max_height <= 720

        lifted = BrowserQualityController()
        for _ in range(6):
            allowed = lifted.observe(
                _sample(metered=True, owner_allows_high_quality_on_metered=True)
            )
        assert allowed.target.bitrate_kbps > 3_000

    def test_a_metered_session_is_not_failed_for_missing_the_unmetered_target(self):
        """§26.2, stated as a test because it is the easiest sentence in the document to
        implement backwards."""
        c = BrowserQualityController()
        verdict = c.observe(_sample(metered=True, rendered_fps=35.0, available_bitrate_kbps=2_500))
        assert verdict.profile is METERED_SLO
        assert verdict.status is SessionQualityStatus.OK

        unmetered = BrowserQualityController()
        same_link = unmetered.observe(_sample(rendered_fps=35.0))
        assert same_link.profile is UNMETERED_SLO
        assert same_link.status is SessionQualityStatus.DEGRADED

    def test_high_quality_certification_is_never_claimed_on_metered_data(self):
        """§26.2's other half: the telemetry must not report a certification it did not earn."""
        c = BrowserQualityController()
        verdict = c.observe(_sample(metered=True, rendered_fps=60.0, packet_loss=0.0))
        assert verdict.status is SessionQualityStatus.OK
        assert verdict.certified_high_quality is False

    def test_a_link_that_cannot_meet_the_budget_is_named_rather_than_blamed_on_the_encoder(self):
        """§26.3 — no encoder setting fixes a round trip."""
        c = BrowserQualityController()
        verdict = c.observe(_sample(rtt_ms=400.0))
        assert verdict.status is SessionQualityStatus.NETWORK_LIMITED
        assert "round trip" in verdict.reason

    def test_quality_drops_at_once_and_climbs_only_after_a_streak(self):
        """§27.4 — without hysteresis the badge flickers and reads as instability."""
        c = BrowserQualityController(mode=QualityMode.ULTRA)
        dropped = c.observe(_sample(available_bitrate_kbps=1_600))
        assert dropped.mode.rank < QualityMode.ULTRA.rank, "a degraded link must not wait"

        before = c.mode
        first = c.observe(_sample(available_bitrate_kbps=9_000))
        assert first.mode is before, "one good sample is not a trend"
        c.observe(_sample(available_bitrate_kbps=9_000))
        third = c.observe(_sample(available_bitrate_kbps=9_000))
        assert third.mode.rank > before.rank

    def test_an_upgrade_climbs_one_rung_at_a_time(self):
        c = BrowserQualityController(mode=QualityMode.SURVIVAL)
        for _ in range(3):
            verdict = c.observe(_sample(available_bitrate_kbps=20_000))
        assert verdict.mode is QualityMode.CONSTRAINED, (
            "jumping the ladder is how an upgrade turns straight back into a downgrade"
        )

    def test_moving_onto_metered_data_mid_session_lowers_the_ceiling(self):
        c = BrowserQualityController(mode=QualityMode.ULTRA)
        verdict = c.observe(_sample(metered=True))
        assert verdict.mode in METERED_LADDER
        assert QualityMode.ULTRA not in METERED_LADDER

    def test_the_owner_summary_says_what_it_cost_and_which_regime_it_was_in(self):
        c = BrowserQualityController()
        c.account(media_received=5_000_000, media_sent=200_000, control=1_000)
        summary = c.owner_summary(_sample(metered=True))
        assert summary["network"] == "mobile data"
        assert summary["metered"] is True
        assert summary["data_used_mb"] == pytest.approx(5.2, abs=0.01)
        assert summary["high_quality_certified"] is False
        assert summary["profile"] == "metered"
