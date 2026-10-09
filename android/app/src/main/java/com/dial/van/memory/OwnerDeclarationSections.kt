package com.dial.van.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.owner.OwnerDataSection
import com.dial.van.command.owner.ownerRows
import com.dial.van.command.owner.ownerValue
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.VanPanel
import org.json.JSONObject

@Composable
fun OwnerVocabularySection(app: VanApplication) {
    val tokens = LocalVanTokens.current
    OwnerDataSection("Define your shared vocabulary", load = { app.gatewayClient.ownerVocabulary() }) { body, actions ->
        var editing by remember { mutableStateOf(false) }
        var term by remember { mutableStateOf("") }
        var meaning by remember { mutableStateOf("") }
        var operation by remember { mutableStateOf("") }
        var examples by remember { mutableStateOf("") }
        var antiExamples by remember { mutableStateOf("") }
        var project by remember { mutableStateOf("") }
        var validationError by remember { mutableStateOf<String?>(null) }
        fun open(entry: JSONObject?) {
            term = entry?.optString("term").orEmpty()
            meaning = entry?.optString("owner_meaning").orEmpty()
            operation = entry?.optString("system_operationalization").orEmpty()
            fun rows(key: String) = entry?.optJSONArray(key)?.let { array -> (0 until array.length()).joinToString("\n") { array.optString(it) } }.orEmpty()
            examples = rows("examples"); antiExamples = rows("anti_examples")
            project = if (entry == null || entry.isNull("project_id")) "" else entry.optString("project_id")
            validationError = null; editing = true
        }
        Text("These are definitions you supply. They grant no execution authority.", style = tokens.type.label, color = tokens.color.textSecondary)
        val entries = body.optJSONArray("entries").ownerRows()
        if (entries.isEmpty()) Text("No shared definitions recorded.")
        entries.forEach { record -> record.optJSONObject("entry")?.let { entry ->
            VanPanel(dense = true) {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Text(entry.ownerValue("term"), style = tokens.type.body)
                    Text("Your meaning: ${entry.ownerValue("owner_meaning")}\nHow VAN should use it: ${entry.ownerValue("system_operationalization")}", style = tokens.type.label)
                    Text(if (record.optString("status") == "SAVED") "Owner-authored definition" else "Observed definition; owner declaration is unconfirmed", style = tokens.type.label)
                    OutlinedButton(enabled = actions.canMutate, onClick = { open(entry) }) { Text("Edit definition") }
                }
            }
        } }
        Button(enabled = actions.canMutate, onClick = { open(null) }) { Text("Define a term") }
        if (editing) AlertDialog(onDismissRequest = { if (actions.canMutate) editing = false }, title = { Text("Your definition") }, text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                OutlinedTextField(term, { term = it }, label = { Text("Term") })
                OutlinedTextField(meaning, { meaning = it }, label = { Text("What it means to you") })
                OutlinedTextField(operation, { operation = it }, label = { Text("How VAN should use it") })
                OutlinedTextField(examples, { examples = it }, label = { Text("Examples, one per line") })
                OutlinedTextField(antiExamples, { antiExamples = it }, label = { Text("Counterexamples, one per line") })
                OutlinedTextField(project, { project = it }, label = { Text("Existing project ID, optional") })
                validationError?.let { Text(it) }
            }
        }, confirmButton = { Button(enabled = actions.canMutate, onClick = {
            val declaration = runCatching { OwnerVocabularyDefinition.prepare(term, meaning, operation,
                examples.lines().filter { it.isNotBlank() }, antiExamples.lines().filter { it.isNotBlank() }, project.takeIf { it.isNotBlank() }) }
                .getOrElse { validationError = it.message; return@Button }
            actions.mutate("vocabulary:${declaration.term}", "Your exact definition was saved and independently read back.") {
                val session = app.vanSession.state.value
                app.gatewayClient.saveOwnerVocabulary(declaration, session.vanSessionId ?: error("Reconnect the owner session before saving."), session.sessionEpoch).also { editing = false }
            }
        }) { Text("Save definition") } }, dismissButton = { TextButton(enabled = actions.canMutate, onClick = { editing = false }) { Text("Cancel") } })
    }
}

@Composable
fun OwnerCollaborationSection(app: VanApplication) {
    val tokens = LocalVanTokens.current
    OwnerDataSection("Your collaboration instructions", load = { app.gatewayClient.ownerCollaborationPreferences() }) { body, actions ->
        var editing by remember { mutableStateOf(false) }
        var domain by remember { mutableStateOf("") }
        var pattern by remember { mutableStateOf("") }
        var validationError by remember { mutableStateOf<String?>(null) }
        Text("Tell VAN how you want to work together in a domain. This records your preference and grants no action permission.", style = tokens.type.label, color = tokens.color.textSecondary)
        val rows = body.optJSONArray("entries").ownerRows()
        if (rows.isEmpty()) Text("No owner-authored collaboration instructions.")
        rows.forEach { record -> record.optJSONObject("entry")?.let { entry ->
            VanPanel(dense = true) {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Text(entry.ownerValue("domain"), style = tokens.type.body)
                    Text(entry.ownerValue("preferred_collaboration_pattern"), style = tokens.type.label)
                    Text(if (record.optString("status") == "SAVED") "Confirmed owner instruction" else "Unconfirmed instruction", style = tokens.type.label)
                    OutlinedButton(enabled = actions.canMutate, onClick = { domain = entry.optString("domain"); pattern = entry.optString("preferred_collaboration_pattern"); validationError = null; editing = true }) { Text("Edit instruction") }
                }
            }
        } }
        Button(enabled = actions.canMutate, onClick = { domain = ""; pattern = ""; validationError = null; editing = true }) { Text("Add collaboration instruction") }
        if (editing) AlertDialog(onDismissRequest = { if (actions.canMutate) editing = false }, title = { Text("Your collaboration instruction") }, text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                OutlinedTextField(domain, { domain = it }, label = { Text("Domain, such as google.gmail") })
                OutlinedTextField(pattern, { pattern = it }, label = { Text("How VAN should collaborate with you") })
                validationError?.let { Text(it) }
            }
        }, confirmButton = { Button(enabled = actions.canMutate, onClick = {
            val preference = runCatching { OwnerCollaborationPreference.prepare(domain, pattern) }.getOrElse { validationError = it.message; return@Button }
            actions.mutate("collaboration:${preference.domain}", "Your instruction was saved and independently read back.") {
                val session = app.vanSession.state.value
                app.gatewayClient.saveOwnerCollaborationPreference(preference, session.vanSessionId ?: error("Reconnect the owner session before saving."), session.sessionEpoch).also { editing = false }
            }
        }) { Text("Save instruction") } }, dismissButton = { TextButton(enabled = actions.canMutate, onClick = { editing = false }) { Text("Cancel") } })
    }
}
