package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * P2-SEC-010 — any voice reaching the microphone produced a transcript signed as an owner
 * command.
 *
 * The device's HMAC proves *this device* sent it. Nothing anywhere proved the person who
 * spoke was the owner, so a visitor, a television or a recording played near the phone had
 * the owner's authority for as long as they were in the room.
 *
 * The obvious fix is wrong and these tests hold the line on why: speaker similarity is a
 * likelihood, not an authentication factor, so it decides how much authority a spoken
 * command carries rather than whether it is heard at all.
 */
class SpeakerVerificationTest {

    @Test
    fun `a read is unaffected by who is speaking`() {
        // Gating these would make VAN useless to talk to, and getting one wrong costs the
        // owner nothing they cannot undo.
        for (evidence in SpeakerEvidence.entries) {
            for (actionClass in listOf("A1", "A2")) {
                assertEquals(
                    VoiceAuthorityDecision.ALLOW,
                    SpeakerVerificationPolicy.decide(actionClass, evidence).decision,
                    "$actionClass with $evidence",
                )
            }
        }
    }

    @Test
    fun `a voice unlike the owner's cannot change anything outside VAN`() {
        val verdict = SpeakerVerificationPolicy.decide("A3", SpeakerEvidence.MISMATCH)
        assertEquals(VoiceAuthorityDecision.REFUSE, verdict.decision)
        // Refused rather than escalated: offering an approval prompt to a voice that is
        // unlike the owner's puts the decision in front of whoever is holding the phone.
        assertTrue(verdict.reason.contains("did not sound like you"))
    }

    @Test
    fun `an uncertain voice asks the owner rather than guessing either way`() {
        for (evidence in listOf(SpeakerEvidence.INCONCLUSIVE, SpeakerEvidence.UNAVAILABLE)) {
            assertEquals(
                VoiceAuthorityDecision.REQUIRE_OWNER_APPROVAL,
                SpeakerVerificationPolicy.decide("A3", evidence).decision,
                evidence.name,
            )
        }
    }

    @Test
    fun `an owner with no voice profile is not locked out of their own assistant`() {
        // UNAVAILABLE is not a refusal. It is the state of every owner who has not enrolled
        // a voice, and refusing them would be a security control that removes the product.
        val verdict = SpeakerVerificationPolicy.decide("A4", SpeakerEvidence.UNAVAILABLE)
        assertEquals(VoiceAuthorityDecision.REQUIRE_OWNER_APPROVAL, verdict.decision)
        assertTrue(verdict.reason.contains("cannot tell voices apart"))
    }

    @Test
    fun `a recognised voice acts normally`() {
        assertEquals(
            VoiceAuthorityDecision.ALLOW,
            SpeakerVerificationPolicy.decide("A3", SpeakerEvidence.MATCH).decision,
        )
    }

    @Test
    fun `scores classify at the stated thresholds`() {
        assertEquals(SpeakerEvidence.UNAVAILABLE, SpeakerVerificationPolicy.classify(null))
        assertEquals(SpeakerEvidence.MISMATCH, SpeakerVerificationPolicy.classify(0.0f))
        assertEquals(
            SpeakerEvidence.MISMATCH,
            SpeakerVerificationPolicy.classify(SpeakerVerificationPolicy.MISMATCH_THRESHOLD),
        )
        assertEquals(SpeakerEvidence.INCONCLUSIVE, SpeakerVerificationPolicy.classify(0.5f))
        assertEquals(
            SpeakerEvidence.MATCH,
            SpeakerVerificationPolicy.classify(SpeakerVerificationPolicy.MATCH_THRESHOLD),
        )
        assertEquals(SpeakerEvidence.MATCH, SpeakerVerificationPolicy.classify(1.0f))
    }

    @Test
    fun `every verdict says something a person would say`() {
        for (evidence in SpeakerEvidence.entries) {
            for (actionClass in listOf("A1", "A2", "A3", "A4")) {
                val verdict = SpeakerVerificationPolicy.decide(actionClass, evidence)
                assertTrue(verdict.reason.isNotBlank())
                assertTrue(
                    evidence.name !in verdict.reason,
                    "$evidence leaks its enum name: ${verdict.reason}",
                )
                assertTrue(verdict.reason.first().isUpperCase(), verdict.reason)
            }
        }
    }

    @Test
    fun `an unrecognised action class is gated, not waved through`() {
        // A class this build does not know about is not one of the two it knows are safe.
        assertEquals(
            VoiceAuthorityDecision.REQUIRE_OWNER_APPROVAL,
            SpeakerVerificationPolicy.decide("A9", SpeakerEvidence.UNAVAILABLE).decision,
        )
        assertEquals(
            VoiceAuthorityDecision.REFUSE,
            SpeakerVerificationPolicy.decide("", SpeakerEvidence.MISMATCH).decision,
        )
    }

    @Test
    fun `the action class is matched regardless of how it was written`() {
        assertEquals(
            VoiceAuthorityDecision.ALLOW,
            SpeakerVerificationPolicy.decide(" a1 ", SpeakerEvidence.MISMATCH).decision,
        )
    }
}
