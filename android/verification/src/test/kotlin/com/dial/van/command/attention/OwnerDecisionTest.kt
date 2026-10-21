package com.dial.van.command.attention

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class OwnerDecisionTest {
    private fun record() = JSONObject().put("id", "decision-1").put("revision", 2).put("status", "OPEN")
        .put("expires_at_unix", 200L).put("grants_action_authority", false)
        .put("choices", JSONArray().put(JSONObject().put("id", "later").put("label", "Later")))

    @Test fun `exact custom choice carries revision reason and recovery identity`() {
        val request = OwnerDecision.parse(record()).prepareAnswer("later", " My reason ", "request-123456789", 100)
        assertEquals("later", request.getString("choice_id")); assertEquals(2, request.getInt("expected_revision"))
        assertEquals("My reason", request.getString("note")); assertEquals("request-123456789", request.getString("request_id"))
    }
    @Test fun `expired and unknown states cannot be answered`() {
        assertFalse(OwnerDecision.parse(record()).answerable(200))
        assertFalse(OwnerDecision.parse(record().put("status", "PENDING")).answerable(100))
        assertFailsWith<IllegalArgumentException> { OwnerDecision.parse(record()).prepareAnswer("later", "", "request-123456789", 201) }
    }
    @Test fun `unadvertised choice and duplicate choices fail closed`() {
        assertFailsWith<IllegalArgumentException> { OwnerDecision.parse(record()).prepareAnswer("approve", "", "request-123456789", 100) }
        val duplicate = record().getJSONArray("choices").put(JSONObject().put("id", "later").put("label", "Other"))
        assertFailsWith<IllegalArgumentException> { OwnerDecision.parse(record().put("choices", duplicate)) }
    }
    @Test fun `readback must match choice reason and exact request`() {
        val request = OwnerDecision.parse(record()).prepareAnswer("later", "why", "request-123456789", 100)
        val answered = record().put("status", "ANSWERED").put("selected_choice_id", "later")
            .put("answer_note", "why").put("resolution_request_id", "request-123456789")
        assertTrue(OwnerDecision.parse(answered).confirms(request))
        assertFalse(OwnerDecision.parse(answered.put("resolution_request_id", "different-request")).confirms(request))
        assertFalse(OwnerDecision.parse(answered.put("resolution_request_id", "request-123456789").put("answer_note", "other")).confirms(request))
    }
    @Test fun `decision must never advertise action authority`() {
        assertFailsWith<IllegalArgumentException> { OwnerDecision.parse(record().put("grants_action_authority", true)) }
    }
}
