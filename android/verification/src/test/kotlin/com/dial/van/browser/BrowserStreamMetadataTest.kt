package com.dial.van.browser

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BrowserStreamMetadataTest {
    private val snapshot = BrowserSessionSnapshot("session-1", BrowserSessionState.CONNECTING, "owner",
        BrowserViewport(800, 600, 1f, 4), null, BrowserControlHolder.OWNER, "lease-1", 3,
        null, null, false, null)
    private fun body() = JSONObject().put("protocol", 1).put("session_id", "session-1")
        .put("control_generation", 3).put("viewport_revision", 4).put("width", 800).put("height", 600)
        .put("media_epoch", "producer-peer-1")
    private fun marker(sequence: Long = 1, frame: Long = 1) = BrowserStreamMetadata.event(body()
        .put("event_type", "viewport.frame").put("event_seq", sequence).put("frame_sequence", frame)) as BrowserStreamMetadata.Event.Frame
    @Test fun `signal answer binds exact session control viewport and geometry`() {
        val answer = BrowserStreamMetadata.answer(body().put("type", "answer").put("sdp", "v=0\n"), snapshot)
        assertEquals("producer-peer-1", answer.binding.mediaEpoch)
        assertEquals("v=0\n", answer.sdp)
        for ((field, value) in listOf("session_id" to "other", "control_generation" to 4,
            "viewport_revision" to 5, "width" to 900, "height" to 601)) {
            assertFails { BrowserStreamMetadata.answer(body().put("type", "answer").put("sdp", "v=0").put(field, value), snapshot) }
        }
    }
    @Test fun `decoded frame alone or metadata alone cannot acknowledge viewport`() {
        val frame = marker()
        val gate = BrowserStreamMetadata.Gate(frame.binding)
        assertNull(gate.decoded(800, 600))
        assertTrue(gate.accept(frame))
        assertNull(gate.decoded(799, 600))
        assertNull(gate.decoded(800, 601))
        val proof = gate.decoded(800, 600)!!
        assertEquals(frame.binding, proof.binding)
        assertEquals(1L, proof.frameSequence)
        assertNull(gate.decoded(800, 600))
    }
    @Test fun `old peer epoch generation viewport or repeated marker cannot confirm new peer`() {
        val frame = marker()
        val gate = BrowserStreamMetadata.Gate(frame.binding)
        for (binding in listOf(frame.binding.copy(mediaEpoch = "old-peer"), frame.binding.copy(controlGeneration = 2),
            frame.binding.copy(viewportRevision = 3), frame.binding.copy(sessionId = "other"))) {
            assertFalse(gate.accept(frame.copy(binding = binding)))
        }
        assertNull(gate.decoded(800, 600))
        assertTrue(gate.accept(frame))
        assertFalse(gate.accept(frame))
        assertFalse(gate.accept(frame.copy(sequence = 2)))
        assertTrue(gate.accept(frame.copy(sequence = 2, frameSequence = 2)))
        assertEquals(2L, gate.decoded(800, 600)!!.frameSequence)
    }
    @Test fun `tab metadata yields actual navigation history without inventing target or security`() {
        val tab = JSONObject().put("target_id", "tab-1").put("title", "Owner page").put("url", "https://example.test")
            .put("url_digest", "digest-1").put("can_go_back", true).put("can_go_forward", false).put("loading", false)
            .put("security_state", "UNKNOWN")
        val event = BrowserStreamMetadata.event(body().put("event_type", "tab.snapshot").put("event_seq", 1)
            .put("tabs", JSONArray().put(tab)).put("active_target_id", "tab-1")) as BrowserStreamMetadata.Event.Tabs
        assertTrue(event.tabs.single().canGoBack)
        assertEquals(SecurityState.UNKNOWN, event.tabs.single().securityState)
        assertEquals("tab-1", event.activeTargetId)
        assertFails { BrowserStreamMetadata.event(body().put("event_type", "tab.snapshot").put("event_seq", 1)
            .put("tabs", JSONArray().put(tab)).put("active_target_id", "invented")) }
    }
    @Test fun `unknown malformed oversized and duplicate target metadata fail closed`() {
        assertFails { BrowserStreamMetadata.event(body().put("event_type", "viewport.frame").put("event_seq", 1).put("frame_sequence", 0)) }
        assertFails { BrowserStreamMetadata.event(body().put("event_type", "viewport.frame").put("event_seq", 1.5).put("frame_sequence", 1)) }
        assertFails { BrowserStreamMetadata.event(body().put("event_type", "raw.cdp").put("event_seq", 1)) }
        assertFails { BrowserStreamMetadata.event(body().put("protocol", 2).put("event_type", "session.state").put("event_seq", 1).put("state", "INTERACTIVE")) }
        val tab = JSONObject().put("target_id", "tab-1").put("title", "x".repeat(513))
        assertFails { BrowserStreamMetadata.event(body().put("event_type", "tab.snapshot").put("event_seq", 1).put("tabs", JSONArray().put(tab))) }
        tab.put("title", "normal")
        assertFails { BrowserStreamMetadata.event(body().put("event_type", "tab.snapshot").put("event_seq", 1).put("tabs", JSONArray().put(tab).put(tab))) }
    }
    @Test fun `file chooser event is bounded and tied to exact peer without host file paths`() {
        val event = BrowserStreamMetadata.event(body().put("event_type", "file.chooser").put("event_seq", 1)
            .put("chooser_id", "chooser-1").put("target_id", "tab-1").put("accept_types", JSONArray().put(".pdf"))
            .put("multiple", false).put("expires_in_ms", 60_000)) as BrowserStreamMetadata.Event.Chooser
        assertEquals("producer-peer-1", event.binding.mediaEpoch)
        assertEquals(listOf(".pdf"), event.acceptTypes)
        assertEquals("chooser-1", event.chooserId)
        assertFails { BrowserStreamMetadata.event(body().put("event_type", "file.chooser").put("event_seq", 1)
            .put("chooser_id", "chooser-1").put("target_id", "tab-1").put("accept_types", JSONArray())
            .put("multiple", true).put("expires_in_ms", 60_000)) }
    }
    @Test fun `producer progress and refusal events remain truthful without treating progress as completion`() {
        val progress = BrowserStreamMetadata.event(body().put("event_type", "download.available").put("event_seq", 1)
            .put("download_id", "download-1").put("state", "IN_PROGRESS")) as BrowserStreamMetadata.Event.Download
        assertEquals("IN_PROGRESS", progress.state)
        val refusal = BrowserStreamMetadata.event(body().put("event_type", "file.refused").put("event_seq", 2)
            .put("reason", "file_producer_event_refused")) as BrowserStreamMetadata.Event.Refused
        assertFalse(refusal.input)
        assertEquals(progress.binding, refusal.binding)
        assertFails { BrowserStreamMetadata.event(body().put("event_type", "download.available").put("event_seq", 1)
            .put("download_id", "download-1").put("state", "invented")) }
    }
}
