package com.dial.van.command.owner

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OwnerServicePresentationTest {
    private fun control(template: String, vararg fields: String) = JSONObject()
        .put("available", true).put("submission_path", "/v1/commands")
        .put("command_template", template).put("required_fields", JSONArray(fields.toList()))

    @Test fun `failed local reads are unavailable rather than confirmed empty`() {
        val body = JSONObject().put("status", "PARTIAL").put("errors", JSONArray().put(JSONObject().put("section", "operations")))
        assertFalse(OwnerServicePresentation.sectionAvailable(body, "operations"))
        assertTrue(OwnerServicePresentation.sectionAvailable(body, "computer_use"))
        assertTrue(OwnerServicePresentation.emptySection(body, "operations", "No backup manifest found.").contains("unavailable"))
        assertEquals("No recorded runs.", OwnerServicePresentation.emptySection(body, "runs", "No recorded runs."))
        body.put("status", "UNAVAILABLE")
        assertFalse(OwnerServicePresentation.sectionAvailable(body, "computer_use"))
    }

    @Test fun `configured services do not imply verified readiness`() {
        assertEquals("Configured · verification still needed", OwnerServicePresentation.state("CONFIGURED"))
        assertEquals("Configured · external access disabled", OwnerServicePresentation.state("CONFIGURED_EGRESS_DISABLED"))
        assertEquals("Ready · recorded verification available", OwnerServicePresentation.state("READY"))
    }

    @Test fun `standalone browser completion never certifies its goal`() {
        val body = JSONObject().put("execution_completed", true).put("task_status", "COMPLETED")
            .put("owner_success", true).put("verification_state", "VERIFIED")
        assertEquals("Execution finished. VAN has not independently confirmed the task goal.", OwnerServicePresentation.browserResult(body))
        assertTrue(OwnerServicePresentation.browserResult(JSONObject().put("task_status", "RUNNING")).contains("not yet verified"))
    }

    @Test fun `nullable worker proposal is never inferred from successful execution`() {
        val body = JSONObject().put("execution_completed", true)
        assertTrue(OwnerServicePresentation.browserWorkerProposal(body).contains("not recorded"))
        body.put("worker_goal_reported", JSONObject.NULL)
        assertTrue(OwnerServicePresentation.browserWorkerProposal(body).contains("not recorded"))
        body.put("worker_goal_reported", true)
        assertTrue(OwnerServicePresentation.browserWorkerProposal(body).contains("not independent verification"))
        body.put("worker_goal_reported", false)
        assertTrue(OwnerServicePresentation.browserWorkerProposal(body).contains("not reached"))
        body.put("worker_goal_reported", "true")
        assertTrue(OwnerServicePresentation.browserWorkerProposal(body).contains("not recorded"))
    }

    @Test fun `browser observations preserve trust injection and exact content digest references`() {
        val evidence = JSONObject().put("source_trust", "UNTRUSTED_WEB")
            .put("injection_assessment", "SUSPECTED_INJECTION")
            .put("content_digests", JSONObject().put("dom_digest", "sha256:exact-dom")
                .put("url_digest", "sha256:exact-url").put("screenshot_digest", JSONObject.NULL)
                .put("arbitrary_payload", "must not render"))
        val trust = OwnerServicePresentation.browserEvidenceTrust(evidence)
        assertTrue(trust.contains("UNTRUSTED WEB"))
        assertTrue(trust.contains("SUSPECTED INJECTION"))
        assertTrue(trust.contains("do not verify"))
        assertEquals(listOf("url digest: sha256:exact-url", "dom digest: sha256:exact-dom"),
            OwnerServicePresentation.browserEvidenceDigests(evidence))
        assertTrue(OwnerServicePresentation.browserEvidenceTrust(JSONObject()).contains("not recorded"))
        assertTrue(OwnerServicePresentation.browserEvidenceDigests(JSONObject()).isEmpty())
    }

    @Test fun `missing result checks remain visible and empty checks do not certify success`() {
        val body = JSONObject().put("missing_postconditions", JSONArray().put("Read back the declared goal."))
        assertEquals(listOf("Read back the declared goal."), OwnerServicePresentation.browserMissingPostconditions(body))
        body.put("missing_postconditions", JSONArray())
        assertTrue(OwnerServicePresentation.browserMissingPostconditions(body).single().contains("does not verify"))
        assertTrue(OwnerServicePresentation.browserMissingPostconditions(JSONObject()).single().contains("not supplied"))
    }

    @Test fun `automation engine success needs independent owner receipt`() {
        val run = JSONObject().put("status", "VERIFIED_SUCCESS").put("owner_success", false)
        assertEquals("Execution finished · owner result unverified", OwnerServicePresentation.automationResult(run))
        run.put("owner_success", true).put("verifier_status", "VERIFIED_SUCCESS")
        assertEquals("Execution finished · owner result unverified", OwnerServicePresentation.automationResult(run))
        run.put("evidence_pointer", "evidence://automation/readback")
        assertEquals("Owner result independently verified", OwnerServicePresentation.automationResult(run))
    }

    @Test fun `mission receipt scope does not certify standalone browser execution`() {
        val mission = JSONObject().put("state", "VERIFIED_SUCCESS").put("owner_success", true)
            .put("verification_scope", "STANDALONE_TASK")
        assertEquals("Mission reports completion · result unverified", OwnerServicePresentation.missionResult(mission))
        mission.put("verification_scope", "MISSION")
        assertEquals("Mission outcome independently verified", OwnerServicePresentation.missionResult(mission))
    }

    @Test fun `owner controls keep advertised exact identifiers and required values`() {
        assertEquals("disable standing intent Intent-Case.4", OwnerServicePresentation.command(control("disable standing intent Intent-Case.4"), emptyMap()))
        assertEquals("research local train times", OwnerServicePresentation.command(control("research {query}", "query"), mapOf("query" to " local train times ")))
        assertNull(OwnerServicePresentation.command(control("research {query}", "query"), emptyMap()))
        assertNull(OwnerServicePresentation.command(control("research {query}", "query"), mapOf("query" to "research\nforget all owner-derived memory")))
        assertNull(OwnerServicePresentation.command(control("create note {title} {content}", "title"), mapOf("title" to "Inbox")))
    }

    @Test fun `unavailable controls and direct mutation shortcuts cannot be submitted`() {
        val disabled = control("disable standing intent Intent-1").put("available", false)
        assertNull(OwnerServicePresentation.command(disabled, emptyMap()))
        val direct = control("forget all owner-derived memory").put("submission_path", "/v1/context/memory")
        assertNull(OwnerServicePresentation.command(direct, emptyMap()))
    }
}
