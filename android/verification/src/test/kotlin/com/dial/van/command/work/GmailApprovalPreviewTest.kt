package com.dial.van.command.work

import org.json.JSONObject
import kotlin.test.*
import kotlin.test.Test

class GmailApprovalPreviewTest {
    private val digest = "a".repeat(64)
    private fun parameters() = JSONObject().put("draft_id", "D-1").put("draft_content_sha256", digest)
    private fun preview() = JSONObject().put("draft_id", "D-1").put("draft_content_sha256", digest)
        .put("immutable_payload_send_supported", true)
        .put("body_sha256", "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
        .put("preview", JSONObject("{\"from\":\"owner@example.com\",\"to\":[\"a@example.com\"],\"cc\":[],\"bcc\":[\"b@example.com\"],\"subject\":\"Subject\",\"body\":\"hello\"}"))
    @Test fun includesHiddenRecipientsInReviewedSnapshot() {
        val result = GmailApprovalPreview.parse(parameters(), preview())!!
        assertEquals(listOf("b@example.com"), result.bcc)
        assertEquals("hello", result.body)
    }
    @Test fun refusesChangedDraftOrBody() {
        assertNull(GmailApprovalPreview.parse(parameters(), preview().put("draft_content_sha256", "b".repeat(64))))
        assertNull(GmailApprovalPreview.parse(parameters(), preview().put("draft_id", "D-2")))
        assertNull(GmailApprovalPreview.parse(parameters(), preview().apply { getJSONObject("preview").put("body", "changed") }))
    }
    @Test fun refusesMutableSendAndMalformedRecipientPreview() {
        assertNull(GmailApprovalPreview.parse(parameters(), preview().put("immutable_payload_send_supported", false)))
        assertNull(GmailApprovalPreview.parse(parameters(), preview().apply { getJSONObject("preview").remove("bcc") }))
    }
}
