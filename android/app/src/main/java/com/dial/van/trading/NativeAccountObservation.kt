package com.dial.van.trading

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Original account facts; cash coverage, settlement and order permission are separate. */
data class NativeAccountObservation(
    val state: String = "UNMEASURED",
    val reason: String? = null,
    val valuationState: String? = null,
    val nativeLogin: String? = null,
    val server: String? = null,
    val currency: String? = null,
    val demo: Boolean? = null,
    val reportedEquity: String? = null,
    val balance: String? = null,
    val credit: String? = null,
    val riskEquity: String? = null,
    val sourceKind: String? = null,
    val sourceReceivedAtMs: Long? = null,
    val observedAtMs: Long? = null,
    val receivedAtMs: Long? = null,
    val scopeHash: String? = null,
    val sourceRef: String? = null,
    val snapshotRef: String? = null,
) {
    val executionAuthority: Boolean get() = false

    companion object {
        fun from(o: JsonObject?): NativeAccountObservation {
            if (o == null || o.text("state") == "UNMEASURED") return NativeAccountObservation()
            if (o.text("state") == "UNAVAILABLE") return NativeAccountObservation("UNAVAILABLE", o.text("reason"))
            fun invalid() = NativeAccountObservation("UNAVAILABLE", "NATIVE_ACCOUNT_PROOF_UNREADABLE")
            val reported = o.money("reported_equity") ?: return invalid()
            val balance = o.money("balance") ?: return invalid()
            val credit = o.money("credit")
            val risk = o.money("risk_equity", derived = true)
            val valuation = o.text("valuation_state")
            val sourceClock = o.integer("source_received_at_ms") ?: return invalid()
            val observed = o.integer("observed_at_ms") ?: return invalid()
            val received = o.integer("received_at_ms") ?: return invalid()
            val login = o["login"] as? JsonPrimitive ?: return invalid()
            val demo = (o["demo"] as? JsonPrimitive)?.takeUnless { it.isString }?.content?.toBooleanStrictOrNull()
            if (o.text("state") != "OBSERVED" || o.text("schema") != "vati.mt5-account-observation/1" ||
                o.text("provider") != "MT5" || o["execution_authority"] != JsonPrimitive(false) ||
                login.isString || login.content.toLongOrNull()?.let { it > 0 } != true || demo == null ||
                listOf("account_alias", "server", "currency", "source_nonce").any { !o.validText(it) } ||
                o.text("source_kind") !in setOf("MT5_SIGNED_MTLS_READ", "MT5_SIGNED_EA_POLL") ||
                o.text("money_basis") != "NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS" ||
                sourceClock < 0 || observed < sourceClock || received < observed ||
                listOf("scope_hash", "source_ref", "snapshot_ref").any { o.text(it)?.matches(Regex("[0-9a-f]{64}")) != true }
            ) return invalid()
            when (valuation) {
                "CREDIT_EXCLUDED" -> if (credit == null || credit.signum() < 0 || risk == null || reported.subtract(credit).compareTo(risk) != 0) return invalid()
                "CREDIT_UNAVAILABLE" -> if (o["credit"] != JsonNull || o["risk_equity"] != JsonNull) return invalid()
                "CREDIT_LIABILITY_UNQUALIFIED" -> if (credit == null || credit.signum() >= 0 || o["risk_equity"] != JsonNull) return invalid()
                else -> return invalid()
            }
            return NativeAccountObservation("OBSERVED", valuationState = valuation, nativeLogin = login.content,
                server = o.text("server"), currency = o.text("currency"), demo = demo,
                reportedEquity = o.text("reported_equity"), balance = o.text("balance"),
                credit = o.text("credit"), riskEquity = o.text("risk_equity"), sourceKind = o.text("source_kind"),
                sourceReceivedAtMs = sourceClock, observedAtMs = observed, receivedAtMs = received,
                scopeHash = o.text("scope_hash"), sourceRef = o.text("source_ref"), snapshotRef = o.text("snapshot_ref"))
        }

        private fun JsonObject.text(key: String): String? =
            (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
        private fun JsonObject.validText(key: String): Boolean = text(key)?.let { it.isNotBlank() && it == it.trim() && it.length <= 256 } == true
        private fun JsonObject.integer(key: String): Long? =
            (this[key] as? JsonPrimitive)?.takeUnless { it.isString }?.content?.toLongOrNull()
        private fun JsonObject.money(key: String, derived: Boolean = false) =
            text(key)?.takeIf { it.length in 1..(if (derived) 1024 else 128) }?.toBigDecimalOrNull()
                ?.takeIf { it.scale().toLong() in (if (derived) -256L..256L else -128L..128L) }
    }
}
