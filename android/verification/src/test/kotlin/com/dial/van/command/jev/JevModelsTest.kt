package com.dial.van.command.jev

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.json.JSONArray
import org.json.JSONObject

class JevModelsTest {
    @Test
    fun `snapshot preserves optional global project and provider qualification state`() {
        val status = JSONObject()
            .put("registry_revision", "abc123")
            .put("global", JSONObject()
                .put("owner_active", true)
                .put("bypassed", false)
                .put("projects", JSONObject()
                    .put("van", true)
                    .put("dial-business-group", false)))
            .put("modules", JSONArray().put(JSONObject()
                .put("module_id", "van.attention.fields.v1")
                .put("owner_system", "VAN")
                .put("project_scope", JSONArray().put("van"))
                .put("status", "SHADOW")
                .put("effect_direction", "ANNOTATE")
                .put("consequence", "MEDIUM")
                .put("deadline_ms", 800)
                .put("fallback", JSONObject().put("class", "ABSTAIN"))
                .put("evaluation", JSONObject().put("shadow_required", true))))
        val health = JSONObject()
            .put("enabled", false)
            .put("deployment_enabled", true)
            .put("owner_active", false)
            .put("circuit", "HEALTHY")
        val provider = JSONObject()
            .put("configured", true)
            .put("qualified", false)
            .put("models", JSONArray().put(JSONObject().put("name", "jev-test")))

        val snapshot = JevJson.snapshot(status, health, provider)

        assertFalse(snapshot.serviceEnabled)
        assertTrue(snapshot.deploymentEnabled)
        assertEquals("HEALTHY", snapshot.circuit)
        assertTrue(snapshot.global.ownerActive)
        assertFalse(snapshot.global.bypassed)
        assertEquals(false, snapshot.global.projects["dial-business-group"])
        assertEquals(1, snapshot.modules.size)
        assertEquals("van.attention.fields.v1", snapshot.modules.single().id)
        assertTrue(snapshot.providerConfigured)
        assertFalse(snapshot.providerQualified)
        assertEquals(listOf("jev-test"), snapshot.providerModels)
    }

    @Test
    fun `activity and performance projections do not mint authority fields`() {
        val activity = JevJson.activity(JSONObject().put("items", JSONArray().put(JSONObject()
            .put("event", "JudgmentCompleted")
            .put("module_id", "van.intent.route.v1")
            .put("request_id", "req-1")
            .put("provider", "jev")
            .put("lifecycle_state", "SHADOW")
            .put("latency_ms", 123)
            .put("observed_at", "2026-09-25T00:00:00Z"))))
        assertEquals(1, activity.size)
        assertEquals("SHADOW", activity.single().lifecycleState)
        assertEquals(123, activity.single().latencyMs)

        val perf = JevJson.performance(JSONObject()
            .put("project_id", "van")
            .put("decisions", 10)
            .put("provider_decisions", 8)
            .put("fallbacks", 2)
            .put("fallback_rate", 0.2)
            .put("p50_latency_ms", 90.0))
        assertEquals(10, perf.decisions)
        assertEquals(2, perf.fallbacks)
        assertEquals(0.2, perf.fallbackRate)
        assertEquals(90.0, perf.p50LatencyMs)
    }

    @Test
    fun `evaluator proposals remain advisory read models`() {
        val proposals = JevJson.proposals(JSONObject().put("items", JSONArray().put(JSONObject()
            .put("proposal_id", "p-1")
            .put("module_id", "van.memory.relevance.v1")
            .put("module_revision", "rev")
            .put("recommendation", "REVISE")
            .put("rationale", "Needs more canonical state.")
            .put("proposer_lineage", "fable-primary")
            .put("status", "PENDING_INDEPENDENT_REVIEW")
            .put("proposed_at", "2026-09-25T00:00:00Z"))))
        assertEquals(1, proposals.size)
        assertEquals("REVISE", proposals.single().recommendation)
        assertEquals("PENDING_INDEPENDENT_REVIEW", proposals.single().status)
    }
    @Test
    fun `review and candidate projections preserve independent lineage`() {
        val reviews = JevJson.reviews(JSONObject().put("items", JSONArray().put(JSONObject()
            .put("review_id", "r-1")
            .put("proposal_id", "p-1")
            .put("reviewer_lineage", "independent-reviewer")
            .put("decision", "APPROVE")
            .put("rationale", "Shadow candidate only.")
            .put("reviewed_at", "2026-09-25T01:00:00Z"))))
        assertEquals(1, reviews.size)
        assertEquals("independent-reviewer", reviews.single().reviewerLineage)
        assertEquals("APPROVE", reviews.single().decision)

        val candidates = JevJson.candidates(JSONObject().put("items", JSONArray().put(JSONObject()
            .put("candidate_id", "c-1")
            .put("proposal_id", "p-1")
            .put("module_id", "van.memory.relevance.v1")
            .put("base_module_revision", "base")
            .put("candidate_module_revision", "candidate")
            .put("lifecycle_state", "SHADOW")
            .put("reviewer_lineage", "independent-reviewer")
            .put("created_at", "2026-09-25T01:05:00Z"))))
        assertEquals(1, candidates.size)
        assertEquals("SHADOW", candidates.single().lifecycleState)
        assertEquals("base", candidates.single().baseModuleRevision)
        assertEquals("candidate", candidates.single().candidateModuleRevision)
    }
    @Test
    fun `safety projection preserves deterministic breach evidence`() {
        val safety = JevJson.safety(JSONObject()
            .put("module_id", "van.attention.fields.v1")
            .put("lifecycle_state", "QUARANTINED")
            .put("healthy", false)
            .put("outcome_samples", 40)
            .put("high_confidence_error_rate", 0.08)
            .put("breaches", JSONArray().put(JSONObject()
                .put("code", "HIGH_CONFIDENCE_ERROR_RATE")
                .put("value", 0.08)
                .put("threshold", 0.05)
                .put("samples", 25))))
        assertFalse(safety.healthy)
        assertEquals("QUARANTINED", safety.lifecycleState)
        assertEquals(40, safety.outcomeSamples)
        assertEquals("HIGH_CONFIDENCE_ERROR_RATE", safety.breaches.single().code)
        assertEquals(0.05, safety.breaches.single().threshold)
    }
}
