package com.dial.van.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceSecondPassTest {
    @Test
    fun lowAndroidConfidenceTriggersSecondPass() {
        val decision = VoiceSecondPassPolicy.decide(result(text = "open vehicle", confidence = 0.41f))
        assertTrue(decision.run)
        assertTrue(SecondPassReason.LOW_HYPOTHESIS_CONFIDENCE in decision.reasons)
    }

    @Test
    fun confidentCleanResultDoesNotTriggerSecondPass() {
        val decision = VoiceSecondPassPolicy.decide(result(text = "open VEKL", confidence = 0.94f))
        assertFalse(decision.run)
    }

    @Test
    fun alternativesTriggerSecondPassEvenWithGoodTopConfidence() {
        val android = result(text = "open vehicle", confidence = 0.85f).copy(
            alternatives = listOf(
                VoiceAlternativeSpanEvidence(5, 12, listOf("VEKL", "vehicle")),
            ),
        )
        val decision = VoiceSecondPassPolicy.decide(android)
        assertTrue(decision.run)
        assertTrue(SecondPassReason.UNRESOLVED_ALTERNATIVES in decision.reasons)
    }

    @Test
    fun corroboratedLocalAlternativeMayReplaceAndroidText() {
        val android = result(text = "open vehicle", confidence = 0.66f).copy(
            alternatives = listOf(
                VoiceAlternativeSpanEvidence(5, 12, listOf("VEKL")),
            ),
        )
        val fused = SpeechFusionEngine.fuse(android, LocalAsrResult("open VEKL", 0.80f))
        assertEquals("open VEKL", fused.text)
        assertEquals(VoiceRecognitionBackend.FUSED_ANDROID_SHERPA, fused.backend)
        assertTrue(fused.secondPassUsed)
    }

    @Test
    fun differingWeakLocalTranscriptCannotOverrideStrongAndroidResult() {
        val android = result(text = "open DDE", confidence = 0.95f)
        val fused = SpeechFusionEngine.fuse(android, LocalAsrResult("open Dial", 0.71f))
        assertEquals("open DDE", fused.text)
        assertEquals(VoiceRecognitionBackend.ANDROID_ON_DEVICE_CALLER_AUDIO, fused.backend)
        assertTrue(fused.secondPassUsed)
    }

    @Test
    fun strongLocalResultCanReplaceWeakAndroidResult() {
        val android = result(text = "vehicle", confidence = 0.31f)
        val fused = SpeechFusionEngine.fuse(android, LocalAsrResult("VEKL", 0.91f))
        assertEquals("VEKL", fused.text)
        assertEquals(VoiceRecognitionBackend.FUSED_ANDROID_SHERPA, fused.backend)
    }

    private fun result(text: String, confidence: Float): VoiceRecognitionResult = VoiceRecognitionResult(
        turnId = "turn-1",
        text = text,
        hypotheses = listOf(text),
        hypothesisConfidence = listOf(confidence),
        words = emptyList(),
        alternatives = emptyList(),
        backend = VoiceRecognitionBackend.ANDROID_ON_DEVICE_CALLER_AUDIO,
        callerAudioInjected = true,
        startedAtMs = 100L,
        finalizedAtMs = 200L,
    )
}
