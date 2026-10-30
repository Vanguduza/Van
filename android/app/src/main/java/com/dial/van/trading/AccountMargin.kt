package com.dial.van.trading

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Original facts and named cash-equity risk bounds. No order permission. */
data class AccountMargin(
    val state: String = "UNMEASURED",
    val basis: String? = null,
    val usedMargin: String? = null,
    val freeMargin: String? = null,
    val marginLevelPct: String? = null,
    val riskFreeMarginBound: String? = null,
    val riskMarginLevelBoundPct: String? = null,
    val observedAtMs: Long? = null,
    val receivedAtMs: Long? = null,
    val snapshotRef: String? = null,
    val marginLevelApplicable: Boolean? = null,
) {
    val executionAuthority: Boolean get() = false
    companion object {
        fun from(o: JsonObject?): AccountMargin {
            if (o == null || o.text("state") == "UNMEASURED") return AccountMargin()
            val state = o.text("state")
            if (state == "UNAVAILABLE") return AccountMargin("UNAVAILABLE")
            val observed = o.text("observed_at_ms")?.toLongOrNull()
            val received = o.text("received_at_ms")?.toLongOrNull()
            val used = o.text("used_margin")?.toBigDecimalOrNull()
            val free = o.text("free_margin")?.toBigDecimalOrNull()
            val level = o.text("margin_level_pct")?.toBigDecimalOrNull()
            val riskFree = o.text("risk_free_margin_bound")?.toBigDecimalOrNull()
            val riskLevel = o.text("risk_margin_level_bound_pct")?.toBigDecimalOrNull()
            val applicable = (o["margin_level_applicable"] as? JsonPrimitive)?.takeUnless { it.isString }?.content?.toBooleanStrictOrNull()
            if (state !in setOf("OBSERVED", "SIMULATED", "NOT_APPLICABLE") ||
                o["execution_authority"] != JsonPrimitive(false) ||
                observed == null || observed < 0 || received == null || received < observed ||
                o.text("snapshot_ref")?.matches(Regex("[0-9a-f]{64}")) != true ||
                (state == "OBSERVED" && (o.text("basis") !in setOf("MT5_NATIVE_ACCOUNT_INFORMATION", "CTRADER_NATIVE_PER_SYMBOL_MARGIN_CASH_EQUITY_BOUND") || used == null || used.signum() < 0 || free == null || riskFree == null ||
                    riskFree > free || (riskLevel != null && level != null && riskLevel > level) ||
                    applicable != (used.signum() > 0) ||
                    (used.signum() > 0 && (level == null || riskLevel == null)) ||
                    (used.signum() == 0 && (level != null || riskLevel != null))))
            ) return AccountMargin("UNAVAILABLE")
            return AccountMargin(state!!, o.text("basis"), o.text("used_margin"), o.text("free_margin"),
                o.text("margin_level_pct"), o.text("risk_free_margin_bound"), o.text("risk_margin_level_bound_pct"),
                observed, received, o.text("snapshot_ref"), applicable)
        }
        private fun JsonObject.text(key: String): String? =
            (this[key] as? JsonPrimitive)?.takeUnless { it is JsonNull }?.content
    }
}
