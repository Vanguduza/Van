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
import com.dial.van.command.owner.ownerTime
import com.dial.van.gateway.VanGatewayClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Independent reads expose known tabs and recorded changes without inventing stream commands. */
@Composable
fun BrowserSessionPanel(gateway: VanGatewayClient, state: BrowserSessionController.State,
    onDelegate: (BrowserControlHolder) -> Unit, onDismiss: () -> Unit) {
    val snapshot = state.snapshot ?: return
    val scope = rememberCoroutineScope()
    var tabs by remember(snapshot.sessionId) { mutableStateOf<List<BrowserSessionRecords.Tab>?>(null) }
    var events by remember(snapshot.sessionId) { mutableStateOf<List<BrowserSessionRecords.Event>?>(null) }
    var tabsError by remember(snapshot.sessionId) { mutableStateOf<String?>(null) }
    var eventsError by remember(snapshot.sessionId) { mutableStateOf<String?>(null) }
    var observedAt by remember(snapshot.sessionId) { mutableStateOf(0L) }
    var loading by remember(snapshot.sessionId) { mutableStateOf(false) }
    var delegate by remember(snapshot.sessionId) { mutableStateOf<BrowserControlHolder?>(null) }
    suspend fun refresh() {
        if (loading) return
        loading = true
        try {
            try {
                tabs = BrowserSessionRecords.tabs(gateway.interactiveBrowserTabs(snapshot.sessionId))
                tabsError = null
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) { tabsError = "Current tabs could not be read. Any visible tabs are last known records." }
            try {
                events = BrowserSessionRecords.events(gateway.interactiveBrowserEvents(snapshot.sessionId))
                eventsError = null
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) { eventsError = "Current session history could not be read. Any visible events are last known records." }
            observedAt = System.currentTimeMillis()
        } finally { loading = false }
    }
    LaunchedEffect(snapshot.sessionId) { refresh() }
    val canDelegate = BrowserControlMutation.mayDelegate(snapshot, state.controlUncertain, state.controlMutationPending)
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Browser control & history") },
        text = { LazyColumn(modifier = Modifier.fillMaxWidth().heightIn(max = 480.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Text(state.ownerReadableState)
                Text("Control: ${snapshot.controlHolder.name.replace('_', ' ')} · generation ${snapshot.controlGeneration}")
                Text("Delegation hands this session to its linked VAN mission; it does not start a new task. Take control remains available while VAN is driving.")
                if (snapshot.missionId.isNullOrBlank()) Text("This session has no linked mission to delegate. Ask VAN to start browser work from Work first.")
                if (snapshot.controlDelegateIssuedFor.isNullOrBlank()) Text("The backend has not supplied an admitted browser worker identity. Delegation is unavailable.")
                else Text("Linked work: ${snapshot.missionId}")
                OutlinedButton(enabled = canDelegate, onClick = { delegate = BrowserControlHolder.HERMES_DETERMINISTIC }) { Text("Hand to deterministic VAN worker") }
                OutlinedButton(enabled = canDelegate, onClick = { delegate = BrowserControlHolder.HERMES_STAGEHAND }) { Text("Hand to VAN browser worker") }
                Text("Known tabs", style = MaterialTheme.typography.titleSmall)
                Text("This is the host's tab inventory. Tab switching, creation and closing have no admitted input command in this build.")
                tabsError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                if (tabs?.isEmpty() == true && tabsError == null) Text("The host reports no tabs.")
            }
            items(tabs.orEmpty(), key = { "tab:${it.id}" }) { tab -> Column {
                HorizontalDivider()
                Text("${if (tab.active) "Active · " else ""}${tab.title}")
                Text("Tab ${tab.id}", style = MaterialTheme.typography.labelMedium)
                tab.urlDigest?.let { Text("Address digest: $it", style = MaterialTheme.typography.labelMedium) }
            } }
            item {
                Text("Recorded session changes", style = MaterialTheme.typography.titleSmall)
                Text("Session activity is separate from a verified work outcome.")
                eventsError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                if (events?.isEmpty() == true && eventsError == null) Text("No durable session events are recorded.")
            }
            items(events.orEmpty(), key = { "event:${it.id}" }) { event -> Column {
                HorizontalDivider()
                Text(event.summary)
                Text("${event.severity} · ${ownerTime(event.occurredAtMs)}", style = MaterialTheme.typography.labelMedium)
                event.evidenceRef?.let { Text("Evidence: $it", style = MaterialTheme.typography.labelMedium) }
            } }
            item {
                if (observedAt > 0L) Text("Last refresh attempt ${ownerTime(observedAt)}", style = MaterialTheme.typography.labelMedium)
                OutlinedButton(enabled = !loading, onClick = { scope.launch { refresh() } }) { Text(if (loading) "Refreshing…" else "Refresh records") }
            }
        } }, confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } })
    delegate?.let { holder ->
        AlertDialog(onDismissRequest = { delegate = null }, title = { Text("Hand this browser to VAN?") },
            text = { Text("The ${if (holder == BrowserControlHolder.HERMES_DETERMINISTIC) "deterministic" else "browser"} worker may actuate this session for its linked mission. The handoff requires a matching control receipt and current readback. You can take control back.") },
            confirmButton = { Button(enabled = canDelegate, onClick = { delegate = null; onDelegate(holder) }) { Text("Hand over control") } },
            dismissButton = { TextButton(onClick = { delegate = null }) { Text("Keep control") } })
    }
}
