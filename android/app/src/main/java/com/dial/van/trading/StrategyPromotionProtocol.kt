package com.dial.van.trading

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.nio.charset.StandardCharsets
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** Pure cross-language wire contract for device-signed strategy promotion requests. */
object StrategyPromotionProtocol {

    fun authorityBody(
        strategyId: String,
        targetState: String,
        ownerSignatureRef: String,
        certificate: JsonObject,
        evidenceRefs: List<String>,
    ): JsonObject = buildJsonObject {
        put("strategy_id", strategyId)
        put("target_state", targetState)
        put("owner_signature_ref", ownerSignatureRef)
        put("certificate", certificate)
        put("evidence_refs", JsonArray(evidenceRefs.map(::JsonPrimitive)))
    }

    fun canonical(
        deviceId: String,
        issuedAtUnix: Long,
        strategyId: String,
        targetState: String,
        ownerSignatureRef: String,
        certificate: JsonObject,
        evidenceRefs: List<String>,
    ): String {
        val body = authorityBody(
            strategyId, targetState, ownerSignatureRef, certificate, evidenceRefs,
        )
        val digest = AccountOnboarding.sha256Hex(
            AccountOnboarding.canonicalJson(body).toByteArray(StandardCharsets.UTF_8)
        )
        return listOf(
            "trading-strategy-promotion",
            deviceId,
            issuedAtUnix.toString(),
            digest,
        ).joinToString("|")
    }

    fun signature(
        deviceSecret: String,
        deviceId: String,
        issuedAtUnix: Long,
        strategyId: String,
        targetState: String,
        ownerSignatureRef: String,
        certificate: JsonObject,
        evidenceRefs: List<String>,
    ): String {
        val canonical = canonical(
            deviceId, issuedAtUnix, strategyId, targetState,
            ownerSignatureRef, certificate, evidenceRefs,
        )
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(deviceSecret.toByteArray(StandardCharsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(canonical.toByteArray(StandardCharsets.UTF_8))
            .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
    }

    fun requestBody(
        deviceSecret: String,
        deviceId: String,
        issuedAtUnix: Long,
        strategyId: String,
        targetState: String,
        ownerSignatureRef: String,
        certificate: JsonObject,
        evidenceRefs: List<String>,
        approvalProof: JsonObject? = null,
    ): JsonObject = buildJsonObject {
        put("device_id", deviceId)
        put("issued_at_unix", issuedAtUnix)
        put(
            "signature",
            signature(
                deviceSecret, deviceId, issuedAtUnix, strategyId, targetState,
                ownerSignatureRef, certificate, evidenceRefs,
            ),
        )
        put("strategy_id", strategyId)
        put("target_state", targetState)
        put("owner_signature_ref", ownerSignatureRef)
        put("certificate", certificate)
        put("evidence_refs", JsonArray(evidenceRefs.map(::JsonPrimitive)))
        if (approvalProof != null) put("approval_proof", approvalProof)
    }
}
