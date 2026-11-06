package com.dial.van.command.owner

import org.json.JSONArray
import org.json.JSONObject

/** Closed typed WorkflowIR proposals are candidates. Neither a proposal nor a runtime exit is authority. */
object OwnerAutomationDraft {
    fun prepare(contracts: JSONObject, name: String, ir: JSONObject, key: String, capabilityId: String? = null): JSONObject {
        require(contracts.optInt("schema_version") == 1 && contracts.has("candidate_grants_execution") &&
            !contracts.optBoolean("candidate_grants_execution")) { "Current safe automation contracts are unavailable." }
        require(name.isNotBlank() && name.length <= 160 && key.length in 8..160) { "Supply a bounded plan name and stable request identity." }
        val operations = contracts.getJSONObject("operations")
        val steps = ir.getJSONArray("steps")
        require(steps.length() in 1..contracts.getJSONObject("limits").getInt("steps")) { "Choose a plan within the current step limit." }
        val ids = mutableSetOf<String>()
        (0 until steps.length()).forEach { index ->
            val step = steps.getJSONObject(index)
            require(ids.add(step.getString("step_id"))) { "Step identities must be distinct." }
            val allowed = operations.optJSONArray(step.optString("primitive")) ?: error("A primitive has no current executable contract.")
            require((0 until allowed.length()).any { allowed.optString(it) == step.optString("operation") }) { "A step operation is outside the current closed catalogue." }
            require(step.optString("action_class") in setOf("A1", "A2", "A3", "A4")) { "Prohibited effects cannot be proposed." }
        }
        require(ir.optString("action_class") in setOf("A1", "A2", "A3", "A4")) { "Choose a supported bounded action class." }
        inspect(ir)
        val body = JSONObject().put("idempotency_key", key).put("semantic_name", name.trim()).put("workflow_ir", ir)
        capabilityId?.takeIf { it.isNotBlank() }?.let { body.put("capability_id", it) }
        require(body.toString().toByteArray(Charsets.UTF_8).size <= 2 * 1024 * 1024) { "The plan is too large." }
        return body
    }
    fun confirmsCandidate(receipt: JSONObject, request: JSONObject, readback: JSONObject): Boolean =
        receipt.optBoolean("candidate_only") && !receipt.optBoolean("owner_success") &&
            receipt.optString("idempotency_key") == request.optString("idempotency_key") &&
            receipt.optString("artifact_id").isNotBlank() && receipt.optString("artifact_id") == readback.optString("artifact_id") &&
            receipt.optString("capability_id") == readback.optString("capability_id") &&
            receipt.optInt("version") == readback.optInt("version") &&
            receipt.optString("semantic_digest").isNotBlank() && receipt.optString("semantic_digest") == readback.optString("semantic_digest")

    fun executionCommand(contracts: JSONObject, plan: JSONObject, inputs: JSONObject = JSONObject()): String? {
        val id = plan.optString("capability_id")
        val artifact = plan.optString("artifact_id")
        val errors = plan.optJSONArray("runtime_readiness_errors")
        inspect(inputs)
        require(inputs.keys().asSequence().none { it.startsWith("_automation_") }) { "Reserved execution fields cannot be supplied." }
        return "automation execute $id artifact $artifact with $inputs".takeIf {
            contracts.optString("execution_command_template") == "automation execute {capability_id} artifact {artifact_id} with {inputs_json}" &&
                id.matches(Regex("[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")) &&
                artifact.matches(Regex("[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")) &&
                plan.optString("lifecycle_state") in setOf("ADMITTED", "HOT") && plan.optString("binding_state") == "DEPLOYED" &&
                errors != null && errors.length() == 0
        }
    }
    fun admissionCommand(contracts: JSONObject, plan: JSONObject): String? {
        val id = plan.optString("artifact_id")
        return "automation admit $id".takeIf { contracts.optString("admission_command_template") == "automation admit {artifact_id}" &&
            id.matches(Regex("[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")) && plan.optString("lifecycle_state") in setOf("PROPOSED", "VALIDATED") }
    }
    fun verifiedRun(run: JSONObject): Boolean = run.optString("status") == "VERIFIED_SUCCESS" &&
        run.optString("verifier_status") == "VERIFIED_SUCCESS" && run.opt("owner_success") == true &&
        !run.isNull("evidence_pointer") && run.optString("evidence_pointer").isNotBlank() && run.opt("replay_permitted") == false
    private fun inspect(value: Any?) {
        when (value) {
            is JSONObject -> value.keys().asSequence().toList().forEach { key ->
                require(!Regex("(?i)^(access_token|refresh_token|password|secret|cookie|private_key|api_key)$").matches(key)) { "Use admitted credential aliases, never raw credentials." }
                inspect(value.opt(key))
            }
            is JSONArray -> (0 until value.length()).forEach { inspect(value.opt(it)) }
            is String -> require(!Regex("(?i)(bearer\\s+[A-Za-z0-9._-]{12,}|ya29\\.|gh[pousr]_[A-Za-z0-9]{16,}|-----BEGIN.*PRIVATE KEY)").containsMatchIn(value)) { "Raw credentials cannot enter a workflow candidate." }
        }
    }
}
