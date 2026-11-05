package com.dial.van.visual

import org.json.JSONObject
import java.security.MessageDigest

/** Signed build type + exact payload binding, never an artwork/owner acceptance. */
object VanCharacterReviewPolicy {
    const val APPLICATION_ID = "com.dial.van.characterreview"
    const val BUILD_TYPE = "characterReview"
    const val RIVE_FILE = "van_review.riv"
    const val CONTEXT_FILE = "van_review.context.json"
    const val MARKER_FILE = "van-character-review.json"
    const val LABEL = "Character review — not production accepted"

    fun enabled(debug: Boolean, requested: Boolean, buildType: String, applicationId: String): Boolean =
        debug && requested && buildType == BUILD_TYPE && applicationId == APPLICATION_ID

    fun validate(binary: ByteArray, context: ByteArray, marker: String,
                 debug: Boolean, requested: Boolean, buildType: String, applicationId: String,
                 expectedRequestSha: String, expectedBinarySha: String, expectedContextSha: String,
                 sourceCommit: String): Boolean {
        if (!enabled(debug, requested, buildType, applicationId) ||
            binary.size !in 1_024..VanAssetReadLimits.RIVE_BYTES || context.size !in 1..VanAssetReadLimits.CONTEXT_BYTES ||
            marker.toByteArray(Charsets.UTF_8).size !in 1..16_384) return false
        val digestPattern = Regex("[a-f0-9]{64}")
        if (listOf(expectedRequestSha, expectedBinarySha, expectedContextSha).any { !it.matches(digestPattern) } ||
            !sourceCommit.matches(Regex("[a-f0-9]{40}"))) return false
        return runCatching {
            val m = JSONObject(marker)
            if (m.getString("schema") != "van.character-review.package/1" ||
                m.get("review_only") != true || m.get("production_accepted") != false ||
                m.get("physical_accepted") != false || m.getString("admission_state") != "UNACCEPTED_CANDIDATE" ||
                m.getString("application_id") != APPLICATION_ID || m.getString("build_type") != BUILD_TYPE ||
                m.getString("source_commit") != sourceCommit || m.getString("request_sha256") != expectedRequestSha ||
                m.getString("rive_sha256") != expectedBinarySha || m.getString("context_sha256") != expectedContextSha ||
                m.getString("rive_runtime") != "9.13.10") return false
            sha(binary) == expectedBinarySha && sha(context) == expectedContextSha &&
                VanRiveContextCapabilities.resolve(binary, context.toString(Charsets.UTF_8)) == (15..26).toSet()
        }.getOrDefault(false)
    }

    private fun sha(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it) }
}
