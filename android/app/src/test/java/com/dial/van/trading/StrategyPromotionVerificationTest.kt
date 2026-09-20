package com.dial.van.trading

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class StrategyPromotionVerificationTest {

    private fun candidate(
        capsuleHash: String = "parent-hash",
        validationHash: String = "validation-hash",
    ) = StrategyPromotionCandidate(
        strategyId = "FX-TREND-PULLBACK-01",
        currentState = "DEMO",
        targetState = "SHADOW",
        capsuleHash = capsuleHash,
        validationHash = validationHash,
        certificateId = "cert-1",
        certificate = buildJsonObject {
            put("strategy_id", "FX-TREND-PULLBACK-01")
            put("capsule_hash", capsuleHash)
            put("validation_hash", validationHash)
        },
        evidenceRefs = listOf("artifact:validation"),
        dataManifestHash = "manifest-1",
        dsrProbability = 0.97,
        pboProbability = 0.05,
        expectancyR = 0.25,
        expectancyLowerBoundR = 0.08,
        profitFactor = 1.6,
        maxDrawdown = 0.07,
        certificateEventHash = "cert-event",
        certificateEventMs = 1234L,
    )

    private fun receipt(
        validationHash: String = "validation-hash",
        capsuleHash: String = "promoted-hash",
        eventHash: String = "event-hash",
        target: String = "SHADOW",
    ): JsonObject = buildJsonObject {
        put("promoted", true)
        put("strategy_id", "FX-TREND-PULLBACK-01")
        put("to", target)
        put("validation_hash", validationHash)
        put("capsule_hash", capsuleHash)
        put("event_hash", eventHash)
    }

    @Test
    fun transportSuccessMustBeBoundToExactCandidateAndLedgerEvidence() {
        val c = candidate()
        assertTrue(StrategyPromotionVerification.receiptMatches(c, receipt()))
        assertFalse(
            StrategyPromotionVerification.receiptMatches(
                c, receipt(validationHash = "other-validation")
            )
        )
        assertFalse(
            StrategyPromotionVerification.receiptMatches(
                c, receipt(capsuleHash = c.capsuleHash)
            )
        )
        assertFalse(
            StrategyPromotionVerification.receiptMatches(
                c, receipt(eventHash = "")
            )
        )
        assertFalse(
            StrategyPromotionVerification.receiptMatches(
                c, receipt(target = "CERTIFIED_LIVE")
            )
        )
    }

    @Test
    fun oldParentCertificateMustDisappearBeforeCompletionIsClaimed() {
        val c = candidate()
        assertTrue(StrategyPromotionVerification.oldParentStillOffered(c, listOf(c)))
        val next = candidate(
            capsuleHash = "promoted-hash",
            validationHash = "new-validation",
        )
        assertFalse(StrategyPromotionVerification.oldParentStillOffered(c, listOf(next)))
        assertTrue(StrategyPromotionVerification.verified(c, receipt(), emptyList()))
        assertFalse(StrategyPromotionVerification.verified(c, receipt(), listOf(c)))
    }

    @Test
    fun candidateParserRequiresSealedIdentityAndPreservesEvidence() {
        val body = """
            {
              "candidates": [{
                "strategy_id": "FX-TREND-PULLBACK-01",
                "current_state": "DEMO",
                "target_state": "SHADOW",
                "capsule_hash": "parent-hash",
                "validation_hash": "validation-hash",
                "certificate_id": "cert-1",
                "certificate": {
                  "strategy_id": "FX-TREND-PULLBACK-01",
                  "capsule_hash": "parent-hash",
                  "validation_hash": "validation-hash"
                },
                "evidence_refs": ["artifact:validation"],
                "data_manifest_hash": "manifest-1",
                "dsr_probability": 0.97,
                "pbo_probability": 0.05,
                "expectancy_R": 0.25,
                "expectancy_lower_bound_R": 0.08,
                "profit_factor": 1.6,
                "max_drawdown": 0.07,
                "certificate_event_hash": "cert-event",
                "certificate_event_ms": 1234
              }]
            }
        """.trimIndent()
        val parsed = StrategyPromotionCandidate.parseAll(body)
        assertNotNull(parsed)
        assertEquals(1, parsed!!.size)
        assertEquals(listOf("artifact:validation"), parsed.single().evidenceRefs)
        assertEquals("manifest-1", parsed.single().dataManifestHash)

        assertEquals(
            null,
            StrategyPromotionCandidate.parseAll(
                """{"candidates":[{"strategy_id":"FX","target_state":"SHADOW","validation_hash":"v"}]}"""
            )
        )
    }
}
