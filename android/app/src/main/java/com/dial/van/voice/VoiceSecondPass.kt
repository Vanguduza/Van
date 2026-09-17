package com.dial.van.voice

import java.util.Locale

enum class SecondPassReason {
    NO_MATCH,
    LOW_HYPOTHESIS_CONFIDENCE,
    UNRESOLVED_ALTERNATIVES,
    KNOWN_PERSONAL_CONFUSION,
}

data class SecondPassDecision(
    val run: Boolean,
    val reasons: Set<SecondPassReason>,
)

data class LocalAsrResult(
    val text: String,
    val confidence: Float,
    val alternatives: List<String> = emptyList(),
)

interface LocalSecondPassAsr {
    fun isReady(): Boolean
    fun transcribe(pcm16: ByteArray, biasingStrings: List<String>): LocalAsrResult
}

object VoiceSecondPassPolicy {
    fun decide(
        android: VoiceRecognitionResult,
        knownPersonalConfusion: Boolean = false,
    ): SecondPassDecision {
        val reasons = linkedSetOf<SecondPassReason>()
        if (android.text.isBlank()) reasons += SecondPassReason.NO_MATCH
        val topConfidence = android.hypothesisConfidence.firstOrNull()
        if (topConfidence != null && topConfidence in 0f..1f && topConfidence < LOW_CONFIDENCE_THRESHOLD) {
            reasons += SecondPassReason.LOW_HYPOTHESIS_CONFIDENCE
        }
        if (android.alternatives.isNotEmpty()) reasons += SecondPassReason.UNRESOLVED_ALTERNATIVES
        if (knownPersonalConfusion) reasons += SecondPassReason.KNOWN_PERSONAL_CONFUSION
        return SecondPassDecision(run = reasons.isNotEmpty(), reasons = reasons)
    }

    private const val LOW_CONFIDENCE_THRESHOLD = 0.68f
}

/**
 * Deterministic transcript fusion. A local second pass cannot replace a plausible Android result
 * merely because its text differs. It needs a strong confidence advantage or evidence that its
 * text was already among Android's hypotheses/alternative spans.
 */
object SpeechFusionEngine {
    fun fuse(android: VoiceRecognitionResult, local: LocalAsrResult): VoiceRecognitionResult {
        val localText = local.text.trim()
        if (localText.isBlank()) {
            return android.copy(
                secondPassUsed = true,
                secondPassText = null,
                secondPassConfidence = local.confidence.coerceIn(0f, 1f),
            )
        }

        val androidText = android.text.trim()
        val androidConfidence = android.hypothesisConfidence.firstOrNull()
            ?.takeIf { it in 0f..1f }
        val localConfidence = local.confidence.coerceIn(0f, 1f)
        val normalizedLocal = normalize(localText)
        val normalizedAndroid = normalize(androidText)

        val corroboratedByAndroid = android.hypotheses.any { normalize(it) == normalizedLocal } ||
            android.alternatives.any { span -> span.alternatives.any { normalize(it) == normalizedLocal } }
        val sameTranscript = normalizedLocal.isNotBlank() && normalizedLocal == normalizedAndroid
        val androidWeak = androidText.isBlank() || (androidConfidence != null && androidConfidence <= ANDROID_WEAK_THRESHOLD)
        val decisiveLocalAdvantage = androidConfidence != null &&
            localConfidence >= LOCAL_STRONG_THRESHOLD &&
            localConfidence - androidConfidence >= MIN_CONFIDENCE_ADVANTAGE

        val chooseLocal = when {
            sameTranscript -> false
            corroboratedByAndroid && localConfidence >= CORROBORATED_LOCAL_THRESHOLD -> true
            androidWeak && localConfidence >= LOCAL_STRONG_THRESHOLD -> true
            decisiveLocalAdvantage -> true
            else -> false
        }

        return if (chooseLocal) {
            android.copy(
                text = localText,
                hypotheses = (listOf(localText) + local.alternatives + android.hypotheses).distinct(),
                backend = VoiceRecognitionBackend.FUSED_ANDROID_SHERPA,
                secondPassUsed = true,
                secondPassText = localText,
                secondPassConfidence = localConfidence,
            )
        } else {
            android.copy(
                secondPassUsed = true,
                secondPassText = localText,
                secondPassConfidence = localConfidence,
            )
        }
    }

    private fun normalize(value: String): String =
        value.trim().lowercase(Locale.ROOT).replace(WHITESPACE, " ")

    private const val ANDROID_WEAK_THRESHOLD = 0.62f
    private const val LOCAL_STRONG_THRESHOLD = 0.82f
    private const val CORROBORATED_LOCAL_THRESHOLD = 0.72f
    private const val MIN_CONFIDENCE_ADVANTAGE = 0.18f
    private val WHITESPACE = Regex("\\s+")
}

class VoiceSecondPassCoordinator(
    private val engine: LocalSecondPassAsr,
) {
    fun shouldRun(android: VoiceRecognitionResult, knownPersonalConfusion: Boolean = false): SecondPassDecision =
        if (!engine.isReady()) SecondPassDecision(false, emptySet())
        else VoiceSecondPassPolicy.decide(android, knownPersonalConfusion)

    fun resolve(
        android: VoiceRecognitionResult,
        pcm16: ByteArray,
        biasingStrings: List<String>,
        knownPersonalConfusion: Boolean = false,
    ): VoiceRecognitionResult {
        val decision = shouldRun(android, knownPersonalConfusion)
        if (!decision.run || pcm16.isEmpty()) return android
        val local = engine.transcribe(pcm16, biasingStrings)
        return SpeechFusionEngine.fuse(android, local)
    }
}
