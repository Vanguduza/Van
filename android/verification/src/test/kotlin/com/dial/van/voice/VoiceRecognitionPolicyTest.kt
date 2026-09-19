package com.dial.van.voice

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
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
        assertFalse(decision.callerAudioSupported)
    }

    @Test
    fun `a supported device missing its recognizer is not told to install Sherpa`() {
        // P1-VOICE-003. The policy's own documentation said it distinguished the designed
        // API 26-30 Sherpa tier from a degraded runtime state, and the code returned
        // SHERPA_PRIMARY_REQUIRED for both. So a modern phone whose speech service was
        // disabled was told it needed a runtime VAN deliberately does not ship and never
        // will (owner decision 2) — an answer the owner can do nothing with.
        //
        // The API level never settles this on its own. minSdk 31 makes a recognizer
        // *possible*; only the runtime probe says whether one is there.
        for (api in 31..36) {
            val decision = VoiceRecognitionPolicy.decide(api, onDeviceAvailable = false)
            assertEquals(
                VoiceRecognitionBackend.UNAVAILABLE, decision.backend,
                "API $api with no recognizer should be UNAVAILABLE, not a Sherpa tier",
            )
            assertNotNull(
                decision.unavailableReason,
                "API $api: an unavailable voice runtime must say why",
            )
            assertTrue(
                decision.unavailableReason!!.contains("recognizer"),
                "the reason must name the thing the owner can change",
            )
        }
    }

    @Test
    fun `the unavailable reason reaches a production consumer`() {
        // P1-VOICE-003 — a field only the tests read is the defect this audit is about, and
        // adding one while closing that defect would be a poor joke. VoiceInputManager
        // needs a device to construct, so this asserts against its source that the reason
        // is surfaced rather than computed and dropped: the callback is told, and the
        // accessor exists for the surface that decides what to show.
        val voiceInterfaces = File(
            "../app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt"
        ).readText().lines().joinToString("\n") { it.substringBefore("//") }
        assertTrue(
            voiceInterfaces.contains("fun unavailableReason()"),
            "no accessor exposes the reason to an owner surface",
        )
        assertTrue(
            voiceInterfaces.contains("callback.onUnavailable(unavailableReason())"),
            "the reason is computed and never handed to the callback",
        )
        assertTrue(
            voiceInterfaces.contains("fun onUnavailable(reason: String?)"),
            "the callback has no way to receive it",
        )
    }

    @Test
    fun `a working backend never carries an unavailable reason`() {
        // The other half of the distinction. A reason attached to a working backend would
        // surface a limitation that is not there.
        for (api in 31..36) {
            val decision = VoiceRecognitionPolicy.decide(api, onDeviceAvailable = true)
            assertEquals(null, decision.unavailableReason, "API $api")
        }
    }

    @Test
    fun `supporting an API level is not a claim that voice works on the device`() {
        // The claim the raise to minSdk 31 does and does not make, stated as a test so it
        // cannot be read back as "31 means voice works".
        val supported = VoiceRecognitionPolicy.decide(33, onDeviceAvailable = true)
        val sameApiNoRecognizer = VoiceRecognitionPolicy.decide(33, onDeviceAvailable = false)
        assertTrue(supported.backend !in needsSherpa)
        assertEquals(VoiceRecognitionBackend.UNAVAILABLE, sameApiNoRecognizer.backend)
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
