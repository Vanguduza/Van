package com.dial.van.command.owner

import org.json.JSONObject

/** Pure mapping: configuration, execution and verified owner outcome stay distinct. */
object OwnerServicePresentation {
    fun sectionAvailable(body: JSONObject, section: String): Boolean {
        if (body.optString("status") !in setOf("AVAILABLE", "PARTIAL")) return false
        val errors = body.optJSONArray("errors") ?: return true
        return (0 until errors.length()).none { errors.optJSONObject(it)?.optString("section") == section }
    }

    fun emptySection(body: JSONObject, section: String, emptyText: String): String =
        if (sectionAvailable(body, section)) emptyText
        else "Current ${section.replace('_', ' ')} information is unavailable. Refresh to retry."

    fun state(value: String): String = when (value) {
        "READY" -> "Ready · recorded verification available"
        "CONFIGURED" -> "Configured · verification still needed"
        "CONFIGURED_EGRESS_DISABLED" -> "Configured · external access disabled"
        "UNCONFIGURED" -> "Setup needed"
        "POLICY_DISABLED", "DISABLED" -> "Disabled by policy"
        "AUTH_REQUIRED" -> "Sign-in needs attention"
        "VERSION_MISMATCH" -> "Runtime version needs attention"
        "DEGRADED" -> "Service needs attention"
        "UNVERIFIED" -> "Result has not been independently verified"
        "VERIFIED_SUCCESS" -> "Verified success"
        "COMPLETED" -> "Execution complete · result unverified"
        else -> value.lowercase().replace('_', ' ').replaceFirstChar { it.uppercase() }
    }

    fun command(control: JSONObject, values: Map<String, String>): String? {
        if (!control.optBoolean("available") || control.optString("submission_path") != "/v1/commands") return null
        var command = control.optString("command_template")
        if (command.isBlank()) return null
        val fields = control.optJSONArray("required_fields")
        if (fields != null) for (index in 0 until fields.length()) {
            val field = fields.optString(index)
            val value = values[field]?.trim().orEmpty()
            if (value.isBlank() || '\n' in value || '\r' in value) return null
            command = command.replace("{$field}", value)
        }
        return command.takeIf { !Regex("\\{[a-z_]+}").containsMatchIn(it) }
    }

    fun unavailable(code: String): String = when (code) {
        "OWNER_COMMAND_NOT_REGISTERED" -> "This owner action is not available on this service."
        "PROVIDER_UNAVAILABLE" -> "The provider needs setup or verification before this action."
        "CURRENT_DEVICE_NOT_AUTHORITY_ROOT" -> "This phone did not authorize this standing work."
        "UNSUPPORTED_INTENT_IDENTIFIER" -> "This older intent needs an operator to disable it safely."
        "ALREADY_DISABLED" -> "This standing work is already disabled."
        else -> "This action is currently unavailable."
    }

    fun browserResult(body: JSONObject): String = when {
        body.optBoolean("execution_completed") -> "Execution finished. VAN has not independently confirmed the task goal."
        else -> "${state(body.optString("task_status"))}. The task goal is not yet verified."
    }

    fun browserWorkerProposal(body: JSONObject): String = when (body.opt("worker_goal_reported")) {
        true -> "The worker reports that the goal was reached. This is a proposal, not independent verification."
        false -> "The worker reports that the goal was not reached. Review the evidence and next step."
        else -> "The worker's final goal proposal was not recorded. Execution completion does not fill this gap."
    }

    fun browserEvidenceTrust(evidence: JSONObject): String {
        val trust = evidence.optString("source_trust").takeIf { !evidence.isNull("source_trust") && it.isNotBlank() }
        val injection = evidence.optString("injection_assessment").takeIf { !evidence.isNull("injection_assessment") && it.isNotBlank() }
        return "Source trust: ${trust?.replace('_', ' ') ?: "not recorded"}\n" +
            "Injection assessment: ${injection?.replace('_', ' ') ?: "not recorded"}. These labels do not verify the task goal."
    }

    fun browserEvidenceDigests(evidence: JSONObject): List<String> {
        val digests = evidence.optJSONObject("content_digests") ?: return emptyList()
        return listOf("url_digest", "dom_digest", "screenshot_digest", "extraction_digest").mapNotNull { key ->
            digests.optString(key).takeIf { !digests.isNull(key) && it.isNotBlank() }
                ?.let { "${key.removeSuffix("_digest").replace('_', ' ')} digest: $it" }
        }
    }

    fun browserMissingPostconditions(body: JSONObject): List<String> {
        val missing = body.optJSONArray("missing_postconditions")
            ?: return listOf("Required postconditions were not supplied. The task goal remains unverified.")
        val recorded = (0 until missing.length()).mapNotNull { index ->
            missing.optString(index).takeIf { !missing.isNull(index) && it.isNotBlank() }
        }
        return recorded.ifEmpty { listOf("No missing postconditions are recorded. This alone does not verify the task goal.") }
    }

    fun automationResult(run: JSONObject): String = when {
        run.optBoolean("owner_success") && run.optString("status") == "VERIFIED_SUCCESS" &&
            run.optString("verifier_status") == "VERIFIED_SUCCESS" && !run.isNull("evidence_pointer") &&
            run.optString("evidence_pointer").isNotBlank() -> "Owner result independently verified"
        run.optString("status") in setOf("VERIFIED_SUCCESS", "COMPLETED") -> "Execution finished · owner result unverified"
        else -> state(run.optString("status"))
    }

    fun missionResult(mission: JSONObject): String = when {
        mission.optBoolean("owner_success") && mission.optString("state") == "VERIFIED_SUCCESS" &&
            mission.optString("verification_scope") == "MISSION" -> "Mission outcome independently verified"
        mission.optString("state") == "VERIFIED_SUCCESS" -> "Mission reports completion · result unverified"
        else -> "Mission result: ${state(mission.optString("state"))}"
    }
}
