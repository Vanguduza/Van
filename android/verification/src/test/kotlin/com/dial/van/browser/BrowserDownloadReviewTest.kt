package com.dial.van.browser

import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BrowserDownloadReviewTest {
    private fun record(state: String = "COMPLETED", actions: List<String> = listOf("DELETE"), id: String = "download-1") =
        JSONObject().put("download_id", id).put("suggested_name", "receipt.pdf")
            .put("mime_type", "application/pdf").put("byte_size", 4096)
            .put("state", state).put("dangerous", false).put("actions", JSONArray(actions))
    private fun download(state: String = "COMPLETED") = BrowserDownloadReview.rows(JSONArray().put(record(state))).single()
    private fun receipt(id: String = "download-1", state: String = "DELETED") =
        JSONObject().put("download_id", id).put("state", state)

    @Test fun `host completion quarantined status and unknown state do not claim local transfer`() {
        assertTrue(download().ownerState.contains("no phone copy is confirmed"))
        assertTrue(download("QUARANTINED").ownerState.contains("transfer are blocked"))
        assertTrue(download("IN_PROGRESS").ownerState.contains("progress is not supplied"))
        assertFalse(download("FUTURE_HOST_STATE").mayDelete)
        assertTrue(download("FUTURE_HOST_STATE").ownerState.contains("unknown"))
        assertTrue(BrowserDownloadReview.TRANSFER_UNAVAILABLE.contains("No phone file has been saved"))
        assertTrue(BrowserDownloadReview.UPLOAD_UNAVAILABLE.contains("will not read or send"))
    }

    @Test fun `deletion requires advertised action identifier and a supported host transition`() {
        for (state in listOf("COMPLETED", "QUARANTINED", "FAILED")) assertTrue(download(state).mayDelete)
        for (state in listOf("CREATED", "IN_PROGRESS", "DELETED", "UNKNOWN")) assertFalse(download(state).mayDelete)
        assertFalse(BrowserDownloadReview.rows(JSONArray().put(record(actions = listOf("SEND_TO_PHONE")))).single().mayDelete)
        assertFalse(BrowserDownloadReview.rows(JSONArray().put(record(id = ""))).single().mayDelete)
    }

    @Test fun `metadata absence stays unknown instead of a zero-byte empty file`() {
        val row = record().put("byte_size", JSONObject.NULL).put("mime_type", JSONObject.NULL)
        val parsed = BrowserDownloadReview.rows(JSONArray().put(row)).single()
        assertNull(parsed.byteSize)
        assertEquals("Type not supplied", parsed.mime)
        assertFailsWith<Exception> { BrowserDownloadReview.rows(JSONArray().put("invalid record")) }
    }

    @Test fun `deletion needs exact receipt and independent record readback`() = runBlocking {
        var requests = 0
        var reads = 0
        val result = BrowserDownloadReview.delete(download(), request = { requests++; receipt() },
            read = { reads++; JSONArray().put(record("DELETED")) })
        assertNull(result.error)
        assertFalse(result.outcomeUnknown)
        assertEquals("DELETED", result.confirmedDownloads!!.single().state)
        assertEquals(1, requests)
        assertEquals(1, reads)
    }

    @Test fun `lost replies stale readback and wrong identifiers remain unknown without retry`() = runBlocking {
        for (mode in listOf("lost reply", "lost read", "wrong id", "old state", "missing row", "malformed read", "malformed reply")) {
            var requests = 0
            var reads = 0
            val result = BrowserDownloadReview.delete(download(), request = {
                requests++
                if (mode == "lost reply") throw IOException("applied but lost")
                if (mode == "malformed reply") return@delete JSONObject("not JSON")
                receipt(id = if (mode == "wrong id") "another-download" else "download-1")
            }, read = {
                reads++
                when (mode) {
                    "lost read" -> throw IOException("read unavailable")
                    "old state" -> JSONArray().put(record())
                    "missing row" -> JSONArray()
                    "malformed read" -> JSONArray().put("broken projection")
                    else -> JSONArray().put(record("DELETED"))
                }
            })
            assertTrue(result.outcomeUnknown, mode)
            assertNull(result.confirmedDownloads, mode)
            assertTrue(result.error!!.contains("may already have been applied"), mode)
            assertEquals(1, requests, mode)
            assertEquals(if (mode in setOf("lost reply", "wrong id", "malformed reply")) 0 else 1, reads, mode)
        }
    }

    @Test fun `refusal unsupported action and cancellation do not invent removal`() = runBlocking {
        var requests = 0
        val refused = BrowserDownloadReview.delete(download(), request = { requests++; throw IllegalStateException("refused") },
            read = { error("refused requests are not certified") })
        assertFalse(refused.outcomeUnknown)
        assertNull(refused.confirmedDownloads)
        val unsupported = BrowserDownloadReview.delete(download("IN_PROGRESS"), request = { requests++; receipt() },
            read = { error("unsupported requests cannot read back") })
        assertFalse(unsupported.outcomeUnknown)
        assertEquals(1, requests)
        assertFailsWith<CancellationException> {
            BrowserDownloadReview.delete(download(), request = { throw CancellationException("left") }, read = { JSONArray() })
        }
        Unit
    }
}
