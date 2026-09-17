package com.dial.van.voice

enum class VoiceRecognitionBackend {
    ANDROID_ON_DEVICE_CALLER_AUDIO,
    ANDROID_ON_DEVICE_DIRECT_MIC,
    SHERPA_PRIMARY_REQUIRED,
    UNAVAILABLE,
}

data class VoiceRecognitionCapabilityDecision(
    val backend: VoiceRecognitionBackend,
    val callerAudioSupported: Boolean,
    val wordEvidenceSupported: Boolean,
    val onDeviceRecognizerRequired: Boolean,
    val requiresArbiterYield: Boolean,
)

/**
 * Pure capability policy for Rev 3.1. It intentionally distinguishes a designed
 * API 26-30 sherpa-primary tier from a degraded runtime state.
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
        apiLevel <= 30 -> VoiceRecognitionCapabilityDecision(
            backend = VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED,
            callerAudioSupported = false,
            wordEvidenceSupported = false,
            onDeviceRecognizerRequired = false,
            requiresArbiterYield = false,
        )
        else -> VoiceRecognitionCapabilityDecision(
            backend = VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED,
            callerAudioSupported = false,
            wordEvidenceSupported = false,
            onDeviceRecognizerRequired = false,
            requiresArbiterYield = false,
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
) {
    val speechEvidenceRef: String = "android://voice/$turnId"
}
