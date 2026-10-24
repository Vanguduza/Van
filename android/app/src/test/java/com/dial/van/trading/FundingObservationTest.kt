package com.dial.van.trading

import org.junit.Assert.*
import org.junit.Test

class FundingObservationTest {
    @Test fun mt5KeepsCashComponentsAndTheirUnqualifiedClockSeparateFromReturns() {
        val observation = FundingObservation.from(parseObject("""{"state":"OBSERVED","return_qualification":"NOT_ISSUED",
            "query_ref":"original-query","native_time_basis":"MT5_TERMINAL_NATIVE_NOT_UTC_QUALIFIED",
            "money_basis":"NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS","coverage_state":"AVAILABLE_QUERY_ONLY",
            "movements":[{"movement":{"native_id":18446744073709551615,"operation":"DEAL_TYPE_BALANCE",
            "native_time_ms":9000,"profit":"10000.0000000000000001","commission":"-0.00000013","swap":"0","fee":"-1.25"}}]}"""))
        val cash = observation.movements.single()
        assertEquals("18446744073709551615", cash.nativeId)
        assertEquals("10000.0000000000000001", cash.profit)
        assertEquals("-0.00000013", cash.commission); assertEquals("-1.25", cash.fee)
        assertNull(cash.delta); assertNull(cash.balanceAfter)
        assertEquals(9000L, cash.nativeTimeMs); assertEquals("original-query", observation.queryRef)
        assertEquals("MT5_TERMINAL_NATIVE_NOT_UTC_QUALIFIED", observation.nativeTimeBasis)
        assertEquals("NOT_ISSUED", observation.returnQualification)
    }
    @Test fun cashIsNotParsedAsProfitAndNativeIdentityKeepsAllDigits() {
        val account = AccountCard.from(parseObject("""{"alias":"native","broker":"CTRADER","day_pnl":null,"drawdown_pct":null,
            "performance_state":"UNMEASURED","funding":{"state":"OBSERVED","reason":"NORMALIZED_HISTORICAL_VALUATION_NOT_QUALIFIED",
            "return_qualification":"NOT_ISSUED","scope_hash":"native-scope","movement_count":101,"movements_truncated":true,
            "movements":[{"movement":{"native_id":9007199254740993,"operation":"BALANCE_DEPOSIT","delta":"1.000000000000000001","balance_after":"200","equity_after":null},
            "original_statement_ref":"original","classification":{"category":"EXTERNAL_CAPITAL","state":"CLASSIFIED"}}]}}""")!!)
        assertNull(account.dayPnl.value); assertNull(account.drawdown.fraction)
        assertEquals("UNMEASURED", account.performanceState)
        assertEquals("NOT_ISSUED", account.funding.returnQualification)
        assertEquals(101L, account.funding.movementCount); assertTrue(account.funding.movementsTruncated)
        val cash = account.funding.movements.single()
        assertEquals("9007199254740993", cash.nativeId); assertEquals("1.000000000000000001", cash.delta)
        assertEquals("EXTERNAL_CAPITAL", cash.classification); assertNull(cash.equityAfter)
    }

    @Test fun absentOrFailedHistoryNeverBecomesAnObservedEmptyOrQualifiedReturn() {
        val absent = FundingObservation.from(null)
        assertEquals("UNMEASURED", absent.state); assertEquals("NOT_ISSUED", absent.returnQualification)
        assertNull(absent.movementCount)
        val failed = FundingObservation.from(parseObject("""{"state":"UNAVAILABLE","reason":"NATIVE_CASH_HISTORY_UNAVAILABLE"}"""))
        assertEquals("UNAVAILABLE", failed.state); assertEquals("NOT_ISSUED", failed.returnQualification)
        assertNull(failed.statementRef)
    }
}
