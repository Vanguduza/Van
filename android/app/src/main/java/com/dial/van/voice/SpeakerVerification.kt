package com.dial.van.voice

/**
 * What a voice command may do, given who VAN thinks was speaking.
 *
 * P2-SEC-010. Any voice reaching the microphone produced a transcript that was signed as an
 * owner command: the device's HMAC proves *this device* sent it, and nothing anywhere
 * proved the person who spoke was the owner. A visitor, a television, or a recording played
 * near the phone had the owner's authority for as long as they were in the room.
 *
 * The obvious fix is wrong. `SpeakerSimilarityScorer` is documented in `WakeRuntime.kt` as
 * "confidence-only — never authentication or an absolute reject gate", and that is correct:
 * speaker embeddings on phone microphones are not an authentication factor, they are a
 * likelihood. Making one a hard gate would produce a VAN that ignores its owner with a cold,
 * and a VAN people learn to shout at is a VAN whose refusals mean nothing.
 *
 * So speaker evidence does not decide *whether* a command is heard. It decides **how much
 * authority a spoken command carries on its own**. Reads and drafts are unaffected, because
 * getting them wrong costs the owner nothing they cannot undo. Anything that changes the
 * world outside VAN needs either a confident speaker match or the owner's explicit approval
 * — the biometric gate that already exists and already means "the owner is here".
 *
 * Pure Kotlin. This is the decision, and it is executed in `android/verification`.
 */
enum class SpeakerEvidence {
    /** No scorer is configured — the owner has not supplied a speaker model. */
    UNAVAILABLE,

    /** A scorer ran and the voice is unlike the owner's enrolled profile. */
    MISMATCH,

    /** A scorer ran and the result is neither clearly the owner nor clearly not. */
    INCONCLUSIVE,

    /** A scorer ran and the voice matches the owner's enrolled profile. */
    MATCH,
}

/** What VAN does with a spoken command at a given action class. */
enum class VoiceAuthorityDecision {
    /** Dispatch it as an ordinary owner command. */
    ALLOW,

    /** Dispatch it, but the gateway must require the biometric owner approval first. */
    REQUIRE_OWNER_APPROVAL,

    /** Do not dispatch. The owner is told why. */
    REFUSE,
}

data class VoiceAuthorityVerdict(
    val decision: VoiceAuthorityDecision,
    val evidence: SpeakerEvidence,
    /** One sentence, in the second person, for the owner. Never an enum name. */
    val reason: String,
)

object SpeakerVerificationPolicy {

    /** Above this similarity the voice is treated as the owner's. */
    const val MATCH_THRESHOLD = 0.72f

    /** Below this it is treated as someone else's. */
    const val MISMATCH_THRESHOLD = 0.35f

    /**
     * Action classes a spoken command may carry on speaker evidence alone.
     *
     * A1 reads and A2 drafts are unaffected: getting them wrong costs the owner nothing
     * they cannot undo, and gating them would make VAN useless to talk to. A3 changes
     * something outside VAN and A4 is already the biometric class.
     */
    val UNGATED_CLASSES = setOf("A1", "A2")

    fun classify(score: Float?): SpeakerEvidence = when {
        score == null -> SpeakerEvidence.UNAVAILABLE
        score >= MATCH_THRESHOLD -> SpeakerEvidence.MATCH
        score <= MISMATCH_THRESHOLD -> SpeakerEvidence.MISMATCH
        else -> SpeakerEvidence.INCONCLUSIVE
    }

    fun decide(actionClass: String, evidence: SpeakerEvidence): VoiceAuthorityVerdict {
        val normalized = actionClass.trim().uppercase()
        if (normalized in UNGATED_CLASSES) {
            return VoiceAuthorityVerdict(
                VoiceAuthorityDecision.ALLOW, evidence,
                "Nothing here changes anything outside VAN, so I acted on what I heard.",
            )
        }
        return when (evidence) {
            SpeakerEvidence.MATCH -> VoiceAuthorityVerdict(
                VoiceAuthorityDecision.ALLOW, evidence,
                "I recognised your voice.",
            )
            SpeakerEvidence.MISMATCH -> VoiceAuthorityVerdict(
                // Refused rather than escalated: a voice that is unlike the owner's asking
                // for something consequential is the case this exists for, and offering it
                // an approval prompt puts the decision in front of whoever is holding the
                // phone.
                VoiceAuthorityDecision.REFUSE, evidence,
                "That did not sound like you, so I have not done anything. " +
                    "Ask me again from the app if it was you.",
            )
            SpeakerEvidence.INCONCLUSIVE -> VoiceAuthorityVerdict(
                VoiceAuthorityDecision.REQUIRE_OWNER_APPROVAL, evidence,
                "I could not be sure it was you, so I need your approval before I do this.",
            )
            SpeakerEvidence.UNAVAILABLE -> VoiceAuthorityVerdict(
                // Not a refusal: an owner who has not enrolled a voice profile should still
                // be able to use their own assistant. Not an allow either: nothing has
                // established who spoke.
                VoiceAuthorityDecision.REQUIRE_OWNER_APPROVAL, evidence,
                "I cannot tell voices apart yet, so I need your approval before I do this.",
            )
        }
    }

    /** Convenience for a caller that has a raw score rather than a classification. */
    fun decide(actionClass: String, score: Float?): VoiceAuthorityVerdict =
        decide(actionClass, classify(score))
}
