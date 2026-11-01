package com.dial.van.gateway

import org.json.JSONArray
import org.json.JSONObject

interface PermissionRevocationStore {
    fun load(): String?
    fun save(value: String): Boolean
}

data class PendingPermissionRevocation(val profileId: String, val deviceId: String, val grantId: String, val requestBody: String) {
    val operationId: String get() = JSONObject(requestBody).getString("operation_id")
    val sourceDigest: String get() = JSONObject(requestBody).getString("expected_source_digest")
}

/** LAC-210 original intent and server-owned deadline survive lost replies and process death. */
class PermissionRevocationOperations(private val store: PermissionRevocationStore) {
    companion object {
        private val lock = Any()
        private val fingerprint = Regex("[0-9a-f]{64}")
        private val identity = Regex("[A-Za-z0-9][A-Za-z0-9._-]{15,127}")
        private val requestKeys = setOf("operation_id", "caller_device_id", "grant_device_id", "expected_revision", "expected_source_digest", "request_token")
    }
    private fun read(): List<PendingPermissionRevocation> {
        val raw = store.load() ?: return emptyList()
        check(raw.length <= 131072) { "permission_revocation_history_unreadable" }
        val rows = JSONArray(raw)
        check(rows.length() <= 64) { "permission_revocation_history_unreadable" }
        val result = (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index)
            check(row.keys().asSequence().toSet() == setOf("profile_id", "device_id", "grant_id", "request_body"))
            val value = PendingPermissionRevocation(row.getString("profile_id"), row.getString("device_id"), row.getString("grant_id"), row.getString("request_body"))
            val request = JSONObject(value.requestBody)
            check(value.profileId.isNotBlank() && value.deviceId.isNotBlank() && value.grantId.isNotBlank())
            check(request.keys().asSequence().toSet() == requestKeys && identity.matches(value.operationId))
            check(request.getString("caller_device_id") == value.deviceId && request.getString("request_token").length in 1..16384)
            check(fingerprint.matches(request.getString("expected_revision")) && fingerprint.matches(value.sourceDigest))
            value
        }
        check(result.map { listOf(it.profileId, it.deviceId, it.grantId, it.sourceDigest) }.toSet().size == result.size)
        check(result.map { it.operationId }.toSet().size == result.size)
        return result
    }
    private fun write(rows: List<PendingPermissionRevocation>) {
        val value = JSONArray()
        rows.forEach { value.put(JSONObject().put("profile_id", it.profileId).put("device_id", it.deviceId).put("grant_id", it.grantId).put("request_body", it.requestBody)) }
        check(value.toString().length <= 131072 && rows.size <= 64)
        check(store.save(value.toString())) { "permission_revocation_original_store_failed" }
    }
    fun pending(profileId: String, deviceId: String, grantId: String, sourceDigest: String): PendingPermissionRevocation? = synchronized(lock) {
        read().firstOrNull { it.profileId == profileId && it.deviceId == deviceId && it.grantId == grantId && it.sourceDigest == sourceDigest }
    }
    fun prepare(profileId: String, deviceId: String, grantId: String, reviewed: JSONObject): PendingPermissionRevocation = synchronized(lock) {
        require(profileId.isNotBlank() && deviceId.isNotBlank() && grantId.isNotBlank() && reviewed.getString("grant_id") == grantId)
        val source = reviewed.getString("source_digest")
        pending(profileId, deviceId, grantId, source)?.let { return@synchronized it }
        check(reviewed.getString("caller_device_id") == deviceId) { "permission_caller_changed" }
        val request = reviewed.optJSONObject("revocation_request") ?: error("permission_revocation_request_unavailable")
        check(request.keys().asSequence().toSet() == requestKeys && request.getString("caller_device_id") == deviceId)
        check(request.opt("grant_device_id") == reviewed.opt("grant_device_id"))
        check(request.getString("expected_revision") == reviewed.getString("source_revision") && request.getString("expected_source_digest") == source)
        check(identity.matches(request.getString("operation_id")) && request.getString("request_token").length in 1..16384)
        check(fingerprint.matches(request.getString("expected_revision")) && fingerprint.matches(source))
        val original = PendingPermissionRevocation(profileId, deviceId, grantId, request.toString())
        // Another UNKNOWN generation is retained; only an explicit fresh reviewed
        // selection can prepare this different generation. No old intent is retargeted.
        write(read() + original)
        original
    }
    fun observe(original: PendingPermissionRevocation, receipt: JSONObject): Boolean = synchronized(lock) {
        val current = read().firstOrNull { it.operationId == original.operationId }
        check(current == null || current == original) { "permission_revocation_original_changed" }
        val request = JSONObject(original.requestBody)
        check(receipt.getString("operation_id") == original.operationId && receipt.getString("grant_id") == original.grantId &&
            receipt.getString("caller_device_id") == original.deviceId && receipt.opt("grant_device_id") == request.opt("grant_device_id") &&
            receipt.getString("expected_revision") == request.getString("expected_revision"))
        check(receipt.opt("native_authority_issued") == false && receipt.getString("source_digest") == original.sourceDigest)
        val applied = receipt.getString("state") == "APPLIED"
        if (applied) {
            val timestamp = receipt.opt("revoked_at_ms")
            check(receipt.opt("revoked") == true && (timestamp is Int || timestamp is Long) && (timestamp as Number).toLong() > 0)
        } else {
            check(receipt.getString("state") == "REFUSED" && receipt.opt("revoked") == false && receipt.isNull("revoked_at_ms"))
            check(receipt.getString("reason_code") in setOf("permission_revocation_stale_revision", "permission_revocation_request_expired", "permission_revocation_caller_changed"))
        }
        if (current != null) write(read().filterNot { it.operationId == original.operationId })
        applied
    }
    /** Real app HTTP adapters use this same persisted exchange tested by the JVM harness. */
    fun revoke(profileId: String, deviceId: String, grantId: String, reviewed: JSONObject,
               currentProfile: () -> String, currentDevice: () -> String?, detail: () -> JSONObject,
               originalResult: (PendingPermissionRevocation) -> JSONObject?, submit: (PendingPermissionRevocation) -> Unit): JSONObject {
        fun currentOwner() = check(currentDevice() == deviceId && currentProfile() == profileId) { "permission_caller_changed" }
        currentOwner()
        val original = prepare(profileId, deviceId, grantId, reviewed)
        var observed = originalResult(original)
        if (observed == null) {
            currentOwner()
            try { submit(original) } catch (failure: Throwable) {
                observed = originalResult(original)
                if (observed == null) throw failure
            }
            if (observed == null) observed = originalResult(original)
        }
        val receipt = observed ?: error("permission_revocation_original_unavailable")
        currentOwner()
        if (receipt.optString("state") == "APPLIED") {
            val current = detail()
            check(current.getString("grant_id") == grantId && current.getLong("revoked_at_ms") == receipt.getLong("revoked_at_ms") &&
                current.getString("source_digest") == receipt.getString("source_digest") && current.getInt("effective_remaining_uses") == 0)
        }
        check(observe(original, receipt)) { receipt.optString("reason_code", "permission_revocation_refused") }
        return receipt
    }
}
