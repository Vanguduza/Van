package com.dial.van.trading

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Read-only current risk evidence. This object cannot authorize, size or send an order. */
data class CurrentAccountRisk(
    val state: String = "UNMEASURED",
    val reasonCode: String? = null,
    val reasonDetail: String? = null,
    val proofRef: String? = null,
    val originalDecisionHash: String? = null,
    val originalCommandHash: String? = null,
    val decisionHash: String? = null,
    val observedAtMs: Long? = null,
    val receivedAtMs: Long? = null,
    val currentSizeLimit: String? = null,
    val originalCommandQuantity: String? = null,
) {
    val executionAuthority: Boolean get() = false

    companion object {
        fun from(o: JsonObject?): CurrentAccountRisk {
            if (o == null || o.text("state") == "UNMEASURED") return CurrentAccountRisk()
            val state = o.text("state")
            if (state == "UNAVAILABLE") return CurrentAccountRisk(state, o.text("reason_code"))
            val observed = o.text("observed_at_ms")?.toLongOrNull()
            val received = o.text("received_at_ms")?.toLongOrNull()
            val limit = o.text("current_size_limit")?.toBigDecimalOrNull()
            val quantity = o.text("original_command_quantity")?.toBigDecimalOrNull()
            val hashes = listOf("proof_ref", "original_decision_hash", "original_command_hash", "decision_hash")
            if (state !in setOf("SUFFICIENT", "REFUSED") || o["execution_authority"] != JsonPrimitive(false) ||
                hashes.any { o.text(it)?.matches(Regex("[0-9a-f]{64}")) != true } ||
                observed == null || observed < 0 || received == null || received < observed ||
                limit == null || limit.signum() < 0 || quantity == null || quantity.signum() <= 0 ||
                (state == "SUFFICIENT" && quantity > limit)
            ) return CurrentAccountRisk("UNAVAILABLE", "CURRENT_RISK_PROOF_UNREADABLE")
            return CurrentAccountRisk(state!!, o.text("reason_code"), o.text("reason_detail"),
                o.text("proof_ref"), o.text("original_decision_hash"), o.text("original_command_hash"),
                o.text("decision_hash"), observed, received, o.text("current_size_limit"),
                o.text("original_command_quantity"))
        }

        private fun JsonObject.text(key: String): String? =
            (this[key] as? JsonPrimitive)?.takeUnless { it is JsonNull }?.content
    }
}
