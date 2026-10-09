package com.dial.van.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dial.van.VanApplication
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel

@Composable
internal fun FactHistoryDialog(app: VanApplication, fact: MemoryFact, onDismiss: () -> Unit) {
    val tokens = LocalVanTokens.current
    AlertDialog(onDismissRequest = onDismiss, title = { Text("History: ${fact.predicate.replace('_', ' ')}") }, text = {
        LazyColumn(modifier = Modifier.heightIn(max = 420.dp), verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            item {
                OwnerDataSection("Fact revisions", load = { app.gatewayClient.contextHistory(fact.subject, fact.predicate, fact.scope) }) { body, _ ->
                    Text("${fact.subject} · ${fact.scope}", style = tokens.type.label, color = tokens.color.textSecondary)
                    val revisions = body.optJSONArray("revisions").ownerRows()
                    if (revisions.isEmpty()) Text("No revisions recorded for this fact.", style = tokens.type.body, color = tokens.color.textSecondary)
                    revisions.forEach { revision ->
                        VanPanel(dense = true) {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                                Text(revision.ownerValue("value"), style = tokens.type.body, color = tokens.color.textPrimary)
                                Text("Revision ${revision.optInt("revision")} · ${revision.ownerValue("authority")}\nSource: ${revision.ownerValue("source_ref")}\nTrust: ${revision.ownerValue("source_trust")}", style = tokens.type.label, color = tokens.color.textSecondary)
                                Text("Valid from ${ownerTime(revision.optLong("valid_from_ms"))}\n${if (revision.isNull("valid_until_ms")) "No recorded end" else "Ended ${ownerTime(revision.optLong("valid_until_ms"))}"}", style = tokens.type.label, color = tokens.color.textTertiary)
                                if (!revision.isNull("superseded_by_fact_id")) Text("Replaced by ${revision.ownerValue("superseded_by_fact_id")}", style = tokens.type.label, color = tokens.color.textTertiary)
                                else if (!revision.isNull("valid_until_ms")) Text("Withdrawn without a replacement.", style = tokens.type.label, color = tokens.color.textTertiary)
                            }
                        }
                    }
                }
            }
        }
    }, confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } })
}

@Composable
internal fun MemoryPrivacyDialog(app: VanApplication, onDismiss: () -> Unit, onRequestErasure: (String?) -> Unit,
    onRequestRecordErasure: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    var target by remember { mutableStateOf<String?>(null) }
    var confirmAll by remember { mutableStateOf(false) }
    var dispatching by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = { if (!dispatching) onDismiss() }, title = { Text("Memory privacy") }, text = {
        LazyColumn(modifier = Modifier.heightIn(max = 420.dp), verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            item {
                OwnerDataSection("What VAN holds about you", load = { app.gatewayClient.contextMemory() }) { body, actions ->
                    val stores = body.optJSONObject("stores")
                    stores?.keys()?.asSequence()?.toList()?.forEach { store ->
                        val detail = stores.optJSONObject(store) ?: return@forEach
                        VanPanel(dense = true) {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                                Text(detail.ownerValue("holds"), style = tokens.type.body, color = tokens.color.textPrimary)
                                Text("${detail.optInt("rows")} records · ${store.replace('_', ' ')}", style = tokens.type.label, color = tokens.color.textSecondary)
                                OutlinedButton(enabled = actions.canMutate && detail.optInt("rows") > 0, onClick = { target = store }) { Text("Forget this store") }
                            }
                        }
                    }
                    DerivedMemoryRecordsSection(app, stores?.keys()?.asSequence()?.toList().orEmpty(), onRequestRecordErasure)
                    OutlinedButton(enabled = actions.canMutate, onClick = { confirmAll = true }) { Text("Forget all owner-derived memory") }
                    SectionHeader("Retained records")
                    body.optJSONObject("kept_deliberately")?.let { kept ->
                        kept.keys().asSequence().toList().forEach { key -> Text(kept.ownerValue(key), style = tokens.type.label, color = tokens.color.textSecondary) }
                    }
                    if (target != null || confirmAll) {
                        val store = target
                        AlertDialog(onDismissRequest = { target = null; confirmAll = false }, title = { Text(if (store == null) "Forget all owner-derived memory?" else "Forget ${store.replace('_', ' ')}?") }, text = {
                            Text("This deletes ${if (store == null) "the owner-derived records in every listed store" else "all owner-derived records in this store"}. Retained records listed in the privacy view remain. This does not undo completed actions. Next, approve this exact deletion with device biometrics in Work. Nothing is erased before VAN verifies that approval.")
                        }, confirmButton = { Button(enabled = actions.canMutate, onClick = {
                            target = null; confirmAll = false
                            if (!dispatching) {
                                dispatching = true
                                onRequestErasure(store)
                            }
                        }) { Text("Forget") } }, dismissButton = { TextButton(onClick = { target = null; confirmAll = false }) { Text("Keep memory") } })
                    }
                }
            }
        }
    }, confirmButton = { TextButton(enabled = !dispatching, onClick = onDismiss) { Text("Close") } })
}
