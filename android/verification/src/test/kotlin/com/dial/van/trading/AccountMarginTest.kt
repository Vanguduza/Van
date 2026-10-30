package com.dial.van.trading

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class AccountMarginTest {
    private fun margin() = """{"state":"OBSERVED","basis":"MT5_NATIVE_ACCOUNT_INFORMATION",
        "used_margin":"100.000000000000000001","free_margin":"1100.000000000000000001","margin_level_pct":"1200",
        "risk_free_margin_bound":"900.000000000000000001","risk_margin_level_bound_pct":"1000",
        "margin_level_applicable":true,"observed_at_ms":9007199254740993,"received_at_ms":9007199254740994,
        "snapshot_ref":"${"a".repeat(64)}","execution_authority":false}"""

    @Test fun existingAccountModelCarriesExactNativeFactsAndNamedBounds() {
        val body = """{"alias":"native","margin":${margin()}}"""
        val account = AccountCard.from(parseObject(body)!!)
        assertEquals("OBSERVED", account.margin.state)
        assertEquals("100.000000000000000001", account.margin.usedMargin)
        assertEquals("1100.000000000000000001", account.margin.freeMargin)
        assertEquals("900.000000000000000001", account.margin.riskFreeMarginBound)
        assertEquals(9007199254740993L, account.margin.observedAtMs)
        assertFalse(account.margin.executionAuthority)
        val portfolio = PortfolioSummary.parse("""{"accounts":[$body]}""")!!
        assertEquals(1000.0, portfolio.toTradeSignals().marginLevelPct)
    }

    @Test fun missingInvalidOrAuthorityClaimingMarginNeverBecomesCapacity() {
        assertEquals("UNMEASURED", AccountMargin.from(null).state)
        for (text in listOf(margin().replace("\"used_margin\":\"100.000000000000000001\"", "\"used_margin\":null"),
            margin().replace("\"execution_authority\":false", "\"execution_authority\":true"),
            margin().replace("\"risk_margin_level_bound_pct\":\"1000\"", "\"risk_margin_level_bound_pct\":\"NaN\""))) {
            val proof = AccountMargin.from(parseObject(text))
            assertEquals("UNAVAILABLE", proof.state)
            assertNull(proof.riskMarginLevelBoundPct)
            assertFalse(proof.executionAuthority)
        }
    }

    @Test fun zeroCommittedMarginHasNoInventedInfiniteLevel() {
        val body = margin().replace("\"used_margin\":\"100.000000000000000001\"", "\"used_margin\":\"0\"")
            .replace("\"margin_level_pct\":\"1200\"", "\"margin_level_pct\":null")
            .replace("\"risk_margin_level_bound_pct\":\"1000\"", "\"risk_margin_level_bound_pct\":null")
            .replace("\"margin_level_applicable\":true", "\"margin_level_applicable\":false")
        val result = AccountMargin.from(parseObject(body))
        assertEquals("OBSERVED", result.state)
        assertEquals("0", result.usedMargin)
        assertNull(result.riskMarginLevelBoundPct)
        assertEquals(false, result.marginLevelApplicable)
    }
}
