package com.dial.van.projects

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel

@Composable
fun ProjectRationaleRoute(app: VanApplication, projectId: String, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    var typeName by rememberSaveable(projectId) { mutableStateOf(ProjectRationaleType.WHY_EXISTS.name) }
    var statement by rememberSaveable(projectId) { mutableStateOf("") }
    var reason by rememberSaveable(projectId) { mutableStateOf("") }
    var evidence by rememberSaveable(projectId) { mutableStateOf("") }
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Project") }; SectionHeader("Project rationale") }
        item {
            OwnerDataSection("Rationale for $projectId", load = { app.gatewayClient.projectStrategicMemory(projectId) }) { body, actions ->
                Text(body.ownerValue("not_project_truth"), style = tokens.type.body, color = tokens.color.textSecondary)
                val entries = body.optJSONArray("entries").ownerRows()
                if (entries.isEmpty()) Text("No rationale has been recorded for this project.", style = tokens.type.body, color = tokens.color.textSecondary)
                entries.forEach { entry ->
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                            Text(entry.ownerValue("entry_type").replace('_', ' '), style = tokens.type.label, color = tokens.color.textSecondary)
                            Text(entry.ownerValue("statement"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("Reason: ${entry.ownerValue("rationale")}\nEvidence references: ${entry.ownerValue("evidence_refs_json")}\nRecorded ${ownerTime(entry.optLong("created_at_ms"))}", style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                    }
                }
                SectionHeader("Record your rationale")
                LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    ProjectRationaleType.entries.forEach { type -> item {
                        OutlinedButton(enabled = actions.canMutate, onClick = { typeName = type.name }) { Text((if (typeName == type.name) "✓ " else "") + type.name.lowercase().replace('_', ' ')) }
                    } }
                }
                OutlinedTextField(value = statement, onValueChange = { statement = it }, enabled = !actions.pending("write"), label = { Text("Your statement") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = reason, onValueChange = { reason = it }, enabled = !actions.pending("write"), label = { Text("Why, if useful") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = evidence, onValueChange = { evidence = it }, enabled = !actions.pending("write"), label = { Text("Evidence references, one per line (optional)") }, modifier = Modifier.fillMaxWidth())
                Text("Your statement is saved as project rationale. References are recorded as supplied and do not establish repository facts or verified evidence.", style = tokens.type.label, color = tokens.color.textSecondary)
                Button(enabled = actions.canMutate && statement.isNotBlank(), onClick = {
                    val selected = ProjectRationaleType.valueOf(typeName)
                    val savedStatement = statement.trim(); val savedReason = reason.trim().takeIf { it.isNotBlank() }
                    val refs = evidence.lines().map { it.trim() }.filter { it.isNotBlank() }.distinct()
                    actions.mutate("write", "Your rationale was saved and read back from this project.") {
                        val receipt = app.gatewayClient.recordProjectRationale(projectId, selected, savedStatement, savedReason, refs)
                        val entryId = receipt.optString("entry_id")
                        check(receipt.optString("project_id") == projectId && entryId.isNotBlank()) { "The rationale receipt did not match this project." }
                        val readback = app.gatewayClient.projectStrategicMemory(projectId).optJSONArray("entries").ownerRows()
                        check(readback.any { it.optString("entry_id") == entryId && it.optString("entry_type") == selected.name && it.optString("statement") == savedStatement }) { "The saved rationale could not be read back." }
                        statement = ""; reason = ""; evidence = ""
                        receipt
                    }
                }) { Text(if (actions.pending("write")) "Saving…" else "Save rationale") }
            }
        }
    }
}
