package com.dial.van.trading

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

/** Only original non-secret identities survive restart. No arguments, proof or key export. */
data class AccountOperationScope(val root: String, val profileId: String, val provisioningId: String?,
                                 val nativeOwnerDomain: String? = null)
data class AccountOperationActor(val scope: AccountOperationScope, val deviceId: String, val credentialContext: String)
data class PendingAccountOperation(val operationId: String, val action: String, val deviceId: String, val alias: String,
                                   val scope: AccountOperationScope? = null, val requestIdentity: String? = null)

interface AccountOperationStore {
    fun load(): String?
    /** True only after a durable write; failure MUST prevent dispatch. */
    fun save(value: String): Boolean
}

class AccountOperationRecovery(private val store: AccountOperationStore) {
    companion object {
        val JOURNALED_ACTIONS = setOf("account_upsert", "account_credentials", "account_remove", "mt5_ea_issue_key", "deriv_create_demo")
        private val idPattern = Regex("^[A-Za-z0-9_-]{20,128}$")
    }

    private fun read(): List<PendingAccountOperation> {
        val text = store.load() ?: return emptyList()
        val root = Json.parseToJsonElement(text) as? JsonObject ?: error("account_operation_history_unreadable")
        check(root.keys == setOf("schema", "operations")) { "account_operation_history_unreadable" }
        val version = root.str("schema")
        check(version in setOf("van.android.account-operations/1", "van.android.account-operations/2")) { "account_operation_history_unreadable" }
        val entries = root["operations"] as? JsonArray ?: error("account_operation_history_unreadable")
        val result = entries.map { entry ->
            val row = entry as? JsonObject ?: error("account_operation_history_unreadable")
            val legacy = version == "van.android.account-operations/1"
            check(row.keys == if (legacy) setOf("operation_id", "action", "device_id", "alias") else
                setOf("operation_id", "action", "device_id", "alias", "scope", "request_identity"))
            val scope = if (legacy || row["scope"] == JsonNull) null else {
                val binding = row.obj("scope") ?: error("unreadable_original_scope")
                check(binding.keys == setOf("root", "profile_id", "provisioning_id", "native_owner_domain"))
                AccountOperationScope(binding.str("root") ?: error("missing_original_root"),
                    binding.str("profile_id") ?: error("missing_original_profile"), binding.str("provisioning_id"),
                    binding.str("native_owner_domain"))
            }
            PendingAccountOperation(row.str("operation_id") ?: error("missing_operation_id"),
                row.str("action") ?: error("missing_action"), row.str("device_id") ?: error("missing_device"),
                row.str("alias") ?: error("missing_alias"), scope, if (legacy) null else row.str("request_identity")).also(::validate)
        }
        check(result.indices.all { i -> result.take(i).none {
            it.operationId == result[i].operationId && samePossibleOwner(it, result[i])
        } }) { "duplicate_operation_identity" }
        return result
    }

    private fun validate(value: PendingAccountOperation) {
        require(idPattern.matches(value.operationId) && value.action in JOURNALED_ACTIONS && value.deviceId.isNotBlank())
        require(AccountOnboarding.validateAlias(value.alias) == null)
        if (value.scope == null) require(value.requestIdentity == null) else {
            require(value.scope.root.isNotBlank() && value.scope.profileId.isNotBlank())
            val uri = java.net.URI(value.scope.root)
            require(uri.scheme in setOf("https","http") && uri.host != null && uri.rawUserInfo == null &&
                uri.rawQuery == null && uri.rawFragment == null)
            require(value.scope.provisioningId == null || value.scope.provisioningId.isNotBlank())
            require(value.scope.nativeOwnerDomain == null || value.scope.nativeOwnerDomain.matches(Regex("[0-9a-f]{64}")))
            require(value.requestIdentity?.matches(Regex("[0-9a-f]{64}")) == true)
        }
    }

    private fun samePossibleOwner(left: PendingAccountOperation, right: PendingAccountOperation): Boolean {
        val a = left.scope?.nativeOwnerDomain
        val b = right.scope?.nativeOwnerDomain
        // Local profiles, URLs, devices and provisioning labels are not native
        // owner-domain proof. Current gateway contracts expose no such proof.
        return a == null || b == null || a == b
    }

    @Synchronized fun blocks(action: String, alias: String?, scope: AccountOperationScope): Boolean = read().any {
        val domain = it.scope?.nativeOwnerDomain
        (domain == null || scope.nativeOwnerDomain == null || domain == scope.nativeOwnerDomain) &&
            (it.alias == alias || action == "deriv_create_demo" && it.action == "deriv_create_demo")
    }

    private fun write(entries: List<PendingAccountOperation>) {
        val text = buildJsonObject {
            put("schema", "van.android.account-operations/2")
            put("operations", JsonArray(entries.map { value -> buildJsonObject {
                put("operation_id", value.operationId); put("action", value.action)
                put("device_id", value.deviceId); put("alias", value.alias)
                put("request_identity", value.requestIdentity?.let(::JsonPrimitive) ?: JsonNull)
                put("scope", value.scope?.let { scope -> buildJsonObject {
                    put("root", scope.root); put("profile_id", scope.profileId)
                    put("provisioning_id", scope.provisioningId?.let(::JsonPrimitive) ?: JsonNull)
                    put("native_owner_domain", scope.nativeOwnerDomain?.let(::JsonPrimitive) ?: JsonNull)
                } } ?: JsonNull)
            } }))
        }.toString()
        check(store.save(text)) { "account_operation_identity_not_saved_no_dispatch" }
    }

    @Synchronized fun pending(deviceId: String): List<PendingAccountOperation> = read().filter { it.deviceId == deviceId }

    @Synchronized fun remember(value: PendingAccountOperation) {
        validate(value)
        check(value.scope?.nativeOwnerDomain != null) { "account_operation_original_scope_unbound" }
        val entries = read()
        val original = entries.firstOrNull { it.operationId == value.operationId && samePossibleOwner(it,value) }
        if (original != null) {
            check(original == value) { "account_operation_identity_conflict" }
            // Never offer a send retry for an already persisted identity.
            error("account_operation_requires_original_result_readback")
        }
        check(entries.none { samePossibleOwner(it,value) && it.alias == value.alias }) {
            "account_requires_original_operation_readback"
        }
        check(value.action != "deriv_create_demo" || entries.none {
            samePossibleOwner(it,value) && it.action == "deriv_create_demo"
        }) { "demo_creation_requires_original_operation_readback" }
        write(entries + value)
    }

    @Synchronized fun observe(value: PendingAccountOperation, body: String, httpCode: Int,
                              currentScope: AccountOperationScope? = null): Boolean {
        val entries = read()
        check(entries.contains(value)) { "account_operation_not_owned" }
        val result = parseObject(body) ?: return false
        if (value.scope?.nativeOwnerDomain == null || value.scope != currentScope ||
            result.str("account_control_domain") != value.scope.nativeOwnerDomain) return false
        if (httpCode !in 200..299 || result.str("operation_id") != value.operationId ||
            result.str("action") != value.action || result.bool("reconciliation_required") != false ||
            result.str("effect_state") !in setOf("APPLIED", "REFUSED")) return false
        if (value.action == "deriv_create_demo" && result.str("effect_state") == "APPLIED") {
            val receipt = result.obj("result") ?: result
            val account = receipt.obj("account") ?: return false
            if (account.str("alias") != value.alias || account.str("broker") != "DERIV" ||
                account["demo"] != JsonPrimitive(true) || account.str("mode") != "DEMO_TRADER" ||
                account.str("safety_identity") != "DEMO" || account.str("login").isNullOrBlank() ||
                account.str("currency").isNullOrBlank() || receipt.str("client_id") != account.str("login") ||
                receipt.str("currency") != account.str("currency")) return false
        }
        write(entries.filterNot { it == value })
        return true
    }

    /** Actual client calls this state machine; persistence precedes any HTTP effect. */
    suspend fun dispatch(value: PendingAccountOperation, actor: AccountOperationActor,
                         current: () -> AccountOperationActor, exchange: (() -> Unit) -> Pair<Int,String>): Pair<Int,String> {
        val context = currentCoroutineContext()
        fun guard() {
            context.ensureActive()
            check(actor == current()) { "account_operation_actor_or_profile_changed" }
            check(value.scope == actor.scope && value.deviceId == actor.deviceId) { "account_operation_original_scope_changed" }
        }
        guard()
        remember(value)
        guard()
        val reply = exchange(::guard)
        guard()
        val confirmed=observe(value,reply.second,reply.first,actor.scope)
        check(confirmed || parseObject(reply.second)?.str("effect_state") !in setOf("APPLIED","REFUSED")) {
            "account_operation_original_receipt_unconfirmed"
        }
        return reply
    }

    suspend fun recover(value: PendingAccountOperation, actor: AccountOperationActor,
                        current: () -> AccountOperationActor, exchange: (() -> Unit) -> Pair<Int,String>): Pair<Int,String> {
        check(value.scope?.nativeOwnerDomain != null && value.requestIdentity != null) { "account_operation_original_scope_unbound" }
        val context = currentCoroutineContext()
        fun guard() {
            context.ensureActive()
            check(actor == current() && value.deviceId == actor.deviceId && value.scope == actor.scope) {
                "account_operation_original_profile_not_current"
            }
        }
        guard()
        val reply = exchange(::guard)
        guard()
        val confirmed=observe(value,reply.second,reply.first,actor.scope)
        check(confirmed || parseObject(reply.second)?.str("effect_state") !in setOf("APPLIED","REFUSED")) {
            "account_operation_original_receipt_unconfirmed"
        }
        return reply
    }
}
