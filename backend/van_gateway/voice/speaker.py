"""Speaker evidence policy at the authoritative command boundary.

Speaker similarity is provenance evidence, not authentication. The paired device signature
proves which device sent the command; biometric owner approval remains the only owner-presence
gate for consequential actions. Speaker evidence can tighten that gate but can never loosen it.
"""

from __future__ import annotations

from enum import Enum

from van_gateway.models import ActionClass


class SpeakerEvidence(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    MISMATCH = "MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"
    MATCH = "MATCH"


class SpeakerDisposition(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_OWNER_APPROVAL = "REQUIRE_OWNER_APPROVAL"
    REFUSE = "REFUSE"


MATCH_THRESHOLD_MILLI = 720
MISMATCH_THRESHOLD_MILLI = 350


def classify_speaker_evidence(score_milli: int | None) -> SpeakerEvidence:
    if score_milli is None:
        return SpeakerEvidence.UNAVAILABLE
    if score_milli >= MATCH_THRESHOLD_MILLI:
        return SpeakerEvidence.MATCH
    if score_milli <= MISMATCH_THRESHOLD_MILLI:
        return SpeakerEvidence.MISMATCH
    return SpeakerEvidence.INCONCLUSIVE


def speaker_disposition(
    action_class: ActionClass,
    evidence: SpeakerEvidence,
) -> SpeakerDisposition:
    """Return the extra voice gate after deterministic action resolution.

    A1/A2 never gain privilege from a speaker score and remain usable without enrollment.
    A3 may proceed on a positive similarity signal, but uncertainty requires the same exact
    owner-presence proof used by A4. A mismatch refuses A3/A4 instead of presenting an
    approval prompt to whoever may currently be holding the phone. A4 always still requires
    biometric approval even on MATCH.
    """
    if action_class in (ActionClass.A1, ActionClass.A2):
        return SpeakerDisposition.ALLOW
    if action_class is ActionClass.A5:
        return SpeakerDisposition.REFUSE
    if evidence is SpeakerEvidence.MISMATCH:
        return SpeakerDisposition.REFUSE
    if action_class is ActionClass.A4:
        return SpeakerDisposition.REQUIRE_OWNER_APPROVAL
    if evidence is SpeakerEvidence.MATCH:
        return SpeakerDisposition.ALLOW
    return SpeakerDisposition.REQUIRE_OWNER_APPROVAL


__all__ = [
    "MATCH_THRESHOLD_MILLI",
    "MISMATCH_THRESHOLD_MILLI",
    "SpeakerDisposition",
    "SpeakerEvidence",
    "classify_speaker_evidence",
    "speaker_disposition",
]
