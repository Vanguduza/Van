package com.dial.van.trading

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.nio.charset.StandardCharsets

/** Exact owner-approved native target. A completed recovery supplies no entry permission. */
class RuntimeRecoveryIntent(
    val deviceId: String,
    val accountAlias: String,
    val sessionId: String,
    val action: String,
    val stateRef: String,
    val issuedAtUnix: Long,
    arguments: Map<String, String>,
) {
    val arguments: Map<String, String> = java.util.Collections.unmodifiableMap(LinkedHashMap(arguments))

    init {
        require(Regex("[A-Za-z0-9_.:-]{1,128}").matches(deviceId))
        require(Regex("[a-z0-9_]{3,32}").matches(accountAlias))
        require(sessionId.isNotEmpty() && sessionId.codePointCount(0, sessionId.length) <= 384 &&
            sessionId.none { it in "|\r\n" })
        require(Regex("[0-9a-f]{64}").matches(stateRef) && issuedAtUnix >= 0)
        val expected = when (action) {
            "clear_kill_switch" -> setOf("trigger")
            "reset_loss_streak" -> setOf("scope")
            "resume_drawdown" -> emptySet()
            else -> error("runtime_recovery_action_unsupported")
        }
        require(this.arguments.keys == expected) { "runtime_recovery_arguments_invalid" }
        if (action == "clear_kill_switch") require(Regex("[A-Z_]{1,128}").matches(this.arguments.getValue("trigger")))
        if (action == "reset_loss_streak") require(this.arguments.getValue("scope") == "*ACCOUNT*" ||
            Regex("[A-Za-z0-9_.:-]{1,128}").matches(this.arguments.getValue("scope")))
    }

    fun body(): JsonObject = buildJsonObject {
        put("schema", "vati.runtime-recovery/1"); put("device_id", deviceId)
        put("account_alias", accountAlias); put("session_id", sessionId); put("action", action)
        put("state_ref", stateRef); put("issued_at_unix", issuedAtUnix)
        put("args", buildJsonObject { arguments.forEach { (key, value) -> put(key, value) } })
    }

    val digest: String get() = AccountOnboarding.sha256Hex(
        AccountOnboarding.canonicalJson(body()).toByteArray(StandardCharsets.UTF_8))
    val actionId: String get() = "trading.runtime.$action"
    val intentDigest: String get() = AccountOnboarding.sha256Hex(
        listOf("van-a4-intent-v1", deviceId, actionId, "", "trading-runtime-control|$digest")
            .joinToString("|").toByteArray(StandardCharsets.UTF_8))

    fun approvalStatement(operationId: String, expiresAtUnix: Long): String {
        require(RuntimeRecoveryProtocol.validOperationId(operationId) && expiresAtUnix >= 0)
        return listOf("van-a4-approval-v2", operationId, deviceId, "runtime:$action", "",
            actionId, intentDigest, expiresAtUnix.toString()).joinToString("|")
    }
}

data class RuntimeRecoveryChallenge(
    val intent: RuntimeRecoveryIntent,
    val operationId: String,
    val canonical: String,
    val expiresAtUnix: Long,
) {
    init { require(canonical == intent.approvalStatement(operationId, expiresAtUnix)) }

    /** Retains the exact original timestamp, state and approval ID on a retry. */
    fun requestBody(signatureBase64: String): JsonObject {
        require(signatureBase64.isNotBlank() && signatureBase64.length <= 1024)
        val signature = java.util.Base64.getDecoder().decode(signatureBase64)
        require(signature.isNotEmpty() && java.util.Base64.getEncoder().encodeToString(signature) == signatureBase64)
        return buildJsonObject {
            put("intent", intent.body())
            put("approval_proof", buildJsonObject {
                put("challenge_id", operationId); put("signature_b64", signatureBase64)
                put("algorithm", "ECDSA_P256_SHA256"); put("expires_at_unix", expiresAtUnix)
            })
        }
    }
}

object RuntimeRecoveryProtocol {
    private val operationId = Regex("[A-Za-z0-9_-]{20,128}")
    fun validOperationId(value: String): Boolean = operationId.matches(value)

    private fun text(row: JsonObject, key: String): String =
        (row[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
            ?: error("runtime_recovery_${key}_invalid")

    private fun integer(row: JsonObject, key: String): Long =
        (row[key] as? JsonPrimitive)?.takeIf { !it.isString }?.longOrNull?.takeIf { it >= 0 }
            ?: error("runtime_recovery_${key}_invalid")

    fun parseIntent(row: JsonObject): RuntimeRecoveryIntent {
        require(row.keys == setOf("schema", "device_id", "account_alias", "session_id", "action", "state_ref", "issued_at_unix", "args"))
        require(text(row, "schema") == "vati.runtime-recovery/1")
        val args = row["args"] as? JsonObject ?: error("runtime_recovery_arguments_invalid")
        return RuntimeRecoveryIntent(text(row,"device_id"), text(row,"account_alias"), text(row,"session_id"),
            text(row,"action"), text(row,"state_ref"), integer(row,"issued_at_unix"),
            args.keys.associateWith { text(args,it) })
    }

    fun challenge(intent: RuntimeRecoveryIntent, response: String): RuntimeRecoveryChallenge {
        val row = Json.parseToJsonElement(response) as? JsonObject ?: error("runtime_recovery_challenge_invalid")
        require(parseIntent(row["intent"] as? JsonObject ?: error("runtime_recovery_intent_missing")).body() == intent.body())
        require(text(row,"resolved_action_id") == intent.actionId)
        val review = row["resolved_review"] as? JsonObject ?: error("runtime_recovery_review_missing")
        val state = review["state"] as? JsonObject ?: error("runtime_recovery_state_missing")
        require(text(review,"state_ref") == intent.stateRef && text(state,"account_alias") == intent.accountAlias &&
            text(state,"session_id") == intent.sessionId)
        return RuntimeRecoveryChallenge(intent, text(row,"approval_challenge_id"), text(row,"approval_challenge"),
            integer(row,"approval_expires_at_unix"))
    }
}
