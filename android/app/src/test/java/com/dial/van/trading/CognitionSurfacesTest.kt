package com.dial.van.trading

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * TRD-REV51-130 owner cognition surfaces.
 *
 * These tests exercise the wire model consumed by the dedicated Cognition page.
 * The page is a read surface: qualification/research/evolution evidence is visible,
 * while live advisory and live eligibility remain explicitly disabled/not claimed.
 */
class CognitionSurfacesTest {

    private val payload = """
        {
          "ledger_available": true,
          "authority": {
            "cognition_mode": "OFFLINE_EVOLUTION+SHADOW_LIVE",
            "live_advisory": "DISABLED",
            "live_status": "NOT_CLAIMED",
            "model_hierarchy": ["fable-5.1","gpt-6-astra","claude-opus-5","gpt-5.6-sol"],
            "execution_authority": "VATI_RISK_AUTHORITY_AND_EXECUTION_ROUTER_ONLY"
          },
          "summary": {
            "assessments": 7,
            "shadow_decisions": 7,
            "handoffs": 1,
            "research_missions": 2,
            "improvement_proposals": 1,
            "proposal_admissions": 1
          },
          "models": [{
            "model_id": "fable-5.1",
            "assessments": 7,
            "latest": {"verdict":"CONCUR","confidence":"0.73"},
            "performance": {"qualified":false,"sample_sufficient":false}
          }],
          "research": {
            "missions": [{"mission_id":"m-1","state":"RUNNING","hypothesis":"edge drift?"}],
            "recent_packets": [],
            "recent_syntheses": [],
            "latest_yield": null
          },
          "evolution": {
            "proposals": [{
              "proposal_id":"p-1",
              "title":"candidate improvement",
              "live_affecting":true,
              "admission":{"decision":"HELD_FOR_AUTHORISED_REVIEW"}
            }],
            "recent_admissions":[]
          },
          "rejections":{"total":3,"by_category":{"safety":2,"stale_or_unknown_data":1},"by_reason":{}},
          "expansion":{"mode_counts":{"SHADOW":4},"recent":[],"live_promotion_claimed":false},
          "shadow":{"by_status":{"OPEN":1},"recent":[]},
          "handoffs":[],
          "decision_exam":null
        }
    """.trimIndent()

    @Test
    fun cognitionSnapshotPreservesAuthorityAndEvidenceTruth() {
        val model = CognitionSnapshot.parse(payload)
        assertNotNull(model)
        model!!
        assertTrue(model.ledgerAvailable)
        assertEquals("OFFLINE_EVOLUTION+SHADOW_LIVE", model.cognitionMode)
        assertEquals("DISABLED", model.liveAdvisory)
        assertEquals("NOT_CLAIMED", model.liveStatus)
        assertEquals(
            listOf("fable-5.1", "gpt-6-astra", "claude-opus-5", "gpt-5.6-sol"),
            model.modelHierarchy,
        )
        assertEquals(7, model.summary["assessments"])
        assertEquals(7, model.summary["shadow_decisions"])
        assertEquals(1, model.models.size)
        assertFalse(model.models.single().qualified ?: true)
        assertEquals("RUNNING", model.missions.single().state)
        assertTrue(model.proposals.single().liveAffecting)
        assertEquals("HELD_FOR_AUTHORISED_REVIEW", model.proposals.single().admission)
        assertEquals(4, model.expansionModes["SHADOW"])
    }

    @Test
    fun malformedPayloadDoesNotInventCognitionState() {
        assertEquals(null, CognitionSnapshot.parse("not-json"))
    }
}
