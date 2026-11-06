package com.dial.van.trading

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class CurrentAccountRiskTest {
    private fun body(authority: String = "false", observed: String = "9007199254740993") = """
        {"potential":[{"symbol":"EURUSD","label":"RISK_RECHECK_REFUSED","reasons":["current size limit is below original command"],
         "current_risk":{"state":"REFUSED","reason_code":"CURRENT_COMMAND_EXCEEDS_RISK","reason_detail":"size changed",
         "execution_authority":$authority,"proof_ref":"${"a".repeat(64)}","original_decision_hash":"${"b".repeat(64)}",
         "original_command_hash":"${"c".repeat(64)}","decision_hash":"${"d".repeat(64)}",
         "observed_at_ms":$observed,"received_at_ms":9007199254740994,"current_size_limit":"0.010000000000000001",
         "original_command_quantity":"0.020000000000000001"}}]}
    """.trimIndent()

    @Test fun refusalCarriesOriginalReferencesExactDecimalsAndClockWithoutAuthority() {
        val row = (TradeBookParser.parse(TradeView.POTENTIAL, body()) as TradeBookState.Ready).rows.single()
        assertEquals("RISK_RECHECK_REFUSED", row.state)
        assertEquals("REFUSED", row.currentRisk.state)
        assertEquals("a".repeat(64), row.currentRisk.proofRef)
        assertEquals("CURRENT_COMMAND_EXCEEDS_RISK", row.currentRisk.reasonCode)
        assertEquals("0.010000000000000001", row.currentRisk.currentSizeLimit)
        assertEquals("0.020000000000000001", row.currentRisk.originalCommandQuantity)
        assertEquals(9007199254740993L, row.currentRisk.observedAtMs)
        assertFalse(row.currentRisk.executionAuthority)
    }

    @Test fun malformedOrAuthorityClaimingProofCannotLookSufficient() {
        for (body in listOf(body("true"), body(observed="true"), body().replace("REFUSED", "SUFFICIENT").replace("0.010000000000000001", "NaN"))) {
            val proof = (TradeBookParser.parse(TradeView.POTENTIAL, body) as TradeBookState.Ready).rows.single().currentRisk
            assertEquals("UNAVAILABLE", proof.state)
            assertFalse(proof.executionAuthority)
        }
        assertEquals("UNMEASURED", CurrentAccountRisk.from(null).state)
    }
}
