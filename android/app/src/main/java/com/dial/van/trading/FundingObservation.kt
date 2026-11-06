package com.dial.van.trading

import kotlinx.serialization.json.JsonObject

/** Original cash facts. Neither an observed transfer nor broker credit is trading alpha. */
data class NativeCashMovement(
    val nativeId: String?, val operation: String?, val delta: String?, val balanceAfter: String?,
    val equityAfter: String?, val originalStatementRef: String?, val classification: String?, val classificationState: String?,
    val observedAtMs: Long? = null, val receivedAtMs: Long? = null,
    val nativeTimeMs: Long? = null, val profit: String? = null, val commission: String? = null,
    val swap: String? = null, val fee: String? = null,
) {
    companion object {
        fun from(row: JsonObject): NativeCashMovement {
            val movement = row.obj("movement")
            val classification = row.obj("classification")
            // Keep provider IDs and money exact; a Double loses integer IDs above 2^53.
            return NativeCashMovement(movement?.str("native_id"), movement?.str("operation"), movement?.str("delta"),
                movement?.str("balance_after"), movement?.str("equity_after"), row.str("original_statement_ref"),
                classification?.str("category"), classification?.str("state"), row.str("observed_at_ms")?.toLongOrNull(), row.str("received_at_ms")?.toLongOrNull(),
                movement?.str("native_time_ms")?.toLongOrNull(), movement?.str("profit"), movement?.str("commission"),
                movement?.str("swap"), movement?.str("fee"))
        }
    }
}

data class FundingObservation(
    val state: String, val reason: String?, val returnQualification: String, val scopeHash: String?,
    val snapshotRef: String?, val statementRef: String?, val collectorState: String?,
    val movementCount: Long?, val movementsTruncated: Boolean, val movements: List<NativeCashMovement>,
    val nativeDeals: NativeDealLedger = NativeDealLedger.from(null), val period: NativeBalancePeriod = NativeBalancePeriod.from(null),
    val queryRef: String? = null, val nativeTimeBasis: String? = null, val moneyBasis: String? = null,
    val coverageState: String? = null,
) {
    companion object {
        fun from(o: JsonObject?): FundingObservation = FundingObservation(
            o?.str("state") ?: "UNMEASURED", o?.str("reason"), o?.str("return_qualification") ?: "NOT_ISSUED",
            o?.str("scope_hash"), o?.str("snapshot_ref"), o?.str("statement_ref"), o?.str("collector_state"),
            o?.str("movement_count")?.toLongOrNull()?.takeIf { it >= 0 }, o?.bool("movements_truncated") ?: false,
            o?.arr("movements")?.map(NativeCashMovement::from) ?: emptyList(),
            NativeDealLedger.from(o?.obj("native_deals")), NativeBalancePeriod.from(o?.obj("period")),
            o?.str("query_ref"), o?.str("native_time_basis"), o?.str("money_basis"), o?.str("coverage_state"),
        )
    }
}
