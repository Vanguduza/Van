"""Rev 1.5 §21.14 — cutting an answer into units it is safe to speak.

§21.14's rule is one line and the whole module is that line: boundaries are clauses,
sentences or short paragraphs, **never arbitrary model-token chunks**. The reason is what
happens on a failover. If a segment ends mid-sentence and the path dies, the owner has
heard half a clause, and resuming from the next segment gives them the other half with no
way to tell that is what happened. Segment at a sentence and the worst case is a pause.

There is a second reason, which is barge-in. A segment is the unit that can be interrupted,
so a segment that spans two sentences means the owner cannot cut in between them.

Nothing here decides *what* to say. §21.13 keeps the screen answer and the spoken answer
separate, and the summarising for speech is Hermes' job; this takes whatever text it is
given and finds the places it is safe to stop.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from van_gateway.voice.speech_cues import SegmentCueTiming, estimate_segment_timing

#: Long enough that VAN does not sound like it is reading a list; short enough that a drop
#: costs at most this much audio, and a barge-in lands within it.
TARGET_CHARS = 160
MAX_CHARS = 320

#: Below this a fragment is not worth its own segment and is joined to the previous one.
#: Without it, "Yes." becomes a segment and the queue fills with one-word units.
MIN_CHARS = 24

#: Sentence ends, with the abbreviations that are not sentence ends.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "no.", "vs.", "etc.", "e.g.", "i.e.",
    "fig.", "approx.", "inc.", "ltd.", "jan.", "feb.", "mar.", "apr.", "jun.", "jul.",
    "aug.", "sep.", "sept.", "oct.", "nov.", "dec.",
}

#: Clause boundaries, used only when a sentence is longer than MAX_CHARS on its own.
_CLAUSE_BREAK = re.compile(r"(?<=[;:,])\s+|\s+(?=(?:and|but|because|which|while|so that)\s)")


@dataclass(frozen=True)
class SpeechSegment:
    """One unit of speech, as it goes on the wire (§21.14)."""

    response_id: str
    speech_stream_id: str
    segment_id: str
    segment_index: int
    text: str
    final: bool
    interruptible: bool
    content_digest: str
    #: GAP-F-013 — estimated viseme cue timing for this segment's text, attached at build
    #: time so the device receives it in the same payload as the words rather than needing
    #: a second round trip. Defaulted via `field` so every existing construction site
    #: (`SpeechSegment(**{**last.__dict__, ...})` in `speech_stream.append`) keeps working
    #: without naming it explicitly.
    cue_timing: SegmentCueTiming = field(
        default_factory=lambda: SegmentCueTiming(cues=(), estimated_duration_ms=0)
    )

    def as_json(self) -> dict:
        return {
            "response_id": self.response_id,
            "speech_stream_id": self.speech_stream_id,
            "segment_id": self.segment_id,
            "segment_index": self.segment_index,
            "text": self.text,
            "final": self.final,
            "interruptible": self.interruptible,
            "content_digest": self.content_digest,
            # GAP-F-013 — the device already receives this segment's text in this same
            # payload; the cue timing rides along so lip sync does not wait on a second
            # request the Gateway would otherwise have to correlate back to this segment.
            "cue_timing": self.cue_timing.as_json(),
        }


def _split_sentences(text: str) -> list[str]:
    """Sentences, with the abbreviations that end in a full stop left alone.

    Splitting on every full stop turns "approx. 40 percent" into two segments, and the
    owner hears a pause in the middle of a number.
    """
    parts = _SENTENCE_END.split(text.strip())
    merged: list[str] = []
    for part in parts:
        if merged and merged[-1].split()[-1].lower() in _ABBREVIATIONS:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return [p for p in merged if p.strip()]


def _split_long(sentence: str) -> list[str]:
    """A sentence longer than the budget, cut at clause boundaries rather than at a width.

    This is where the "never arbitrary chunks" rule earns itself: cutting at a character
    count lands mid-word or mid-number, and a resume then repeats or drops part of one.
    """
    if len(sentence) <= MAX_CHARS:
        return [sentence]
    pieces = [p for p in _CLAUSE_BREAK.split(sentence) if p and p.strip()]
    # No early return for a sentence with no clause boundary. There was one, and a mutation
    # deleting it changed nothing: `_CLAUSE_BREAK.split` returns the whole sentence as a
    # single piece, and the loop below then emits exactly that. The behaviour it was meant
    # to guarantee — rather than cut mid-word, send one over-long segment, because a long
    # pause beats a severed word — is what the loop already does, and it is pinned by
    # `test_a_long_sentence_with_no_clause_boundary_is_not_cut_mid_word`.
    out: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip()
        if current and len(candidate) > MAX_CHARS:
            out.append(current)
            current = piece
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def segment(text: str) -> list[str]:
    """Split [text] into speakable units. Empty input gives no segments, not one empty one."""
    if not text or not text.strip():
        return []

    units: list[str] = []
    for paragraph in (p for p in text.split("\n\n") if p.strip()):
        for sentence in _split_sentences(paragraph):
            units.extend(_split_long(sentence.strip()))

    # Join anything too short to the one before it, so the queue is not full of fragments.
    packed: list[str] = []
    for unit in units:
        if packed and (len(unit) < MIN_CHARS or len(packed[-1]) < MIN_CHARS):
            joined = f"{packed[-1]} {unit}".strip()
            if len(joined) <= MAX_CHARS:
                packed[-1] = joined
                continue
        packed.append(unit)
    return packed


def build_segments(
    *,
    response_id: str,
    speech_stream_id: str,
    text: str,
    interruptible: bool = True,
    first_index: int = 0,
) -> list[SpeechSegment]:
    """Segment [text] and give each unit its identity.

    The digest is over the text alone. A resent segment must be recognisable as the same
    one, and a digest that included the index would make a renumbered stream look like
    different content.
    """
    pieces = segment(text)
    out: list[SpeechSegment] = []
    for offset, piece in enumerate(pieces):
        index = first_index + offset
        out.append(
            SpeechSegment(
                response_id=response_id,
                speech_stream_id=speech_stream_id,
                segment_id=f"{speech_stream_id}_{index:04d}",
                segment_index=index,
                text=piece,
                final=offset == len(pieces) - 1,
                interruptible=interruptible,
                content_digest=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
                cue_timing=estimate_segment_timing(piece),
            )
        )
    return out
