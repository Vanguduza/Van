"""GAP-F-013 — per-segment cue timing, estimated from text and attached to the wire payload.

The device already receives a segment's text in the same message; these tests are about the
timing that now rides along with it, and about the fact that `SpeechCueClock` — moved out of
`test_speech_sync.py` into production — actually consumes the shape `segmentation.py`
produces, rather than the two agreeing only by inspection.
"""

from __future__ import annotations

from van_gateway.voice.segmentation import build_segments
from van_gateway.voice.speech_cues import (
    SegmentCueTiming,
    SpeechCueClock,
    estimate_segment_timing,
)


class TestEstimateSegmentTiming:

    def test_empty_text_has_no_cues_and_zero_duration(self):
        timing = estimate_segment_timing("   ")
        assert timing.cues == ()
        assert timing.estimated_duration_ms == 0
        assert timing.rms_fallback is True

    def test_cues_start_at_zero_and_end_with_a_closing_cue(self):
        timing = estimate_segment_timing("VAN is thinking about it.")
        assert timing.cues[0][0] == 0
        last = timing.cues[-1]
        assert last[1] == 0 and last[2] == 0.0
        assert last[0] == timing.estimated_duration_ms

    def test_offsets_are_non_decreasing_and_bounded_by_the_duration(self):
        timing = estimate_segment_timing(
            "The second important factor is cost, which runs high in the first year."
        )
        offsets = [cue[0] for cue in timing.cues]
        assert offsets == sorted(offsets)
        assert all(0 <= offset <= timing.estimated_duration_ms for offset in offsets)

    def test_consecutive_cues_never_repeat_the_same_viseme(self):
        timing = estimate_segment_timing("One two three four five six seven eight nine ten")
        visemes = [cue[1] for cue in timing.cues[:-1]]
        assert all(a != b for a, b in zip(visemes, visemes[1:]))

    def test_a_longer_word_opens_the_mouth_more_than_a_short_one(self):
        timing = estimate_segment_timing("a extraordinarily")
        mouths = [cue[2] for cue in timing.cues[:-1]]
        assert mouths[1] > mouths[0]

    def test_mouth_open_never_exceeds_one(self):
        timing = estimate_segment_timing("supercalifragilisticexpialidocious indubitably")
        assert all(0.0 <= cue[2] <= 1.0 for cue in timing.cues)

    def test_a_faster_rate_produces_a_shorter_duration(self):
        text = "This is a segment of a reasonable, ordinary length for the estimate."
        slow = estimate_segment_timing(text, chars_per_second=8.0)
        fast = estimate_segment_timing(text, chars_per_second=30.0)
        assert fast.estimated_duration_ms < slow.estimated_duration_ms


class TestSegmentsCarryCueTiming:

    def test_every_built_segment_has_cue_timing(self):
        segments = build_segments(
            response_id="rsp_1", speech_stream_id="sp_1", text="Here is the answer. It works."
        )
        assert segments
        for seg in segments:
            assert isinstance(seg.cue_timing, SegmentCueTiming)
            assert seg.cue_timing.cues
            assert seg.cue_timing.rms_fallback is True

    def test_the_wire_payload_includes_cue_timing(self):
        segments = build_segments(response_id="rsp_1", speech_stream_id="sp_1", text="Yes it did.")
        payload = segments[0].as_json()
        assert "cue_timing" in payload
        assert payload["cue_timing"]["rms_fallback"] is True
        assert isinstance(payload["cue_timing"]["cues"], list)

    def test_the_digest_is_unaffected_by_cue_timing(self):
        """The content digest identifies the text, not the estimate derived from it —
        otherwise changing the estimation heuristic would make a resent segment look like
        different content to a device matching on `content_digest`."""
        a = build_segments(response_id="a", speech_stream_id="sp_a", text="Yes it did.")
        b = build_segments(response_id="b", speech_stream_id="sp_b", text="Yes it did.")
        assert a[0].content_digest == b[0].content_digest


class TestSpeechCueClockPlaysBackEstimatedCues:

    def test_the_clock_walks_the_estimated_cues_over_time(self):
        timing = estimate_segment_timing("Hello there friend")
        clock = SpeechCueClock(visual_lead_ms=0, max_slew=1.0)
        clock.start_phrase(list(timing.cues), now_ms=0)
        first = clock.tick(0)
        assert first["speaking"] is True
        ended = clock.tick(timing.estimated_duration_ms + 50)
        assert ended["mouth_open"] == 0.0

    def test_interrupt_mid_estimate_closes_the_mouth_immediately(self):
        timing = estimate_segment_timing("A reasonably long sentence to interrupt midway.")
        clock = SpeechCueClock(visual_lead_ms=0, max_slew=1.0)
        clock.start_phrase(list(timing.cues), now_ms=0)
        clock.tick(10)
        clock.interrupt()
        out = clock.tick(20)
        assert out["speaking"] is False
        assert out["mouth_open"] == 0.0
