package com.dial.van.voice

enum class VoiceRecognitionBackend {
    ANDROID_ON_DEVICE_CALLER_AUDIO,
    ANDROID_ON_DEVICE_DIRECT_MIC,
    SHERPA_PRIMARY,
    FUSED_ANDROID_SHERPA,
    SHERPA_PRIMARY_REQUIRED,
    UNAVAILABLE,
}

data class VoiceRecognitionCapabilityDecision(
    val backend: VoiceRecognitionBackend,
    val callerAudioSupported: Boolean,
    val wordEvidenceSupported: Boolean,
    val onDeviceRecognizerRequired: Boolean,
    val requiresArbiterYield: Boolean,
    /**
     * Why VAN cannot hear on this device, when it cannot.
     *
     * P1-VOICE-003 — null whenever a backend exists. An API level the app supports is not
     * a promise that the device has a recognizer installed, and the owner is entitled to
     * the difference between "your Android is too old" and "your device supports this and
     * the recognizer is missing": the second is something they can fix.
     */
    val unavailableReason: String? = null,
)

/**
 * Pure capability policy for Rev 3.1. It distinguishes a designed API 26-30 sherpa-primary
 * tier from a degraded runtime state.
 *
 * P1-VOICE-003 — that sentence was already here and the code contradicted it: both cases
 * returned SHERPA_PRIMARY_REQUIRED, so a supported device with no recognizer installed was
 * reported as needing a runtime tier that the app deliberately does not ship (owner
 * decision 2). The two are now different answers, because they are different situations
 * and only one of them is the owner's to do anything about.
 *
 * The API level alone never settles this. `onDeviceAvailable` is a runtime probe of the
 * actual device, and a build that supports API 31 still has to ask.
 */
object VoiceRecognitionPolicy {
    fun decide(apiLevel: Int, onDeviceAvailable: Boolean): VoiceRecognitionCapabilityDecision = when {
        apiLevel >= 34 && onDeviceAvailable -> VoiceRecognitionCapabilityDecision(
            backend = VoiceRecognitionBackend.ANDROID_ON_DEVICE_CALLER_AUDIO,
            callerAudioSupported = true,
            wordEvidenceSupported = true,
            onDeviceRecognizerRequired = true,
            requiresArbiterYield = false,
        )
        apiLevel >= 33 && onDeviceAvailable -> VoiceRecognitionCapabilityDecision(
            backend = VoiceRecognitionBackend.ANDROID_ON_DEVICE_CALLER_AUDIO,
            callerAudioSupported = true,
            wordEvidenceSupported = false,
            onDeviceRecognizerRequired = true,
            requiresArbiterYield = false,
        )
        apiLevel >= 31 && onDeviceAvailable -> VoiceRecognitionCapabilityDecision(
            backend = VoiceRecognitionBackend.ANDROID_ON_DEVICE_DIRECT_MIC,
            callerAudioSupported = false,
            wordEvidenceSupported = false,
            onDeviceRecognizerRequired = true,
            requiresArbiterYield = true,
        )
        // The designed tier: below API 31 there is no on-device recognizer API at all, so
        // Sherpa was always the plan here. Unreachable in a shipping build, because minSdk
        // is 31 and the build guard refuses any lower floor without a Sherpa runtime.
        apiLevel <= 30 -> VoiceRecognitionCapabilityDecision(
            backend = VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED,
            callerAudioSupported = false,
            wordEvidenceSupported = false,
            onDeviceRecognizerRequired = false,
            requiresArbiterYield = false,
        )
        // The degraded runtime state: the device supports the recognizer API and does not
        // have a recognizer installed. Reporting this as SHERPA_PRIMARY_REQUIRED pointed
        // the owner at a runtime VAN does not ship and never will; UNAVAILABLE with a
        // reason points them at the thing they can actually change.
        else -> VoiceRecognitionCapabilityDecision(
            backend = VoiceRecognitionBackend.UNAVAILABLE,
            callerAudioSupported = false,
            wordEvidenceSupported = false,
            onDeviceRecognizerRequired = true,
            requiresArbiterYield = false,
            unavailableReason =
                "this device has no on-device speech recognizer installed, so VAN cannot " +
                    "listen. Installing or enabling the device's speech recognition " +
                    "service restores it.",
        )
    }
}

data class VoiceWordEvidence(
    val rawText: String,
    val formattedText: String?,
    val timestampMs: Long,
    val confidenceLevel: Int,
)

data class VoiceAlternativeSpanEvidence(
    val start: Int,
    val end: Int,
    val alternatives: List<String>,
)

data class VoiceRecognitionResult(
    val turnId: String,
    val text: String,
    val hypotheses: List<String>,
    val hypothesisConfidence: List<Float>,
    val words: List<VoiceWordEvidence>,
    val alternatives: List<VoiceAlternativeSpanEvidence>,
    val backend: VoiceRecognitionBackend,
    val callerAudioInjected: Boolean,
    val startedAtMs: Long,
    val finalizedAtMs: Long,
    val secondPassUsed: Boolean = false,
    val secondPassText: String? = null,
    val secondPassConfidence: Float? = null,
    /** Confidence-only provenance signal; never authentication. */
    val speakerSimilarity: Float? = null,
) {
    val speechEvidenceRef: String = "android://voice/$turnId"
}
