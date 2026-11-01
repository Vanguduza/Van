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
                                   val scope: AccountOperationScope? = null, val requestIdentity: String? = null,
                                   val oauthState: String? = null, val dispatchStage: String = "UNKNOWN",
                                   val oauthArguments: JsonObject? = null, val originalApprovalExpiresAt: Long? = null,
                                   val originalResourceVersion: String? = null, val originalIssuedAt: Long? = null)

interface AccountOperationStore {
    fun load(): String?
    /** True only after a durable write; failure MUST prevent dispatch. */
    fun save(value: String): Boolean
}

class AccountOperationRecovery(private val store: AccountOperationStore) {
    companion object {
        val OAUTH_LINK_ACTIONS = setOf("deriv_oauth_link", "ctrader_link")
        val JOURNALED_ACTIONS = setOf("account_upsert", "account_credentials", "account_remove", "mt5_ea_issue_key", "deriv_create_demo") + OAUTH_LINK_ACTIONS
        fun requiresOriginalReadback(action: String, args: JsonObject): Boolean =
            action in JOURNALED_ACTIONS && (action !in OAUTH_LINK_ACTIONS || args.str("state") != null)
        private val idPattern = Regex("^[A-Za-z0-9_-]{20,128}$")
        private val selectorKeys = setOf("alias", "state", "loginid", "ctid_trader_account_id", "is_live", "currency", "label")
        fun resumableSelectors(args: JsonObject): Boolean = args.keys.all { it in selectorKeys } &&
            args.values.all { it is JsonPrimitive } && args.str("state")?.matches(idPattern) == true
    }

    private fun read(): List<PendingAccountOperation> {
        val text = store.load() ?: return emptyList()
        val root = Json.parseToJsonElement(text) as? JsonObject ?: error("account_operation_history_unreadable")
        check(root.keys == setOf("schema", "operations")) { "account_operation_history_unreadable" }
        val version = root.str("schema")
        check(version in setOf("van.android.account-operations/1", "van.android.account-operations/2", "van.android.account-operations/3", "van.android.account-operations/4", "van.android.account-operations/5")) { "account_operation_history_unreadable" }
        val entries = root["operations"] as? JsonArray ?: error("account_operation_history_unreadable")
        val result = entries.map { entry ->
            val row = entry as? JsonObject ?: error("account_operation_history_unreadable")
            val legacy = version == "van.android.account-operations/1"
            check(row.keys == if (legacy) setOf("operation_id", "action", "device_id", "alias") else
                setOf("operation_id", "action", "device_id", "alias", "scope", "request_identity") +
                    (if (version in setOf("van.android.account-operations/3", "van.android.account-operations/4", "van.android.account-operations/5")) setOf("oauth_state") else emptySet()) +
                    (if (version in setOf("van.android.account-operations/4", "van.android.account-operations/5")) setOf("dispatch_stage", "oauth_arguments", "original_approval_expires_at_unix") else emptySet()) +
                    (if (version == "van.android.account-operations/5") setOf("original_resource_version", "original_issued_at_unix") else emptySet()))
            val scope = if (legacy || row["scope"] == JsonNull) null else {
                val binding = row.obj("scope") ?: error("unreadable_original_scope")
                check(binding.keys == setOf("root", "profile_id", "provisioning_id", "native_owner_domain"))
                AccountOperationScope(binding.str("root") ?: error("missing_original_root"),
                    binding.str("profile_id") ?: error("missing_original_profile"), binding.str("provisioning_id"),
                    binding.str("native_owner_domain"))
            }
            PendingAccountOperation(row.str("operation_id") ?: error("missing_operation_id"),
                row.str("action") ?: error("missing_action"), row.str("device_id") ?: error("missing_device"),
                row.str("alias") ?: error("missing_alias"), scope, if (legacy) null else row.str("request_identity"),
                row.str("oauth_state"), if (version in setOf("van.android.account-operations/4", "van.android.account-operations/5")) row.str("dispatch_stage") ?: error("missing_dispatch_stage") else "UNKNOWN",
                if (version in setOf("van.android.account-operations/4", "van.android.account-operations/5")) row.obj("oauth_arguments") else null,
                if (version in setOf("van.android.account-operations/4", "van.android.account-operations/5")) row.str("original_approval_expires_at_unix")?.toLongOrNull() else null,
                if (version == "van.android.account-operations/5") row.str("original_resource_version") else null,
                if (version == "van.android.account-operations/5") row.str("original_issued_at_unix")?.toLongOrNull() else null).also(::validate)
        }
        check(result.indices.all { i -> result.take(i).none {
            it.operationId == result[i].operationId && samePossibleOwner(it, result[i])
        } }) { "duplicate_operation_identity" }
        return result
    }

    private fun validate(value: PendingAccountOperation) {
        require(idPattern.matches(value.operationId) && value.action in JOURNALED_ACTIONS && value.deviceId.isNotBlank())
        require(AccountOnboarding.validateAlias(value.alias) == null)
        require(if (value.action in OAUTH_LINK_ACTIONS) value.oauthState?.matches(idPattern) == true else value.oauthState == null)
        require(value.dispatchStage in setOf("UNKNOWN", "PREPARED", "MAY_HAVE_SENT"))
        if (value.oauthArguments != null) {
            require(resumableSelectors(value.oauthArguments) && value.oauthArguments.str("state") == value.oauthState &&
                value.oauthArguments.str("alias")?.trim()?.lowercase() == value.alias && value.originalApprovalExpiresAt?.let { it > 0 } == true)
        }
        if (value.dispatchStage == "PREPARED") require(value.oauthState != null && value.oauthArguments != null)
        if (value.originalResourceVersion != null || value.originalIssuedAt != null)
            require(value.originalResourceVersion?.matches(Regex("[0-9a-f]{64}")) == true && value.originalIssuedAt?.let { it > 0 } == true)
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
        // Only authenticated native descriptors distinguish control domains;
        // local profiles, URLs, devices and provisioning labels do not.
        return a == null || b == null || a == b
    }

    @Synchronized fun blocks(action: String, alias: String?, scope: AccountOperationScope): Boolean = read().any {
        val domain = it.scope?.nativeOwnerDomain
        (domain == null || scope.nativeOwnerDomain == null || domain == scope.nativeOwnerDomain) &&
            (it.alias == alias || action == "deriv_create_demo" && it.action == "deriv_create_demo")
    }

    private fun write(entries: List<PendingAccountOperation>) {
        val text = buildJsonObject {
            put("schema", "van.android.account-operations/5")
            put("operations", JsonArray(entries.map { value -> buildJsonObject {
                put("operation_id", value.operationId); put("action", value.action)
                put("device_id", value.deviceId); put("alias", value.alias)
                put("request_identity", value.requestIdentity?.let(::JsonPrimitive) ?: JsonNull)
                put("oauth_state", value.oauthState?.let(::JsonPrimitive) ?: JsonNull)
                put("dispatch_stage", value.dispatchStage)
                put("oauth_arguments", value.oauthArguments ?: JsonNull)
                put("original_approval_expires_at_unix", value.originalApprovalExpiresAt?.let(::JsonPrimitive) ?: JsonNull)
                put("original_resource_version", value.originalResourceVersion?.let(::JsonPrimitive) ?: JsonNull)
                put("original_issued_at_unix", value.originalIssuedAt?.let(::JsonPrimitive) ?: JsonNull)
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

    private fun sameRecord(a: PendingAccountOperation, b: PendingAccountOperation) =
        a.copy(dispatchStage = "UNKNOWN") == b.copy(dispatchStage = "UNKNOWN")

    @Synchronized fun markPossibleSend(value: PendingAccountOperation) {
        val entries = read()
        val original = entries.singleOrNull { sameRecord(it, value) } ?: error("account_operation_not_owned")
        check(original.oauthState != null && original.dispatchStage != "MAY_HAVE_SENT") { "original_link_may_already_have_been_sent" }
        write(entries.map { if (it == original) it.copy(dispatchStage = "MAY_HAVE_SENT") else it })
    }

    @Synchronized fun canResume(value: PendingAccountOperation, currentScope: AccountOperationScope?): Boolean = read().any {
        sameRecord(it, value) && it.dispatchStage == "PREPARED" && it.oauthArguments != null &&
            it.scope?.nativeOwnerDomain != null && it.scope == currentScope &&
            it.originalResourceVersion != null && it.originalIssuedAt != null
    }

    @Synchronized fun resumeArguments(value: PendingAccountOperation, currentScope: AccountOperationScope?): JsonObject {
        check(canResume(value, currentScope)) { "original_link_has_no_proven_never_sent_state" }
        val original = read().single { sameRecord(it, value) }
        return JsonObject(original.oauthArguments!!.toMutableMap().apply {
            put("original_operation_id", JsonPrimitive(original.operationId))
            put("original_approval_expires_at_unix", JsonPrimitive(original.originalApprovalExpiresAt!!))
            put("original_resource_version", JsonPrimitive(original.originalResourceVersion!!))
            put("original_issued_at_unix", JsonPrimitive(original.originalIssuedAt!!))
            put("original_account_control_domain", JsonPrimitive(original.scope!!.nativeOwnerDomain!!))
        })
    }

    @Synchronized fun observe(value: PendingAccountOperation, body: String, httpCode: Int,
                              currentScope: AccountOperationScope? = null): Boolean {
        val entries = read()
        val original = entries.singleOrNull { sameRecord(it, value) } ?: error("account_operation_not_owned")
        val result = parseObject(body) ?: return false
        if (value.scope?.nativeOwnerDomain == null || value.scope != currentScope ||
            result.str("account_control_domain") != value.scope.nativeOwnerDomain) return false
        if (httpCode !in 200..299 || result.str("operation_id") != value.operationId ||
            result.str("action") != value.action || result.bool("reconciliation_required") != false ||
            result.str("effect_state") !in setOf("APPLIED", "REFUSED")) return false
        if (value.oauthState != null) {
            if (result.str("oauth_state") != value.oauthState || result.str("device_id") != value.deviceId ||
                result.str("native_resource_version")?.matches(Regex("[0-9a-f]{64}")) != true) return false
            if (result.str("effect_state") == "APPLIED") {
                val account = (result.obj("result") ?: result).obj("account") ?: return false
                if (account.str("alias") != value.alias || account.str("broker") !=
                    if (value.action == "deriv_oauth_link") "DERIV" else "CTRADER") return false
            }
        }
        if (value.action == "deriv_create_demo" && result.str("effect_state") == "APPLIED") {
            val receipt = result.obj("result") ?: result
            val account = receipt.obj("account") ?: return false
            if (account.str("alias") != value.alias || account.str("broker") != "DERIV" ||
                account["demo"] != JsonPrimitive(true) || account.str("mode") != "DEMO_TRADER" ||
                account.str("safety_identity") != "DEMO" || account.str("login").isNullOrBlank() ||
                account.str("currency").isNullOrBlank() || receipt.str("client_id") != account.str("login") ||
                receipt.str("currency") != account.str("currency")) return false
        }
        write(entries.filterNot { it == original })
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
        if (value.oauthState != null && !confirmed) {
            val body = parseObject(reply.second)
            val prepared = reply.first in 200..299 && body != null && body.bool("ready") == true &&
                body.str("effect_state") == null && canResume(value, actor.scope)
            return reply.first to buildJsonObject {
                put("operation_id", value.operationId); put("action", value.action)
                put("effect_state", if (prepared) "NOT_DISPATCHED" else "UNKNOWN")
                put("status", if (prepared) "OWNER_RECONFIRMATION_REQUIRED" else "ORIGINAL_LINK_UNCONFIRMED")
                put("oauth_state", value.oauthState)
                put("reconciliation_required", !prepared)
                put("resume_requires_owner_approval", prepared)
                // Preserve recorded historical facts (including unbound
                // APPLIED), without turning them into this link's completion.
                put("source_readback", body ?: JsonNull)
            }.toString()
        }
        return reply
    }

    suspend fun resume(value: PendingAccountOperation, actor: AccountOperationActor,
                       current: () -> AccountOperationActor, exchange: (() -> Unit) -> Pair<Int,String>): Pair<Int,String> {
        val context = currentCoroutineContext()
        fun guard() {
            context.ensureActive()
            check(actor == current() && value.deviceId == actor.deviceId && value.scope == actor.scope) { "account_operation_original_profile_not_current" }
        }
        guard(); check(canResume(value, actor.scope)) { "original_link_requires_hold" }
        val reply = exchange(::guard)
        guard()
        val confirmed = observe(value, reply.second, reply.first, actor.scope)
        check(confirmed || parseObject(reply.second)?.str("effect_state") !in setOf("APPLIED", "REFUSED")) { "account_operation_original_receipt_unconfirmed" }
        return reply
    }
}
