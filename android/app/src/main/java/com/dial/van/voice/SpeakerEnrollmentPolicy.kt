package com.dial.van.voice

import com.dial.van.security.VanCanonicalJson
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt
import org.json.JSONObject

/** Exact current hardware/owner binding; none of these fields is inferred from microphone audio. */
data class SpeakerProfileBinding(
    val deviceId: String,
    val deviceFingerprint: String,
    val approvalFingerprint: String,
    val bindingId: String,
    val ownerPrincipalId: String,
) {
    fun toJson(): JSONObject = JSONObject().put("device_id", deviceId)
        .put("device_fingerprint", deviceFingerprint).put("approval_fingerprint", approvalFingerprint)
        .put("binding_id", bindingId).put("owner_principal_id", ownerPrincipalId)
}

/** Read from the local hardware-backed owner keys, never fabricated from a remote binding. */
data class SpeakerLocalIdentity(
    val deviceId: String,
    val deviceFingerprint: String,
    val approvalFingerprint: String,
)

enum class SpeakerEnrollmentOperation { ENROLL, REMOVE }
enum class SpeakerEnrollmentPhase { PREPARING, UNAVAILABLE, READY, AWAITING_CONSENT, CAPTURING, ENROLLED, FAILED }

data class SpeakerEnrollmentState(
    val phase: SpeakerEnrollmentPhase = SpeakerEnrollmentPhase.PREPARING,
    val message: String = "",
    val clipIndex: Int = 0,
    val clipCount: Int = 3,
    val progress: Float = 0f,
    val profilePresent: Boolean = false,
    val modelReady: Boolean = false,
    val profileCreatedAtMs: Long? = null,
)

data class SpeakerConsentClaims(
    val id: String,
    val nonce: String,
    val operation: SpeakerEnrollmentOperation,
    val binding: SpeakerProfileBinding,
    val modelSha256: String,
    val profileRevision: String?,
    val issuedAtMs: Long,
    val expiresAtMs: Long,
) {
    fun canonical(): String = VanCanonicalJson.render(JSONObject()
        .put("schema_version", 1).put("purpose", "van.local-speaker-profile")
        .put("id", id).put("nonce", nonce).put("operation", operation.name)
        .put("binding", binding.toJson()).put("model_sha256", modelSha256)
        .put("profile_revision", profileRevision ?: JSONObject.NULL)
        .put("issued_at_ms", issuedAtMs).put("expires_at_ms", expiresAtMs))
}

data class SpeakerClipQuality(
    val accepted: Boolean,
    val durationMs: Long,
    val rms: Double,
    val peak: Double,
    val voicedMs: Long,
    val reason: String?,
)

/**
 * Local signal usability and exact envelope policy, not speaker identification.
 * The manager separately verifies real biometric consent, one-use ownership and native capture.
 * Generic models or a passing energy check cannot manufacture owner consent or identity.
 */
object SpeakerEnrollmentPolicy {
    const val CLIP_COUNT = 3
    const val SAMPLE_RATE_HZ = 16_000
    const val MIN_CLIP_MS = 2_500L
    const val MAX_CLIP_MS = 3_500L
    const val MAX_EMBEDDING_DIMENSION = 4_096
    private const val FRAME_MS = 20
    private const val MIN_ENERGY_RMS = 0.012
    private const val MIN_VARIANCE = 0.00001
    private const val MIN_VOICED_MS = 600L
    private const val CLIPPING_AMPLITUDE = 0.98
    private const val MAX_CLIPPED_FRACTION = 0.01
    private const val MIN_PAIRWISE_COSINE = 0.70
    private const val MIN_EMBEDDING_NORM = 1e-12
    private val SHA256 = Regex("[0-9a-f]{64}")
    private val bindingKeys = setOf("device_id", "device_fingerprint", "approval_fingerprint", "binding_id", "owner_principal_id")
    private val profileKeys = setOf("schema_version", "binding", "model_sha256", "embedding", "created_at_ms",
        "clip_qualities", "consent_id", "consent_sha256")
    private val qualityKeys = setOf("duration_ms", "rms", "peak", "voiced_ms")

    private fun identifier(value: String): Boolean = value.isNotBlank() && value.length <= 256 &&
        value == value.trim() && value.all { it.code in 33..126 }

    private fun validBinding(binding: SpeakerProfileBinding): Boolean =
        identifier(binding.deviceId) && identifier(binding.bindingId) && identifier(binding.ownerPrincipalId) &&
            SHA256.matches(binding.deviceFingerprint) && SHA256.matches(binding.approvalFingerprint)

    fun parseBinding(json: JSONObject): SpeakerProfileBinding? = runCatching {
        if (json.keys().asSequence().toSet() != bindingKeys || bindingKeys.any { json.opt(it) !is String }) return null
        SpeakerProfileBinding(json.getString("device_id"), json.getString("device_fingerprint"),
            json.getString("approval_fingerprint"), json.getString("binding_id"), json.getString("owner_principal_id"))
            .takeIf(::validBinding)
    }.getOrNull()

    /** Offline erasure is bound to genuine local keys; it does not invent current remote authority. */
    fun privacyRemovalBindingMatches(storedBinding: SpeakerProfileBinding, localIdentity: SpeakerLocalIdentity): Boolean =
        validBinding(storedBinding) && identifier(localIdentity.deviceId) &&
            SHA256.matches(localIdentity.deviceFingerprint) && SHA256.matches(localIdentity.approvalFingerprint) &&
            storedBinding.deviceId == localIdentity.deviceId && storedBinding.deviceFingerprint == localIdentity.deviceFingerprint &&
            storedBinding.approvalFingerprint == localIdentity.approvalFingerprint

    fun validateConsent(
        claims: SpeakerConsentClaims,
        binding: SpeakerProfileBinding,
        modelSha256: String,
        profileRevision: String?,
        nowMs: Long,
    ): Boolean = validBinding(binding) && claims.binding == binding &&
        identifier(claims.id) && SHA256.matches(claims.nonce) && SHA256.matches(modelSha256) &&
        claims.modelSha256 == modelSha256 && claims.profileRevision == profileRevision &&
        (profileRevision == null || SHA256.matches(profileRevision)) &&
        (claims.operation != SpeakerEnrollmentOperation.REMOVE || profileRevision != null) &&
        claims.issuedAtMs > 0 && nowMs >= claims.issuedAtMs && nowMs < claims.expiresAtMs &&
        claims.expiresAtMs > claims.issuedAtMs && claims.expiresAtMs - claims.issuedAtMs <= 30_000

    /** Signed little-endian PCM16 mono at the actual capture rate; no caller-supplied quality flag. */
    fun quality(pcm16: ByteArray, sampleRateHz: Int = SAMPLE_RATE_HZ): SpeakerClipQuality {
        fun invalid(reason: String, duration: Long = 0) = SpeakerClipQuality(false, duration, 0.0, 0.0, 0, reason)
        if (sampleRateHz != SAMPLE_RATE_HZ) return invalid("unsupported_sample_rate")
        if (pcm16.size % 2 != 0) return invalid("pcm_format_invalid")
        val samples = pcm16.size / 2
        val duration = samples.toLong() * 1_000 / sampleRateHz
        // Bound the actual sample count, so rounding cannot admit an overlong clip.
        if (samples < MIN_CLIP_MS * sampleRateHz / 1_000) return invalid("clip_too_short", duration)
        if (samples > MAX_CLIP_MS * sampleRateHz / 1_000) return invalid("clip_too_long", duration)
        var sum = 0.0
        var squares = 0.0
        var peak = 0.0
        var clipped = 0
        var frameSum = 0.0
        var frameSquares = 0.0
        var frameSamples = 0
        var voicedMs = 0L
        val samplesPerFrame = sampleRateHz * FRAME_MS / 1_000
        for (index in 0 until samples) {
            val offset = index * 2
            val integer = ((pcm16[offset].toInt() and 255) or ((pcm16[offset + 1].toInt() and 255) shl 8)).toShort().toInt()
            val sample = integer / 32_768.0
            sum += sample
            squares += sample * sample
            peak = max(peak, abs(sample))
            if (abs(sample) >= CLIPPING_AMPLITUDE) clipped++
            frameSum += sample
            frameSquares += sample * sample
            frameSamples++
            if (frameSamples == samplesPerFrame) {
                val mean = frameSum / frameSamples
                // DC offsets cannot qualify as voiced energy, even when they change between frames.
                val acRms = sqrt(max(0.0, frameSquares / frameSamples - mean * mean))
                if (acRms >= MIN_ENERGY_RMS) voicedMs += FRAME_MS
                frameSum = 0.0; frameSquares = 0.0; frameSamples = 0
            }
        }
        val rms = sqrt(squares / samples)
        val mean = sum / samples
        val variance = max(0.0, squares / samples - mean * mean)
        val reason = when {
            clipped.toDouble() / samples > MAX_CLIPPED_FRACTION -> "clip_clipped"
            rms < MIN_ENERGY_RMS -> "clip_silent"
            variance < MIN_VARIANCE -> "clip_constant"
            voicedMs < MIN_VOICED_MS -> "clip_insufficient_voice"
            else -> null
        }
        return SpeakerClipQuality(reason == null, duration, rms, peak, voicedMs, reason)
    }

    /** Three consistent native observations; normalization does not establish who produced them. */
    fun aggregate(embeddings: List<FloatArray>): FloatArray {
        require(embeddings.size == CLIP_COUNT) { "speaker_clip_count_invalid" }
        val dimension = embeddings.first().size
        require(dimension in 1..MAX_EMBEDDING_DIMENSION) { "speaker_embedding_dimension_invalid" }
        val normalized = embeddings.map { vector ->
            require(vector.size == dimension && vector.all { it.isFinite() }) { "speaker_embedding_shape_invalid" }
            val norm = sqrt(vector.sumOf { it.toDouble() * it.toDouble() })
            require(norm.isFinite() && norm > MIN_EMBEDDING_NORM) { "speaker_embedding_norm_invalid" }
            DoubleArray(dimension) { vector[it] / norm }
        }
        for (left in normalized.indices) for (right in left + 1 until normalized.size) {
            val cosine = normalized[left].indices.sumOf { normalized[left][it] * normalized[right][it] }
            require(cosine >= MIN_PAIRWISE_COSINE) { "speaker_clips_inconsistent" }
        }
        val mean = DoubleArray(dimension) { index -> normalized.sumOf { it[index] } / CLIP_COUNT }
        val norm = sqrt(mean.sumOf { it * it })
        require(norm.isFinite() && norm > MIN_EMBEDDING_NORM) { "speaker_aggregate_norm_invalid" }
        return FloatArray(dimension) { (mean[it] / norm).toFloat() }
    }

    /** Structural readback for the encrypted store, with exact current device/model binding. */
    fun validateProfile(profile: JSONObject, binding: SpeakerProfileBinding, modelSha256: String, dimension: Int): Boolean = runCatching {
        if (!validBinding(binding) || !SHA256.matches(modelSha256) || dimension !in 1..MAX_EMBEDDING_DIMENSION) return false
        if (profile.keys().asSequence().toSet() != profileKeys) return false
        if (profile.opt("schema_version") != 1 || profile.opt("model_sha256") != modelSha256) return false
        val actualBinding = profile.optJSONObject("binding") ?: return false
        if (parseBinding(actualBinding) != binding) return false
        val created = profile.opt("created_at_ms")
        if (created !is Long && created !is Int) return false
        if ((created as Number).toLong() <= 0) return false
        val consentId = profile.opt("consent_id") as? String ?: return false
        val consentSha256 = profile.opt("consent_sha256") as? String ?: return false
        if (!identifier(consentId) || !SHA256.matches(consentSha256)) return false
        val qualities = profile.optJSONArray("clip_qualities") ?: return false
        if (qualities.length() != CLIP_COUNT) return false
        for (index in 0 until CLIP_COUNT) {
            val quality = qualities.optJSONObject(index) ?: return false
            if (quality.keys().asSequence().toSet() != qualityKeys) return false
            val duration = quality.opt("duration_ms")
            val voiced = quality.opt("voiced_ms")
            if ((duration !is Long && duration !is Int) || (voiced !is Long && voiced !is Int)) return false
            val durationMs = (duration as Number).toLong()
            val voicedMs = (voiced as Number).toLong()
            val rms = (quality.opt("rms") as? Number)?.toDouble() ?: return false
            val peak = (quality.opt("peak") as? Number)?.toDouble() ?: return false
            if (durationMs !in MIN_CLIP_MS..MAX_CLIP_MS || voicedMs !in MIN_VOICED_MS..durationMs || voicedMs % FRAME_MS != 0L ||
                !rms.isFinite() || !peak.isFinite() || rms < MIN_ENERGY_RMS || rms > peak || peak > 1.0) return false
        }
        val vector = profile.optJSONArray("embedding") ?: return false
        if (vector.length() != dimension) return false
        var squaredNorm = 0.0
        for (index in 0 until dimension) {
            val number = vector.opt(index) as? Number ?: return false
            val value = number.toDouble()
            if (!value.isFinite() || abs(value) > 1.001) return false
            squaredNorm += value * value
        }
        // The persisted representation is the normalized aggregate, not an arbitrary model tensor.
        squaredNorm.isFinite() && abs(sqrt(squaredNorm) - 1.0) <= 0.001
    }.getOrDefault(false)
}
