package com.dial.van.voice

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

enum class WakeDecision {
    REJECT,
    UNCERTAIN,
    ACCEPT,
}

data class WakeEvidence(
    val vadActive: Boolean,
    val kwsScore: Float,
    val phraseScore: Float,
    val speakerScore: Float?,
    val decision: WakeDecision,
)

data class WakeThresholds(
    val vadRms: Float = 0.012f,
    val kwsCandidate: Float = 0.58f,
    val kwsStrong: Float = 0.82f,
    val phraseAccept: Float = 0.72f,
    val phraseStrong: Float = 0.88f,
    val speakerSupport: Float = 0.70f,
)

fun interface WakeWordEngine {
    /** Returns a normalized 0..1 score for the configured wake phrase. */
    fun score(pcm16: ByteArray): Float
}

fun interface WakePhraseVerifier {
    /** Independent local phrase verification score, normalized 0..1. */
    fun verify(pcm16: ByteArray): Float
}

fun interface SpeakerSimilarityScorer {
    /** Confidence-only signal. It is never authentication or an absolute reject gate. */
    fun similarity(pcm16: ByteArray): Float
}

class EnergyVadGate(private val threshold: Float = WakeThresholds().vadRms) {
    fun isSpeech(pcm16: ByteArray): Boolean {
        if (pcm16.size < 2) return false
        val samples = pcm16.size / 2
        val buffer = ByteBuffer.wrap(pcm16, 0, samples * 2).order(ByteOrder.LITTLE_ENDIAN)
        var sumSquares = 0.0
        repeat(samples) {
            val normalized = buffer.short.toDouble() / Short.MAX_VALUE.toDouble()
            sumSquares += normalized * normalized
        }
        val rms = sqrt(sumSquares / samples).toFloat()
        return rms >= threshold
    }
}

/** Pure two-stage wake policy. No network, owner authority, or action execution lives here. */
class WakeDecisionEngine(private val thresholds: WakeThresholds = WakeThresholds()) {
    fun decide(vadActive: Boolean, kwsScore: Float, phraseScore: Float, speakerScore: Float?): WakeDecision {
        if (!vadActive) return WakeDecision.REJECT
        if (kwsScore < thresholds.kwsCandidate) return WakeDecision.REJECT
        if (phraseScore < thresholds.phraseAccept) return WakeDecision.REJECT

        // Strong phrase evidence is sufficient. Speaker similarity may support but never veto it.
        if (kwsScore >= thresholds.kwsStrong && phraseScore >= thresholds.phraseStrong) {
            return WakeDecision.ACCEPT
        }
        if (speakerScore != null && speakerScore >= thresholds.speakerSupport) {
            return WakeDecision.ACCEPT
        }
        return WakeDecision.UNCERTAIN
    }
}

class WakePipeline(
    private val kws: WakeWordEngine,
    private val verifier: WakePhraseVerifier,
    private val speaker: SpeakerSimilarityScorer? = null,
    private val vad: EnergyVadGate = EnergyVadGate(),
    private val decisionEngine: WakeDecisionEngine = WakeDecisionEngine(),
    private val speechHangoverFrames: Int = 6,
) {
    private var remainingSpeechHangover = 0

    @Synchronized
    fun evaluate(pcm16: ByteArray): WakeEvidence {
        val speechNow = vad.isSpeech(pcm16)
        if (speechNow) {
            remainingSpeechHangover = speechHangoverFrames
        } else if (remainingSpeechHangover > 0) {
            remainingSpeechHangover--
        } else {
            // Do not spend KWS compute on indefinite room silence. Once speech begins,
            // however, trailing silence must still reach sherpa: KWS may need those blank
            // frames before it emits the keyword.
            return WakeEvidence(false, 0f, 0f, null, WakeDecision.REJECT)
        }

        // Both native streams see the same admitted PCM history. Calling the verifier only
        // after the first detector fired left its stream with no phrase history, making a
        // two-stage detector structurally incapable of agreeing on the same utterance.
        val kwsScore = kws.score(pcm16).coerceIn(0f, 1f)
        val phraseScore = verifier.verify(pcm16).coerceIn(0f, 1f)
        val speechWindowActive = speechNow || remainingSpeechHangover > 0
        val speakerScore = if (kwsScore > 0f || phraseScore > 0f) {
            speaker?.similarity(pcm16)?.coerceIn(0f, 1f)
        } else {
            null
        }
        return WakeEvidence(
            vadActive = speechWindowActive,
            kwsScore = kwsScore,
            phraseScore = phraseScore,
            speakerScore = speakerScore,
            decision = decisionEngine.decide(
                speechWindowActive, kwsScore, phraseScore, speakerScore,
            ),
        )
    }
}

/**
 * Continuously feeds the wake pipeline from VoiceAudioArbiter. The arbiter remains the only
 * VAN AudioRecord owner. A concrete local KWS implementation is injected at construction.
 */
class WakeRuntimeController(
    private val arbiter: VoiceAudioArbiter,
    private val pipeline: WakePipeline,
    private val onAccepted: (WakeEvidence) -> Unit,
    private val onUncertain: (WakeEvidence) -> Unit = {},
) {
    private val armed = AtomicBoolean(false)
    private val sink: (ByteArray) -> Unit = { frame ->
        if (armed.get()) {
            val evidence = pipeline.evaluate(frame)
            when (evidence.decision) {
                WakeDecision.ACCEPT -> if (armed.compareAndSet(true, false)) onAccepted(evidence)
                WakeDecision.UNCERTAIN -> onUncertain(evidence)
                WakeDecision.REJECT -> Unit
            }
        }
    }

    fun arm(): Boolean {
        if (armed.get()) return true
        if (!arbiter.start()) return false
        arbiter.registerSink(sink)
        armed.set(true)
        return true
    }

    fun disarm(stopCapture: Boolean = false) {
        armed.set(false)
        arbiter.unregisterSink(sink)
        if (stopCapture) arbiter.stopCapture(clearPreRoll = false)
    }

    fun isArmed(): Boolean = armed.get()
}
