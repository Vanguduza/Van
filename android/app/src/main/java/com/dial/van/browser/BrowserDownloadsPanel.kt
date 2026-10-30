package com.dial.van.browser

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerValue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

/** A reachable owner review surface for the actual record GET/DELETE contracts only. */
@Composable
fun BrowserDownloadsPanel(gateway: VanGatewayClient, sessionId: String, onDismiss: () -> Unit,
    onSaveToPhone: (BrowserDownloadReview.Download) -> Unit = {}, transferPending: Boolean = false,
    transferAvailable: Boolean = false, onPaste: () -> Unit = {}, onCopy: () -> Unit = {}, transferNotice: String? = null,
    onImport: () -> Unit = {}, onAnalyse: (BrowserDownloadReview.Download) -> Unit = {},
    onOpen: (BrowserDownloadReview.Download) -> Unit = {}, onRecover: () -> Unit = {},
    ownerApp: VanApplication? = null, ownerActivity: FragmentActivity? = null) {
    val scope = rememberCoroutineScope()
    var downloads by remember(sessionId) { mutableStateOf<List<BrowserDownloadReview.Download>?>(null) }
    var error by remember(sessionId) { mutableStateOf<String?>(null) }
    var notice by remember(sessionId) { mutableStateOf<String?>(null) }
    var loading by remember(sessionId) { mutableStateOf(false) }
    var fresh by remember(sessionId) { mutableStateOf(false) }
    var removing by remember(sessionId) { mutableStateOf(false) }
    var selected by remember(sessionId) { mutableStateOf<BrowserDownloadReview.Download?>(null) }
    var providerContracts by remember(sessionId) { mutableStateOf<JSONObject?>(null) }
    var providerError by remember(sessionId) { mutableStateOf<String?>(null) }
    var providerFresh by remember(sessionId) { mutableStateOf(false) }
    var selectedProvider by remember(sessionId) { mutableStateOf<Pair<BrowserDownloadReview.Download, BrowserFileProvider.Contract>?>(null) }

    suspend fun refresh() {
        loading = true
        try {
            downloads = BrowserDownloadReview.rows(gateway.interactiveBrowserDownloads(sessionId))
            fresh = true
            error = null
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            fresh = false
            error = "Current downloads could not be read. Last confirmed records remain visible; refresh to retry."
        } finally { loading = false }
        try {
            val current = gateway.browserFileProviderContracts(sessionId)
            check(current.optString("session_id") == sessionId)
            BrowserFileProvider.contracts(current, sessionId)
            providerContracts = current; providerError = null; providerFresh = true
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { providerFresh = false; providerError = "Current archive/VEKL target contracts could not be read. These effects remain unavailable." }
    }
    LaunchedEffect(sessionId) { refresh() }
    if (selectedProvider == null) AlertDialog(
        onDismissRequest = { if (!removing) onDismiss() }, title = { Text("Downloads & phone files") },
        text = {
            LazyColumn(modifier = Modifier.fillMaxWidth().heightIn(max = 480.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    Text("Save a completed safe download to a phone location you choose. VAN verifies its size and hash before writing the phone copy.")
                    Text("Import a phone file into this session's native file store, without attaching it to a page. Page uploads remain separate and require that page's chooser.")
                    OutlinedButton(enabled = transferAvailable && !transferPending, onClick = onImport) { Text("Import phone file…") }
                    OutlinedButton(enabled = !transferPending, onClick = onRecover) { Text("Recover uncertain file outcome") }
                    providerError?.let { Text(it) }
                    if (providerContracts == null && providerError == null) Text("Reading governed file-provider readiness…")
                    providerContracts?.optJSONArray("contracts").ownerRows().forEach { contract ->
                        val label = when (contract.optString("owner_action")) { "SAVE_ON_ORACLE" -> "Save on Oracle"; "ADD_TO_VEKL" -> "Add to VEKL"; else -> contract.ownerValue("owner_action") }
                        Text("$label: ${contract.ownerValue("state").replace('_', ' ')} · ${contract.ownerValue("reason").replace('_', ' ')}")
                        Text("Requires a governed target, exact owner project scope, native A4 approval and independent persisted-byte readback. Configured transport does not verify the target.")
                    }
                    Text("Automatic clipboard sharing is off. These buttons authorize one explicit text action.")
                    OutlinedButton(enabled = transferAvailable && !transferPending, onClick = onPaste) { Text("Paste phone clipboard text into this page") }
                    OutlinedButton(enabled = transferAvailable && !transferPending, onClick = onCopy) { Text("Copy selected page text to phone clipboard") }
                    transferNotice?.let { Text(it) }
                    if (transferPending) Text("A phone file action is in progress…")
                    if (loading) Text("Reading download records…")
                    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    notice?.let { Text(it) }
                    if (downloads?.isEmpty() == true && fresh) Text("No downloads are recorded for this browser session.")
                }
                items(downloads.orEmpty()) { download ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        HorizontalDivider()
                        Text(download.name, style = MaterialTheme.typography.titleSmall)
                        Text(download.ownerState)
                        Text("${download.mime} · ${download.byteSize?.let { "$it bytes" } ?: "Size not supplied"}")
                        if (download.dangerous) Text("The host flagged this content as dangerous. File transfer and opening are blocked.")
                        download.failureReason?.let { Text("Host reason: ${it.replace('_', ' ')}") }
                        Text("Record: ${download.id.ifBlank { "Not supplied" }}", style = MaterialTheme.typography.labelMedium)
                        OutlinedButton(enabled = fresh && !loading && !removing && !transferPending && transferAvailable && download.maySave,
                            onClick = { onSaveToPhone(download) }) { Text("Save to phone…") }
                        OutlinedButton(enabled = fresh && !loading && !removing && !transferPending && transferAvailable && download.mayOpen,
                            onClick = { onOpen(download) }) { Text("Open safely in VAN") }
                        OutlinedButton(enabled = fresh && !loading && !removing && !transferPending && transferAvailable && download.mayAnalyse,
                            onClick = { onAnalyse(download) }) { Text("Inspect file without executing it") }
                        providerContracts?.let { body -> BrowserFileProvider.contracts(body, sessionId).forEach { target ->
                            OutlinedButton(enabled = fresh && providerFresh && target.mayPrepare && BrowserFileProvider.safeSource(download) &&
                                !loading && !removing && !transferPending && ownerApp != null && ownerActivity != null,
                                onClick = { selectedProvider = download to target }) { Text("${target.label}…") }
                        } }
                        if (!download.maySave && download.state == "COMPLETED") Text("The current host has not admitted a verified phone transfer for this file.")
                        OutlinedButton(enabled = fresh && !loading && !removing && download.mayDelete,
                            onClick = { selected = download }) { Text("Remove download") }
                        if (download.state in setOf("CREATED", "IN_PROGRESS")) Text("Removal is unavailable until the host records a supported final state.")
                    }
                }
                item { OutlinedButton(enabled = !loading && !removing,
                    onClick = { scope.launch { refresh() } }) { Text("Refresh records") } }
            }
        },
        confirmButton = { TextButton(enabled = !removing, onClick = onDismiss) { Text("Close") } },
    )
    selectedProvider?.let { (download, target) ->
        if (ownerApp != null && ownerActivity != null) BrowserFileProvidersPanel(ownerApp, ownerActivity, sessionId, download, target,
            onDismiss = { selectedProvider = null; scope.launch { refresh() } })
    }
    selected?.let { download ->
        AlertDialog(onDismissRequest = { selected = null }, title = { Text("Remove this download?") },
            text = { Text("${download.name}\nThis removes the host's download record. The browser host manages file cleanup. It does not remove a separate phone copy.") },
            confirmButton = { Button(enabled = fresh && !removing, onClick = {
                selected = null
                removing = true
                notice = null
                scope.launch {
                    try {
                        val result = BrowserDownloadReview.delete(download,
                            request = { gateway.interactiveBrowserDeleteDownload(sessionId, download.id) },
                            read = { gateway.interactiveBrowserDownloads(sessionId) })
                        result.confirmedDownloads?.let {
                            downloads = it
                            notice = "Download record removal was confirmed by readback. The browser host manages file cleanup."
                        }
                        error = result.error
                        fresh = result.error == null
                    } finally { removing = false }
                }
            }) { Text("Remove record") } },
            dismissButton = { TextButton(onClick = { selected = null }) { Text("Keep download") } })
    }
}
