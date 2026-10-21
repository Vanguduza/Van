package com.dial.van.browser

import java.io.InputStream
import java.io.OutputStream
import java.security.MessageDigest
import org.json.JSONObject

/** A separate, one-use capability. A stream grant never authorizes moving a file. */
object BrowserTransfers {
    const val MAX_FILE_BYTES = 64L * 1024 * 1024
    const val MAX_CLIPBOARD_BYTES = 65_536L
    private val HASH = Regex("[0-9a-f]{64}")
    enum class Operation(val wire: String) { DOWNLOAD("download"), UPLOAD("upload"), PASTE("paste"), COPY("copy"), ANALYSE("analyse"), FILE_IMPORT("file_import") }
    data class Context(val sessionId: String, val targetId: String, val mediaEpoch: String)
    data class Request(val context: Context, val operation: Operation, val resourceId: String,
        val byteSize: Long? = null, val contentSha256: String? = null, val name: String? = null, val mime: String? = null) {
        fun body(): JSONObject = JSONObject().put("operation", operation.wire).put("target_id", context.targetId).apply {
            when (operation) {
                Operation.DOWNLOAD, Operation.ANALYSE -> put("download_id", resourceId)
                Operation.UPLOAD -> put("chooser_id", resourceId)
                else -> Unit
            }
            byteSize?.let { put("byte_size", it) }
            contentSha256?.let { put("content_sha256", it) }
            name?.let { put("suggested_name", it) }
            mime?.let { put("mime_type", it) }
        }
    }
    data class Grant(val token: String, val context: Context, val operation: Operation, val resourceId: String,
        val byteSize: Long?, val contentSha256: String?, val hostUrl: String, val expiresAtMs: Long,
        val transferId: String? = null)
    data class Bytes(val size: Long, val sha256: String)

    fun grant(row: JSONObject, request: Request, nowMs: Long): Grant {
        fun text(key: String, max: Int = 256): String = row.getString(key).also { require(it.isNotBlank() && it.length <= max) }
        val context = Context(text("session_id"), text("target_id"), text("producer_session_id"))
        require(context == request.context) { "browser_transfer_binding_mismatch" }
        val resource = text("resource_id")
        val resourceMatches = if (request.operation == Operation.FILE_IMPORT)
            resource.matches(Regex("import_[a-f0-9]{32}")) else resource == request.resourceId
        require(text("operation") == request.operation.wire && resourceMatches) { "browser_transfer_resource_mismatch" }
        val expires = (row.opt("expires_at_ms") as? Number)?.toLong() ?: error("browser_transfer_expiry_required")
        require(expires > nowMs && expires - nowMs <= 300_000) { "browser_transfer_grant_expired" }
        val size = (row.opt("byte_size") as? Number)?.toLong()
        val hash = if (row.isNull("content_sha256")) null else row.getString("content_sha256")
        val limit = if (request.operation in setOf(Operation.COPY, Operation.PASTE)) MAX_CLIPBOARD_BYTES else MAX_FILE_BYTES
        if (request.operation != Operation.COPY) {
            require(size != null && size in 0..limit && hash != null && HASH.matches(hash)) { "browser_transfer_content_proof_required" }
            request.byteSize?.let { require(size == it) { "browser_transfer_size_mismatch" } }
            request.contentSha256?.let { require(hash == it) { "browser_transfer_hash_mismatch" } }
        }
        return Grant(text("transfer_grant", 16_384), context, request.operation, resource,
            size, hash, text("host_url", 4096), expires, row.optString("transfer_id").takeIf { !row.isNull("transfer_id") && it.isNotBlank() })
    }

    /** Bound while streaming, not after an unbounded allocation. The caller owns and closes both streams. */
    fun copy(input: InputStream, output: OutputStream, limit: Long, expected: Bytes? = null): Bytes {
        val digest = MessageDigest.getInstance("SHA-256")
        var total = 0L
        val buffer = ByteArray(32 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            if (count == 0) continue
            require(total <= limit - count) { "browser_transfer_too_large" }
            total += count
            digest.update(buffer, 0, count)
            output.write(buffer, 0, count)
        }
        val actual = Bytes(total, digest.digest().joinToString("") { "%02x".format(it) })
        require(expected == null || actual == expected) { "browser_transfer_content_mismatch" }
        return actual
    }
    fun textProof(text: String): Bytes {
        val bytes = text.toByteArray(Charsets.UTF_8)
        require(bytes.size.toLong() <= MAX_CLIPBOARD_BYTES && '\u0000' !in text) { "browser_clipboard_text_too_large" }
        return Bytes(bytes.size.toLong(), MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })
    }
    fun verifyEffect(row: JSONObject, grant: Grant) {
        require(row.optString("producer_session_id") == grant.context.mediaEpoch) { "browser_transfer_receipt_epoch_mismatch" }
        require(row.optString("target_id") == grant.context.targetId) { "browser_transfer_receipt_target_mismatch" }
        when (grant.operation) {
            Operation.UPLOAD -> require(row.opt("attached") == true && row.optString("chooser_id") == grant.resourceId)
            Operation.PASTE -> require(row.opt("pasted") == true)
            else -> return
        }
        require(row.optLong("byte_size", -1) == grant.byteSize && row.optString("content_sha256") == grant.contentSha256) {
            "browser_transfer_effect_unconfirmed"
        }
    }
}
