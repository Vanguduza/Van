package com.dial.van.visual

import org.json.JSONObject
import java.security.MessageDigest

/** Optional metadata can enable extra poses only for the EXACT loaded Rive bytes. */
object VanRiveContextCapabilities {
    const val ASSET_FILE = "van.context.json"
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
                val gesture = VanContextGesture.fromCode(row.getInt("code")) ?: return emptySet()
                if (row.getString("name") != gesture.name ||
                    row.getLong("duration_ms") != gesture.durationMs ||
                    row.getInt("legacy_action") != gesture.legacyAction.code ||
                    !codes.add(gesture.code)) return emptySet()
            }
            codes
        }.getOrDefault(emptySet())
    }

    fun actionCode(legacyCode: Int, contextCode: Int, supported: Set<Int>): Int {
        val context = VanContextGesture.fromCode(contextCode)
        return if (context != null && context.code in supported && context.legacyAction.code == legacyCode) context.code else legacyCode
    }
}
