package com.dial.van.trading

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Compiles and executes the same pure funding parser the Android app uses. */
class FundingSourceContractTest {
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
