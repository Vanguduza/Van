"""Rev 1.5 §§21.14, 21.15, 21.16 — segmenting an answer, and serving it from where the
owner actually got to.

The failure the whole module exists to prevent is one sentence long and every streaming
assistant produces it at least once: a reconnect makes

    "Here is your answer..."

start again from the beginning, when the owner has already heard four sentences of it.

Two cursors are what prevent it, and the tests below are mostly about the difference
between them. `last_received` is what reached the phone; `last_spoken` is what came out of
the speaker. A path that dies between the two leaves segments that arrived and were never
heard, and resuming from the wrong one either repeats a sentence or puts a hole in the
middle of the answer that nobody can see.
"""

from __future__ import annotations

import pytest

from van_gateway.voice.segmentation import (
    MAX_CHARS,
    build_segments,
    segment,
)
from van_gateway.voice.speech_stream import SpeechStreamService

LONG = (
    "The second important factor is cost, which runs high. "
    "It takes approx. 40 percent of the budget in the first year. "
    "After that the figure settles and the remainder is fixed. "
    "That is the whole of it."
)


class TestSegmentation:

    def test_an_answer_is_cut_at_sentences_not_at_a_width(self):
        """§21.14 — never arbitrary chunks.

        A segment that ends mid-sentence means a failover leaves the owner with half a
        clause and no way to tell that is what happened.
        """
        pieces = segment(LONG)
        assert len(pieces) >= 3
        assert all(p.rstrip()[-1] in ".!?" for p in pieces), pieces

    def test_an_abbreviation_is_not_a_sentence_end(self):
        """Splitting on every full stop puts a pause in the middle of a number.

        Both halves are deliberately long here. A shorter example passed with the
        abbreviation handling removed, because the fragment packing rejoined the pieces —
        the test was green for a reason that had nothing to do with what it was checking,
        and a mutation found it.
        """
        sentence = (
            "The first year consumes approx. 40 percent of the total budget allocated to "
            "the programme, and the remainder is spread across the following two years."
        )
        pieces = segment(sentence)
        assert len(pieces) == 1, pieces
        # And the half that would have been severed is long enough to survive packing.
        assert len("The first year consumes approx.") > 24

    def test_a_fragment_is_joined_rather_than_given_its_own_segment(self):
        """Otherwise "Yes." becomes a segment and the queue fills with one-word units."""
        pieces = segment("This is a reasonably long opening sentence for the answer. Yes.")
        assert len(pieces) == 1
        assert pieces[0].endswith("Yes.")

    def test_a_sentence_within_the_ceiling_stays_whole(self):
        """§21.14's rule, from the other side: a sentence is not cut because it is long.

        This was written as a "long sentences are split" test with a 299-character
        sentence, which is under the 320 ceiling — it passed for the wrong reason until the
        assertion was tightened. One sentence is one segment, however long, until it
        exceeds the ceiling.
        """
        sentence = (
            "The system holds the owner's session, and it keeps the profile on the host, "
            "but it never moves the authority off Trading Core, because that is where the "
            "policy lives, which is the whole reason the topology is what it is, so the "
            "control path stays private and narrow throughout the entire deployment."
        )
        assert len(sentence) < MAX_CHARS
        assert segment(sentence) == [sentence]

    def test_a_sentence_over_the_ceiling_is_cut_at_a_clause(self):
        sentence = (
            "The system holds the owner's session, and it keeps the profile on the host, "
            "but it never moves the authority off Trading Core, because that is where the "
            "policy lives, which is the whole reason the topology is what it is, so the "
            "control path stays private and narrow throughout the entire deployment, and "
            "that is the arrangement the blueprint describes at considerable length."
        )
        assert len(sentence) > MAX_CHARS
        pieces = segment(sentence)
        assert len(pieces) > 1
        assert all(len(p) <= MAX_CHARS for p in pieces), [len(p) for p in pieces]
        # And the cuts landed on clause boundaries, not on a character count.
        assert all(p[-1] in ",.;:" for p in pieces[:-1]), pieces

    def test_a_long_sentence_with_no_clause_boundary_is_not_cut_mid_word(self):
        """A long pause is a better outcome than a severed word."""
        sentence = "word " * 100
        pieces = segment(sentence.strip())
        assert len(pieces) == 1

    def test_empty_input_produces_no_segments_rather_than_one_empty_one(self):
        assert segment("") == []
        assert segment("   \n\n  ") == []

    def test_only_the_last_segment_is_final(self):
        segments = build_segments(response_id="rsp_1", speech_stream_id="sp_1", text=LONG)
        assert [s.final for s in segments] == [False] * (len(segments) - 1) + [True]

    def test_the_digest_is_over_the_text_alone(self):
        """A resent segment must be recognisable as the same one; a digest that included
        the index would make a renumbered stream look like different content."""
        first = build_segments(response_id="a", speech_stream_id="sp_a", text=LONG)
        second = build_segments(
            response_id="b", speech_stream_id="sp_b", text=LONG, first_index=10
        )
        assert [s.content_digest for s in first] == [s.content_digest for s in second]

    def test_segment_ids_are_stable_and_ordered(self):
        segments = build_segments(response_id="rsp_1", speech_stream_id="sp_1", text=LONG)
        assert segments[0].segment_id == "sp_1_0000"
        assert [s.segment_index for s in segments] == list(range(len(segments)))


class TestServingFromTheCursor:

    def _stream(self):
        service = SpeechStreamService()
        stream = service.open(
            response_id="rsp_58", turn_id="turn_196", device_id="s24", text=LONG
        )
        return service, stream

    def test_a_reconnect_resumes_from_what_was_heard_not_from_what_arrived(self):
        """The whole point. Received is not spoken."""
        service, stream = self._stream()
        service.report_cursors(
            stream.speech_stream_id, last_received_segment=3, last_spoken_segment=1
        )
        resumed = [s.segment_index for s in service.resume_from(stream.speech_stream_id)]
        assert resumed[0] == 2, "resuming from received would skip segment 2"

    def test_nothing_spoken_yet_resumes_from_the_beginning(self):
        service, stream = self._stream()
        resumed = service.resume_from(stream.speech_stream_id)
        assert len(resumed) == len(stream.segments)

    def test_cursors_only_move_forward(self):
        """A device that restarted its queue must not cause audio to be resent.

        That is the same §21.16 failure arriving from the other direction: the owner hears
        a sentence they already heard, because the phone forgot and the Gateway believed it.
        """
        service, stream = self._stream()
        service.report_cursors(
            stream.speech_stream_id, last_received_segment=3, last_spoken_segment=3
        )
        service.report_cursors(
            stream.speech_stream_id, last_received_segment=0, last_spoken_segment=0
        )
        assert service.get(stream.speech_stream_id).last_spoken_segment == 3

    def test_reopening_a_response_keeps_what_the_device_reported(self):
        """The property the idempotency guard actually protects.

        The stream id is derived from the response id, so a second `open` produced an
        identical-looking stream and the original assertions held with the guard removed —
        a mutation found that. What a second `open` really destroys is the cursor: the
        device has told us it heard three segments, and a fresh stream forgets, so the
        resume replays audio the owner already heard.
        """
        service, stream = self._stream()
        service.report_cursors(
            stream.speech_stream_id, last_received_segment=3, last_spoken_segment=2
        )

        again = service.open(
            response_id="rsp_58", turn_id="turn_196", device_id="s24", text=LONG
        )

        assert again.speech_stream_id == stream.speech_stream_id
        assert again.last_spoken_segment == 2, "re-opening forgot what the owner heard"
        assert [s.segment_index for s in service.resume_from(again.speech_stream_id)][0] == 3

    def test_appending_numbers_after_what_is_already_there(self):
        """Re-segmenting the accumulated text would renumber segments already spoken."""
        service, stream = self._stream()
        before = len(stream.segments)
        fresh = service.append(stream.speech_stream_id, "And one more thing worth saying.")
        assert fresh[0].segment_index == before
        assert not stream.segments[before - 1].final, "an answer that continues did not end"
        assert stream.segments[-1].final

    def test_delivered_is_not_complete(self):
        service, stream = self._stream()
        last = stream.segments[-1].segment_index
        service.report_cursors(
            stream.speech_stream_id, last_received_segment=last, last_spoken_segment=last - 1
        )
        assert not service.get(stream.speech_stream_id).complete
        service.report_cursors(
            stream.speech_stream_id, last_received_segment=last, last_spoken_segment=last
        )
        assert service.get(stream.speech_stream_id).complete


class TestWhatResumeReports:

    def test_an_unfinished_answer_is_offered_back_on_resume(self):
        service = SpeechStreamService()
        stream = service.open(
            response_id="rsp_58", turn_id="turn_196", device_id="s24", text=LONG
        )
        service.report_cursors(
            stream.speech_stream_id, last_received_segment=2, last_spoken_segment=1
        )

        state = service.response_state("s24")

        assert state["response_id"] == "rsp_58"
        assert state["resume_from_segment"] == 2
        assert state["last_received_segment"] == 2
        assert state["last_spoken_segment"] == 1
        assert [s["segment_index"] for s in state["segments"]][0] == 2

    def test_a_finished_answer_is_not_offered_again(self):
        service = SpeechStreamService()
        stream = service.open(
            response_id="rsp_58", turn_id="turn_196", device_id="s24", text=LONG
        )
        last = stream.segments[-1].segment_index
        service.report_cursors(
            stream.speech_stream_id, last_received_segment=last, last_spoken_segment=last
        )
        assert service.response_state("s24") is None

    def test_a_barged_in_answer_is_not_resumed(self):
        """The owner stopped it. Resuming would be VAN finishing a sentence they cut off."""
        service = SpeechStreamService()
        stream = service.open(
            response_id="rsp_58", turn_id="turn_196", device_id="s24", text=LONG
        )
        service.interrupt(stream.speech_stream_id)
        assert service.response_state("s24") is None

    def test_another_device_sees_nothing(self):
        service = SpeechStreamService()
        service.open(response_id="rsp_58", turn_id="t", device_id="s24", text=LONG)
        assert service.response_state("another-phone") is None

    def test_no_answer_in_flight_reports_nothing_rather_than_an_empty_shape(self):
        """An empty `response_state` would make the device resume speech that does not
        exist, which is a queue that never drains."""
        assert SpeechStreamService().response_state("s24") is None

    def test_streams_are_swept_after_the_retention_window(self):
        service = SpeechStreamService()
        service.open(
            response_id="rsp_1", turn_id="t", device_id="s24", text=LONG, now_ms=0
        )
        assert service.sweep(now_ms=1_000) == 0
        assert service.sweep(now_ms=48 * 60 * 60 * 1000) == 1
        assert service.response_state("s24") is None


@pytest.mark.asyncio
class TestTheResumeRouteCarriesIt:

    async def test_the_snapshot_includes_the_spoken_cursor(self):
        """Read through the app so the wiring is what is tested, not the service.

        Without this the resume tells the client where its *commands* got to and says
        nothing about where its answer got to, so a reconnect mid-sentence has nothing to
        resume speech from.
        """
        import inspect

        from van_gateway import app as app_module

        source = inspect.getsource(app_module.create_app)
        assert '"response_state": speech_streams.response_state(device_id)' in source
