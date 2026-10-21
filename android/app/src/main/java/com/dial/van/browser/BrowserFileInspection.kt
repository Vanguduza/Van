package com.dial.van.browser

import org.json.JSONObject

/** Static inspection is untrusted file evidence; no byte becomes an assistant instruction. */
object BrowserFileInspection {
    fun matchesImport(saved: JSONObject, row: JSONObject): Boolean =
        row.optString("download_id") == saved.optString("resource_id") && row.optString("download_id").matches(Regex("import_[a-f0-9]{32}")) &&
            row.optLong("byte_size", -1) == saved.optLong("byte_size", -2) && row.optString("content_sha256") == saved.optString("content_sha256") &&
            row.optString("state") in setOf("COMPLETED", "QUARANTINED")
    fun validateNative(result: JSONObject, grant: BrowserTransfers.Grant) {
        require(grant.operation == BrowserTransfers.Operation.ANALYSE && !grant.transferId.isNullOrBlank() &&
            result.optString("transfer_id") == grant.transferId && result.optString("status") == "VERIFIED_SUCCESS" &&
            result.optString("operation") == "analyse" && result.optString("resource_id") == grant.resourceId &&
            result.optString("session_id") == grant.context.sessionId && result.optString("producer_session_id") == grant.context.mediaEpoch &&
            result.optString("download_id") == grant.resourceId && result.optLong("byte_size", -1) == grant.byteSize &&
            result.optString("content_sha256") == grant.contentSha256) { "File inspection identity or content did not match." }
        validateReceipt(result)
    }
    fun validateImport(result: JSONObject, grant: BrowserTransfers.Grant) {
        require(grant.operation == BrowserTransfers.Operation.FILE_IMPORT && !grant.transferId.isNullOrBlank() &&
            result.optString("transfer_id") == grant.transferId && result.optString("status") == "VERIFIED_SUCCESS" &&
            result.optString("operation") == "file_import" && result.optString("session_id") == grant.context.sessionId &&
            result.optString("producer_session_id") == grant.context.mediaEpoch && result.optString("resource_id") == grant.resourceId &&
            result.optString("download_id") == grant.resourceId && result.optLong("byte_size", -1) == grant.byteSize &&
            result.optString("content_sha256") == grant.contentSha256) { "File import receipt identity or content did not match." }
    }
    fun validateReceipt(result: JSONObject) {
        require(result.optString("analysis_kind") == "BOUNDED_STATIC_INSPECTION" &&
            result.optString("content_authority") == "UNTRUSTED_FILE_EVIDENCE" && result.opt("executed_content") == false &&
            result.optString("analysis_sha256").matches(Regex("[a-f0-9]{64}"))) { "File inspection has no safe static evidence contract." }
        if (!result.isNull("text_preview")) require(result.optString("text_preview").toByteArray(Charsets.UTF_8).size <= 65536) { "File preview exceeds the inspection bound." }
    }
    fun confirms(result: JSONObject, operation: JSONObject, sessionId: String): Boolean {
        val receipt = operation.optJSONObject("receipt") ?: return false
        return operation.optString("status") == "VERIFIED_SUCCESS" && operation.optString("operation") == "analyse" &&
            operation.optString("session_id") == sessionId && operation.optString("resource_id") == result.optString("download_id") &&
            operation.optString("transfer_id") == result.optString("transfer_id") &&
            receipt.optString("analysis_sha256") == result.optString("analysis_sha256") &&
            receipt.optString("content_sha256") == result.optString("content_sha256") &&
            receipt.optLong("byte_size", -1) == result.optLong("byte_size", -2)
    }
    fun matchesRecovery(saved: JSONObject, operation: JSONObject): Boolean {
        val receipt = operation.optJSONObject("receipt") ?: return false
        return operation.optString("status") == "VERIFIED_SUCCESS" && operation.optString("operation") == "analyse" &&
            operation.optString("session_id") == saved.optString("session_id") && operation.optString("resource_id") == saved.optString("download_id") &&
            operation.optString("transfer_id") == saved.optString("transfer_id") && receipt.optString("content_sha256") == saved.optString("content_sha256") &&
            receipt.optLong("byte_size", -1) == saved.optLong("byte_size", -2)
    }
    fun inertKind(mime: String): String? = when (mime.lowercase()) {
        "text/plain", "application/json" -> "TEXT"
        "image/png", "image/jpeg", "image/webp" -> "IMAGE"
        "application/pdf" -> "PDF"
        else -> null
    }
}
