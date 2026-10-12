package com.dial.van.muse

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dial.van.VanApplication
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

private enum class Pane(val label: String) {
    CONVERSATION("Chat"), TASKS("Tasks"), APPROVALS("Approvals"), PROJECTS("Projects"),
}

private fun JSONObject.array(name: String): List<JSONObject> =
    (optJSONArray(name) ?: JSONArray()).let { array ->
        (0 until array.length()).mapNotNull { array.optJSONObject(it) }
    }

private fun sourceTime(value: String?): Long? =
    value?.takeIf { it.isNotBlank() }?.let { runCatching { Instant.parse(it).toEpochMilli() }.getOrNull() }

private fun JSONObject.sourceHealth(): MuseSourceHealth {
    val relay = optJSONObject("relay")
    return MuseSourceHealth(
        sessionGreen = optJSONObject("health")?.optString("state") == "GREEN",
        watchdogGreen = optJSONObject("watchdog")?.optString("state") == "GREEN",
        relayLive = relay?.optString("state") == "live",
        lastSourceAtEpochMs = sourceTime(relay?.optString("last_source_at")),
    )
}

private fun JSONObject.approvalFence(): MuseApprovalFence {
    val allowed = arrayOf(MuseDecision.ALLOW_ONCE, MuseDecision.DENY).filter { choice ->
        optJSONArray("allowed_actions")?.let { actions ->
            (0 until actions.length()).any { actions.optString(it) == choice.name }
        } ?: false
    }.toSet()
    return MuseApprovalFence(
        approvalId = optString("id"),
        sessionId = optString("session_id"),
        taskId = optString("task_id"),
        projectId = optString("project_id").takeIf { it.isNotBlank() },
        actionFingerprint = optString("action_fingerprint"),
        controlGeneration = optLong("control_generation"),
        revision = optLong("revision"),
        expiresAtEpochMs = optLong("expires_at_epoch_ms"),
        state = optString("state"),
        allowed = allowed,
    )
}

/**
 * Native owner control — no WebView, screenshot tapping, browser credentials or second agent.
 *
 * Reads and action intents go through the existing VAN device-authenticated gateway.
 * The gateway and the Site consume one source-of-truth Muse broker; an unavailable upstream
 * yields an explicit unavailable state. The first release cannot claim live approval support
 * until the server-side adapter and the Site consumer both pass end-to-end qualification.
 */
@Composable
fun MuseRoute(app: VanApplication, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var pane by rememberSaveable { mutableStateOf(Pane.TASKS) }
    var current by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var draft by rememberSaveable { mutableStateOf("") }
    var selectedProject by rememberSaveable { mutableStateOf("") }

    // Foreground-only observation: Android background notifications use the existing
    // VAN notification channel, never an always-on mobile polling service.
    LaunchedEffect(app) {
        while (true) {
            if (app.gatewayClient.backgroundCallsAdvisable()) {
                runCatching { app.gatewayClient.museOverview() }
                    .onSuccess { current = it; error = null }
                    .onFailure { error = "Muse interaction gateway unavailable. Controls are disabled." }
            }
            delay(10_000L)
        }
    }

    val status = current?.sourceHealth()
    val fresh = error == null && status?.fresh(System.currentTimeMillis()) == true
    fun submit(body: JSONObject) {
        if (!fresh || busy) return
        busy = true
        scope.launch {
            runCatching { app.gatewayClient.museOwnerAction(body) }
                .onSuccess {
                    notice = "Request recorded. Waiting for Muse's confirmed state."
                    // A command receipt is never a claim that an approval click succeeded.
                }
                .onFailure { notice = "Request refused or unavailable; no success is assumed." }
            busy = false
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Spacer(Modifier.height(12.dp))
            OutlinedButton(onClick = onBack) { Text("← Work") }
            Text("Muse", style = MaterialTheme.typography.headlineMedium)
            Text("Native control • Shared with DIAL Work Tracker", style = MaterialTheme.typography.bodySmall)
            Text(
                if (fresh) "Live session and watchdog" else "Source unavailable or stale — controls disabled",
                color = if (fresh) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
            )
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            notice?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                Pane.entries.forEach { tab ->
                    FilterChip(
                        selected = pane == tab,
                        onClick = { pane = tab },
                        label = { Text(tab.label) },
                    )
                }
            }
        }
        when (pane) {
            Pane.TASKS -> {
                val tasks = current?.array("jobs").orEmpty()
                if (tasks.isEmpty()) item { Text("No Muse task observations available.") }
                items(tasks, key = { "muse-${it.optString("id")}" }) { task ->
                    Card {
                        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(task.optString("title", "Muse task"), style = MaterialTheme.typography.titleMedium)
                            Text("${task.optString("state")} · ${task.optString("project_title", "Independent task")}")
                            val jobId = task.optString("id")
                            val state = task.optString("state")
                            if (fresh && jobId.isNotBlank() && state in setOf("RUNNING", "SUBMITTED", "QUEUED")) {
                                OutlinedButton(enabled = !busy, onClick = {
                                    submit(JSONObject()
                                        .put("action", "CANCEL_TASK")
                                        .put("job_id", jobId)
                                        .put("confirmed_job_id", jobId)
                                        .put("idempotency_key", UUID.randomUUID().toString()))
                                }) { Text("Cancel this task") }
                            }
                        }
                    }
                }
            }
            Pane.CONVERSATION -> {
                val messages = current?.array("messages").orEmpty()
                items(messages, key = { "message-${it.optString("id")}" }) { message ->
                    Card {
                        Column(Modifier.fillMaxWidth().padding(12.dp)) {
                            Text(message.optString("role", "Muse"), style = MaterialTheme.typography.labelMedium)
                            Text(message.optString("text"))
                        }
                    }
                }
                item {
                    OutlinedTextField(
                        value = draft,
                        onValueChange = { draft = it.take(4000) },
                        label = { Text("Message Muse") },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 2,
                    )
                    Button(enabled = fresh && !busy && draft.isNotBlank(), onClick = {
                        submit(JSONObject()
                            .put("action", "SEND_MESSAGE")
                            .put("text", draft)
                            .put("idempotency_key", UUID.randomUUID().toString()))
                    }) { Text("Send") }
                }
            }
            Pane.APPROVALS -> {
                val prompts = current?.array("approvals").orEmpty()
                if (prompts.isEmpty()) item { Text("No pending permission requests.") }
                items(prompts, key = { "approval-${it.optString("id")}" }) { obj ->
                    val fence = remember(obj.toString()) { obj.approvalFence() }
                    Card {
                        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Muse is requesting permission", style = MaterialTheme.typography.titleMedium)
                            Text(obj.optString("description", "The provider supplied no description."))
                            Text("Task: ${fence.taskId}")
                            Text("Scope: ${obj.optString("scope", "Unverified")}")
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                listOf(MuseDecision.ALLOW_ONCE, MuseDecision.DENY).forEach { choice ->
                                    val permitted = fence.canAct(choice, System.currentTimeMillis(), fresh)
                                    OutlinedButton(enabled = permitted && !busy, onClick = {
                                        submit(JSONObject()
                                            .put("action", "DECIDE_APPROVAL")
                                            .put("choice", choice.name)
                                            .put("approval_id", fence.approvalId)
                                            .put("session_id", fence.sessionId)
                                            .put("task_id", fence.taskId)
                                            .put("project_id", fence.projectId)
                                            .put("action_fingerprint", fence.actionFingerprint)
                                            .put("control_generation", fence.controlGeneration)
                                            .put("expected_revision", fence.revision)
                                            .put("idempotency_key", UUID.randomUUID().toString()))
                                    }) { Text(if (choice == MuseDecision.ALLOW_ONCE) "Allow once" else "Deny") }
                                }
                            }
                        }
                    }
                }
            }
            Pane.PROJECTS -> {
                val projects = current?.array("projects").orEmpty()
                items(projects, key = { "project-${it.optString("id")}" }) { project ->
                    OutlinedButton(onClick = { selectedProject = project.optString("id") }, modifier = Modifier.fillMaxWidth()) {
                        Text(project.optString("title", "Unnamed project"))
                    }
                }
                item {
                    Text(if (selectedProject.isBlank()) "Choose a project to work on." else "Selected: $selectedProject")
                    Text(
                        "Project creation and new-task scope previews use the shared project registry. " +
                            "They become available only after the same gateway contract is admitted.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
        item { Spacer(Modifier.height(30.dp)) }
    }
}
