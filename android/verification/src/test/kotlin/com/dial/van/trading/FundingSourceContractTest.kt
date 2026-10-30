package com.dial.van.trading

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Compiles and executes the same pure funding parser the Android app uses. */
class FundingSourceContractTest {
    @Test fun mt5NativeComponentsKeepTheirClockAndNeverBecomeFabricatedDelta() {
        val funding = FundingObservation.from(parseObject("""{"state":"OBSERVED","query_ref":"original-query",
            "native_time_basis":"MT5_TERMINAL_NATIVE_NOT_UTC_QUALIFIED","money_basis":"NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS",
            "movements":[{"movement":{"native_id":18446744073709551615,"operation":"DEAL_TYPE_CREDIT","native_time_ms":9000,
            "profit":"10000.0000000000000001","commission":"-0.00000013","swap":"0","fee":"-1.25"}}]}"""))
        val cash = funding.movements.single()
        assertEquals("18446744073709551615", cash.nativeId); assertNull(cash.delta)
        assertEquals("10000.0000000000000001", cash.profit); assertEquals("-0.00000013", cash.commission)
        assertEquals("-1.25", cash.fee); assertEquals(9000L, cash.nativeTimeMs)
        assertEquals("original-query", funding.queryRef); assertEquals("NOT_ISSUED", funding.returnQualification)
        assertEquals("MT5_TERMINAL_NATIVE_NOT_UTC_QUALIFIED", funding.nativeTimeBasis)
    }
    @Test fun accountFundingDependencyKeepsNativeIdentityAndMoneyExact() {
        val account = AccountCard.from(parseObject("""{"alias":"native","day_pnl":null,"funding":{"state":"OBSERVED",
            "return_qualification":"NOT_ISSUED","movement_count":1,"movements":[{"movement":{"native_id":9007199254740993,
            "operation":"BALANCE_DEPOSIT","delta":"1.000000000000000001"},"classification":{"category":"EXTERNAL_CAPITAL","state":"CLASSIFIED"}}]}}""")!!)
        assertNull(account.dayPnl.value)
        assertEquals("NOT_ISSUED", account.funding.returnQualification)
        assertEquals("9007199254740993", account.funding.movements.single().nativeId)
        assertEquals("1.000000000000000001", account.funding.movements.single().delta)
    }

    @Test fun legacyOrUnavailableFundingDoesNotInventAZeroReturn() {
        val absent = FundingObservation.from(null)
        assertEquals("UNMEASURED", absent.state)
        assertEquals("NOT_ISSUED", absent.returnQualification)
        assertNull(absent.movementCount)
        assertTrue(absent.movements.isEmpty())
    }
}
