package com.dial.van.browser

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class BrowserActionPlanTest {
    @Test fun `mutation editor requires actual admitted profile policy rather than guessed alias`() {
        val contract = JSONObject().put("action_id", "browser.plan.execute").put("required_action_class", "A4")
            .put("profile_mutation_policy", "gateway_authorized_only").put("profile_mutation_permitted", true)
            .put("freshness_seconds", 30).put("max_steps", 12).put("task_plan_limit", 1)
        assertEquals(true, BrowserActionPlan.mayDraft(contract))
        assertFalse(BrowserActionPlan.mayDraft(contract.put("profile_mutation_permitted", false).put("profile_alias", "authenticated_owner")))
        assertFalse(BrowserActionPlan.mayDraft(contract.put("profile_mutation_permitted", true).put("profile_mutation_policy", "read_only")))
        assertFalse(BrowserActionPlan.mayDraft(null))
    }
    @Test fun `prepare command binds owner goal exact native domain and never guesses page URL`() {
        val prepared = BrowserActionPlan.prepareTask("sid", "owner.example", "Review the draft", 1000)
        assertEquals(1030L, prepared.expiresAtUnix)
        assertEquals(true, prepared.noStaleReplay)
        val parameters = JSONObject(prepared.text.removePrefix("prepare browser task "))
        assertEquals("sid", parameters.getString("session_id")); assertEquals("owner.example", parameters.getString("target_domain"))
        assertFailsWith<IllegalArgumentException> { BrowserActionPlan.prepareTaskCommand("sid", "https://owner.example/path", "Review") }
        assertFailsWith<IllegalArgumentException> { BrowserActionPlan.prepareTaskCommand("sid", "owner.example", "x".repeat(1001)) }
    }
    private fun plan() = JSONObject().put("plan_id", "bplan_" + "a".repeat(32)).put("plan_sha256", "b".repeat(64))
        .put("session_id", "sid").put("action_class", "A4").put("status", "DRAFT").put("deadline_ms", 200)
        .put("approval_command", "execute browser plan " + JSONObject().put("session_id", "sid")
            .put("plan_id", "bplan_" + "a".repeat(32)).put("plan_sha256", "b".repeat(64)).toString())

    @Test fun `fill binds exact same element and independent value readback`() {
        val check = JSONObject().put("kind", "input_value_equals").put("selector", "#title").put("value", "Hello")
        val step = BrowserActionPlan.step("step_1", "fill_element", "#title", "Hello", check)
        assertEquals("Hello", step.getString("text"))
        assertFailsWith<IllegalArgumentException> { BrowserActionPlan.step("step_1", "fill_element", "#other", "Hello", check) }
        assertFailsWith<IllegalArgumentException> { BrowserActionPlan.step("step_1", "fill_element", "#title", "Different", check) }
    }
    @Test fun `unrelated predicate fields and duplicate effects are refused`() {
        val check = JSONObject().put("kind", "url_equals").put("url", "https://owner.example").put("text", "unrelated")
        assertFailsWith<IllegalArgumentException> { BrowserActionPlan.step("step_1", "click_element", "#go", "", check) }
        val steps = JSONArray().put(JSONObject().put("step_id", "same")).put(JSONObject().put("step_id", "same"))
        assertFailsWith<IllegalArgumentException> { BrowserActionPlan.draft("task", "target", steps, "key", 200, 100) }
    }
    @Test fun `approval must name exact session current digest and unexpired draft`() {
        assertNotNull(BrowserActionPlan.approvalCommand(plan(), "sid", 100))
        assertNull(BrowserActionPlan.approvalCommand(plan(), "different", 100))
        assertNull(BrowserActionPlan.approvalCommand(plan(), "sid", 200))
        assertNull(BrowserActionPlan.approvalCommand(plan().put("status", "UNKNOWN"), "sid", 100))
    }
    @Test fun `another pending action never approves this browser plan`() {
        val resolved = JSONObject().put("session_id", "sid").put("plan_id", plan().getString("plan_id")).put("plan_sha256", "b".repeat(64))
        assertEquals(true, BrowserActionPlan.matchesApproval(plan(), "browser.plan.execute", resolved))
        assertFalse(BrowserActionPlan.matchesApproval(plan(), "memory.erase", resolved))
        assertFalse(BrowserActionPlan.matchesApproval(plan(), "browser.plan.execute", resolved.put("plan_sha256", "c".repeat(64))))
    }
    @Test fun `success requires every effect receipt and independent result`() {
        val row = plan().put("status", "VERIFIED_SUCCESS").put("steps", JSONArray().put(JSONObject().put("step_id", "first")))
        assertEquals("The reported success lacks complete effect readback.", BrowserActionPlan.ownerOutcome(row))
        row.put("step_states", JSONObject().put("first", JSONObject().put("status", "VERIFIED")
            .put("effect_receipt", JSONObject().put("effect_dispatched", true)).put("independent_readback", JSONObject().put("postcondition_matched", true))))
        assertEquals("Every approved effect has independent matching readback.", BrowserActionPlan.ownerOutcome(row))
        assertEquals("An effect may have occurred. VAN will read evidence and will not repeat the mutation.", BrowserActionPlan.ownerOutcome(row.put("status", "UNKNOWN")))
    }
}
