package com.dial.van.browser

import org.json.JSONArray
import org.json.JSONObject

/** Owner review of exact native effects; draft creation and verified execution stay separate. */
object BrowserActionPlan {
    fun mayDraft(contract: JSONObject?): Boolean = contract != null && contract.opt("profile_mutation_permitted") == true &&
        contract.optString("profile_mutation_policy") == "gateway_authorized_only" && contract.optString("action_id") == "browser.plan.execute" &&
        contract.optString("required_action_class") == "A4" && contract.optInt("freshness_seconds") == 30 &&
        contract.optInt("max_steps") in 1..12 && contract.optInt("task_plan_limit") == 1
    data class TaskPreparation(val text: String, val expiresAtUnix: Long, val noStaleReplay: Boolean)
    fun prepareTask(sessionId: String, domain: String, goal: String, nowUnix: Long): TaskPreparation {
        require(nowUnix in 1..(Long.MAX_VALUE - 30)) { "A current bounded preparation timestamp is required." }
        return TaskPreparation(prepareTaskCommand(sessionId, domain, goal), nowUnix + 30, true)
    }
    fun prepareTaskCommand(sessionId: String, domain: String, goal: String): String {
        require(sessionId.isNotBlank() && domain.matches(Regex("[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")) &&
            !domain.contains("..") && goal.isNotBlank() && goal.length <= 1000 && '\u0000' !in goal) { "Supply the exact current domain and a bounded owner goal." }
        return "prepare browser task " + JSONObject().put("session_id", sessionId).put("target_domain", domain).put("goal", goal.trim())
    }
    fun step(id: String, operation: String, selector: String, text: String, predicate: JSONObject): JSONObject {
        require(id.matches(Regex("[A-Za-z0-9_-]{1,64}"))) { "Step identity is invalid." }
        require(selector.isNotBlank() && selector.length <= 1024) { "Supply a bounded exact element selector." }
        require(operation in setOf("click_element", "fill_element")) { "Unsupported browser effect." }
        val kind = predicate.optString("kind")
        val shape = when (kind) {
            "url_equals" -> setOf("kind", "url")
            "element_text_equals" -> setOf("kind", "selector", "text")
            "element_attribute_equals" -> setOf("kind", "selector", "attribute", "value")
            "input_value_equals" -> setOf("kind", "selector", "value")
            else -> error("Select an exact supported result check.")
        }
        require(predicate.keys().asSequence().toSet() == shape) { "The result check contains unrelated fields." }
        if (operation == "fill_element") require(text.length <= 4096 && kind == "input_value_equals" &&
            predicate.optString("selector") == selector && predicate.optString("value") == text) {
            "Filling requires an independent readback of that exact element value."
        }
        return JSONObject().put("step_id", id).put("operation", operation).put("selector", selector)
            .put("postcondition", predicate).also { if (operation == "fill_element") it.put("text", text) }
    }

    fun draft(taskId: String, targetId: String, steps: JSONArray, requestId: String,
        deadlineMs: Long, nowMs: Long): JSONObject {
        require(taskId.isNotBlank() && targetId.isNotBlank()) { "Choose the current linked task and browser target." }
        require(steps.length() in 1..12) { "A plan needs 1 to 12 exact steps." }
        require((0 until steps.length()).map { steps.getJSONObject(it).getString("step_id") }.distinct().size == steps.length()) {
            "Step identities must be distinct."
        }
        require(deadlineMs > nowMs && deadlineMs <= nowMs + 900_000L) { "The plan must expire within fifteen minutes." }
        require(requestId.isNotBlank() && requestId.length <= 128) { "Draft request identity is invalid." }
        return JSONObject().put("task_id", taskId).put("target_id", targetId).put("steps", steps)
            .put("idempotency_key", requestId).put("deadline_ms", deadlineMs)
    }

    fun approvalCommand(plan: JSONObject, sessionId: String, nowMs: Long): String? {
        val id = plan.optString("plan_id")
        val sha = plan.optString("plan_sha256")
        val exact = plan.optString("approval_command")
        val parameters = exact.takeIf { it.startsWith("execute browser plan ") }?.let {
            runCatching { JSONObject(it.removePrefix("execute browser plan ")) }.getOrNull()
        }
        return exact.takeIf { plan.optString("session_id") == sessionId &&
            id.matches(Regex("bplan_[a-f0-9]{32}")) && sha.matches(Regex("[a-f0-9]{64}")) &&
            plan.optString("status") == "DRAFT" && plan.optString("action_class") == "A4" &&
            plan.optLong("deadline_ms") > nowMs && parameters != null &&
            parameters.keys().asSequence().toSet() == setOf("session_id", "plan_id", "plan_sha256") &&
            matchesApproval(plan, "browser.plan.execute", parameters) }
    }

    fun matchesApproval(plan: JSONObject, action: String, resolved: JSONObject): Boolean =
        action == "browser.plan.execute" && resolved.keys().asSequence().toSet() == setOf("plan_id", "plan_sha256", "session_id") && resolved.optString("plan_id") == plan.optString("plan_id") &&
            resolved.optString("plan_sha256") == plan.optString("plan_sha256") &&
            resolved.optString("session_id") == plan.optString("session_id")

    fun ownerOutcome(plan: JSONObject): String {
        val steps = plan.optJSONArray("steps")
        val states = plan.optJSONObject("step_states")
        val allVerified = steps != null && steps.length() > 0 && (0 until steps.length()).all { index ->
            val state = states?.optJSONObject(steps.getJSONObject(index).optString("step_id"))
            state?.optString("status") == "VERIFIED" && state.optJSONObject("effect_receipt")?.optBoolean("effect_dispatched") == true &&
                state.optJSONObject("independent_readback")?.optBoolean("postcondition_matched") == true
        }
        return when (plan.optString("status")) {
            "VERIFIED_SUCCESS" -> if (allVerified) "Every approved effect has independent matching readback." else "The reported success lacks complete effect readback."
            "DRAFT" -> "Prepared for review; no effect is authorized yet."
            "RUNNING" -> "Approved plan is executing; the final result is pending."
            "UNKNOWN" -> "An effect may have occurred. VAN will read evidence and will not repeat the mutation."
            "UNVERIFIABLE" -> "Execution could not establish the exact required result."
            "CANCELLED" -> "Future effects are fenced. Already-dispatched effects are not undone."
            else -> "The current plan result is unknown."
        }
    }
}
