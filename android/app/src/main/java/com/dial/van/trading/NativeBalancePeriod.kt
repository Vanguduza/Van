package com.dial.van.trading

import kotlinx.serialization.json.JsonObject

/** Read evidence only. No marked account return grants an execution permission. */
data class NativeBalancePeriod(
    val state: String, val reason: String?, val balanceState: String, val returnQualification: String,
    val baselineRef: String?, val closingRef: String?, val coverageState: String?,
    val fromMs: Long?, val toMs: Long?, val knowledgeThroughReceivedMs: Long?, val knowledgeBasis: String?,
    val flowNeutralReturn: String?, val netAccountPnl: String?, val observedDrawdown: String?, val evidenceRefs: List<String>,
    val cashNeutralNetAccountPnl: String? = null, val separateBusinessIncomeOrExpense: String? = null,
    val netAccountPnlExcludingCapitalAndSeparateBusiness: String? = null,
    val balanceReconciliationBasis: String? = null, val tradeCostSettlementQualification: String = "NOT_ISSUED",
) {
    companion object {
        fun from(o: JsonObject?): NativeBalancePeriod {
            val performance = o?.obj("performance")
            return NativeBalancePeriod(o?.str("state") ?: "UNMEASURED", o?.str("reason"), o?.str("balance_state") ?: "UNRECONCILED",
                o?.str("return_qualification") ?: "NOT_ISSUED", o?.str("baseline_ref"), o?.str("closing_ref"), o?.str("coverage_state"),
                o?.str("from_ms")?.toLongOrNull(), o?.str("to_ms")?.toLongOrNull(), o?.str("knowledge_through_received_ms")?.toLongOrNull(), o?.str("knowledge_basis"),
                performance?.str("flow_neutral_return"), performance?.str("net_account_pnl"), performance?.str("worst_observed_drawdown"),
                o?.strList("evidence_refs") ?: emptyList(), o?.str("cash_neutral_net_account_pnl"), o?.str("separate_business_income_or_expense"),
                o?.str("net_account_pnl_excluding_capital_and_separate_business"), o?.str("balance_reconciliation_basis"),
                o?.str("trade_cost_settlement_qualification") ?: "NOT_ISSUED")
        }
    }
}

data class NativeCloseBalanceObservation(
    val balanceAfter: String?, val grossProfit: String?, val swap: String?, val commission: String?,
    val pnlConversionFee: String?, val balanceVersion: String?, val closedVolumeCents: String?,
) {
    companion object {
        fun from(o: JsonObject?) = o?.let { NativeCloseBalanceObservation(it.str("balance_after"), it.str("gross_profit"), it.str("swap"),
            it.str("commission"), it.str("pnl_conversion_fee"), it.str("balance_version"), it.str("closed_volume_cents")) }
    }
}

data class NativeDealObservation(
    val nativeId: String?, val orderId: String?, val positionId: String?, val symbolId: String?, val status: String?,
    val filledVolumeCents: String?, val commission: String?, val close: NativeCloseBalanceObservation?,
    val originalStatementRef: String?, val observedAtMs: Long?, val receivedAtMs: Long?,
) {
    companion object {
        fun from(o: JsonObject): NativeDealObservation {
            val deal = o.obj("deal")
            return NativeDealObservation(deal?.str("native_id"), deal?.str("order_id"), deal?.str("position_id"), deal?.str("symbol_id"),
                deal?.str("status"), deal?.str("filled_volume_cents"), deal?.str("commission"), NativeCloseBalanceObservation.from(deal?.obj("close")),
                o.str("original_statement_ref"), o.str("observed_at_ms")?.toLongOrNull(), o.str("received_at_ms")?.toLongOrNull())
        }
    }
}

data class NativeDealLedger(val state: String, val count: Long?, val truncated: Boolean, val deals: List<NativeDealObservation>) {
    companion object {
        fun from(o: JsonObject?) = NativeDealLedger(o?.str("state") ?: "NO_DATA", o?.str("deal_count")?.toLongOrNull()?.takeIf { it >= 0 },
            o?.bool("deals_truncated") ?: false, o?.arr("deals")?.map(NativeDealObservation::from) ?: emptyList())
    }
}
