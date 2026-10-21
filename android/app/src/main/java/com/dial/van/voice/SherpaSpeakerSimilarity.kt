package com.dial.van.voice

import android.content.Context
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractor
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

/** Generic pinned extractor. Its existence says nothing about an owner enrollment. */
class SherpaSpeakerModel private constructor(
    private val extractor: SpeakerEmbeddingExtractor,
    val sha256: String,
    val dimension: Int,
) {
    @Synchronized fun extract(pcm16: ByteArray): FloatArray {
        require(pcm16.isNotEmpty() && pcm16.size % 2 == 0) { "speaker_pcm_invalid" }
        val stream = extractor.createStream()
        val buffer = ByteBuffer.wrap(pcm16).order(ByteOrder.LITTLE_ENDIAN)
        val samples = FloatArray(pcm16.size / 2) { buffer.short / 32768f }
        try {
            stream.acceptWaveform(samples, SpeakerEnrollmentPolicy.SAMPLE_RATE_HZ)
            stream.inputFinished()
            require(extractor.isReady(stream)) { "speaker_signal_unusable" }
            val vector = extractor.compute(stream)
            require(vector.size == dimension && vector.all { it.isFinite() }) { "speaker_tensor_invalid" }
            require(vector.sumOf { it.toDouble() * it } > 1e-12) { "speaker_tensor_empty" }
            return vector
        } finally {
            samples.fill(0f)
            stream.release()
        }
    }
    companion object {
        fun fromInstalled(): SherpaSpeakerModel? {
            val installed = VoiceAssetInstaller.installedOrNull() ?: return null
            val entry = installed.bundle.entries.firstOrNull { it.path == "speaker/model.onnx" } ?: return null
            if (entry.capability != VoiceCapability.LOCAL_SPEAKER || entry.kind != VoiceAssetKind.MODEL) return null
            val model = EmbeddedVoiceAssetInstaller.confined(installed.root, entry.path)
            return runCatching {
                val extractor = SpeakerEmbeddingExtractor(config = SpeakerEmbeddingExtractorConfig(
                    model = model.absolutePath, numThreads = 2, debug = false, provider = "cpu",
                ))
                try {
                    require(extractor.dim() == 256) { "speaker_model_dimension_invalid" }
                    SherpaSpeakerModel(extractor, entry.sha256, extractor.dim()).also { admitted ->
                        // Inference compatibility only: silence is never accepted as enrollment audio.
                        admitted.extract(ByteArray(3 * 16_000 * 2)).fill(0f)
                    }
                } catch (failure: Throwable) {
                    extractor.release()
                    throw failure
                }
            }.getOrNull()
        }
    }
}

/** Revocable evidence, never command authentication. A fresh current binding is checked per score. */
class SherpaSpeakerSimilarityScorer(
    private val model: SherpaSpeakerModel,
    referenceEmbedding: FloatArray,
    private val bindingStillCurrent: () -> Boolean,
) : SpeakerSimilarityScorer {
    private val active = AtomicBoolean(true)
    private val reference = referenceEmbedding.copyOf()
    fun revoke() { active.set(false); synchronized(reference) { reference.fill(0f) } }
    override fun similarity(pcm16: ByteArray): Float {
        if (!active.get() || pcm16.size < 16_000) return INCONCLUSIVE_SCORE
        return try {
            if (!bindingStillCurrent() || !active.get()) return INCONCLUSIVE_SCORE
            val vector = model.extract(pcm16)
            try {
                val norm = sqrt(vector.sumOf { it.toDouble() * it })
                val score = synchronized(reference) {
                    if (!active.get()) INCONCLUSIVE_SCORE
                    else vector.indices.sumOf { reference[it] * vector[it].toDouble() / norm }.toFloat().coerceIn(0f, 1f)
                }
                if (active.get()) score else INCONCLUSIVE_SCORE
            } finally { vector.fill(0f) }
        } catch (_: Exception) { INCONCLUSIVE_SCORE }
    }
    companion object {
        const val INCONCLUSIVE_SCORE = 0.5f
        /** Historical plaintext self-described embeddings are deliberately not admitted. */
        @Suppress("UNUSED_PARAMETER")
        fun fromFiles(context: Context): SherpaSpeakerSimilarityScorer? = null
    }
}
