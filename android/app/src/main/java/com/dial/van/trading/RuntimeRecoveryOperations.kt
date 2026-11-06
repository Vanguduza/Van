package com.dial.van.trading

import kotlinx.serialization.json.*

/** Durable public identity only. Arguments, signatures and credentials stay out of this store. */
data class PendingRuntimeRecovery(
    val operationId: String, val deviceId: String, val accountAlias: String,
    val sessionId: String, val action: String, val bodyDigest: String,
) {
    companion object {
        fun from(challenge: RuntimeRecoveryChallenge) = PendingRuntimeRecovery(
            challenge.operationId, challenge.intent.deviceId, challenge.intent.accountAlias,
            challenge.intent.sessionId, challenge.intent.action, challenge.intent.digest)
    }
}

class RuntimeRecoveryOperations(private val store: AccountOperationStore) {
    companion object { private val lock = Any() }
    private val fields = setOf("operation_id", "device_id", "account_alias", "session_id", "action", "body_digest")
    private fun validate(value: PendingRuntimeRecovery) {
        require(RuntimeRecoveryProtocol.validOperationId(value.operationId))
        require(Regex("[A-Za-z0-9_.:-]{1,128}").matches(value.deviceId))
        require(Regex("[a-z0-9_]{3,32}").matches(value.accountAlias))
        require(value.sessionId.isNotEmpty() && value.sessionId.codePointCount(0,value.sessionId.length) <= 384 &&
            value.sessionId.none { it in "|\r\n" })
        require(value.action in setOf("clear_kill_switch", "reset_loss_streak", "resume_drawdown"))
        require(Regex("[0-9a-f]{64}").matches(value.bodyDigest))
    }

    private fun read(): List<PendingRuntimeRecovery> {
        val text = store.load() ?: return emptyList()
        val root = Json.parseToJsonElement(text) as? JsonObject ?: error("runtime_recovery_history_unreadable")
        check(root.keys == setOf("schema", "operations") && root.str("schema") == "van.android.runtime-recovery/1")
        val entries = root["operations"] as? JsonArray ?: error("runtime_recovery_history_unreadable")
        val result = entries.map {
            val row = it as? JsonObject ?: error("runtime_recovery_history_unreadable")
            check(row.keys == fields)
            fun text(key: String) = (row[key] as? JsonPrimitive)?.takeIf { p -> p.isString }?.content
                ?: error("runtime_recovery_history_unreadable")
            PendingRuntimeRecovery(text("operation_id"),text("device_id"),text("account_alias"),
                text("session_id"),text("action"),text("body_digest")).also(::validate)
        }
        check(result.map { it.operationId }.toSet().size == result.size)
        return result
    }

    private fun write(values: List<PendingRuntimeRecovery>) {
        val body = buildJsonObject {
            put("schema", "van.android.runtime-recovery/1")
            put("operations", JsonArray(values.map { value -> buildJsonObject {
                put("operation_id",value.operationId); put("device_id",value.deviceId)
                put("account_alias",value.accountAlias); put("session_id",value.sessionId)
                put("action",value.action); put("body_digest",value.bodyDigest)
            } }))
        }
        check(store.save(body.toString())) { "runtime_recovery_identity_not_saved_no_dispatch" }
    }

    fun pending(deviceId: String) = synchronized(lock) { read().filter { it.deviceId == deviceId } }

    fun prepareDispatch(challenge: RuntimeRecoveryChallenge, nowUnix: Long): PendingRuntimeRecovery = synchronized(lock) {
        require(nowUnix >= 0)
        val original = PendingRuntimeRecovery.from(challenge)
        if (read().none { it.operationId == original.operationId }) {
            require(nowUnix < challenge.expiresAtUnix) { "runtime_recovery_approval_expired_no_dispatch" }
            val issued = challenge.intent.issuedAtUnix
            require(if (nowUnix >= issued) nowUnix-issued < 300 else issued-nowUnix <= 60) {
                "runtime_recovery_intent_stale_no_dispatch"
            }
        }
        remember(original)
        original
    }

    fun remember(value: PendingRuntimeRecovery) { synchronized(lock) {
        validate(value)
        val entries = read()
        val original = entries.firstOrNull { it.operationId == value.operationId }
        if (original != null) {
            check(original == value) { "runtime_recovery_original_identity_conflict" }
            return // Exact original POST can resume its original durable dispatch.
        }
        check(entries.none { it.deviceId == value.deviceId && it.accountAlias == value.accountAlias }) {
            "runtime_recovery_requires_original_readback"
        }
        write(entries + value)
    } }

    fun observe(value: PendingRuntimeRecovery, body: String, httpCode: Int): Boolean { synchronized(lock) {
        val entries = read(); check(value in entries)
        val row = parseObject(body) ?: return false
        if (httpCode !in 200..299 || row.str("operation_id") != value.operationId) return false
        val intent = runCatching { RuntimeRecoveryProtocol.parseIntent(row.obj("intent") ?: return false) }.getOrNull()
            ?: return false
        if (intent.deviceId != value.deviceId || intent.accountAlias != value.accountAlias ||
            intent.sessionId != value.sessionId || intent.action != value.action || intent.digest != value.bodyDigest) return false
        val phase = row.str("phase")
        if (phase !in setOf("APPLIED","REFUSED")) return false
        val result = row.obj("result") ?: return false
        val permission = result["entry_authority_granted"] as? JsonPrimitive ?: return false
        if (permission.isString || permission.content != "false" ||
            !Regex("[0-9a-f]{64}").matches(row.str("native_event_ref").orEmpty())) return false
        val reason = result.str("reason_code")
        if ((phase == "APPLIED" && reason != "APPLIED") || (phase == "REFUSED" && reason !in setOf(
            "APPROVAL_EXPIRED","OWNER_KEY_UNREGISTERED","SESSION_CHANGED","STATE_CHANGED","PRECONDITION_UNMET","ACTOR_LEASE_LOST"))) return false
        val effects = result["effect_refs"] as? JsonArray ?: return false
        if ((phase == "APPLIED" && effects.isEmpty()) || (phase == "REFUSED" && effects.isNotEmpty()) ||
            effects.any { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content?.let { ref ->
                Regex("[0-9a-f]{64}").matches(ref) } != true }) return false
        write(entries.filterNot { it == value })
        return true
    } }
}
