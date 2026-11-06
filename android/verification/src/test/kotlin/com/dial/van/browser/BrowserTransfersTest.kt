package com.dial.van.browser

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class BrowserTransfersTest {
    private val context = BrowserTransfers.Context("session", "tab", "peer")
    private val proof = BrowserTransfers.textProof("owner selected bytes")
    private val request = BrowserTransfers.Request(context, BrowserTransfers.Operation.UPLOAD, "chooser", proof.size, proof.sha256)
    private fun row() = JSONObject().put("session_id", "session").put("target_id", "tab")
        .put("producer_session_id", "peer").put("operation", "upload").put("resource_id", "chooser")
        .put("byte_size", proof.size).put("content_sha256", proof.sha256).put("expires_at_ms", 2_000)
        .put("transfer_grant", "one-use-token").put("host_url", "https://stream.test/rtc/files/upload/chooser")
    @Test fun `transfer grant cannot cross session target peer operation resource or content`() {
        assertEquals(context, BrowserTransfers.grant(row(), request, 1_000).context)
        for ((field, value) in listOf("session_id" to "other", "target_id" to "other", "producer_session_id" to "old-peer",
            "operation" to "download", "resource_id" to "old-chooser", "byte_size" to 1,
            "content_sha256" to "0".repeat(64), "expires_at_ms" to 1_000)) {
            assertFails(field) { BrowserTransfers.grant(row().put(field, value), request, 1_000) }
        }
    }
    @Test fun `bytes are bounded during streaming and require exact content proof`() {
        val content = "owner selected bytes".toByteArray()
        val output = ByteArrayOutputStream()
        assertEquals(proof, BrowserTransfers.copy(ByteArrayInputStream(content), output, content.size.toLong(), proof))
        assertTrue(output.toByteArray().contentEquals(content))
        assertFails { BrowserTransfers.copy(ByteArrayInputStream(content), ByteArrayOutputStream(), content.size.toLong() - 1) }
        assertFails { BrowserTransfers.copy(ByteArrayInputStream("other".toByteArray()), ByteArrayOutputStream(), 64, proof) }
    }
    @Test fun `clipboard bound uses UTF8 bytes and rejects oversized text`() {
        assertEquals(4L, BrowserTransfers.textProof("🙂").size)
        assertFails { BrowserTransfers.textProof("🙂".repeat(16_385)) }
        assertFails { BrowserTransfers.textProof("secret\u0000") }
    }
    @Test fun `upload receipt needs actual attachment target epoch and identical bytes`() {
        val grant = BrowserTransfers.grant(row(), request, 1_000)
        val receipt = JSONObject().put("attached", true).put("chooser_id", "chooser").put("producer_session_id", "peer")
            .put("target_id", "tab").put("byte_size", proof.size).put("content_sha256", proof.sha256)
        BrowserTransfers.verifyEffect(receipt, grant)
        for ((field, value) in listOf("attached" to false, "chooser_id" to "other", "producer_session_id" to "other",
            "target_id" to "other", "byte_size" to 1, "content_sha256" to "0".repeat(64))) {
            assertFails(field) { BrowserTransfers.verifyEffect(JSONObject(receipt.toString()).put(field, value), grant) }
        }
    }
    @Test fun `download policy actions alone never admit actual phone transfer`() {
        val metadata = BrowserDownloadReview.Download("download", "file.txt", "text/plain", proof.size, "COMPLETED", false,
            null, setOf("SEND_TO_PHONE"), contentSha256 = proof.sha256, targetId = "tab")
        assertFalse(metadata.maySave)
        assertTrue(metadata.copy(executableActions = setOf("SEND_TO_PHONE")).maySave)
        assertFalse(metadata.copy(executableActions = setOf("SEND_TO_PHONE"), dangerous = true).maySave)
        assertFalse(metadata.copy(executableActions = setOf("SEND_TO_PHONE"), contentSha256 = null).maySave)
    }
}
