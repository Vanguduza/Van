"""Rev 1.5 §§21.15, 21.16, 21.25 — serving an answer's speech from where the owner got to.

The thing this exists to prevent, stated once: a reconnect must not make VAN start reading
the answer again from the beginning. §21.16 is explicit, and the mechanism is that the
Gateway serves from the cursor the *device* reports, not from its own idea of progress.

Two cursors, not one, and the difference is the whole point:

    last_received_segment    what reached the phone
    last_spoken_segment      what the owner actually heard

A path that dies between those two leaves segments that arrived and were never spoken.
Resuming from `last_received` skips them — the answer develops a hole in the middle that
nobody can see. Resuming from `last_spoken` repeats at most one segment, which the device
discards by `segment_id`, and the owner hears a continuous answer.

The Gateway is not the authority on what was heard. It cannot be: the audio came out of a
speaker in a room it has no access to. So it stores what the device reports and serves
accordingly, and a device that reports a cursor it never reached is a device that loses its
own audio — which is a phone bug rather than a Gateway one, and is not something the
Gateway can or should second-guess.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from van_gateway.voice.segmentation import SpeechSegment, build_segments

#: §21.15 — the cursors persist; synthesized audio does not. The Gateway never holds audio
#: at all, so this is only about how long the *text* of an answered stream is kept.
STREAM_RETENTION_MS = 24 * 60 * 60 * 1000


@dataclass
class SpeechStream:
    """One response's spoken form."""

    speech_stream_id: str
    response_id: str
    turn_id: str
    device_id: str
    segments: list[SpeechSegment] = field(default_factory=list)
    created_at_ms: int = 0
    #: What the device last told us. Never inferred.
    last_received_segment: int = -1
    last_spoken_segment: int = -1
    interrupted: bool = False

    @property
    def final_index(self) -> int:
        return max((s.segment_index for s in self.segments if s.final), default=-1)

    @property
    def complete(self) -> bool:
        """Complete means the owner heard the last segment, not that we sent it."""
        return self.final_index >= 0 and self.last_spoken_segment >= self.final_index


class SpeechStreamService:
    """In-memory because a speech stream outlives a socket and not a Gateway restart.

    That is a deliberate boundary rather than an oversight. A restart loses the *text* of an
    answer in flight; the command that produced it is durable and its result is durable, so
    the owner can ask again and the work is not repeated. Persisting the speech itself would
    mean storing what VAN said to its owner, indefinitely, for a benefit that lasts seconds.
    """

    def __init__(self) -> None:
        self._streams: dict[str, SpeechStream] = {}
        self._by_response: dict[str, str] = {}

    def open(
        self,
        *,
        response_id: str,
        turn_id: str,
        device_id: str,
        text: str,
        interruptible: bool = True,
        now_ms: int | None = None,
    ) -> SpeechStream:
        """Segment an answer and register it. Re-opening the same response returns it.

        Idempotent on `response_id` because a retried delivery must not produce a second
        stream: two streams for one answer means two sets of segment ids, and the device's
        de-duplication is by id.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        existing = self._by_response.get(response_id)
        if existing is not None:
            return self._streams[existing]

        stream_id = f"sp_{response_id}"
        stream = SpeechStream(
            speech_stream_id=stream_id,
            response_id=response_id,
            turn_id=turn_id,
            device_id=device_id,
            segments=build_segments(
                response_id=response_id,
                speech_stream_id=stream_id,
                text=text,
                interruptible=interruptible,
            ),
            created_at_ms=now,
        )
        self._streams[stream_id] = stream
        self._by_response[response_id] = stream_id
        return stream

    def append(self, speech_stream_id: str, text: str, *, interruptible: bool = True) -> list[SpeechSegment]:
        """More of an answer that is still being produced.

        Streaming responses arrive in pieces, and each piece is segmented on its own and
        numbered after the last. Re-segmenting the whole accumulated text would renumber
        segments the device has already spoken.
        """
        stream = self._streams.get(speech_stream_id)
        if stream is None:
            return []
        # The previous last segment stops being final: an answer that continues did not end.
        if stream.segments:
            last = stream.segments[-1]
            stream.segments[-1] = SpeechSegment(**{**last.__dict__, "final": False})
        fresh = build_segments(
            response_id=stream.response_id,
            speech_stream_id=stream.speech_stream_id,
            text=text,
            interruptible=interruptible,
            first_index=len(stream.segments),
        )
        stream.segments.extend(fresh)
        return fresh

    def report_cursors(
        self,
        speech_stream_id: str,
        *,
        last_received_segment: int,
        last_spoken_segment: int,
    ) -> None:
        """What the device says it got and what it says the owner heard.

        Cursors only ever move forward. A device reporting a lower one has restarted its
        queue, and honouring that would resend audio the owner has already heard — the
        exact §21.16 failure, arriving from the other direction.
        """
        stream = self._streams.get(speech_stream_id)
        if stream is None:
            return
        stream.last_received_segment = max(stream.last_received_segment, last_received_segment)
        stream.last_spoken_segment = max(stream.last_spoken_segment, last_spoken_segment)

    def resume_from(self, speech_stream_id: str) -> list[SpeechSegment]:
        """§21.16 — everything after what the owner heard.

        Not after what arrived. The overlap is intentional and is de-duplicated on the
        device by `segment_id`.
        """
        stream = self._streams.get(speech_stream_id)
        if stream is None:
            return []
        return [s for s in stream.segments if s.segment_index > stream.last_spoken_segment]

    def interrupt(self, speech_stream_id: str) -> None:
        """§21.21 — the owner spoke. The Gateway records it and stops serving more.

        The audio has already stopped on the phone; this is the semantic half arriving
        afterwards, which is the correct order and the reason barge-in does not wait for a
        network round trip.
        """
        stream = self._streams.get(speech_stream_id)
        if stream is not None:
            stream.interrupted = True

    def response_state(self, device_id: str) -> dict | None:
        """§20.11 — what goes into a resume, so the device is told what the Gateway holds.

        Returns the most recent unfinished stream for this device, or None. "Unfinished"
        is judged by what the owner heard: a stream whose final segment was delivered but
        never spoken is unfinished, and is exactly the case a resume exists to repair.
        """
        candidates = [
            s for s in self._streams.values()
            if s.device_id == device_id and not s.complete and not s.interrupted
        ]
        if not candidates:
            return None
        stream = max(candidates, key=lambda s: s.created_at_ms)
        return {
            "response_id": stream.response_id,
            "speech_stream_id": stream.speech_stream_id,
            "turn_id": stream.turn_id,
            "last_received_segment": max(stream.last_received_segment, 0),
            "last_spoken_segment": max(stream.last_spoken_segment, 0),
            "resume_from_segment": stream.last_spoken_segment + 1,
            "total_segments": len(stream.segments),
            "segments": [s.as_json() for s in self.resume_from(stream.speech_stream_id)],
        }

    def sweep(self, *, now_ms: int | None = None) -> int:
        """Drop streams older than the retention window. Returns how many went."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        stale = [
            sid for sid, s in self._streams.items()
            if now - s.created_at_ms > STREAM_RETENTION_MS
        ]
        for sid in stale:
            response_id = self._streams[sid].response_id
            del self._streams[sid]
            self._by_response.pop(response_id, None)
        return len(stale)

    def get(self, speech_stream_id: str) -> SpeechStream | None:
        return self._streams.get(speech_stream_id)
