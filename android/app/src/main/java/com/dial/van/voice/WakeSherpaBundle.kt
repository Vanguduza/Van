package com.dial.van.voice

import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

class WakeBundleInvalid(message: String) : IllegalArgumentException(message)
class WakeBundleDigestMismatch(message: String) : IllegalArgumentException(message)

/**
 * Checksum-pinned deployment bundle for the local sherpa-onnx keyword spotter.
 *
 * The executable runtime is part of the APK; the acoustic model is an independently
 * replaceable artefact. Every file the native runtime can open is named and hashed by the
 * manifest, and every path is confined below app-private voice storage.
 */
data class WakeSherpaBundle(
    val voiceRoot: File,
    val manifestFile: File,
    val manifestSha256: String,
    val encoder: File,
    val decoder: File,
    val joiner: File,
    val tokens: File,
    val keywords: File,
    val totalModelBytes: Long,
    val sampleRateHz: Int,
    val featureDim: Int,
    val modelType: String,
    val numThreads: Int,
    val maxActivePaths: Int,
    val keywordsScore: Float,
    val candidateThreshold: Float,
    val verificationThreshold: Float,
    val numTrailingBlanks: Int,
) {
    companion object {
        const val SCHEMA_VERSION = 1
        const val RUNTIME = "sherpa-onnx"
        const val RUNTIME_VERSION = "1.13.8"
        const val KEYWORD_IDENTITY = "@HEY_VAN"
        private const val MAX_MANIFEST_BYTES = 256L * 1024L
        private const val MAX_TEXT_ASSET_BYTES = 2L * 1024L * 1024L
        private val SHA256 = Regex("^[0-9a-fA-F]{64}$")

        fun load(
            voiceRoot: File,
            manifestFile: File,
            expectedManifestSha256: String? = null,
        ): WakeSherpaBundle {
            if (!manifestFile.isFile) throw WakeBundleInvalid("wake_manifest_missing")
            if (manifestFile.length() !in 1..MAX_MANIFEST_BYTES) {
                throw WakeBundleInvalid("wake_manifest_size_invalid")
            }

            val manifestSha = sha256(manifestFile)
            if (
                expectedManifestSha256 != null &&
                !expectedManifestSha256.equals(manifestSha, ignoreCase = true)
            ) {
                throw WakeBundleDigestMismatch("wake_manifest_digest_mismatch")
            }

            val json = runCatching { JSONObject(manifestFile.readText(Charsets.UTF_8)) }
                .getOrElse { throw WakeBundleInvalid("wake_manifest_json_invalid") }
            if (json.optInt("schema_version", -1) != SCHEMA_VERSION) {
                throw WakeBundleInvalid("wake_manifest_schema_unsupported")
            }
            if (json.optString("runtime") != RUNTIME) {
                throw WakeBundleInvalid("wake_runtime_not_sherpa")
            }
            if (json.optString("runtime_version") != RUNTIME_VERSION) {
                throw WakeBundleInvalid("wake_runtime_version_mismatch")
            }
            if (json.optString("phrase") != WakeModelPolicy.PHRASE) {
                throw WakeBundleInvalid("wake_phrase_mismatch")
            }

            val sampleRate = json.optInt("sample_rate_hz", VoiceAudioArbiter.SAMPLE_RATE_HZ)
            if (sampleRate != VoiceAudioArbiter.SAMPLE_RATE_HZ) {
                throw WakeBundleInvalid("wake_sample_rate_unsupported")
            }
            val featureDim = json.optInt("feature_dim", 80)
            if (featureDim !in 20..160) throw WakeBundleInvalid("wake_feature_dim_invalid")
            val modelType = json.optString("model_type", "zipformer2").trim()
            if (modelType.isEmpty() || modelType.length > 64) {
                throw WakeBundleInvalid("wake_model_type_invalid")
            }
            val numThreads = json.optInt("num_threads", 2)
            if (numThreads !in 1..4) throw WakeBundleInvalid("wake_num_threads_invalid")
            val maxActivePaths = json.optInt("max_active_paths", 4)
            if (maxActivePaths !in 1..8) throw WakeBundleInvalid("wake_max_active_paths_invalid")
            val keywordsScore = json.optDouble("keywords_score", 1.5).toFloat()
            val candidateThreshold = json.optDouble("candidate_threshold", 0.25).toFloat()
            val verificationThreshold = json.optDouble("verification_threshold", 0.45).toFloat()
            if (keywordsScore !in 0.1f..10f) throw WakeBundleInvalid("wake_keywords_score_invalid")
            if (candidateThreshold !in 0.05f..0.95f) {
                throw WakeBundleInvalid("wake_candidate_threshold_invalid")
            }
            if (verificationThreshold !in candidateThreshold..0.99f) {
                throw WakeBundleInvalid("wake_verification_threshold_invalid")
            }
            val trailing = json.optInt("num_trailing_blanks", 2)
            if (trailing !in 0..8) throw WakeBundleInvalid("wake_trailing_blanks_invalid")

            val files = json.optJSONObject("files")
                ?: throw WakeBundleInvalid("wake_files_missing")
            val root = voiceRoot.canonicalFile

            fun admitted(logical: String, suffix: String): File {
                val entry = files.optJSONObject(logical)
                    ?: throw WakeBundleInvalid("wake_file_missing:$logical")
                val relative = entry.optString("path").trim()
                val digest = entry.optString("sha256").trim()
                if (relative.isEmpty() || File(relative).isAbsolute || !relative.endsWith(suffix)) {
                    throw WakeBundleInvalid("wake_file_path_invalid:$logical")
                }
                if (!SHA256.matches(digest)) {
                    throw WakeBundleInvalid("wake_file_digest_invalid:$logical")
                }
                val file = File(root, relative).canonicalFile
                val rootPrefix = root.path.trimEnd(File.separatorChar) + File.separator
                if (!file.path.startsWith(rootPrefix) || !file.isFile || file.length() <= 0L) {
                    throw WakeBundleInvalid("wake_file_unavailable:$logical")
                }
                if (!sha256(file).equals(digest, ignoreCase = true)) {
                    throw WakeBundleDigestMismatch("wake_file_digest_mismatch:$logical")
                }
                return file
            }

            val encoder = admitted("encoder", ".onnx")
            val decoder = admitted("decoder", ".onnx")
            val joiner = admitted("joiner", ".onnx")
            val tokens = admitted("tokens", ".txt")
            val keywords = admitted("keywords", ".txt")
            if (tokens.length() > MAX_TEXT_ASSET_BYTES || keywords.length() > MAX_TEXT_ASSET_BYTES) {
                throw WakeBundleInvalid("wake_text_asset_too_large")
            }

            // The KWS decoder may accept several phrases in one file. VAN intentionally
            // does not: the authority-sensitive foreground service listens for exactly one
            // product name, and a model update cannot silently add another trigger.
            val keywordLines = keywords.readLines(Charsets.UTF_8)
                .map { it.trim() }
                .filter { it.isNotEmpty() }
            if (keywordLines.size != 1) {
                throw WakeBundleInvalid("wake_keywords_not_exactly_one_phrase")
            }
            val keywordLine = keywordLines.single()
            // sherpa KWS permits per-keyword :boost and #threshold suffixes. English BPE
            // files may omit the @ORIGINAL_PHRASE marker entirely, so the signed manifest
            // is the canonical human-readable identity. If a marker is present, however,
            // it must agree with that identity rather than silently naming a second phrase.
            val originalMarker = keywordLine
                .split(Regex("\\s+"))
                .firstOrNull { it.startsWith("@") }
            if (originalMarker != null && originalMarker != KEYWORD_IDENTITY) {
                throw WakeBundleInvalid("wake_keyword_identity_mismatch")
            }

            val total = listOf(encoder, decoder, joiner, tokens, keywords).sumOf { it.length() }
            if (total !in WakeModelPolicy.MIN_MODEL_BYTES..WakeModelPolicy.MAX_MODEL_BYTES) {
                throw WakeBundleInvalid("wake_bundle_size_invalid")
            }

            return WakeSherpaBundle(
                voiceRoot = root,
                manifestFile = manifestFile.canonicalFile,
                manifestSha256 = manifestSha,
                encoder = encoder,
                decoder = decoder,
                joiner = joiner,
                tokens = tokens,
                keywords = keywords,
                totalModelBytes = total,
                sampleRateHz = sampleRate,
                featureDim = featureDim,
                modelType = modelType,
                numThreads = numThreads,
                maxActivePaths = maxActivePaths,
                keywordsScore = keywordsScore,
                candidateThreshold = candidateThreshold,
                verificationThreshold = verificationThreshold,
                numTrailingBlanks = trailing,
            )
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
