package com.dial.van.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerTime
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel
import org.json.JSONObject

@Composable
fun UnderstandingRoute(app: VanApplication, onBack: () -> Unit, onOpenRoute: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Memory") }; SectionHeader("What VAN understands") }
        item { OwnerVocabularySection(app) }
        item { OwnerCollaborationSection(app) }
        item {
            OwnerDataSection("Collaboration preferences", load = { app.gatewayClient.understanding() }) { body, actions ->
                var correcting by remember { mutableStateOf<JSONObject?>(null) }
                var correction by rememberSaveable { mutableStateOf("") }
                val fields = body.optJSONObject("fields") ?: JSONObject()
                if (!fields.keys().hasNext()) Text("No collaboration preferences have been recorded.", style = tokens.type.body, color = tokens.color.textSecondary)
                fields.keys().asSequence().toList().forEach { field ->
                    SectionHeader(field.replace('_', ' '))
                    fields.optJSONArray(field).ownerRows().forEach { assertion ->
                        val id = assertion.optString("assertion_id")
                        VanPanel {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                Text(assertion.ownerValue("value"), style = tokens.type.body, color = tokens.color.textPrimary)
                                val state = assertion.optString("state")
                                Text(when (state) { "CONFIRMED" -> "Confirmed by you"; "EVIDENCED" -> "VAN's conclusion from evidence, awaiting your own confirmation"; "REJECTED" -> "Rejected by you"; else -> state.lowercase().replace('_', ' ') }, style = tokens.type.label, color = tokens.color.textSecondary)
                                Text("Confidence ${(assertion.optDouble("confidence", 0.0) * 100).toInt()}% · ${assertion.optInt("independent_episodes")} independent episodes", style = tokens.type.label, color = tokens.color.textTertiary)
                                if (assertion.optBoolean("temporary")) Text("Temporary preference", style = tokens.type.label, color = tokens.color.textSecondary)
                                if (!assertion.isNull("project_id")) Text("Project ${assertion.ownerValue("project_id")}", style = tokens.type.label, color = tokens.color.textSecondary)
                                Text("Updated ${ownerTime(assertion.optLong("updated_at_ms"))}", style = tokens.type.label, color = tokens.color.textTertiary)
                                val evidence = assertion.optJSONArray("evidence_refs")
                                if (evidence == null || evidence.length() == 0) Text("No evidence references supplied.", style = tokens.type.label, color = tokens.color.textTertiary)
                                else (0 until evidence.length()).forEach { Text("Evidence: ${evidence.optString(it)}", style = tokens.type.label, color = tokens.color.textTertiary) }
                                val episodes = assertion.optJSONArray("supporting_episode_refs")
                                if (episodes != null) (0 until episodes.length()).map { episodes.optString(it) }.filter { it.startsWith("mission:") }.forEach { ref ->
                                    TextButton(onClick = { onOpenRoute(VanRoute.missionRoute(ref.removePrefix("mission:"))) }) { Text("Open supporting mission") }
                                }
                                if (assertion.optBoolean("autonomy_bearing")) Text("This affects collaboration. Confirming it grants no new standing permission and approves no consequential action.", style = tokens.type.label, color = tokens.color.textSecondary)
                                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                    if (state != "CONFIRMED" && state != "REJECTED") Button(enabled = actions.canMutate && id.isNotBlank(), onClick = {
                                        actions.mutate("confirm:$id", "Preference confirmed by you.") { app.gatewayClient.confirmUnderstanding(id).also { check(it.optString("assertion_id") == id && it.optString("state") == "CONFIRMED") { "Confirmation receipt did not match." } } }
                                    }) { Text("Confirm") }
                                    OutlinedButton(enabled = actions.canMutate && id.isNotBlank(), onClick = { correcting = assertion; correction = assertion.optString("value") }) { Text("Correct") }
                                    if (state != "REJECTED") OutlinedButton(enabled = actions.canMutate && id.isNotBlank(), onClick = {
                                        actions.mutate("reject:$id", "Preference rejected. VAN must not treat it as your confirmed preference.") { app.gatewayClient.rejectUnderstanding(id).also { check(it.optString("assertion_id") == id && it.optString("state") == "REJECTED") { "Rejection receipt did not match." } } }
                                    }) { Text("Reject") }
                                }
                            }
                        }
                    }
                }
                SectionHeader("Shared vocabulary")
                val vocabulary = body.optJSONArray("shared_vocabulary").ownerRows()
                if (vocabulary.isEmpty()) Text("No shared terms recorded.", style = tokens.type.label, color = tokens.color.textSecondary)
                vocabulary.forEach { term ->
                    VanPanel(dense = true) {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                            Text(term.ownerValue("term"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("Your meaning: ${term.ownerValue("owner_meaning")}\nHow VAN applies it: ${term.ownerValue("system_operationalization")}", style = tokens.type.label, color = tokens.color.textSecondary)
                            Text("Examples: ${term.ownerValue("examples")}\nWhat it excludes: ${term.ownerValue("anti_examples")}\nEvidence: ${term.ownerValue("evidence_refs")}", style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                    }
                }
                SectionHeader("Collaboration hypotheses")
                val complement = body.optJSONArray("cognitive_complement").ownerRows()
                if (complement.isEmpty()) Text("No collaboration hypotheses recorded.", style = tokens.type.label, color = tokens.color.textSecondary)
                complement.forEach { entry ->
                    VanPanel(dense = true) {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                            Text(entry.ownerValue("domain"), style = tokens.type.body, color = tokens.color.textPrimary)
                            Text("Observed owner strength: ${entry.ownerValue("owner_strength")}\nCandidate working pattern: ${entry.ownerValue("owner_vulnerability_candidate")}\nVAN strength: ${entry.ownerValue("van_strength")}\nPreferred collaboration: ${entry.ownerValue("preferred_collaboration_pattern")}", style = tokens.type.label, color = tokens.color.textSecondary)
                            Text("These are task-based hypotheses.\nEvidence: ${entry.ownerValue("evidence_refs_json")}\nUpdated ${ownerTime(entry.optLong("updated_at_ms"))}", style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                    }
                }
                body.optJSONObject("calibration")?.let { calibration ->
                    SectionHeader("Current communication style")
                    Text("${calibration.ownerValue("challenge_mode")} · ${calibration.ownerValue("verbosity")} · ${calibration.ownerValue("evidence_presentation")}", style = tokens.type.label, color = tokens.color.textSecondary)
                    Text("Reasons: ${calibration.ownerValue("reasons")}\nCommunication style changes neither truth standards nor action authority.", style = tokens.type.label, color = tokens.color.textTertiary)
                }
                correcting?.let { assertion ->
                    AlertDialog(onDismissRequest = { correcting = null }, title = { Text("Correct this preference") }, text = {
                        OutlinedTextField(value = correction, onValueChange = { correction = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Your correction") })
                    }, confirmButton = { Button(enabled = actions.canMutate && correction.isNotBlank(), onClick = {
                        val id = assertion.getString("assertion_id"); val value = correction.trim(); correcting = null
                        actions.mutate("correct:$id", "Correction recorded as your stated preference; the old version is superseded.") { app.gatewayClient.correctUnderstanding(id, value).also { check(it.optString("state") == "CONFIRMED" && it.optString("value") == value && it.optString("assertion_id").isNotBlank()) { "Correction receipt did not match." } } }
                    }) { Text("Save correction") } }, dismissButton = { TextButton(onClick = { correcting = null }) { Text("Cancel") } })
                }
            }
        }
    }
}

@Composable
fun AdaptationsRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Memory") }; SectionHeader("Adaptations") }
        item {
            OwnerDataSection("How VAN has adapted", load = { app.gatewayClient.understanding() }) { body, actions ->
                var reverting by remember { mutableStateOf<JSONObject?>(null) }
                val waiting = body.optJSONArray("adaptation_awaiting_you").ownerRows()
                val active = body.optJSONArray("recent_adaptation").ownerRows()
                if (waiting.isEmpty() && active.isEmpty()) Text("No adaptations are active or awaiting you.", style = tokens.type.body, color = tokens.color.textSecondary)
                listOf("Waiting for you" to waiting, "Currently in effect" to active).forEach { (label, rows) ->
                    if (rows.isNotEmpty()) SectionHeader(label)
                    rows.forEach { change ->
                        val id = change.optString("change_id")
                        VanPanel {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                Text(change.ownerValue("observed_pattern"), style = tokens.type.body, color = tokens.color.textPrimary)
                                Text("Before: ${change.ownerValue("previous_behavior")}\nAfter: ${change.ownerValue("new_behavior")}", style = tokens.type.body, color = tokens.color.textSecondary)
                                Text("Reason: ${change.ownerValue("reason")}", style = tokens.type.label, color = tokens.color.textSecondary)
                                Text("Evidence: ${change.ownerValue("evidence_refs_json")}\nRecorded ${ownerTime(change.optLong("created_at_ms"))}", style = tokens.type.label, color = tokens.color.textTertiary)
                                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                    if (change in waiting) Button(enabled = actions.canMutate && id.isNotBlank(), onClick = {
                                        actions.mutate("confirm:$id", "Adaptation confirmed and read back from VAN.") {
                                            val receipt = app.gatewayClient.confirmAdaptation(id)
                                            check(receipt.optString("change_id") == id && receipt.optBoolean("confirmed")) { "No matching confirmation receipt." }
                                            val readback = app.gatewayClient.understanding().optJSONArray("recent_adaptation").ownerRows()
                                            check(readback.any { it.optString("change_id") == id && it.optLong("owner_confirmed_at_ms") > 0L }) { "Adaptation confirmation could not be read back." }
                                            receipt
                                        }
                                    }) { Text("Confirm adaptation") }
                                    if (change.optInt("reversible") == 1 || change.optBoolean("reversible")) OutlinedButton(enabled = actions.canMutate && id.isNotBlank(), onClick = { reverting = change }) { Text("Revert") }
                                    else Text("This adaptation has no supported rollback.", style = tokens.type.label, color = tokens.color.textSecondary)
                                }
                            }
                        }
                    }
                }
                reverting?.let { change -> AlertDialog(onDismissRequest = { reverting = null }, title = { Text("Revert this adaptation?") }, text = { Text("VAN will stop using this adaptation. ${change.ownerValue("new_behavior")}") }, confirmButton = {
                    Button(enabled = actions.canMutate, onClick = {
                        val id = change.getString("change_id"); reverting = null
                        actions.mutate("revert:$id", "Adaptation reverted.") { app.gatewayClient.revertAdaptation(id).also { check(it.optString("change_id") == id && it.optBoolean("reverted")) { "Rollback was not confirmed." } } }
                    }) { Text("Revert") }
                }, dismissButton = { TextButton(onClick = { reverting = null }) { Text("Keep adaptation") } }) }
            }
        }
    }
}
