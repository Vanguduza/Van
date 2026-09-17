package com.dial.van.voice

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceRecognitionPolicyTest {
    @Test
    fun api30IsDesignedSherpaPrimaryNotAndroidDegraded() {
        val decision = VoiceRecognitionPolicy.decide(apiLevel = 30, onDeviceAvailable = false)
        assertEquals(VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED, decision.backend)
        assertFalse(decision.onDeviceRecognizerRequired)
        assertFalse(decision.requiresArbiterYield)
    }

    @Test
    fun api31OnDeviceSerializesMicrophoneOwnership() {
        val decision = VoiceRecognitionPolicy.decide(apiLevel = 31, onDeviceAvailable = true)
        assertEquals(VoiceRecognitionBackend.ANDROID_ON_DEVICE_DIRECT_MIC, decision.backend)
        assertFalse(decision.callerAudioSupported)
        assertTrue(decision.requiresArbiterYield)
    }

    @Test
    fun api33UsesCallerFedAudio() {
        val decision = VoiceRecognitionPolicy.decide(apiLevel = 33, onDeviceAvailable = true)
        assertEquals(VoiceRecognitionBackend.ANDROID_ON_DEVICE_CALLER_AUDIO, decision.backend)
        assertTrue(decision.callerAudioSupported)
        assertFalse(decision.wordEvidenceSupported)
        assertFalse(decision.requiresArbiterYield)
    }

    @Test
    fun api34AddsWordEvidence() {
        val decision = VoiceRecognitionPolicy.decide(apiLevel = 34, onDeviceAvailable = true)
        assertEquals(VoiceRecognitionBackend.ANDROID_ON_DEVICE_CALLER_AUDIO, decision.backend)
        assertTrue(decision.callerAudioSupported)
        assertTrue(decision.wordEvidenceSupported)
    }

    @Test
    fun modernDeviceWithoutOnDeviceRecognizerRequiresLocalFallback() {
        val decision = VoiceRecognitionPolicy.decide(apiLevel = 36, onDeviceAvailable = false)
        assertEquals(VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED, decision.backend)
    }

    @Test
    fun rollingBufferReturnsNewestBytesInChronologicalOrder() {
        val ring = PcmRingBuffer(5)
        ring.append(byteArrayOf(1, 2, 3))
        assertArrayEquals(byteArrayOf(1, 2, 3), ring.snapshot())

        ring.append(byteArrayOf(4, 5, 6, 7))
        assertArrayEquals(byteArrayOf(3, 4, 5, 6, 7), ring.snapshot())

        ring.clear()
        assertArrayEquals(ByteArray(0), ring.snapshot())
    }
}
