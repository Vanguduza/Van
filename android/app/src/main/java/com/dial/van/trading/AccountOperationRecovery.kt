package com.dial.van.trading

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Only original non-secret identities survive restart. No arguments, proof or key export. */
data class PendingAccountOperation(val operationId: String, val action: String, val deviceId: String, val alias: String)

interface AccountOperationStore {
    fun load(): String?
    /** True only after a durable write; failure MUST prevent dispatch. */
    fun save(value: String): Boolean
}

class AccountOperationRecovery(private val store: AccountOperationStore) {
    companion object {
        val JOURNALED_ACTIONS = setOf("account_upsert", "account_credentials", "account_remove", "mt5_ea_issue_key")
        private val idPattern = Regex("^[A-Za-z0-9_-]{20,128}$")
    }

    private fun read(): List<PendingAccountOperation> {
        val text = store.load() ?: return emptyList()
        val root = Json.parseToJsonElement(text) as? JsonObject ?: error("account_operation_history_unreadable")
        check(root.keys == setOf("schema", "operations")) { "account_operation_history_unreadable" }
        check(root.str("schema") == "van.android.account-operations/1") { "account_operation_history_unreadable" }
        val entries = root["operations"] as? JsonArray ?: error("account_operation_history_unreadable")
        val result = entries.map { entry ->
            val row = entry as? JsonObject ?: error("account_operation_history_unreadable")
            check(row.keys == setOf("operation_id", "action", "device_id", "alias"))
            PendingAccountOperation(row.str("operation_id") ?: error("missing_operation_id"),
                row.str("action") ?: error("missing_action"), row.str("device_id") ?: error("missing_device"),
                row.str("alias") ?: error("missing_alias")).also(::validate)
        }
        check(result.map { it.operationId }.toSet().size == result.size) { "duplicate_operation_identity" }
        return result
    }

    private fun validate(value: PendingAccountOperation) {
        require(idPattern.matches(value.operationId) && value.action in JOURNALED_ACTIONS && value.deviceId.isNotBlank())
        require(AccountOnboarding.validateAlias(value.alias) == null)
    }

    private fun write(entries: List<PendingAccountOperation>) {
        val text = buildJsonObject {
            put("schema", "van.android.account-operations/1")
            put("operations", JsonArray(entries.map { value -> buildJsonObject {
                put("operation_id", value.operationId); put("action", value.action)
                put("device_id", value.deviceId); put("alias", value.alias)
            } }))
        }.toString()
        check(store.save(text)) { "account_operation_identity_not_saved_no_dispatch" }
    }

    @Synchronized fun pending(deviceId: String): List<PendingAccountOperation> = read().filter { it.deviceId == deviceId }

    @Synchronized fun remember(value: PendingAccountOperation) {
        validate(value)
        val entries = read()
        val original = entries.firstOrNull { it.operationId == value.operationId }
        if (original != null) {
            check(original == value) { "account_operation_identity_conflict" }
            // Never offer a send retry for an already persisted identity.
            error("account_operation_requires_original_result_readback")
        }
        check(entries.none { it.deviceId == value.deviceId && it.alias == value.alias }) {
            "account_requires_original_operation_readback"
        }
        write(entries + value)
    }

    @Synchronized fun observe(value: PendingAccountOperation, body: String, httpCode: Int): Boolean {
        val entries = read()
        check(entries.contains(value)) { "account_operation_not_owned" }
        val result = parseObject(body) ?: return false
        if (httpCode !in 200..299 || result.str("operation_id") != value.operationId ||
            result.str("action") != value.action || result.bool("reconciliation_required") != false ||
            result.str("effect_state") !in setOf("APPLIED", "REFUSED")) return false
        write(entries.filterNot { it == value })
        return true
    }
}
