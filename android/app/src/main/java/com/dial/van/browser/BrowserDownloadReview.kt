package com.dial.van.browser

import java.io.IOException
import kotlinx.coroutines.CancellationException
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/** Download records are owner observations. They never prove a local file transfer. */
object BrowserDownloadReview {
    data class Download(
        val id: String, val name: String, val mime: String, val byteSize: Long?,
        val state: String, val dangerous: Boolean, val failureReason: String?, val actions: Set<String>,
        val executableActions: Set<String> = emptySet(), val contentSha256: String? = null, val targetId: String? = null,
    ) {
        val mayDelete: Boolean get() = id.isNotBlank() && "DELETE" in actions &&
            state in setOf("COMPLETED", "QUARANTINED", "FAILED")
        val maySave: Boolean get() = id.isNotBlank() && "SEND_TO_PHONE" in executableActions && state == "COMPLETED" &&
            !dangerous && byteSize != null && byteSize in 0..BrowserTransfers.MAX_FILE_BYTES &&
            contentSha256?.matches(Regex("[0-9a-f]{64}")) == true && !targetId.isNullOrBlank()
        val mayOpen: Boolean get() = nativeProof && !dangerous && state == "COMPLETED" && "OPEN_IN_VAN" in executableActions && BrowserFileInspection.inertKind(mime) != null
        val mayAnalyse: Boolean get() = nativeProof && state in setOf("COMPLETED", "QUARANTINED") && "ANALYSE" in executableActions
        private val nativeProof: Boolean get() = id.isNotBlank() && byteSize != null && byteSize in 0..BrowserTransfers.MAX_FILE_BYTES &&
            contentSha256?.matches(Regex("[0-9a-f]{64}")) == true && !targetId.isNullOrBlank()
        val ownerState: String get() = when (state) {
            "CREATED" -> "Download recorded; transfer has not started"
            "IN_PROGRESS" -> "Download in progress on the browser host; progress is not supplied"
            "COMPLETED" -> "Download complete on the browser host; no phone copy is confirmed"
            "QUARANTINED" -> "Quarantined on the browser host; opening and phone transfer are blocked"
            "FAILED" -> "Download failed on the browser host"
            "DELETED" -> "Download record removed; the browser host manages file cleanup"
            else -> "Download state is unknown; actions are unavailable"
        }
    }

    data class DeleteOutcome(
        val confirmedDownloads: List<Download>? = null,
        val error: String? = null,
        val outcomeUnknown: Boolean = false,
    )
    private class UnconfirmedReceipt : IllegalStateException()

    fun rows(body: JSONArray): List<Download> = (0 until body.length()).map { index ->
        val row = body.getJSONObject(index)
        val advertised = row.optJSONArray("actions")
        val executable = row.optJSONArray("executable_actions")
        Download(
            id = row.optString("download_id").takeUnless { row.isNull("download_id") }.orEmpty(),
            name = row.optString("suggested_name").takeUnless { row.isNull("suggested_name") || it.isBlank() }
                ?: "Unnamed download",
            mime = row.optString("mime_type").takeUnless { row.isNull("mime_type") || it.isBlank() }
                ?: "Type not supplied",
            byteSize = (row.opt("byte_size") as? Number)?.toLong()?.takeIf { it >= 0 },
            state = row.optString("state"), dangerous = row.optBoolean("dangerous"),
            failureReason = row.optString("failure_reason").takeUnless { row.isNull("failure_reason") || it.isBlank() },
            actions = if (advertised == null) emptySet() else (0 until advertised.length())
                .map { advertised.optString(it) }.toSet(),
            executableActions = if (executable == null) emptySet() else (0 until executable.length()).map { executable.optString(it) }.toSet(),
            contentSha256 = row.optString("content_sha256").takeUnless { row.isNull("content_sha256") || it.isBlank() },
            targetId = row.optString("target_id").takeUnless { row.isNull("target_id") || it.isBlank() },
        )
    }

    /** Exactly one mutation, then independent record readback. A lost reply is never retried. */
    suspend fun delete(download: Download, request: suspend () -> JSONObject, read: suspend () -> JSONArray): DeleteOutcome {
        if (!download.mayDelete) return DeleteOutcome(error = "Removing this download is currently unavailable.")
        var receivedMutationReply = false
        return try {
            val receipt = request()
            receivedMutationReply = true
            if (receipt.optString("download_id") != download.id || receipt.optString("state") != "DELETED")
                throw UnconfirmedReceipt()
            val observed = rows(read())
            if (observed.singleOrNull { it.id == download.id }?.state != "DELETED") throw UnconfirmedReceipt()
            DeleteOutcome(confirmedDownloads = observed)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            val unknown = failure is IOException || failure is JSONException || failure is UnconfirmedReceipt || receivedMutationReply
            DeleteOutcome(error = if (unknown) {
                "Removal could not be confirmed. The request may already have been applied. Refresh the records before another decision."
            } else {
                "The download could not be removed. The last confirmed record remains visible. Refresh to check its current state."
            }, outcomeUnknown = unknown)
        }
    }

    const val TRANSFER_UNAVAILABLE = "This session has not admitted a verified phone transfer. No phone file has been saved."
    const val UPLOAD_UNAVAILABLE = "This session has not supplied a current page chooser and scoped upload grant. VAN will not read or send an unselected phone file."
}
