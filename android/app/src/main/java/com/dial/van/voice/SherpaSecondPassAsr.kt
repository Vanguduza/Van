package com.dial.van.voice

import android.content.Context
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineTransducerModelConfig
import com.k2fsa.sherpa.onnx.getFeatureConfig
import org.json.JSONObject
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest

/**
 * Real local second-pass ASR over a checksum-pinned sherpa-onnx transducer bundle.
 *
 * The model is a deployment artefact under app-private storage, not an APK asset. Absence
 * therefore means "second pass unavailable" rather than silently falling back to a network
 * recognizer. Android on-device ASR remains the first pass.
 */
class SherpaLocalSecondPassAsr private constructor(
    private val recognizer: OfflineRecognizer,
    private val sampleRateHz: Int,
) : LocalSecondPassAsr {

    override fun isReady(): Boolean = true

    @Synchronized
    override fun transcribe(pcm16: ByteArray, biasingStrings: List<String>): LocalAsrResult {
        if (pcm16.size < 2) return LocalAsrResult("", 0f)
        val stream = recognizer.createStream()
        return try {
            stream.acceptWaveform(pcm16ToFloat(pcm16), sampleRateHz)
            recognizer.decode(stream)
            val result = recognizer.getResult(stream)
            val text = result.text.trim()
            LocalAsrResult(
                text = text,
                // The current sherpa Kotlin OfflineRecognizer result exposes text/tokens/
                // timestamps but no calibrated utterance probability. Claiming 0.95 here
                // would let a made-up confidence override a strong Android result.
                confidence = if (text.isBlank()) 0f else CONSERVATIVE_CONFIDENCE,
                alternatives = emptyList(),
            )
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
        const val MANIFEST_PATH = "voice/asr_second_pass.json"
        private const val SCHEMA_VERSION = 1
        private const val RUNTIME_VERSION = "1.13.8"
        private const val CONSERVATIVE_CONFIDENCE = 0.74f
        private const val MAX_MANIFEST_BYTES = 256L * 1024L
        private val SHA256 = Regex("^[0-9a-fA-F]{64}$")

        fun fromFiles(context: Context): SherpaLocalSecondPassAsr? {
            val root = File(context.applicationContext.filesDir, "voice").canonicalFile
            val manifest = File(context.applicationContext.filesDir, MANIFEST_PATH)
            if (!manifest.isFile || manifest.length() !in 1..MAX_MANIFEST_BYTES) return null

            val json = runCatching { JSONObject(manifest.readText(Charsets.UTF_8)) }.getOrNull()
                ?: return null
            if (json.optInt("schema_version", -1) != SCHEMA_VERSION) return null
            if (json.optString("runtime") != "sherpa-onnx") return null
            if (json.optString("runtime_version") != RUNTIME_VERSION) return null
            if (json.optString("model_type") != "transducer") return null

            val sampleRate = json.optInt("sample_rate_hz", VoiceAudioArbiter.SAMPLE_RATE_HZ)
            if (sampleRate != VoiceAudioArbiter.SAMPLE_RATE_HZ) return null
            val featureDim = json.optInt("feature_dim", 80)
            if (featureDim !in 20..160) return null
            val numThreads = json.optInt("num_threads", 2)
            if (numThreads !in 1..4) return null
            val maxActivePaths = json.optInt("max_active_paths", 4)
            if (maxActivePaths !in 1..8) return null

            val files = json.optJSONObject("files") ?: return null
            fun admitted(name: String, suffix: String): File? {
                val entry = files.optJSONObject(name) ?: return null
                val relative = entry.optString("path").trim()
                val expected = entry.optString("sha256").trim()
                if (relative.isEmpty() || File(relative).isAbsolute || !relative.endsWith(suffix)) return null
                if (!SHA256.matches(expected)) return null
                val file = File(root, relative).canonicalFile
                val prefix = root.path.trimEnd(File.separatorChar) + File.separator
                if (!file.path.startsWith(prefix) || !file.isFile || file.length() <= 0L) return null
                if (!sha256(file).equals(expected, ignoreCase = true)) return null
                return file
            }

            val encoder = admitted("encoder", ".onnx") ?: return null
            val decoder = admitted("decoder", ".onnx") ?: return null
            val joiner = admitted("joiner", ".onnx") ?: return null
            val tokens = admitted("tokens", ".txt") ?: return null

            val config = OfflineRecognizerConfig(
                featConfig = getFeatureConfig(sampleRate = sampleRate, featureDim = featureDim),
                modelConfig = OfflineModelConfig(
                    transducer = OfflineTransducerModelConfig(
                        encoder = encoder.absolutePath,
                        decoder = decoder.absolutePath,
                        joiner = joiner.absolutePath,
                    ),
                    tokens = tokens.absolutePath,
                    numThreads = numThreads,
                    debug = false,
                    provider = "cpu",
                    modelType = "transducer",
                ),
                decodingMethod = "greedy_search",
                maxActivePaths = maxActivePaths,
            )
            return runCatching {
                SherpaLocalSecondPassAsr(
                    recognizer = OfflineRecognizer(config = config),
                    sampleRateHz = sampleRate,
                )
            }.getOrNull()
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
