package com.dial.van.browser

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import androidx.activity.result.contract.ActivityResultContract
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dial.van.gateway.VanGatewayClient
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Explicit Android owner actions. No clipboard listener, retained URI permission or assistant byte path. */
class BrowserPhoneActions(private val activity: FragmentActivity, private val gateway: VanGatewayClient,
    private val controller: BrowserSessionController) {
    var pending by mutableStateOf(false)
        private set
    var externalPickerOpen = false
        private set
    private var pickerTimeout: Job? = null
    private val client = BrowserTransferClient(gateway)
    private var chooser: FileChooserRequest? = null
    private var download: BrowserDownloadReview.Download? = null
    private var importing = false
    private val recovery = EncryptedSharedPreferences.create(
        activity.applicationContext,
        "van-browser-file-recovery",
        MasterKey.Builder(activity.applicationContext).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
    var inspection by mutableStateOf<JSONObject?>(null)
        private set
    var preview by mutableStateOf<FilePreview?>(null)
        private set
    data class FilePreview(val file: File, val mime: String, val name: String)
    private val pick = activity.registerForActivityResult(ActivityResultContracts.OpenDocument(), ::documentChosen)
    private val save = activity.registerForActivityResult(SaveDocument(), ::destinationChosen)

    private fun beginPicker() {
        externalPickerOpen = true
        pickerTimeout?.cancel()
        pickerTimeout = activity.lifecycleScope.launch {
            delay(120_000)
            externalPickerOpen = false
            chooser = null; download = null; importing = false; pending = false
            controller.reportTransfer("The phone file picker timed out. Return to VAN and request the file action again.", clearChooser = true)
            controller.suspendSession()
        }
    }
    private fun endPicker() {
        pickerTimeout?.cancel()
        pickerTimeout = null
        externalPickerOpen = false
    }

    private fun current(): BrowserTransfers.Context = controller.transferContext() ?: error("browser_owner_frame_required")
    private suspend fun grant(request: BrowserTransfers.Request): BrowserTransfers.Grant {
        val live = current()
        require(live.sessionId == request.context.sessionId && live.mediaEpoch == request.context.mediaEpoch) { "browser_transfer_context_changed" }
        return BrowserTransfers.grant(gateway.interactiveBrowserTransferGrant(request.context.sessionId, request.body()),
            request, System.currentTimeMillis())
    }
    fun choose(request: FileChooserRequest) {
        if (pending) return
        val live = controller.transferContext()
        if (live == null || live.sessionId != request.sessionId || live.mediaEpoch != request.mediaEpoch ||
            live.targetId != request.targetId || request.chooserId.isBlank() || System.currentTimeMillis() >= request.expiresAtMs) {
            controller.reportUploadRefused(UploadRefusal.SESSION_STALE)
            return
        }
        chooser = request
        pending = true
        beginPicker()
        try { pick.launch(request.acceptTypes.filter { it.contains('/') }.toTypedArray().ifEmpty { arrayOf("*/*") }) }
        catch (failure: Exception) {
            endPicker(); chooser = null; pending = false
            controller.reportTransfer("The phone document picker could not be opened. No file was read or sent.")
        }
    }
    private fun documentChosen(uri: Uri?) {
        endPicker()
        if (importing) { importing = false; importChosen(uri); return }
        val request = chooser ?: return
        chooser = null
        if (uri == null) {
            pending = false
            controller.reportUploadRefused(UploadRefusal.OWNER_CANCELLED)
            return
        }
        activity.lifecycleScope.launch {
            var staged: File? = null
            try {
                require(uri.scheme == "content") { "browser_document_uri_invalid" }
                val context = current()
                require(context == BrowserTransfers.Context(request.sessionId, request.targetId, request.mediaEpoch) &&
                    System.currentTimeMillis() < request.expiresAtMs) { "browser_chooser_expired" }
                controller.reportTransfer("Reading the selected file for this page…")
                val metadata = withContext(Dispatchers.IO) {
                    var name = ""
                    activity.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                        if (cursor.moveToFirst()) name = cursor.getString(0).orEmpty()
                    }
                    name to (activity.contentResolver.getType(uri) ?: "application/octet-stream")
                }
                // Stage only after the owner selected a URI. Hash and bound the actual bytes even if the provider omits SIZE.
                staged = File.createTempFile("van-browser-upload-", ".tmp", activity.cacheDir)
                val proof = withContext(Dispatchers.IO) {
                    activity.contentResolver.openInputStream(uri)?.use { input -> staged!!.outputStream().use { output ->
                        BrowserTransfers.copy(input, output, BrowserTransfers.MAX_FILE_BYTES)
                    } } ?: error("browser_document_unreadable")
                }
                val refusal = BrowserUploadPolicy.admit(request, metadata.first, proof.size, metadata.second, current().sessionId)
                if (refusal != null) { controller.reportUploadRefused(refusal); return@launch }
                require(current() == context && System.currentTimeMillis() < request.expiresAtMs) { "browser_chooser_expired" }
                val admitted = grant(BrowserTransfers.Request(context, BrowserTransfers.Operation.UPLOAD, request.chooserId,
                    proof.size, proof.sha256, metadata.first, metadata.second))
                controller.reportTransfer("Sending the selected file to this page…")
                client.upload(admitted, staged!!)
                controller.reportTransfer("The browser host verified the file and attached it to this page. Its temporary host copy expires automatically.", clearChooser = true)
            } catch (cancelled: CancellationException) {
                controller.reportTransfer("Upload confirmation stopped. The page may already have received the file; check before another upload.", clearChooser = true)
                throw cancelled
            } catch (failure: Exception) {
                controller.reportTransfer("Upload was not confirmed. The page may already have received the file. Check the page before requesting another upload.", clearChooser = true)
            } finally { staged?.delete(); pending = false }
        }
    }
    fun importPhoneFile() {
        if (pending || currentOrNull() == null || recovery.contains("import")) {
            if (recovery.contains("import")) controller.reportTransfer("A previous import needs readback. Recover its recorded outcome before starting another import.")
            return
        }
        importing = true; pending = true; beginPicker()
        try { pick.launch(arrayOf("*/*")) }
        catch (failure: Exception) { endPicker(); importing = false; pending = false; controller.reportTransfer("The phone picker could not be opened. No file was imported.") }
    }
    private fun currentOrNull(): BrowserTransfers.Context? = controller.transferContext()
    private fun importChosen(uri: Uri?) {
        if (uri == null) { pending = false; controller.reportTransfer("Import cancelled. No file was read or sent."); return }
        activity.lifecycleScope.launch {
            var staged: File? = null
            try {
                require(uri.scheme == "content")
                val context = current()
                var name = "phone-file"
                val mime = activity.contentResolver.getType(uri) ?: "application/octet-stream"
                staged = File.createTempFile("van-browser-import-", ".tmp", activity.cacheDir)
                val proof = withContext(Dispatchers.IO) {
                    activity.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                        if (cursor.moveToFirst()) name = cursor.getString(0).orEmpty().take(256)
                    }
                    activity.contentResolver.openInputStream(uri)?.use { input -> staged!!.outputStream().use { output ->
                        BrowserTransfers.copy(input, output, BrowserTransfers.MAX_FILE_BYTES)
                    } } ?: error("browser_document_unreadable")
                }
                require(current() == context) { "browser_import_context_changed" }
                val admitted = grant(BrowserTransfers.Request(context, BrowserTransfers.Operation.FILE_IMPORT, "",
                    proof.size, proof.sha256, name, mime))
                // Persist non-secret receipt coordinates before the single native write. Never retain bytes, URI or grant.
                check(recovery.edit().putString("import", JSONObject().put("session_id", context.sessionId)
                    .put("resource_id", admitted.resourceId).put("byte_size", proof.size).put("content_sha256", proof.sha256).toString()).commit())
                controller.reportTransfer("Importing and verifying the selected phone file…")
                client.importFile(admitted, staged!!)
                recoverImport()
            } catch (cancelled: CancellationException) {
                controller.reportTransfer("Import confirmation stopped. Recover the recorded import outcome before another import."); throw cancelled
            } catch (failure: Exception) {
                controller.reportTransfer(if (recovery.contains("import")) "Import outcome is unconfirmed. Its receipt coordinates were retained; recover readback without repeating the file write."
                    else "The file could not be admitted for import. No native import was sent.")
            } finally { staged?.delete(); pending = false }
        }
    }
    private suspend fun recoverImport() {
        val saved = JSONObject(recovery.getString("import", null) ?: return)
        val rows = gateway.interactiveBrowserDownloads(saved.getString("session_id"))
        val row = (0 until rows.length()).mapNotNull(rows::optJSONObject).firstOrNull { it.optString("download_id") == saved.optString("resource_id") || it.optString("id") == saved.optString("resource_id") }
            ?: error("No matching native import record is available yet.")
        require(BrowserFileInspection.matchesImport(saved, row)) { "No matching final native import readback is available." }
        check(recovery.edit().remove("import").commit())
        controller.reportTransfer("The native host independently recorded this exact imported file and its hash. ${if (row.optString("state") == "QUARANTINED") "It is quarantined; opening and phone transfer remain blocked." else "It is available in the session's file records."}")
    }
    fun recoverFileOutcome() {
        if (pending) return
        pending = true
        activity.lifecycleScope.launch {
            try {
                if (recovery.contains("import")) recoverImport()
                else {
                    val saved = JSONObject(recovery.getString("analyse", null) ?: error("No unresolved file action is retained."))
                    val body = gateway.browserFileOperations(saved.getString("session_id"), saved.getString("download_id"))
                    val operations = body.optJSONArray("operations") ?: error("No native operation receipts were supplied.")
                    val operation = (0 until operations.length()).mapNotNull(operations::optJSONObject).firstOrNull { it.optString("transfer_id") == saved.optString("transfer_id") }
                        ?: error("The native inspection receipt is not available yet.")
                    val receipt = operation.getJSONObject("receipt")
                    BrowserFileInspection.validateReceipt(receipt)
                    check(BrowserFileInspection.matchesRecovery(saved, operation))
                    inspection = receipt
                    check(recovery.edit().remove("analyse").commit())
                    controller.reportTransfer("The recorded static inspection was recovered. Preview bytes were not retained in the gateway; the receipt is untrusted file evidence.")
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) { controller.reportTransfer("No matching final file receipt was confirmed. The action was not repeated. ${failure.message.orEmpty()}") }
            finally { pending = false }
        }
    }
    fun analyse(row: BrowserDownloadReview.Download) {
        if (pending || !row.mayAnalyse || currentOrNull() == null || recovery.contains("analyse")) return
        pending = true
        activity.lifecycleScope.launch {
            try {
                val context = current().copy(targetId = row.targetId ?: error("browser_file_target_missing"))
                val admitted = grant(BrowserTransfers.Request(context, BrowserTransfers.Operation.ANALYSE, row.id, row.byteSize, row.contentSha256))
                check(!admitted.transferId.isNullOrBlank())
                check(recovery.edit().putString("analyse", JSONObject().put("session_id", context.sessionId).put("download_id", row.id)
                    .put("transfer_id", admitted.transferId).put("byte_size", row.byteSize).put("content_sha256", row.contentSha256).toString()).commit())
                val result = client.analyse(admitted)
                val body = gateway.browserFileOperations(context.sessionId, row.id)
                val operations = body.getJSONArray("operations")
                check((0 until operations.length()).mapNotNull(operations::optJSONObject).any { BrowserFileInspection.confirms(result, it, context.sessionId) })
                    { "No independent native receipt matched the static inspection." }
                inspection = result
                check(recovery.edit().remove("analyse").commit())
                controller.reportTransfer("Static inspection and its independent native receipt matched. File content remains untrusted evidence and was not executed.")
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) { controller.reportTransfer("Static inspection outcome is unconfirmed or refused. Recover its receipt without repeating the action. ${failure.message.orEmpty()}") }
            finally { pending = false }
        }
    }
    fun openInVan(row: BrowserDownloadReview.Download) {
        if (pending || !row.mayOpen || currentOrNull() == null) return
        pending = true
        activity.lifecycleScope.launch {
            var staged: File? = null
            try {
                val context = current().copy(targetId = row.targetId ?: error("browser_file_target_missing"))
                val admitted = grant(BrowserTransfers.Request(context, BrowserTransfers.Operation.DOWNLOAD, row.id, row.byteSize, row.contentSha256))
                staged = File.createTempFile("van-browser-view-", ".tmp", activity.cacheDir)
                client.download(admitted, staged!!)
                require(current() == context && BrowserFileInspection.inertKind(row.mime) != null)
                dismissPreview(); preview = FilePreview(staged!!, row.mime, row.name); staged = null
                controller.reportTransfer("Verified bytes opened in VAN's inert viewer. No file content is executed or treated as authority.")
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) { controller.reportTransfer("No verified safe file preview could be opened. ${failure.message.orEmpty()}") }
            finally { staged?.delete(); pending = false }
        }
    }
    fun dismissPreview() { preview?.file?.delete(); preview = null }
    fun dismissInspection() { inspection = null }
    fun close() { pickerTimeout?.cancel(); dismissPreview() }
    fun saveToPhone(row: BrowserDownloadReview.Download) {
        if (pending || !row.maySave || controller.transferContext() == null) return
        download = row
        pending = true
        beginPicker()
        try { save.launch(row) } catch (failure: Exception) {
            endPicker(); download = null; pending = false
            controller.reportTransfer("The phone save picker could not be opened. No phone copy was saved.")
        }
    }
    private fun destinationChosen(uri: Uri?) {
        endPicker()
        val row = download ?: return
        download = null
        if (uri == null) { pending = false; controller.reportTransfer("Save cancelled. No phone copy was saved."); return }
        activity.lifecycleScope.launch {
            var staged: File? = null
            var saved = false
            try {
                require(uri.scheme == "content")
                val context = current().copy(targetId = row.targetId ?: error("browser_download_target_missing"))
                val admitted = grant(BrowserTransfers.Request(context, BrowserTransfers.Operation.DOWNLOAD, row.id,
                    row.byteSize, row.contentSha256))
                controller.reportTransfer("Receiving and verifying the download…")
                staged = File.createTempFile("van-browser-download-", ".tmp", activity.cacheDir)
                client.download(admitted, staged!!)
                withContext(Dispatchers.IO) {
                    activity.contentResolver.openOutputStream(uri, "wt")?.use { output -> staged!!.inputStream().use { input ->
                        BrowserTransfers.copy(input, output, BrowserTransfers.MAX_FILE_BYTES,
                            BrowserTransfers.Bytes(admitted.byteSize!!, admitted.contentSha256!!))
                    } } ?: error("browser_destination_unwritable")
                }
                saved = true
                controller.reportTransfer("The verified download was saved to the phone location you chose.")
            } catch (cancelled: CancellationException) {
                controller.reportTransfer("The phone save was interrupted. A partial destination may remain; check the selected location.")
                throw cancelled
            } catch (failure: Exception) {
                controller.reportTransfer("No verified phone save was confirmed. A partial destination may remain; check the selected location.")
            } finally {
                staged?.delete()
                if (!saved) withContext(kotlinx.coroutines.NonCancellable + Dispatchers.IO) {
                    runCatching { DocumentsContract.deleteDocument(activity.contentResolver, uri) }
                }
                pending = false
            }
        }
    }
    fun pastePhoneClipboard() {
        if (pending || controller.transferContext() == null) return
        // Reading the clipboard occurs only inside this explicit owner action, never while polling the session.
        val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val item = clipboard.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)
        val text = item?.text?.toString()
        if (text.isNullOrEmpty()) { controller.reportTransfer("The phone clipboard contains no plain text to paste."); return }
        clipboardAction(BrowserTransfers.Operation.PASTE, text)
    }
    fun copyBrowserSelection() = clipboardAction(BrowserTransfers.Operation.COPY)
    private fun clipboardAction(operation: BrowserTransfers.Operation, text: String? = null) {
        if (pending || controller.transferContext() == null) return
        pending = true
        activity.lifecycleScope.launch {
            try {
                val context = current()
                val proof = text?.let(BrowserTransfers::textProof)
                val admitted = grant(BrowserTransfers.Request(context, operation, context.targetId, proof?.size, proof?.sha256))
                val selected = client.clipboard(admitted, text)
                if (operation == BrowserTransfers.Operation.COPY) {
                    require(current() == context) { "browser_copy_context_changed" }
                    if (selected.isNullOrEmpty()) controller.reportTransfer("No non-sensitive page text was selected. The phone clipboard was unchanged.")
                    else {
                        val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                        clipboard.setPrimaryClip(ClipData.newPlainText("VAN browser selection", selected))
                        controller.reportTransfer("The selected page text was copied to the phone clipboard for this action.")
                    }
                } else controller.reportTransfer("The browser host confirmed this one paste. Automatic clipboard sharing remains off.")
            } catch (cancelled: CancellationException) {
                controller.reportTransfer("Clipboard confirmation stopped. A paste may already have been applied; check the page before repeating it.")
                throw cancelled
            } catch (failure: Exception) {
                controller.reportTransfer(if (operation == BrowserTransfers.Operation.PASTE)
                    "Paste was not confirmed. It may already have been applied; check the page before repeating it."
                    else "Copy was not confirmed. The phone clipboard was unchanged.")
            } finally { pending = false }
        }
    }
    private class SaveDocument : ActivityResultContract<BrowserDownloadReview.Download, Uri?>() {
        override fun createIntent(context: Context, input: BrowserDownloadReview.Download): Intent =
            Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType(input.mime.takeIf { it.contains('/') } ?: "application/octet-stream")
                .putExtra(Intent.EXTRA_TITLE, input.name)
        override fun parseResult(resultCode: Int, intent: Intent?): Uri? =
            if (resultCode == android.app.Activity.RESULT_OK) intent?.data else null
    }
}
