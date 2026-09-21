package com.dial.van.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WakeRuntimeTest {
    @Test
    fun silenceIsRejectedBeforeKws() {
        var kwsCalled = false
        val pipeline = WakePipeline(
            kws = WakeWordEngine { kwsCalled = true; 1f },
            verifier = WakePhraseVerifier { 1f },
            vad = EnergyVadGate(threshold = 0.05f),
        )
        val evidence = pipeline.evaluate(ByteArray(3200))
        assertEquals(WakeDecision.REJECT, evidence.decision)
        assertFalse(kwsCalled)
    }

    @Test
    fun strongPhraseAcceptsEvenWhenSpeakerSimilarityIsLow() {
        val pcm = loudPcm()
        val pipeline = WakePipeline(
            kws = WakeWordEngine { 0.95f },
            verifier = WakePhraseVerifier { 0.95f },
            speaker = SpeakerSimilarityScorer { 0.01f },
        )
        val evidence = pipeline.evaluate(pcm)
        assertEquals(WakeDecision.ACCEPT, evidence.decision)
        assertEquals(0.01f, evidence.speakerScore ?: -1f, 0.0001f)
    }

    @Test
    fun speakerSimilarityCanSupportBorderlineVerifiedWake() {
        val pcm = loudPcm()
        val pipeline = WakePipeline(
            kws = WakeWordEngine { 0.70f },
            verifier = WakePhraseVerifier { 0.78f },
            speaker = SpeakerSimilarityScorer { 0.88f },
        )
        assertEquals(WakeDecision.ACCEPT, pipeline.evaluate(pcm).decision)
    }

    @Test
    fun borderlineWakeWithoutSpeakerSupportIsUncertain() {
        val pcm = loudPcm()
        val pipeline = WakePipeline(
            kws = WakeWordEngine { 0.70f },
            verifier = WakePhraseVerifier { 0.78f },
            speaker = SpeakerSimilarityScorer { 0.20f },
        )
        assertEquals(WakeDecision.UNCERTAIN, pipeline.evaluate(pcm).decision)
    }

    @Test
    fun badPhraseVerifierRejectsDespiteHighKwsAndSpeaker() {
        val pcm = loudPcm()
        val pipeline = WakePipeline(
            kws = WakeWordEngine { 0.95f },
            verifier = WakePhraseVerifier { 0.50f },
            speaker = SpeakerSimilarityScorer { 0.99f },
        )
        assertEquals(WakeDecision.REJECT, pipeline.evaluate(pcm).decision)
    }

    @Test
    fun energyVadRecognizesPcmSpeechEnergy() {
        val vad = EnergyVadGate(threshold = 0.01f)
        assertTrue(vad.isSpeech(loudPcm()))
        assertFalse(vad.isSpeech(ByteArray(3200)))
    }



    @Test
    fun trailingSilenceStillFeedsBothKwsStagesAfterSpeech() {
        var kwsCalls = 0
        var verifierCalls = 0
        val pipeline = WakePipeline(
            kws = WakeWordEngine {
                kwsCalls++
                if (kwsCalls >= 2) 0.99f else 0f
            },
            verifier = WakePhraseVerifier {
                verifierCalls++
                if (verifierCalls >= 2) 0.99f else 0f
            },
            vad = EnergyVadGate(threshold = 0.01f),
        )

        assertEquals(WakeDecision.REJECT, pipeline.evaluate(loudPcm()).decision)
        val trailing = pipeline.evaluate(ByteArray(3200))
        assertEquals(WakeDecision.ACCEPT, trailing.decision)
        assertTrue(trailing.vadActive)
        assertEquals(2, kwsCalls)
        assertEquals(2, verifierCalls)
    }

    private fun loudPcm(): ByteArray {
        val result = ByteArray(3200)
        var i = 0
        while (i + 1 < result.size) {
            val sample: Short = if ((i / 2) % 2 == 0) 8000 else -8000
            result[i] = (sample.toInt() and 0xff).toByte()
            result[i + 1] = ((sample.toInt() shr 8) and 0xff).toByte()
            i += 2
        }
        return result
    }
}
