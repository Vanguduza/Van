package com.dial.van.command.owner

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.VanPanel
import org.json.JSONObject

@Composable
private fun ServiceText(text: String, secondary: Boolean = false) {
    val tokens = LocalVanTokens.current
    Text(text, style = if (secondary) tokens.type.label else tokens.type.body,
        color = if (secondary) tokens.color.textSecondary else tokens.color.textPrimary)
}

@Composable
private fun ReadAvailability(body: JSONObject) {
    val errors = body.optJSONArray("errors").ownerRows()
    if (errors.isNotEmpty()) ServiceText("Some information could not be read: ${errors.joinToString { it.optString("section").replace('_', ' ') }}. Refresh to retry.")
    ServiceText("Service state observed ${ownerTime(body.optLong("observed_at_ms"))}", secondary = true)
}

@Composable
private fun ProviderCard(provider: JSONObject) {
    VanPanel {
        Column {
            ServiceText(provider.ownerValue("provider", provider.ownerValue("capability")))
            ServiceText(OwnerServicePresentation.state(provider.optString("state")))
            if (!provider.isNull("verified_at_ms")) ServiceText("Last verification ${ownerTime(provider.optLong("verified_at_ms"))}", true)
            if (!provider.isNull("evidence_pointer")) ServiceText("Verification receipt: ${provider.ownerValue("evidence_pointer")}", true)
            if (!provider.isNull("runtime_version")) ServiceText("Runtime ${provider.ownerValue("runtime_version")} · expected ${provider.ownerValue("expected_version")}", true)
        }
    }
}

@Composable
private fun CitationCard(citation: JSONObject, referenceField: String, snippet: String) {
    val clipboard = LocalClipboardManager.current
    val ref = citation.ownerValue(referenceField, "Source reference withheld or unavailable")
    val title = citation.ownerValue("title", "Evidence")
    VanPanel {
        Column {
            ServiceText(title)
            if (snippet.isNotBlank()) ServiceText(snippet)
            ServiceText(ref, true)
            ServiceText("Retrieved ${ownerTime(citation.optLong("retrieved_at_ms"))} · external evidence remains subject to review", true)
            ServiceText("Source trust: ${citation.ownerValue("source_trust", "Not recorded").replace('_', ' ')}", true)
            if (!citation.isNull("epistemic_state")) ServiceText("Evidence state: ${citation.ownerValue("epistemic_state").replace('_', ' ')} · scope: ${citation.ownerValue("scope")}", true)
            if (!citation.isNull("content_digest")) ServiceText("Content digest: ${citation.ownerValue("content_digest")}", true)
            OutlinedButton(onClick = { clipboard.setText(AnnotatedString("$title\n$ref\n$snippet")) }) { Text("Copy citation") }
        }
    }
}

@Composable
private fun CommandControl(control: JSONObject, canSubmit: Boolean, onCommand: (String) -> Unit) {
    val fields = control.optJSONArray("required_fields")
    val fieldNames = if (fields == null) emptyList() else (0 until fields.length()).map { fields.optString(it) }
    var values by remember(control.optString("control_id")) { mutableStateOf<Map<String, String>>(emptyMap()) }
    var confirming by remember(control.optString("control_id")) { mutableStateOf(false) }
    val available = canSubmit && control.optBoolean("available")
    VanPanel {
        Column {
            ServiceText(control.ownerValue("label"))
            if (!control.optBoolean("available")) ServiceText(OwnerServicePresentation.unavailable(control.optString("unavailable_reason")), true)
            fieldNames.forEach { field ->
                OutlinedTextField(value = values[field].orEmpty(), onValueChange = { values = values + (field to it) },
                    enabled = available, modifier = Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text(field.replace('_', ' ').replaceFirstChar { it.uppercase() }) })
            }
            val command = OwnerServicePresentation.command(control, values)
            Button(enabled = available && command != null, onClick = { confirming = true }) { Text("Request through VAN") }
            if (control.optString("action_class") == "A4") ServiceText("VAN will require a fresh biometric approval for this exact action.", true)
        }
    }
    if (confirming) AlertDialog(onDismissRequest = { confirming = false }, title = { Text(control.ownerValue("label")) },
        text = { Text("${OwnerServicePresentation.command(control, values).orEmpty()}\nVAN will check authority and report the result in Work.") },
        confirmButton = { Button(enabled = available, onClick = {
            OwnerServicePresentation.command(control, values)?.let(onCommand); confirming = false
        }) { Text("Submit request") } }, dismissButton = { TextButton(onClick = { confirming = false }) { Text("Cancel") } })
}

@Composable
fun KnowledgeServicesRoute(app: VanApplication, onBack: () -> Unit, onCommand: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Back") }; SectionHeader("Knowledge & citations") }
        item { OwnerDataSection("Knowledge providers", load = { app.gatewayClient.ownerKnowledge() }) { body, actions ->
            ReadAvailability(body)
            body.optJSONArray("providers").ownerRows().forEach { ProviderCard(it) }
            SectionHeader("Recent evidence")
            val evidence = body.optJSONArray("evidence").ownerRows()
            if (evidence.isEmpty()) ServiceText(OwnerServicePresentation.emptySection(body, "evidence", "No knowledge evidence has been recorded."))
            evidence.forEach { CitationCard(it, "source_ref", it.optString("snippet")) }
            SectionHeader("Notebook work")
            val operations = body.optJSONArray("operations").ownerRows()
            if (operations.isEmpty()) ServiceText(OwnerServicePresentation.emptySection(body, "operations", "No notebook operations have been recorded."))
            operations.forEach { op ->
                ServiceText("${op.ownerValue("operation").replace('_', ' ')} · ${OwnerServicePresentation.state(op.optString("status"))}")
                ServiceText("Resource: ${op.ownerValue("resource_id")}\nReceipt: ${op.ownerValue("evidence_pointer")}", true)
                if (!op.isNull("error_code")) ServiceText("This operation needs attention: ${op.ownerValue("error_code").replace('_', ' ')}", true)
            }
            SectionHeader("Owner requests")
            body.optJSONArray("controls").ownerRows().forEach { CommandControl(it, actions.canMutate, onCommand) }
        } }
    }
}

@Composable
fun ResearchServicesRoute(app: VanApplication, onBack: () -> Unit, onCommand: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    var query by rememberSaveable { mutableStateOf("") }
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Back") }; SectionHeader("Web research") }
        item { OwnerDataSection("Research service", load = { app.gatewayClient.ownerResearch() }) { body, actions ->
            ReadAvailability(body)
            body.optJSONObject("provider")?.let { ProviderCard(it) }
            val control = body.optJSONArray("controls")?.optJSONObject(0)
            val enabled = actions.canMutate && control?.optBoolean("available") == true
            val command = control?.let { OwnerServicePresentation.command(it, mapOf("query" to query)) }
            OutlinedTextField(value = query, onValueChange = { query = it }, enabled = enabled, modifier = Modifier.fillMaxWidth(), label = { Text("What would you like to research?") })
            ServiceText("Your query is sent to the external research provider through VAN. Do not include credentials or one-time codes.", true)
            Button(enabled = enabled && command != null, onClick = { command?.let(onCommand) }) { Text("Research through VAN") }
            SectionHeader("Recorded citations")
            val evidence = body.optJSONArray("evidence").ownerRows()
            if (evidence.isEmpty()) ServiceText(OwnerServicePresentation.emptySection(body, "evidence", "No research citations have been recorded."))
            evidence.forEach { citation ->
                val highlights = citation.optJSONArray("highlights")
                val snippet = if (highlights == null) "" else (0 until highlights.length()).joinToString("\n") { highlights.optString(it) }
                CitationCard(citation, "source_url", snippet)
            }
        } }
    }
}

@Composable
fun AutomationServicesRoute(app: VanApplication, onBack: () -> Unit, onCommand: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    var disabling by remember { mutableStateOf<String?>(null) }
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Back") }; SectionHeader("Automation & standing work") }
        item { OwnerAutomationPlansSection(app, onCommand) }
        item { OwnerDataSection("Automation supervision", load = { app.gatewayClient.ownerAutomation() }) { body, actions ->
            ReadAvailability(body)
            body.optJSONObject("runtime")?.let { ProviderCard(it) }
            if (!OwnerServicePresentation.sectionAvailable(body, "governance")) ServiceText("Current production activation decisions could not be read. Refresh to retry.")
            else if (body.optJSONObject("governance")?.optBoolean("production_activation_permitted") != true) ServiceText("Production activation still needs the required owner decisions.")
            SectionHeader("Standing work")
            val intents = body.optJSONArray("standing_intents").ownerRows()
            if (intents.isEmpty()) ServiceText(OwnerServicePresentation.emptySection(body, "standing_intents", "No standing intents have been recorded."))
            intents.forEach { intent ->
                val control = intent.optJSONObject("disable_control")
                VanPanel { Column {
                    ServiceText(intent.ownerValue("owner_goal"))
                    ServiceText(when { !intent.optBoolean("enabled") -> "Disabled"; intent.optBoolean("expired") -> "Expired"; !intent.optBoolean("executable_authority_present") -> "Enabled; no live authority remains"; else -> "Enabled with live bounded authority" })
                    ServiceText("Workflow version ${intent.optInt("workflow_version")} · ${intent.optInt("active_authorities")} live authority roots", true)
                    if (!intent.isNull("expires_at_ms")) ServiceText("Expires ${ownerTime(intent.optLong("expires_at_ms"))}", true)
                    OutlinedButton(enabled = actions.canMutate && control?.optBoolean("available") == true, onClick = { disabling = intent.optString("intent_id") }) { Text("Disable standing work") }
                    if (control?.optBoolean("available") != true) ServiceText(OwnerServicePresentation.unavailable(control?.optString("unavailable_reason").orEmpty()), true)
                } }
            }
            SectionHeader("Recent runs")
            val runs = body.optJSONArray("runs").ownerRows()
            if (runs.isEmpty()) ServiceText(OwnerServicePresentation.emptySection(body, "runs", "No automation runs have been recorded."))
            runs.forEach { run ->
                VanPanel { Column {
                    ServiceText(run.ownerValue("capability_id"))
                    ServiceText(OwnerServicePresentation.automationResult(run))
                    ServiceText("Verification: ${run.ownerValue("verifier_status")}\nReceipt: ${run.ownerValue("evidence_pointer")}", true)
                    if (!run.isNull("error_code")) ServiceText("Needs attention: ${run.ownerValue("error_code").replace('_', ' ')}", true)
                    if (!run.isNull("run_id") && run.optString("run_id").isNotBlank()) OwnerAutomationRunDetails(app, run.getString("run_id"))
                } }
            }
            SectionHeader("Work needing attention")
            val dead = body.optJSONArray("dead_letters").ownerRows()
            if (dead.isEmpty()) ServiceText(OwnerServicePresentation.emptySection(body, "dead_letters", "No unresolved automation failures have been recorded."))
            dead.forEach { ServiceText("${it.ownerValue("capability_id")} · ${it.ownerValue("failure_class").replace('_', ' ')}\nNext step: ${it.ownerValue("next_action").replace('_', ' ')}") }
            SectionHeader("Registered capabilities")
            body.optJSONArray("capabilities").ownerRows().forEach { ServiceText("${it.ownerValue("semantic_name")} · ${it.ownerValue("lifecycle_state").replace('_', ' ')}", true) }
            body.optJSONObject("ladder")?.let { ServiceText("${it.optInt("generations")} recorded generations · ${(it.optDouble("hot_hit_rate", 0.0) * 100).toInt()}% served from admitted cached work", true) }
            intents.firstOrNull { it.optString("intent_id") == disabling }?.let { intent ->
                val control = intent.optJSONObject("disable_control")
                AlertDialog(onDismissRequest = { disabling = null }, title = { Text("Disable this standing work?") },
                    text = { Text("${intent.ownerValue("owner_goal")}\nVAN will revoke the authority for future runs and verify the disabled state. The result appears in Work.") },
                    confirmButton = { Button(enabled = actions.canMutate && control?.optBoolean("available") == true, onClick = {
                        control?.let { OwnerServicePresentation.command(it, emptyMap())?.let(onCommand) }; disabling = null
                    }) { Text("Request disable") } }, dismissButton = { TextButton(onClick = { disabling = null }) { Text("Keep standing work") } })
            }
        } }
    }
}

@Composable
fun DiagnosticsServicesRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    val clipboard = LocalClipboardManager.current
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Back") }; SectionHeader("Service diagnostics") }
        item { OwnerDataSection("Service readiness & recovery", load = { app.gatewayClient.ownerDiagnostics() }) { body, _ ->
            ReadAvailability(body)
            body.optJSONArray("services").ownerRows().forEach { ProviderCard(it) }
            val surfaces = body.optJSONObject("computer_use")?.optJSONArray("surfaces_with_a_worker")
            ServiceText(if (!OwnerServicePresentation.sectionAvailable(body, "computer_use")) "Current computer control state is unavailable. Refresh to retry."
                else if (surfaces == null || surfaces.length() == 0) "Computer control has no registered surface worker." else "Registered computer surfaces: ${surfaces}")
            body.optJSONObject("temporal")?.let { ServiceText("Durable workflow service: ${OwnerServicePresentation.state(it.optString("state"))}. Live qualification is not recorded.") }
            body.optJSONObject("interactive_browser")?.let { ServiceText("Live browser: ${OwnerServicePresentation.state(it.optString("state"))}. Stream and device qualification still require evidence.") }
            if (!OwnerServicePresentation.sectionAvailable(body, "operations")) ServiceText("Current scheduler, certificate and backup state is unavailable. Refresh to retry.")
            else {
                SectionHeader("Scheduled work")
                body.optJSONObject("scheduler")?.let { scheduler ->
                    ServiceText(if (scheduler.optBoolean("running")) "Scheduler is running" else "Scheduler is stopped")
                    scheduler.optJSONArray("jobs").ownerRows().forEach { job ->
                        val last = job.optJSONObject("last_run")
                        ServiceText("${job.ownerValue("name").replace('.', ' ')} · ${last?.ownerValue("outcome") ?: "No recorded run"}\nLast run ${ownerTime((last?.optLong("finished_at_unix") ?: 0) * 1000)}", true)
                    }
                }
                SectionHeader("Certificates & backup")
                listOf("pki" to "Trading certificates", "device_pki" to "Phone certificates").forEach { (field, label) ->
                    val certs = body.optJSONObject(field)
                    ServiceText("$label: ${if (certs?.optBoolean("present") == true) "${certs.ownerValue("days_remaining")} days remaining" else "Not present"}")
                }
                body.optJSONObject("backup")?.let { backup -> ServiceText(if (backup.optBoolean("present")) "Backup manifest present · age ${backup.optLong("age_seconds") / 3600} hours. This does not certify a restore." else "No backup manifest found.") }
            }
            OutlinedButton(onClick = { clipboard.setText(AnnotatedString(body.toString(2))) }) { Text("Copy safe diagnostic receipt") }
        } }
    }
}

@Composable
fun BrowserOutcomeRoute(app: VanApplication, taskId: String, onBack: () -> Unit, onOpenMission: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter), contentPadding = PaddingValues(vertical = tokens.space.space3), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { OutlinedButton(onClick = onBack) { Text("← Browser tasks") }; SectionHeader("Browser task result") }
        item { OwnerDataSection("Browser result $taskId", load = { app.gatewayClient.ownerBrowserOutcome(taskId) }) { body, _ ->
            ReadAvailability(body)
            ServiceText(OwnerServicePresentation.browserResult(body))
            SectionHeader("Worker proposal")
            ServiceText(OwnerServicePresentation.browserWorkerProposal(body))
            SectionHeader("Required result checks")
            OwnerServicePresentation.browserMissingPostconditions(body).forEach { ServiceText(it) }
            ServiceText(body.ownerValue("next_action"))
            SectionHeader("Recorded observations")
            val evidence = body.optJSONArray("evidence").ownerRows()
            if (evidence.isEmpty()) ServiceText(OwnerServicePresentation.emptySection(body, "evidence", "No secret-free browser observations are recorded for this task."))
            evidence.forEach { record -> VanPanel { Column {
                ServiceText("${record.ownerValue("kind")} · ${ownerTime(record.optLong("created_at_ms"))}\nReceipt: ${record.ownerValue("evidence_id")}", true)
                ServiceText(OwnerServicePresentation.browserEvidenceTrust(record), true)
                val digests = OwnerServicePresentation.browserEvidenceDigests(record)
                if (digests.isEmpty()) ServiceText("No content digests were recorded for this observation.", true)
                digests.forEach { ServiceText(it, true) }
            } } }
            SectionHeader("Linked mission outcomes")
            val missions = body.optJSONArray("mission_outcomes").ownerRows()
            if (missions.isEmpty()) ServiceText(OwnerServicePresentation.emptySection(body, "mission_outcomes", "This task has no recorded mission outcome. Completing browser execution alone does not verify the goal."))
            missions.forEach { mission ->
                VanPanel { Column {
                    ServiceText(OwnerServicePresentation.missionResult(mission))
                    ServiceText("This verification belongs to the mission's declared result.", true)
                    if (!mission.isNull("verified_at_ms")) ServiceText("Observed ${ownerTime(mission.optLong("verified_at_ms"))}", true)
                    val refs = mission.optJSONArray("evidence_refs")
                    if (refs == null || refs.length() == 0) ServiceText("No mission evidence references were supplied.", true)
                    else (0 until refs.length()).forEach { ServiceText("Receipt: ${refs.optString(it)}", true) }
                    OutlinedButton(onClick = { onOpenMission(mission.getString("mission_id")) }) { Text("Open mission evidence") }
                } }
            }
        } }
    }
}
