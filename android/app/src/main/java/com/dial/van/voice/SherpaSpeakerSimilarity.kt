package com.dial.van.voice

import android.content.Context
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractor
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig
import org.json.JSONObject
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import kotlin.math.sqrt

/**
 * Local speaker-similarity evidence over a provisioned owner embedding.
 *
 * This is deliberately not an authenticator. It emits a bounded similarity score that the
 * paired device signs as fixed-point provenance; the gateway interprets it only after
 * deterministic action resolution. Destructive authority still comes from the paired
 * device and biometric approval. Missing/short/unusable evidence maps to 0.5
 * (inconclusive), not to a mismatch that could lock the owner out.
 */
class SherpaSpeakerSimilarityScorer private constructor(
    private val extractor: SpeakerEmbeddingExtractor,
    referenceEmbedding: FloatArray,
    private val sampleRateHz: Int,
) : SpeakerSimilarityScorer {
    private val reference = normalized(referenceEmbedding)

    @Synchronized
    override fun similarity(pcm16: ByteArray): Float {
        if (pcm16.size < MIN_PCM_BYTES) return INCONCLUSIVE_SCORE
        val stream = runCatching { extractor.createStream() }.getOrNull()
            ?: return INCONCLUSIVE_SCORE
        return try {
            stream.acceptWaveform(pcm16ToFloat(pcm16), sampleRateHz)
            stream.inputFinished()
            if (!extractor.isReady(stream)) return INCONCLUSIVE_SCORE
            val embedding = extractor.compute(stream)
            if (embedding.isEmpty() || embedding.size != reference.size) {
                return INCONCLUSIVE_SCORE
            }
            cosine(reference, normalized(embedding)).coerceIn(0f, 1f)
        } catch (_: Throwable) {
            INCONCLUSIVE_SCORE
        } finally {
            runCatching { stream.release() }
        }
    }

    private fun pcm16ToFloat(pcm16: ByteArray): FloatArray {
        val count = pcm16.size / 2
        val buffer = ByteBuffer.wrap(pcm16, 0, count * 2).order(ByteOrder.LITTLE_ENDIAN)
        return FloatArray(count) { buffer.short.toFloat() / 32768.0f }
    }

    companion object {
        const val MANIFEST_PATH = "voice/speaker_profile.json"
        private const val SCHEMA_VERSION = 1
        private const val RUNTIME_VERSION = "1.13.8"
        private const val INCONCLUSIVE_SCORE = 0.5f
        private const val MIN_PCM_BYTES = VoiceAudioArbiter.SAMPLE_RATE_HZ *
            VoiceAudioArbiter.PCM_BYTES_PER_SAMPLE / 2 // 500 ms
        private const val MAX_MANIFEST_BYTES = 128L * 1024L
        private const val MAX_EMBEDDING_BYTES = 32L * 1024L
        private val SHA256 = Regex("^[0-9a-fA-F]{64}$")

        fun fromFiles(context: Context): SherpaSpeakerSimilarityScorer? {
            val root = File(context.applicationContext.filesDir, "voice").canonicalFile
            val manifest = File(context.applicationContext.filesDir, MANIFEST_PATH)
            if (!manifest.isFile || manifest.length() !in 1..MAX_MANIFEST_BYTES) return null
            val json = runCatching { JSONObject(manifest.readText(Charsets.UTF_8)) }.getOrNull()
                ?: return null
            if (json.optInt("schema_version", -1) != SCHEMA_VERSION) return null
            if (json.optString("runtime") != "sherpa-onnx") return null
            if (json.optString("runtime_version") != RUNTIME_VERSION) return null
            val sampleRate = json.optInt("sample_rate_hz", VoiceAudioArbiter.SAMPLE_RATE_HZ)
            if (sampleRate != VoiceAudioArbiter.SAMPLE_RATE_HZ) return null
            val numThreads = json.optInt("num_threads", 1)
            if (numThreads !in 1..4) return null

            val files = json.optJSONObject("files") ?: return null
            fun admitted(name: String, suffix: String, maxBytes: Long): File? {
                val entry = files.optJSONObject(name) ?: return null
                val relative = entry.optString("path").trim()
                val expected = entry.optString("sha256").trim()
                if (relative.isEmpty() || File(relative).isAbsolute || !relative.endsWith(suffix)) {
                    return null
                }
                if (!SHA256.matches(expected)) return null
                val file = File(root, relative).canonicalFile
                val prefix = root.path.trimEnd(File.separatorChar) + File.separator
                if (
                    !file.path.startsWith(prefix) ||
                    !file.isFile ||
                    file.length() !in 1..maxBytes
                ) {
                    return null
                }
                if (!sha256(file).equals(expected, ignoreCase = true)) return null
                return file
            }

            val model = admitted("model", ".onnx", WakeModelPolicy.MAX_MODEL_BYTES) ?: return null
            val embeddingFile = admitted("owner_embedding", ".f32", MAX_EMBEDDING_BYTES) ?: return null
            val embedding = readEmbedding(embeddingFile) ?: return null

            val config = SpeakerEmbeddingExtractorConfig(
                model = model.absolutePath,
                numThreads = numThreads,
                debug = false,
                provider = "cpu",
            )
            return runCatching {
                val extractor = SpeakerEmbeddingExtractor(config = config)
                if (extractor.dim() != embedding.size) {
                    extractor.release()
                    return null
                }
                SherpaSpeakerSimilarityScorer(extractor, embedding, sampleRate)
            }.getOrNull()
        }

        private fun readEmbedding(file: File): FloatArray? {
            val bytes = runCatching { file.readBytes() }.getOrNull() ?: return null
            if (bytes.size < 64 || bytes.size % 4 != 0) return null
            val count = bytes.size / 4
            if (count !in 16..4096) return null
            val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            val values = FloatArray(count) { buffer.float }
            if (values.any { !it.isFinite() }) return null
            val norm = sqrt(values.fold(0.0) { acc, value -> acc + value * value }).toFloat()
            return if (norm > 1e-6f) values else null
        }

        private fun normalized(values: FloatArray): FloatArray {
            val norm = sqrt(values.fold(0.0) { acc, value -> acc + value * value }).toFloat()
            if (norm <= 1e-6f) return FloatArray(values.size)
            return FloatArray(values.size) { index -> values[index] / norm }
        }

        private fun cosine(a: FloatArray, b: FloatArray): Float {
            var dot = 0.0
            for (i in a.indices) dot += a[i] * b[i]
            return dot.toFloat()
        }

        private fun sha256(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { input ->
                val buffer = ByteArray(1 shl 16)
                while (true) {
                    val read = input.read(buffer)
                    if (read <= 0) break
                    digest.update(buffer, 0, read)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }
    }
}
