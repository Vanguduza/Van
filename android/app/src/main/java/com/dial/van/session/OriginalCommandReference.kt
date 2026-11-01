package com.dial.van.session

import org.json.JSONObject

/** Exact stored evidence for read-only recovery, never a rebuilt execution request. */
object OriginalCommandReference {
    fun fromStored(entry: OutboxEntry, envelope: JSONObject, profileId: String, deviceId: String): JSONObject? {
        if (entry.profileId != profileId || entry.messageId != envelope.optString("message_id") ||
            entry.idempotencyKey != envelope.optString("idempotency_key") ||
            envelope.optString("device_id") != deviceId || envelope.optString("kind") != "command.submit") return null
        val body = envelope.optJSONObject("payload") ?: return null
        if (body.optString("device_id") != deviceId || body.optString("command_id") != entry.commandId ||
            body.optString("idempotency_key").isBlank() || body.optString("signature").isBlank() ||
            !body.has("issued_at_unix") || !body.has("text")) return null
        val sessionId = envelope.optString("van_session_id")
        if (sessionId.isBlank()) return null
        return JSONObject()
            .put("van_session_id", sessionId).put("message_id", entry.messageId)
            .put("idempotency_key", entry.idempotencyKey).put("command_id", entry.commandId)
            .put("device_id", deviceId).put("profile_id", profileId)
            .put("command_request", JSONObject(body.toString()))
    }
    /** An authenticated read transfers result ownership; it never grants execution. */
    fun verifiedResult(entry: OutboxEntry, envelope: JSONObject, profile: String, device: String,
                       receipt: JSONObject?): JSONObject? {
        val expected = fromStored(entry, envelope, profile, device) ?: return null
        val observed = receipt ?: return null
        val reference = observed.optJSONObject("reference") ?: return null
        for (key in listOf("van_session_id", "message_id", "idempotency_key", "command_id", "device_id", "profile_id"))
            if (reference.optString(key) != expected.optString(key)) return null
        if (!Regex("[a-f0-9]{64}").matches(observed.optString("request_hash"))) return null
        val result = observed.optJSONObject("result") ?: return null
        val body = expected.getJSONObject("command_request")
        if (result.optString("command_id") != entry.commandId ||
            result.optString("idempotency_key") != body.optString("idempotency_key")) return null
        val mission = result.optString("mission_id").takeUnless { it.isBlank() || it == "null" }
        when (observed.optString("history_owner")) {
            "command_mission" -> {
                val owner = observed.optJSONObject("owner_result") ?: return null
                if (mission == null || owner.optString("mission_id") != mission ||
                    owner.optString("command_id") != entry.commandId) return null
                val correlation = result.optString("correlation_id").takeUnless { it.isBlank() || it == "null" }
                if (correlation != null && owner.optString("correlation_id") != correlation) return null
            }
            "idempotency_refusal" -> if (mission != null || result.optString("status") !in
                setOf("denied", "expired", "rejected_untrusted", "conflict")) return null
            else -> return null
        }
        return observed
    }

}
