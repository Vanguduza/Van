package com.dial.van.browser

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BrowserFileInspectionTest {
    private val hash = "a".repeat(64)
    private val context = BrowserTransfers.Context("sid", "tab", "epoch")
    private fun receipt() = JSONObject().put("status", "VERIFIED_SUCCESS").put("transfer_id", "transfer")
        .put("operation", "analyse").put("resource_id", "file").put("session_id", "sid").put("producer_session_id", "epoch")
        .put("download_id", "file").put("byte_size", 12).put("content_sha256", hash).put("analysis_sha256", "b".repeat(64))
        .put("analysis_kind", "BOUNDED_STATIC_INSPECTION").put("content_authority", "UNTRUSTED_FILE_EVIDENCE").put("executed_content", false)
    private fun grant() = BrowserTransfers.Grant("grant", context, BrowserTransfers.Operation.ANALYSE, "file", 12, hash, "https://host/files/analyse/file", 999, "transfer")
    @Test fun `native inspection must match one-use transfer exact bytes and inert evidence`() {
        BrowserFileInspection.validateNative(receipt(), grant())
        for ((field, value) in listOf("transfer_id" to "another", "content_sha256" to "c".repeat(64), "byte_size" to 13,
            "session_id" to "other", "producer_session_id" to "old-epoch", "operation" to "download",
            "executed_content" to true, "content_authority" to "OWNER_AUTHORITY", "analysis_kind" to "EXECUTE_FILE")) {
            assertFails(field) { BrowserFileInspection.validateNative(receipt().put(field, value), grant()) }
        }
        assertFails { BrowserFileInspection.validateNative(receipt(), grant().copy(transferId = null)) }
        assertFails { BrowserFileInspection.validateReceipt(receipt().put("text_preview", "🙂".repeat(16385))) }
    }
    @Test fun `lost inspection recovers only matching native receipt without preview or repeat`() {
        val saved = JSONObject().put("session_id", "sid").put("download_id", "file").put("transfer_id", "transfer").put("byte_size", 12).put("content_sha256", hash)
        val operation = JSONObject().put("session_id", "sid").put("resource_id", "file").put("transfer_id", "transfer")
            .put("status", "VERIFIED_SUCCESS").put("operation", "analyse").put("receipt", receipt())
        assertTrue(BrowserFileInspection.matchesRecovery(saved, operation))
        assertTrue(BrowserFileInspection.confirms(receipt(), operation, "sid"))
        assertFalse(BrowserFileInspection.matchesRecovery(saved, operation.put("transfer_id", "other")))
        assertFalse(BrowserFileInspection.confirms(receipt(), operation.put("transfer_id", "transfer"), "other"))
    }
    @Test fun `import accepts server-generated opaque identity and final matching readback`() {
        val request = BrowserTransfers.Request(context, BrowserTransfers.Operation.FILE_IMPORT, "", 12, hash, "notes.txt", "text/plain")
        val id = "import_" + "a".repeat(32)
        val row = JSONObject().put("session_id", "sid").put("target_id", "tab").put("producer_session_id", "epoch").put("operation", "file_import")
            .put("resource_id", id).put("byte_size", 12).put("content_sha256", hash).put("expires_at_ms", 999).put("transfer_grant", "one-use").put("host_url", "https://host/files/import/$id")
        assertEquals(id, BrowserTransfers.grant(row, request, 1).resourceId)
        assertFails { BrowserTransfers.grant(row.put("resource_id", "../../other"), request, 1) }
        val saved = JSONObject().put("resource_id", id).put("byte_size", 12).put("content_sha256", hash)
        val record = JSONObject().put("download_id", id).put("byte_size", 12).put("content_sha256", hash).put("state", "QUARANTINED")
        assertTrue(BrowserFileInspection.matchesImport(saved, record))
        assertFalse(BrowserFileInspection.matchesImport(saved, record.put("byte_size", 13)))
        val grant = BrowserTransfers.Grant("grant", context, BrowserTransfers.Operation.FILE_IMPORT, id, 12, hash, "https://host/files/import/$id", 999, "transfer")
        val native = JSONObject().put("operation", "file_import").put("session_id", "sid").put("producer_session_id", "epoch")
            .put("transfer_id", "transfer").put("status", "VERIFIED_SUCCESS").put("resource_id", id).put("download_id", id).put("byte_size", 12).put("content_sha256", hash)
        BrowserFileInspection.validateImport(native, grant)
        assertFails { BrowserFileInspection.validateImport(native.put("producer_session_id", "old"), grant) }
    }
    @Test fun `active content and quarantine never open while static analysis stays separately gated`() {
        assertNull(BrowserFileInspection.inertKind("text/html")); assertNull(BrowserFileInspection.inertKind("application/javascript"))
        assertEquals("PDF", BrowserFileInspection.inertKind("application/pdf"))
        val file = BrowserDownloadReview.Download("id", "file", "text/plain", 12, "COMPLETED", false, null, emptySet(), setOf("OPEN_IN_VAN", "ANALYSE"), hash, "tab")
        assertTrue(file.mayOpen); assertTrue(file.mayAnalyse)
        assertFalse(file.copy(state = "QUARANTINED", dangerous = true).mayOpen)
        assertTrue(file.copy(state = "QUARANTINED", dangerous = true).mayAnalyse)
        assertFalse(file.copy(executableActions = emptySet()).mayAnalyse)
    }
}
