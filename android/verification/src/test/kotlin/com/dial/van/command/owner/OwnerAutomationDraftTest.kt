package com.dial.van.command.owner

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertFails
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OwnerAutomationDraftTest {
    private fun catalog() = JSONObject().put("schema_version", 1).put("candidate_grants_execution", false)
        .put("operations", JSONObject().put("MAP_FIELDS", JSONArray().put("map_fields"))).put("limits", JSONObject().put("steps", 40))
        .put("execution_command_template", "automation execute {capability_id} artifact {artifact_id} with {inputs_json}")
        .put("admission_command_template", "automation admit {artifact_id}")
    private fun ir() = JSONObject().put("action_class", "A1").put("steps", JSONArray().put(JSONObject().put("step_id", "map")
        .put("primitive", "MAP_FIELDS").put("operation", "map_fields").put("action_class", "A1")))
    private fun plan() = JSONObject().put("artifact_id", "artifact-1").put("capability_id", "capability-1").put("version", 1)
        .put("lifecycle_state", "ADMITTED").put("binding_state", "DEPLOYED").put("runtime_readiness_errors", JSONArray()).put("semantic_digest", "sha256:sealed")
    @Test fun `candidate permits current closed IR but no scripts unknown operation A5 or raw credentials`() {
        assertNotNull(OwnerAutomationDraft.prepare(catalog(), "Owner mapping", ir(), "request-id"))
        assertFails { OwnerAutomationDraft.prepare(catalog().put("candidate_grants_execution", true), "Owner mapping", ir(), "request-id") }
        assertFails { OwnerAutomationDraft.prepare(catalog(), "Owner mapping", ir().put("secret", "value"), "request-id") }
        val unknown = ir().also { it.getJSONArray("steps").getJSONObject(0).put("operation", "eval") }
        assertFails { OwnerAutomationDraft.prepare(catalog(), "Owner mapping", unknown, "request-id") }
        assertFails { OwnerAutomationDraft.prepare(catalog(), "Owner mapping", ir().put("action_class", "A5"), "request-id") }
    }
    @Test fun `candidate recovery matches request and immutable independently read artifact`() {
        val request = OwnerAutomationDraft.prepare(catalog(), "Owner mapping", ir(), "request-id")
        val receipt = plan().put("candidate_only", true).put("owner_success", false).put("idempotency_key", "request-id")
        assertTrue(OwnerAutomationDraft.confirmsCandidate(receipt, request, plan()))
        assertFalse(OwnerAutomationDraft.confirmsCandidate(receipt.put("idempotency_key", "other"), request, plan()))
        assertFalse(OwnerAutomationDraft.confirmsCandidate(receipt.put("idempotency_key", "request-id"), request, plan().put("artifact_id", "other")))
    }
    @Test fun `execution seals exact admitted artifact and inputs and blocks reserved fields`() {
        val command = OwnerAutomationDraft.executionCommand(catalog(), plan(), JSONObject().put("amount", 4))
        assertTrue(command!!.contains("artifact artifact-1 with")); assertTrue(command.contains("\"amount\":4"))
        assertNull(OwnerAutomationDraft.executionCommand(catalog(), plan().put("lifecycle_state", "PROPOSED")))
        assertNull(OwnerAutomationDraft.executionCommand(catalog(), plan().put("runtime_readiness_errors", JSONArray().put("missing-binding"))))
        assertFails { OwnerAutomationDraft.executionCommand(catalog(), plan(), JSONObject().put("_automation_artifact_id", "other")) }
        assertNotNull(OwnerAutomationDraft.admissionCommand(catalog(), plan().put("lifecycle_state", "PROPOSED")))
    }
    @Test fun `engine exit alone does not verify owner run or permit replay`() {
        val run = JSONObject().put("status", "VERIFIED_SUCCESS").put("verifier_status", "VERIFIED_SUCCESS").put("owner_success", true)
            .put("evidence_pointer", "receipt:exact").put("replay_permitted", false)
        assertTrue(OwnerAutomationDraft.verifiedRun(run))
        assertFalse(OwnerAutomationDraft.verifiedRun(run.put("verifier_status", "NOT_VERIFIED")))
        assertFalse(OwnerAutomationDraft.verifiedRun(run.put("verifier_status", "VERIFIED_SUCCESS").put("replay_permitted", true)))
    }
}
