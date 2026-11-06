package com.dial.van.command.settings

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class OwnerPermissionDraftTest {
    private fun selected() = JSONObject().put("permission", "email.send").put("action_id", "google.gmail.send").put("action_class", "A4")
        .put("parameter_schema", JSONObject().put("required", JSONArray().put("draft_id"))
            .put("properties", JSONObject().put("draft_id", JSONObject().put("type", "string"))))
    private fun contracts(selected: JSONObject) = JSONObject().put("command_prefix", "grant owner permission ")
        .put("native_authority_required", true).put("max_duration_ms", 1000).put("max_uses", 10)
        .put("contracts", JSONArray().put(selected))

    @Test fun `grant is exact scoped consent and contains no action approval flag`() {
        val action = selected()
        val command = OwnerPermissionDraft.command(contracts(action), action, JSONObject().put("draft_id", "draft-1"), 500, 2, 100)
        val body = JSONObject(command.removePrefix("grant owner permission "))
        assertEquals(setOf("permission", "action_id", "parameters", "expires_at_ms", "max_uses"), body.keys().asSequence().toSet())
        assertEquals("draft-1", body.getJSONObject("parameters").getString("draft_id"))
    }
    @Test fun `unknown action missing field and wrong type fail closed`() {
        val action = selected(); val catalogue = contracts(action)
        assertFailsWith<IllegalArgumentException> { OwnerPermissionDraft.command(catalogue, selected().put("action_id", "unknown"), JSONObject(), 500, 1, 100) }
        assertFailsWith<IllegalArgumentException> { OwnerPermissionDraft.command(catalogue, action, JSONObject(), 500, 1, 100) }
        assertFailsWith<IllegalArgumentException> { OwnerPermissionDraft.command(catalogue, action, JSONObject().put("draft_id", 12), 500, 1, 100) }
    }
    @Test fun `expired unlimited and wildcard scopes are refused`() {
        val action = selected(); val catalogue = contracts(action); val fields = JSONObject().put("draft_id", "draft-1")
        assertFailsWith<IllegalArgumentException> { OwnerPermissionDraft.command(catalogue, action, fields, 100, 1, 100) }
        assertFailsWith<IllegalArgumentException> { OwnerPermissionDraft.command(catalogue, action, fields, 2000, 1, 100) }
        assertFailsWith<IllegalArgumentException> { OwnerPermissionDraft.command(catalogue, action, fields, 500, 0, 100) }
        assertFailsWith<IllegalArgumentException> { OwnerPermissionDraft.command(catalogue, action, JSONObject().put("draft_id", "*"), 500, 1, 100) }
    }
    @Test fun `provider secret material cannot enter stored scope`() {
        val action = selected(); val catalogue = contracts(action)
        assertFailsWith<IllegalArgumentException> { OwnerPermissionDraft.command(catalogue, action,
            JSONObject().put("draft_id", "Bearer synthetic-credential-never-send"), 500, 1, 100) }
    }
}
