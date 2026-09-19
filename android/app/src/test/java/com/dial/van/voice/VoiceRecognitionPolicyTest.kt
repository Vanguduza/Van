package com.dial.van.voice

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
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
    fun modernDeviceWithoutOnDeviceRecognizerIsUnavailableNotSherpaRequired() {
        // P1-VOICE-003 — this asserted SHERPA_PRIMARY_REQUIRED, which told an owner whose
        // speech service is disabled that they need a runtime VAN deliberately does not
        // ship (owner decision 2). That is an answer they can do nothing with. The
        // designed sub-31 Sherpa tier and a supported device missing its recognizer are
        // different situations, and only the second is something the owner can fix.
        val decision = VoiceRecognitionPolicy.decide(apiLevel = 36, onDeviceAvailable = false)
        assertEquals(VoiceRecognitionBackend.UNAVAILABLE, decision.backend)
        assertNotNull(decision.unavailableReason)
        assertTrue(decision.unavailableReason!!.contains("recognizer"))
    }

    @Test
    fun supportingAnApiLevelIsNotAClaimThatVoiceWorks() {
        // minSdk 31 makes a recognizer possible; only the runtime probe says whether one
        // is installed. Asserted here as well as in the verification harness because this
        // is the module that ships.
        assertEquals(
            VoiceRecognitionBackend.ANDROID_ON_DEVICE_CALLER_AUDIO,
            VoiceRecognitionPolicy.decide(apiLevel = 33, onDeviceAvailable = true).backend,
        )
        assertEquals(
            VoiceRecognitionBackend.UNAVAILABLE,
            VoiceRecognitionPolicy.decide(apiLevel = 33, onDeviceAvailable = false).backend,
        )
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
