package com.dial.van.gateway

import org.json.JSONArray
import org.json.JSONObject

interface GoogleWithdrawalStore {
    fun load(): String?
    fun save(value: String): Boolean
}

data class PendingGoogleWithdrawal(val profileId: String, val deviceId: String, val requestBody: String) {
    val request: JSONObject get() = JSONObject(requestBody)
    val operationId: String get() = request.getString("operation_id")
    val generation: String get() = request.getString("connection_generation")
}

/** LAC-230: original local Workspace withdrawal survives replies lost across process death. */
class GoogleWithdrawalOperations(private val store: GoogleWithdrawalStore) {
    companion object {
        private val lock = Any()
        private val keys = setOf("operation_id", "caller_device_id", "owner_id", "connection_generation", "expected_revision", "request_token")
        private val operation = Regex("workspace-withdraw-[a-f0-9]{32}")
        private val generation = Regex("([a-f0-9]{32}|legacy-[a-f0-9]{64})")
        private val revision = Regex("[a-f0-9]{64}")
    }
    private fun validate(request: JSONObject, deviceId: String) {
        check(request.keys().asSequence().toSet() == keys)
        check(operation.matches(request.getString("operation_id")) && generation.matches(request.getString("connection_generation")))
        check(revision.matches(request.getString("expected_revision")))
        check(request.getString("owner_id") == "owner" && request.getString("caller_device_id") == deviceId)
        check(request.getString("request_token").length in 1..16384)
    }
    private fun read(): List<PendingGoogleWithdrawal> {
        val raw = store.load() ?: return emptyList()
        check(raw.length <= 131072) { "Workspace recovery history could not be read." }
        val rows = JSONArray(raw)
        check(rows.length() <= 64)
        val result = (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index)
            check(row.keys().asSequence().toSet() == setOf("profile_id", "device_id", "request_body"))
            PendingGoogleWithdrawal(row.getString("profile_id"), row.getString("device_id"), row.getString("request_body")).also {
                check(it.profileId.isNotBlank() && it.deviceId.isNotBlank())
                validate(it.request, it.deviceId)
            }
        }
        check(result.map { it.operationId }.toSet().size == result.size)
        check(result.map { listOf(it.profileId, it.deviceId, it.generation) }.toSet().size == result.size)
        return result
    }
    private fun write(rows: List<PendingGoogleWithdrawal>) {
        val value = JSONArray()
        rows.forEach { value.put(JSONObject().put("profile_id", it.profileId).put("device_id", it.deviceId).put("request_body", it.requestBody)) }
        check(rows.size <= 64 && value.toString().length <= 131072)
        check(store.save(value.toString())) { "Workspace recovery request could not be saved." }
    }
    fun pending(profileId: String, deviceId: String): List<PendingGoogleWithdrawal> = synchronized(lock) {
        read().filter { it.profileId == profileId && it.deviceId == deviceId }
    }
    fun prepare(profileId: String, deviceId: String, reviewed: JSONObject): PendingGoogleWithdrawal = synchronized(lock) {
        val selected = reviewed.getString("connection_generation")
        read().firstOrNull { it.profileId == profileId && it.deviceId == deviceId && it.generation == selected }?.let { return@synchronized it }
        val request = reviewed.getJSONObject("withdrawal_request")
        validate(request, deviceId)
        check(request.getString("connection_generation") == selected && request.getString("expected_revision") == reviewed.getString("source_revision"))
        check(reviewed.getString("owner_id") == request.getString("owner_id"))
        val original = PendingGoogleWithdrawal(profileId, deviceId, request.toString())
        // Persist before POST; a new explicitly reviewed generation never clears or retargets old UNKNOWN.
        write(read() + original)
        original
    }
    private fun terminal(original: PendingGoogleWithdrawal, receipt: JSONObject, current: JSONObject?) {
        val request = original.request
        for (key in keys - "request_token") check(receipt.getString(key) == request.getString(key))
        check(receipt.getString("effect_scope") == "gateway_held_workspace_credential_only" && receipt.opt("provider_token_revoked") == false)
        check(receipt.getLong("request_deadline_ms") > 0 && receipt.getLong("completed_at_ms") > 0)
        check(receipt.opt("changed") is Boolean)
        when (receipt.getString("state")) {
            "APPLIED" -> {
                check(receipt.opt("withdrawn") == true && receipt.isNull("reason_code"))
                check(current != null && current.getString("owner_id") == request.getString("owner_id"))
                // An original withdrawal can be complete while a later explicit host reconnect is active.
                if (current.getString("connection_generation") == original.generation) check(current.opt("connected") == false)
                else check(generation.matches(current.getString("connection_generation")))
            }
            "REFUSED" -> {
                check(receipt.opt("withdrawn") == false && receipt.opt("changed") == false)
                check(receipt.getString("reason_code") in setOf("workspace_withdrawal_request_expired", "workspace_withdrawal_request_not_current", "workspace_withdrawal_stale_connection"))
            }
            else -> error("Workspace withdrawal is still unconfirmed.")
        }
    }
    private fun observe(original: PendingGoogleWithdrawal, receipt: JSONObject, current: JSONObject?) = synchronized(lock) {
        val saved = read().firstOrNull { it.operationId == original.operationId }
        check(saved == original) { "Workspace recovery request changed." }
        terminal(original, receipt, current)
        write(read().filterNot { it.operationId == original.operationId })
    }
    fun revoke(profileId: String, deviceId: String, reviewed: JSONObject,
               currentProfile: () -> String, currentDevice: () -> String?,
               originalResult: (PendingGoogleWithdrawal) -> JSONObject?,
               submit: (PendingGoogleWithdrawal) -> Unit, detail: () -> JSONObject): JSONObject {
        fun currentOwner() = check(currentProfile() == profileId && currentDevice() == deviceId) { "The active owner or connection changed. Review Workspace access again." }
        currentOwner()
        val original = prepare(profileId, deviceId, reviewed)
        var receipt = originalResult(original)
        if (receipt == null) {
            currentOwner()
            try { submit(original) } catch (failure: Throwable) {
                if (failure is java.util.concurrent.CancellationException) throw failure
                currentOwner()
                receipt = originalResult(original)
                if (receipt == null) throw failure
            }
            if (receipt == null) { currentOwner(); receipt = originalResult(original) }
        }
        val observed = receipt ?: error("Workspace withdrawal is still unconfirmed. Refresh before retrying.")
        currentOwner()
        val current = if (observed.optString("state") == "APPLIED") detail() else null
        currentOwner()
        observe(original, observed, current)
        check(observed.getString("state") == "APPLIED") { "Workspace access changed or this review expired. Review current details and confirm again." }
        return JSONObject().put("withdrawal_receipt", observed).put("current_connection", current)
    }
    /** Startup/refresh reconciliation is read-only: it never submits an unresolved operation. */
    fun recover(profileId: String, deviceId: String, currentProfile: () -> String, currentDevice: () -> String?,
                originalResult: (PendingGoogleWithdrawal) -> JSONObject?, detail: () -> JSONObject): Int {
        var recovered = 0
        pending(profileId, deviceId).forEach { original ->
            check(currentProfile() == profileId && currentDevice() == deviceId)
            val receipt = originalResult(original) ?: return@forEach
            val current = if (receipt.optString("state") == "APPLIED") detail() else null
            check(currentProfile() == profileId && currentDevice() == deviceId)
            observe(original, receipt, current)
            recovered++
        }
        return recovered
    }
}
