package com.dial.van.browser

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BrowserSessionRecordsTest {
    @Test fun `server inventory retains target identity digest and active state`() {
        val rows = JSONArray().put(JSONObject().put("target_id", "target-1").put("title", "Owner page")
            .put("url_digest", "sha256:page").put("is_active", true))
        val tab = BrowserSessionRecords.tabs(rows).single()
        assertEquals("target-1", tab.id)
        assertEquals("Owner page", tab.title)
        assertEquals("sha256:page", tab.urlDigest)
        assertTrue(tab.active)
    }
    @Test fun `null digest and title do not become secret or invented address`() {
        val tab = BrowserSessionRecords.tabs(JSONArray().put(JSONObject().put("target_id", "target-1")
            .put("title", JSONObject.NULL).put("url_digest", JSONObject.NULL).put("is_active", false))).single()
        assertEquals("Untitled tab", tab.title)
        assertNull(tab.urlDigest)
    }
    @Test fun `malformed or repeated identity is unavailable rather than empty records`() {
        assertFails { BrowserSessionRecords.tabs(JSONArray().put(JSONObject().put("title", "page"))) }
        val row = JSONObject().put("target_id", "target-1").put("is_active", false)
        assertFails { BrowserSessionRecords.tabs(JSONArray().put(row).put(row)) }
        assertFails { BrowserSessionRecords.events(JSONArray().put(JSONObject().put("event_id", ""))) }
    }
    @Test fun `events preserve durable time severity evidence without claiming work completion`() {
        val event = BrowserSessionRecords.events(JSONArray().put(JSONObject().put("event_id", "event-1")
            .put("summary", "Owner took control").put("severity", "INFO")
            .put("occurred_at_ms", 123L).put("evidence_ref", "receipt:1"))).single()
        assertEquals("Owner took control", event.summary)
        assertEquals("receipt:1", event.evidenceRef)
        assertEquals(123L, event.occurredAtMs)
    }
}
