package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Rev 1.5 §§21.9, 21.10 — when a second recogniser runs, and when it is allowed to win.
 *
 * `VoiceSecondPass.kt` was written before this checkpoint and had no tests: it is pure, it
 * decides what VAN believes the owner said, and nothing executed it. That combination is
 * the shape this programme keeps finding, so the file is now in the harness and these are
 * the cases that matter.
 *
 * The rule §21.10 states and these pin: **biasing cannot rewrite the transcript merely
 * because a term is expected.** A local model that returns something different is not
 * thereby right — it has to be corroborated by what Android already heard, or be decisively
 * more confident, or be answering where Android had nothing. Anything weaker and VAN
 * confidently reports a sentence the owner did not say, which is worse than reporting one
 * it is unsure about.
 */
class VoiceSecondPassPolicyTest {

    private fun android(
        text: String,
        confidence: Float? = null,
        alternatives: List<VoiceAlternativeSpanEvidence> = emptyList(),
        hypotheses: List<String> = emptyList(),
    ) = VoiceRecognitionResult(
        turnId = "turn_1",
        text = text,
        hypotheses = hypotheses,
        hypothesisConfidence = confidence?.let { listOf(it) } ?: emptyList(),
        words = emptyList(),
        alternatives = alternatives,
        backend = VoiceRecognitionBackend.ANDROID_ON_DEVICE_DIRECT_MIC,
        callerAudioInjected = false,
        startedAtMs = 0,
        finalizedAtMs = 0,
    )

    @Test
    fun `an easy turn does not pay for a second pass`() {
        // §21.9 — "do not run an expensive second pass on every easy turn."
        val decision = VoiceSecondPassPolicy.decide(android("open the browser", confidence = 0.95f))
        assertFalse(decision.run)
        assertTrue(decision.reasons.isEmpty())
    }

    @Test
    fun `nothing heard is a reason to try again`() {
        val decision = VoiceSecondPassPolicy.decide(android(""))
        assertTrue(decision.run)
        assertTrue(SecondPassReason.NO_MATCH in decision.reasons)
    }

    @Test
    fun `low confidence is a reason`() {
        val decision = VoiceSecondPassPolicy.decide(android("something", confidence = 0.4f))
        assertTrue(SecondPassReason.LOW_HYPOTHESIS_CONFIDENCE in decision.reasons)
    }

    @Test
    fun `a correction the owner has made before is a reason`() {
        // §21.9 lists owner correction history explicitly: VAN has been told it got this
        // wrong, so it should look harder rather than repeat the mistake.
        val decision = VoiceSecondPassPolicy.decide(
            android("vecal", confidence = 0.9f), knownPersonalConfusion = true,
        )
        assertTrue(decision.run)
        assertTrue(SecondPassReason.KNOWN_PERSONAL_CONFUSION in decision.reasons)
    }

    @Test
    fun `a confidence outside the valid range is ignored rather than treated as low`() {
        // Android does not always supply one. Treating a missing value as zero would run a
        // second pass on every turn from a device that reports no confidence at all.
        val decision = VoiceSecondPassPolicy.decide(android("a clear sentence", confidence = -1f))
        assertFalse(SecondPassReason.LOW_HYPOTHESIS_CONFIDENCE in decision.reasons)
    }
}

class SpeechFusionEngineTest {

    private fun android(
        text: String,
        confidence: Float? = null,
        hypotheses: List<String> = emptyList(),
        alternatives: List<VoiceAlternativeSpanEvidence> = emptyList(),
    ) = VoiceRecognitionResult(
        turnId = "turn_1",
        text = text,
        hypotheses = hypotheses,
        hypothesisConfidence = confidence?.let { listOf(it) } ?: emptyList(),
        words = emptyList(),
        alternatives = alternatives,
        backend = VoiceRecognitionBackend.ANDROID_ON_DEVICE_DIRECT_MIC,
        callerAudioInjected = false,
        startedAtMs = 0,
        finalizedAtMs = 0,
    )

    @Test
    fun `a different local transcript does not win on its own`() {
        // §21.10's rule. The local model is not right merely because it disagrees.
        val fused = SpeechFusionEngine.fuse(
            android("send the report", confidence = 0.8f),
            LocalAsrResult(text = "send the resort", confidence = 0.7f),
        )
        assertEquals("send the report", fused.text)
        assertTrue(fused.secondPassUsed, "the attempt is still recorded as evidence")
        assertEquals("send the resort", fused.secondPassText)
    }

    @Test
    fun `a local transcript Android also heard can win`() {
        // Corroboration: it is in Android's own hypotheses, so this is choosing between
        // two things the platform already considered, not inventing a third.
        val fused = SpeechFusionEngine.fuse(
            android("open vecal", confidence = 0.55f, hypotheses = listOf("open vecal", "open VEKL")),
            LocalAsrResult(text = "open VEKL", confidence = 0.8f),
        )
        assertEquals("open VEKL", fused.text)
        assertEquals(VoiceRecognitionBackend.FUSED_ANDROID_SHERPA, fused.backend)
    }

    @Test
    fun `a decisively more confident local transcript can win`() {
        val fused = SpeechFusionEngine.fuse(
            android("open the deedee", confidence = 0.5f),
            LocalAsrResult(text = "open the DDE", confidence = 0.9f),
        )
        assertEquals("open the DDE", fused.text)
    }

    @Test
    fun `a marginally more confident local transcript does not win`() {
        // The margin exists so that two models that roughly agree do not flip the answer
        // on noise.
        val fused = SpeechFusionEngine.fuse(
            android("open the deedee", confidence = 0.80f),
            LocalAsrResult(text = "open the DDE", confidence = 0.86f),
        )
        assertEquals("open the deedee", fused.text)
    }

    @Test
    fun `a local transcript wins where Android heard nothing`() {
        val fused = SpeechFusionEngine.fuse(
            android(""),
            LocalAsrResult(text = "what is the weather", confidence = 0.85f),
        )
        assertEquals("what is the weather", fused.text)
    }

    @Test
    fun `an empty local result leaves the transcript alone`() {
        val fused = SpeechFusionEngine.fuse(
            android("send the report", confidence = 0.8f),
            LocalAsrResult(text = "   ", confidence = 0.1f),
        )
        assertEquals("send the report", fused.text)
        assertTrue(fused.secondPassUsed)
    }

    @Test
    fun `two readings that differ only in punctuation are not a disagreement`() {
        // This test found a real reporting defect. The comparison kept trailing
        // punctuation, so "Open the browser." and "open the browser" counted as
        // disagreeing: the fusion then chose on confidence and recorded the result as
        // FUSED_ANDROID_SHERPA with a second-pass transcript, when both recognisers had
        // heard the same sentence. The text was identical either way; the evidence was not.
        val fused = SpeechFusionEngine.fuse(
            android("open the browser", confidence = 0.6f),
            LocalAsrResult(text = "Open the browser.", confidence = 0.99f),
        )
        assertEquals("open the browser", fused.text)
        assertEquals(VoiceRecognitionBackend.ANDROID_ON_DEVICE_DIRECT_MIC, fused.backend)
    }

    @Test
    fun `raw alternatives survive fusion as evidence`() {
        // §21.10 — "raw alternatives and confidence remain evidence." A fusion that threw
        // them away would leave nothing to explain why VAN chose what it chose.
        val fused = SpeechFusionEngine.fuse(
            android("open vecal", confidence = 0.5f, hypotheses = listOf("open vecal", "open VEKL")),
            LocalAsrResult(text = "open VEKL", confidence = 0.9f, alternatives = listOf("open vehicle")),
        )
        assertTrue(fused.hypotheses.contains("open vecal"), "Android's reading is still there")
        assertTrue(fused.hypotheses.contains("open vehicle"), "the local alternative is too")
        assertEquals(0.9f, fused.secondPassConfidence)
    }

    @Test
    fun `a stale alternative span is ignored rather than guessed`() {
        // Android's API 34 spans are offsets into the original text. One that no longer
        // fits is not evidence, and reconstructing from it would fabricate a transcript
        // neither recogniser produced.
        val fused = SpeechFusionEngine.fuse(
            android(
                "open vecal",
                confidence = 0.5f,
                alternatives = listOf(
                    VoiceAlternativeSpanEvidence(start = 5, end = 999, alternatives = listOf("VEKL")),
                ),
            ),
            LocalAsrResult(text = "open VEKL", confidence = 0.75f),
        )
        assertEquals("open vecal", fused.text, "an out-of-range span must not corroborate")
    }

    @Test
    fun `a valid alternative span does corroborate`() {
        val fused = SpeechFusionEngine.fuse(
            android(
                "open vecal",
                confidence = 0.5f,
                alternatives = listOf(
                    VoiceAlternativeSpanEvidence(start = 5, end = 10, alternatives = listOf("VEKL")),
                ),
            ),
            LocalAsrResult(text = "open VEKL", confidence = 0.75f),
        )
        assertEquals("open VEKL", fused.text)
    }
}
