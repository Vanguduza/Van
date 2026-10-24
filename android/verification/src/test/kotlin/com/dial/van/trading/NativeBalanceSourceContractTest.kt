package com.dial.van.trading

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class NativeBalanceSourceContractTest {
    @Test fun capitalCanReconcileWhilePercentagePerformanceRemainsUnknown() {
        val source = FundingObservation.from(parseObject("""{"period":{"state":"UNMEASURED","balance_state":"RECONCILED","balance_reconciliation_basis":"NATIVE_BALANCE_VERSIONS_AND_POST_OPERATION_BALANCES",
            "trade_cost_settlement_qualification":"NOT_ISSUED",
            "cash_neutral_net_account_pnl":"10","separate_business_income_or_expense":"10",
            "net_account_pnl_excluding_capital_and_separate_business":"0","return_qualification":"NOT_ISSUED",
            "performance":null,"knowledge_through_received_ms":9007199254740993,"knowledge_basis":"LATEST_OBSERVED_HISTORY_NOT_AS_KNOWN_AT_TRADE_TIME"}}""")!!)
        assertEquals("RECONCILED", source.period.balanceState)
        assertEquals("10", source.period.cashNeutralNetAccountPnl)
        assertEquals("0", source.period.netAccountPnlExcludingCapitalAndSeparateBusiness)
        assertNull(source.period.flowNeutralReturn)
        assertEquals(9007199254740993L, source.period.knowledgeThroughReceivedMs)
        assertEquals("NOT_ISSUED", source.period.returnQualification)
        assertEquals("NATIVE_BALANCE_VERSIONS_AND_POST_OPERATION_BALANCES", source.period.balanceReconciliationBasis)
        assertEquals("NOT_ISSUED", source.period.tradeCostSettlementQualification)
    }

    @Test fun originalDealMoneyIdentityAndMissingFeeRemainExact() {
        val source = FundingObservation.from(parseObject("""{"native_deals":{"state":"OBSERVED","deal_count":1,"deals":[
            {"deal":{"native_id":9007199254740993,"commission":"-0.00000013","close":{"pnl_conversion_fee":null}},
            "original_statement_ref":"original","observed_at_ms":1000,"received_at_ms":2000}]}}""")!!)
        val deal = source.nativeDeals.deals.single()
        assertEquals("9007199254740993", deal.nativeId)
        assertEquals("-0.00000013", deal.commission)
        assertNull(deal.close?.pnlConversionFee)
        assertEquals(2000L, deal.receivedAtMs)
    }
}
