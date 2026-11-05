package com.dial.van.visual

import org.json.JSONObject
import java.security.MessageDigest

/** Optional metadata can enable extra poses only for the EXACT loaded Rive bytes. */
object VanRiveContextCapabilities {
    const val ASSET_FILE = "van.context.json"
    const val CANDIDATE_ASSET_FILE = "van_candidate.context.json"
    private const val SCHEMA = "van.character.context/1"

    fun resolve(assetBytes: ByteArray, metadata: String?): Set<Int> {
        if (metadata == null || metadata.length > 16_384) return emptySet()
        return runCatching {
            val root = JSONObject(metadata)
            if (root.optString("schema") != SCHEMA) return emptySet()
            val digest = MessageDigest.getInstance("SHA-256").digest(assetBytes)
                .joinToString("") { "%02x".format(it) }
            if (root.optString("asset_sha256") != digest) return emptySet()
            val records = root.optJSONArray("gestures") ?: return emptySet()
            if (records.length() != VanContextGesture.entries.size) return emptySet()
            val codes = LinkedHashSet<Int>()
            for (i in 0 until records.length()) {
                val row = records.getJSONObject(i)
                val gesture = VanContextGesture.fromCode(exactInt(row, "code")) ?: return emptySet()
                if (row.getString("name") != gesture.name ||
                    exactInt(row, "duration_ms").toLong() != gesture.durationMs ||
                    exactInt(row, "legacy_action") != gesture.legacyAction.code ||
                    !codes.add(gesture.code)) return emptySet()
            }
            codes
        }.getOrDefault(emptySet())
    }

    private fun exactInt(row: JSONObject, name: String): Int {
        val value = row.get(name)
        require(value is Number && value.toDouble().isFinite() && value.toInt().toDouble() == value.toDouble())
        return value.toInt()
    }

    /** Debug inspection must not address unadvertised states in an older asset. */
    fun candidateActions(supported: Set<Int>): List<Int> = (0..14).toList() +
        VanContextGesture.entries.map { it.code }.filter { it in supported }

    fun candidateAction(requested: Int, supported: Set<Int>): Int =
        requested.takeIf { it in candidateActions(supported) } ?: 0

    fun actionCode(legacyCode: Int, contextCode: Int, supported: Set<Int>): Int {
        val context = VanContextGesture.fromCode(contextCode)
        return if (context != null && context.code in supported && context.legacyAction.code == legacyCode) context.code else legacyCode
    }
}
