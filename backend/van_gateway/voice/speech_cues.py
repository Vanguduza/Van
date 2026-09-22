"""GAP-F-013 — per-segment viseme cue timing, and the clock that plays it back.

Two things live here, and they are two halves of one contract.

`estimate_segment_timing` runs on the Gateway, the moment a segment is built, and gives the
device a cue track before any audio exists: `(offset_ms, viseme, mouth_open)` triples spaced
by how long each word is expected to take to say. It is a length heuristic, not a
measurement — there is no synthesiser on this side of the wire to measure — and every
timing it produces is marked `rms_fallback=True` so a consumer never mistakes a guess for
ground truth. A device that can read RMS off the audio it is actually playing should prefer
that; `estimate_segment_timing`'s job is only to give a device that cannot do that something
better than a static mouth.

`SpeechCueClock` is the reference playback of a cue track: given `now_ms` it walks the cues
that have started, slews `mouth_open` toward the current target rather than snapping to it,
and falls back to an RMS-derived target when a phrase was started with no cues at all. It
moved here from `backend/tests/test_speech_sync.py`, where it was written, exercised and
never imported by anything that runs — a decision function with one caller, and that caller
was a test. It is production now: `speech_stream.py`'s segment cues are exactly the shape
this clock consumes, so the two are tested against each other rather than against two
separate ideas of what a cue is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Average spoken rate used to estimate cue timing from text length alone. Conversational
#: TTS commonly lands near 150 words/minute, which is roughly this many characters a second
#: including spaces and punctuation. It is a heuristic constant, not a measured one — see
#: the module docstring on `rms_fallback`.
DEFAULT_CHARS_PER_SECOND = 15.0

#: Visemes cycle through this small set rather than being classified from phonemes: nothing
#: downstream needs phoneme-accurate mouth shapes, only a mouth that looks like it is
#: forming *something* while the length-based timing says a sound is happening. 0 is the
#: closed/rest shape and is never emitted mid-word, only as the closing cue.
_VISEME_CYCLE = (1, 2, 3, 2, 4, 2)

_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class SegmentCueTiming:
    """Estimated viseme cues for one speech segment.

    `cues` is `(offset_ms, viseme, mouth_open)` triples, sorted by offset, starting at 0 and
    always ending with a `(duration_ms, 0, 0.0)` cue that closes the mouth at the segment's
    estimated end. Empty for a segment with no words to speak.
    """

    cues: tuple[tuple[int, int, float], ...]
    estimated_duration_ms: int
    #: Always True today: there is no per-phoneme timing on this side of the wire, only a
    #: length estimate. Carried explicitly rather than implied so a consumer that ignores it
    #: is a consumer that chose to trust a guess as though it were measured — see
    #: `TtsOutputManager`/cue consumption on the device, which prefers real RMS when it has
    #: audio to read it from and falls back to these cues otherwise.
    rms_fallback: bool = True

    def as_json(self) -> dict:
        return {
            "cues": [list(cue) for cue in self.cues],
            "estimated_duration_ms": self.estimated_duration_ms,
            "rms_fallback": self.rms_fallback,
        }


def estimate_segment_timing(
    text: str,
    *,
    chars_per_second: float = DEFAULT_CHARS_PER_SECOND,
) -> SegmentCueTiming:
    """Estimate cue timing for `text` from its length alone.

    One cue per word, each timed by that word's share of the segment's estimated total
    duration, with the viseme alternating so consecutive cues never repeat a shape and a
    static mouth never reads as "still speaking". A word's `mouth_open` target scales with
    its own length relative to the longest word in the segment, so a segment of short words
    does not open as wide as one with a long one.

    Empty or whitespace-only text produces no cues and a zero duration: there is nothing to
    lip-sync, and a caller should not start a phrase from this at all.
    """
    stripped = text.strip()
    if not stripped or chars_per_second <= 0:
        return SegmentCueTiming(cues=(), estimated_duration_ms=0, rms_fallback=True)

    total_ms = max(1, round(len(stripped) / chars_per_second * 1000))
    words = _WORD.findall(stripped)
    if not words:
        return SegmentCueTiming(cues=(), estimated_duration_ms=total_ms, rms_fallback=True)

    total_chars = sum(len(word) for word in words) or 1
    longest = max(len(word) for word in words)
    cues: list[tuple[int, int, float]] = []
    offset = 0.0
    for index, word in enumerate(words):
        share = len(word) / total_chars
        duration = share * total_ms
        viseme = _VISEME_CYCLE[index % len(_VISEME_CYCLE)]
        mouth_open = 0.35 + 0.5 * (len(word) / longest)
        cues.append((round(offset), viseme, round(min(1.0, mouth_open), 3)))
        offset += duration
    cues.append((total_ms, 0, 0.0))
    return SegmentCueTiming(cues=tuple(cues), estimated_duration_ms=total_ms, rms_fallback=True)


class SpeechCueClock:
    """Timestamped visemes with RMS/mouth_open fallback, bounded slew, visual lead.

    Task state is independent from TTS state — ending TTS must not imply task SUCCESS.
    """

    def __init__(self, *, visual_lead_ms: int = 40, max_slew: float = 0.25) -> None:
        self.visual_lead_ms = visual_lead_ms
        self.max_slew = max_slew
        self.mouth_open = 0.0
        self.viseme = 0
        self.speaking = False
        self.paused = False
        self._anchor_ms = 0
        self._cues: list[tuple[int, int, float]] = []

    def start_phrase(self, cues: list[tuple[int, int, float]], now_ms: int) -> None:
        self._cues = sorted(cues)
        self._anchor_ms = now_ms
        self.speaking = True
        self.paused = False

    def pause(self) -> None:
        self.paused = True

    def resume(self, now_ms: int) -> None:
        if not self.paused:
            return
        self._anchor_ms = now_ms
        self.paused = False

    def interrupt(self) -> None:
        self.speaking = False
        self.paused = False
        self.mouth_open = 0.0
        self.viseme = 0
        self._cues = []

    def tick(self, now_ms: int, *, rms: float | None = None) -> dict:
        if not self.speaking or self.paused:
            target = 0.0
            viseme = 0
        elif self._cues:
            t = now_ms - self._anchor_ms + self.visual_lead_ms
            current = self._cues[0]
            for cue in self._cues:
                if cue[0] <= t:
                    current = cue
                else:
                    break
            viseme, target = current[1], current[2]
        else:
            viseme = 0
            target = max(0.0, min(1.0, (rms or 0.0) * 1.5))

        delta = target - self.mouth_open
        if delta > self.max_slew:
            delta = self.max_slew
        elif delta < -self.max_slew:
            delta = -self.max_slew
        self.mouth_open = max(0.0, min(1.0, self.mouth_open + delta))
        self.viseme = viseme
        return {"mouth_open": self.mouth_open, "viseme": self.viseme, "speaking": self.speaking}
