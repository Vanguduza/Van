package com.dial.van.trading

import org.junit.Assert.*
import org.junit.Test

class NativeBalancePeriodTest {
    @Test fun markedAccountEvidencePreservesItsBasisAvailabilityAndMissingFee() {
        val value = FundingObservation.from(parseObject("""{"state":"OBSERVED","native_deals":{"state":"OBSERVED","deal_count":1,"deals":[
            {"deal":{"native_id":9007199254740993,"order_id":9007199254740995,"position_id":9007199254740997,"status":"FILLED",
            "commission":"-0.00000013","close":{"balance_after":"100.000000000000000001","pnl_conversion_fee":null,"balance_version":9007199254740999}},
            "original_statement_ref":"native-original","received_at_ms":9007199254740993}]},
            "period":{"state":"MEASURED","balance_state":"RECONCILED","balance_reconciliation_basis":"NATIVE_BALANCE_VERSIONS_AND_POST_OPERATION_BALANCES",
            "trade_cost_settlement_qualification":"NOT_ISSUED","return_qualification":"NOT_ISSUED","from_ms":1000,"to_ms":3000,
            "knowledge_through_received_ms":9007199254740993,"knowledge_basis":"LATEST_OBSERVED_HISTORY_NOT_AS_KNOWN_AT_TRADE_TIME",
            "performance":{"flow_neutral_return":"0.100000000000000001","net_account_pnl":"10.000000000000000001","worst_observed_drawdown":"0.2"},
            "evidence_refs":["original-a","original-b"]}}""")!!)
        assertEquals("9007199254740993", value.nativeDeals.deals.single().nativeId)
        assertEquals(9007199254740993L, value.nativeDeals.deals.single().receivedAtMs)
        assertEquals("100.000000000000000001", value.nativeDeals.deals.single().close?.balanceAfter)
        assertNull(value.nativeDeals.deals.single().close?.pnlConversionFee)
        assertEquals("MEASURED", value.period.state); assertEquals("NOT_ISSUED", value.period.returnQualification)
        assertEquals(9007199254740993L, value.period.knowledgeThroughReceivedMs)
        assertEquals("0.100000000000000001", value.period.flowNeutralReturn)
        assertEquals(listOf("original-a", "original-b"), value.period.evidenceRefs)
        assertEquals("NATIVE_BALANCE_VERSIONS_AND_POST_OPERATION_BALANCES", value.period.balanceReconciliationBasis)
        assertEquals("NOT_ISSUED", value.period.tradeCostSettlementQualification)
    }

    @Test fun unmeasuredPeriodDoesNotCreateZeroReturnOrAnEmptyObservedDealLedger() {
        val value = FundingObservation.from(parseObject("""{"period":{"state":"UNMEASURED","balance_state":"RECONCILED","balance_reconciliation_basis":"NATIVE_BALANCE_VERSIONS_AND_POST_OPERATION_BALANCES",
            "trade_cost_settlement_qualification":"NOT_ISSUED",
            "reason":"NORMALIZED_HISTORICAL_FLOW_EQUITY_UNAVAILABLE","performance":null}}""")!!)
        assertEquals("UNMEASURED", value.period.state); assertEquals("NOT_ISSUED", value.period.returnQualification)
        assertNull(value.period.flowNeutralReturn); assertNull(value.period.observedDrawdown)
        assertEquals("NO_DATA", value.nativeDeals.state); assertNull(value.nativeDeals.count)
    }
}
