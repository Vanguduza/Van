package com.dial.van.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import com.dial.van.VanApplication
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
internal fun DerivedMemoryRecordsSection(app: VanApplication, stores: List<String>, onRequestErasure: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    var selectedStore by remember { mutableStateOf<String?>(null) }
    var cursor by remember(selectedStore) { mutableStateOf(0) }
    var selected by remember { mutableStateOf<DerivedMemoryRecord?>(null) }
    SectionHeader("Inspect individual records")
    Text("Inspect what VAN inferred, observed or retained in each store. Deleting one record requires approval for its exact current revision.", style = tokens.type.label)
    stores.forEach { store -> TextButton(onClick = { selectedStore = store }) { Text(if (store == selectedStore) "✓ ${store.replace('_', ' ')}" else store.replace('_', ' ')) } }
    selectedStore?.let { store ->
        OwnerDataSection("Records in ${store.replace('_', ' ')} · page ${cursor / 50 + 1}", load = { app.gatewayClient.contextRecords(store, cursor = cursor) }) { body, actions ->
            Text("${body.optInt("total")} records · offsets may move after writes; refresh after a deletion.", style = tokens.type.label)
            val records = body.optJSONArray("records").ownerRows()
            if (records.isEmpty()) Text("No records on this page.")
            records.forEach { raw ->
                val record = runCatching { DerivedMemoryRecord.parse(raw) }.getOrNull()
                VanPanel(dense = true) {
                    Column {
                        Text(raw.ownerValue("title"), style = tokens.type.body)
                        Text(record?.sourceLabel ?: "Record inspection contract unavailable", style = tokens.type.label)
                        OutlinedButton(enabled = actions.canMutate && record?.store == store, onClick = { selected = record }) { Text("Inspect record") }
                    }
                }
            }
            if (cursor > 0) OutlinedButton(enabled = actions.canMutate, onClick = { cursor = (cursor - 50).coerceAtLeast(0) }) { Text("Previous page") }
            if (!body.isNull("next_cursor")) OutlinedButton(enabled = actions.canMutate, onClick = { cursor = body.getInt("next_cursor") }) { Text("Next page") }
        }
    }
    selected?.let { record -> DerivedMemoryRecordDialog(app, record, onDismiss = { selected = null }, onRequestErasure) }
}

@Composable
private fun DerivedMemoryRecordDialog(app: VanApplication, selected: DerivedMemoryRecord, onDismiss: () -> Unit, onRequestErasure: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    var pending by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var erasurePlan by remember { mutableStateOf<JSONObject?>(null) }
    AlertDialog(onDismissRequest = { if (!pending) onDismiss() }, title = { Text("Inspect derived memory") }, text = {
        Column(modifier = Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            OwnerDataSection("Current record ${selected.id}", load = { app.gatewayClient.contextRecord(selected.store, selected.id) }) { raw, actions ->
                val current = runCatching { DerivedMemoryRecord.parse(raw) }.getOrNull()
                Text(raw.ownerValue("title"), style = tokens.type.body)
                Text(current?.sourceLabel ?: "Record contract unavailable", style = tokens.type.label)
                raw.optJSONArray("fields").ownerRows().forEach { field -> Text("${field.ownerValue("name").replace('_', ' ')}: ${field.ownerValue("value")}", style = tokens.type.body) }
                raw.optJSONObject("provenance")?.let { provenance ->
                    Text("Source: ${provenance.ownerValue("source_ref")}\nAuthority: ${provenance.ownerValue("authority")}\nState: ${provenance.ownerValue("state")}\nObserved ${ownerTime(provenance.optLong("observed_at_ms"))}", style = tokens.type.label)
                    Text("Evidence: ${provenance.ownerValue("evidence_refs")}", style = tokens.type.label)
                }
                Text("Revision: ${raw.ownerValue("revision_sha256")}", style = tokens.type.label)
                Button(enabled = actions.canMutate && current != null && !pending, onClick = {
                    val exact = current ?: return@Button
                    pending = true; error = null; notice = null
                    scope.launch {
                        try {
                            val exported = app.gatewayClient.exportContextRecord(exact.store, exact.id)
                            check(exact.matches(DerivedMemoryRecord.parse(exported))) { "The record changed before export. Refresh it." }
                            clipboard.setText(AnnotatedString(exported.toString(2)))
                            notice = "The screened record export was copied. It grants no execution permission."
                        } catch (cancel: CancellationException) { throw cancel }
                        catch (failure: Exception) { error = failure.message ?: "Record export could not be read." }
                        finally { pending = false }
                    }
                }) { Text("Copy screened export") }
                OutlinedButton(enabled = actions.canMutate && current != null && !pending, onClick = {
                    val exact = current ?: return@OutlinedButton
                    pending = true; error = null; notice = null
                    scope.launch {
                        try {
                            val plan = app.gatewayClient.contextRecordErasurePlan(exact.store, exact.id)
                            exact.erasureCommand(plan)
                            erasurePlan = plan
                        } catch (cancel: CancellationException) { throw cancel }
                        catch (failure: Exception) { error = failure.message ?: "No current erasure plan could be read." }
                        finally { pending = false }
                    }
                }) { Text("Review exact record erasure") }
            }
            error?.let { Text(it) }; notice?.let { Text(it) }
        }
    }, confirmButton = { TextButton(enabled = !pending, onClick = onDismiss) { Text("Close") } })
    erasurePlan?.let { plan ->
        AlertDialog(onDismissRequest = { erasurePlan = null }, title = { Text("Forget this exact record?") }, text = {
            Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) {
                Text("This removes the selected current record and its dependent links. Other work and audit records are retained. Approve the sealed scope with fresh biometrics in Work.")
                Text("Affected stores: ${plan.ownerValue("affected_stores")}")
                plan.optJSONArray("affected_records").ownerRows().forEach { affected ->
                    Text("${affected.ownerValue("store")}: ${affected.optInt("count")} records${if (affected.optBoolean("truncated")) " (listed identities truncated)" else ""}")
                    Text(affected.ownerValue("record_ids"))
                }
                plan.optJSONObject("kept_deliberately")?.let { kept -> kept.keys().asSequence().toList().forEach { Text(kept.ownerValue(it)) } }
            }
        }, confirmButton = { Button(onClick = { erasurePlan = null; onRequestErasure(plan.getString("command_text")) }) { Text("Continue to approval") } }, dismissButton = { TextButton(onClick = { erasurePlan = null }) { Text("Keep record") } })
    }
}
