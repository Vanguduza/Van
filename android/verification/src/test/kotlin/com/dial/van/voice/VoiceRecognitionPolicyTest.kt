package com.dial.van.voice

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P1-VOICE-002 — VAN must not be installable on a device where it can never hear.
 *
 * `VoiceRecognitionPolicy` maps an API level to a recognition backend. Two of those backends
 * need a Sherpa runtime that this build does not ship. While `minSdk` was 26 the policy
 * resolved every device below 31 to one of them, so the APK installed on phones where voice
 * capture could never work, and the only signal was an error code at the moment the owner
 * first spoke. Failing honestly at runtime is not the same as being usable.
 *
 * The build guard in `app/build.gradle.kts` enforces this at assembly time. This asserts the
 * same invariant against the policy itself, so the two cannot drift apart silently.
 */
class VoiceRecognitionPolicyTest {

    private val buildFile = File("../app/build.gradle.kts")

    private val minSdk: Int
        get() = Regex("""^\s*minSdk = (\d+)""", RegexOption.MULTILINE)
            .find(buildFile.readText())?.groupValues?.get(1)?.toInt()
            ?: error("minSdk not found in app/build.gradle.kts")

    /** Backends that need a runtime this build does not contain. */
    private val needsSherpa = setOf(
        VoiceRecognitionBackend.SHERPA_PRIMARY,
        VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED,
        VoiceRecognitionBackend.FUSED_ANDROID_SHERPA,
    )

    @Test
    fun `every supported device can reach a recognition backend that exists`() {
        // The whole finding, as one assertion. A device inside the supported range that
        // resolves to a runtime this build does not ship is a device that installs VAN and
        // can never speak to it.
        for (api in minSdk..36) {
            val decision = VoiceRecognitionPolicy.decide(api, onDeviceAvailable = true)
            assertFalse(
                decision.backend in needsSherpa,
                "API $api is supported and resolves to ${decision.backend}, which needs a " +
                    "Sherpa runtime this build does not ship",
            )
        }
    }

    @Test
    fun `the supported floor is at or above the on-device recognizer floor`() {
        // createOnDeviceSpeechRecognizer arrived in API 31. Below it the policy has nothing
        // Android-native to offer, which is why minSdk was raised rather than the branch
        // deleted.
        assertTrue(minSdk >= 31, "minSdk is $minSdk; the on-device recognizer needs 31")
    }

    @Test
    fun `a device with no on-device recognizer still fails closed rather than going to the cloud`() {
        // Google's on-device recognizer can be absent on a supported API level. VAN must not
        // answer that by reaching for the cloud recognizer: owner speech is not something to
        // send away because the local path was inconvenient.
        val decision = VoiceRecognitionPolicy.decide(34, onDeviceAvailable = false)
        assertTrue(
            decision.backend in needsSherpa || decision.backend == VoiceRecognitionBackend.UNAVAILABLE,
            "expected a fail-closed backend, got ${decision.backend}",
        )
        assertFalse(decision.onDeviceRecognizerRequired && decision.backend in needsSherpa &&
            decision.callerAudioSupported)
    }

    @Test
    fun `the retained low-API branch is kept deliberately and still resolves`() {
        // Kept, not deleted: the day a Sherpa engine ships, lowering minSdk is a one-line
        // change rather than rewriting the policy. It must still be coherent.
        val decision = VoiceRecognitionPolicy.decide(29, onDeviceAvailable = false)
        assertEquals(VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED, decision.backend)
        assertFalse(decision.onDeviceRecognizerRequired)
    }

    @Test
    fun `caller audio is only claimed where the platform actually supports it`() {
        // EXTRA_SEGMENTED_SESSION and caller-supplied audio arrived in 33; claiming it below
        // that produces a recognizer that silently hears nothing.
        assertFalse(VoiceRecognitionPolicy.decide(31, true).callerAudioSupported)
        assertFalse(VoiceRecognitionPolicy.decide(32, true).callerAudioSupported)
        assertTrue(VoiceRecognitionPolicy.decide(33, true).callerAudioSupported)
        assertTrue(VoiceRecognitionPolicy.decide(34, true).callerAudioSupported)
    }

    @Test
    fun `word-level evidence is only claimed from the version that emits it`() {
        assertFalse(VoiceRecognitionPolicy.decide(33, true).wordEvidenceSupported)
        assertTrue(VoiceRecognitionPolicy.decide(34, true).wordEvidenceSupported)
    }

    @Test
    fun `the build guard is installed and depends on the assemble tasks`() {
        // A guard nothing depends on is a guard that never runs.
        val build = buildFile.readText()
        assertTrue(build.contains("assertVoiceRuntimeIsShippable"), "guard task is absent")
        assertTrue(
            build.contains("""startsWith("assemble")""") && build.contains("dependsOn(voiceRuntimeGuard)"),
            "the guard is not attached to the assemble tasks",
        )
    }
}
