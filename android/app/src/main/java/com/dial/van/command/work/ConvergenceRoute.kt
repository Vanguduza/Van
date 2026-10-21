package com.dial.van.command.work

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.control.VanCommandSource
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray

/**
 * OMV convergence surface under Work, not a new top-level destination.
 *
 * This screen projects canonical gateway state. It does not become a second task engine:
 * suggestions still return a fresh owner prompt, Goals are not Missions, and artifact cards
 * remain projections over source/evidence digests.
 */
@Composable
fun ConvergenceRoute(
    app: VanApplication,
    onBack: () -> Unit,
    onOpenDocument: (String) -> Unit,
    onOpenThread: (String) -> Unit,
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var artifacts by remember { mutableStateOf(JSONArray()) }
    var documents by remember { mutableStateOf(JSONArray()) }
    var goals by remember { mutableStateOf(JSONArray()) }
    var watches by remember { mutableStateOf(JSONArray()) }
    var suggestions by remember { mutableStateOf(JSONArray()) }
    var threads by remember { mutableStateOf(JSONArray()) }
    var error by remember { mutableStateOf<String?>(null) }
    var goalTitle by remember { mutableStateOf("") }
    var watchTitle by remember { mutableStateOf("") }
    var watchTarget by remember { mutableStateOf("") }
    var threadTitle by remember { mutableStateOf("") }

    fun refresh() {
        scope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    listOf(
                        app.gatewayClient.convergenceArtifacts(),
                        app.gatewayClient.convergenceDocuments(),
                        app.gatewayClient.convergenceGoals(),
                        app.gatewayClient.convergenceWatches(),
                        app.gatewayClient.convergenceSuggestions(),
                        app.gatewayClient.convergenceThreads(),
                    )
                }
            }.onSuccess { payloads ->
                artifacts = JSONArray(payloads[0])
                documents = JSONArray(payloads[1])
                goals = JSONArray(payloads[2])
                watches = JSONArray(payloads[3])
                suggestions = JSONArray(payloads[4])
                threads = JSONArray(payloads[5])
                error = null
            }.onFailure {
                error = it.message ?: "Unable to load VAN work assets"
            }
        }
    }

    LaunchedEffect(Unit) { refresh() }

    Column(
        modifier = Modifier.fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Button(onClick = onBack) { Text("← Work") }
            OutlinedButton(onClick = { refresh() }) { Text("Refresh") }
        }
        SectionHeader("VAN work assets", detail = "Documents, goals, watches, suggestions and generated results")
        error?.let {
            VanPanel {
                Text(it, style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
            }
        }

        SectionHeader("Documents", detail = "${documents.length()} available")
        if (documents.length() == 0) {
            Text("No documents yet.", style = tokens.type.body, color = tokens.color.textSecondary)
        }
        jsonObjects(documents).take(20).forEach { doc ->
            val id = doc.optString("document_id")
            VanPressable(
                onClick = { if (id.isNotBlank()) onOpenDocument(id) },
                modifier = Modifier.fillMaxWidth(),
                contentDescription = "Open ${doc.optString("filename", "document")}",
            ) {
                VanPanel(dense = true) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text(doc.optString("filename", "Document"), style = tokens.type.headline, color = tokens.color.textPrimary)
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            StatusChip(
                                label = doc.optString("status", "UNKNOWN"),
                                role = if (doc.optString("status") == "FILLED") StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_MONITOR,
                            )
                            Text(
                                "${doc.optInt("page_count", 0)} page(s) • ${doc.optJSONArray("fields")?.length() ?: 0} field(s)",
                                style = tokens.type.label,
                                color = tokens.color.textSecondary,
                            )
                        }
                    }
                }
            }
        }

        SectionHeader("Goals", detail = "${goals.length()} owner outcomes")
        VanPanel(dense = true) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                OutlinedTextField(
                    value = goalTitle,
                    onValueChange = { goalTitle = it },
                    label = { Text("New goal") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(
                    enabled = goalTitle.isNotBlank(),
                    onClick = {
                        val title = goalTitle.trim()
                        scope.launch {
                            runCatching { app.gatewayClient.convergenceCreateGoal(title) }
                                .onSuccess { goalTitle = ""; refresh() }
                                .onFailure { error = it.message ?: "Unable to create goal" }
                        }
                    },
                ) { Text("Add goal") }
            }
        }
        jsonObjects(goals).take(20).forEach { goal ->
            VanPanel(dense = true) {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Text(goal.optString("title", "Goal"), style = tokens.type.headline, color = tokens.color.textPrimary)
                    StatusChip(label = goal.optString("status", "UNKNOWN"), role = statusRole(goal.optString("status")))
                    val milestones = goal.optJSONArray("milestones")
                    if (milestones != null && milestones.length() > 0) {
                        val done = jsonObjects(milestones).count { it.optBoolean("done", false) }
                        Text("$done/${milestones.length()} milestones complete", style = tokens.type.label, color = tokens.color.textSecondary)
                    }
                }
            }
        }

        SectionHeader("Watches", detail = "${watches.length()} standing checks")
        VanPanel(dense = true) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                OutlinedTextField(
                    value = watchTitle,
                    onValueChange = { watchTitle = it },
                    label = { Text("Watch name") },
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = watchTarget,
                    onValueChange = { watchTarget = it },
                    label = { Text("HTTPS page") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(
                    enabled = watchTitle.isNotBlank() && watchTarget.startsWith("https://"),
                    onClick = {
                        val title = watchTitle.trim()
                        val target = watchTarget.trim()
                        scope.launch {
                            runCatching { app.gatewayClient.convergenceCreatePageWatch(title, target) }
                                .onSuccess { watchTitle = ""; watchTarget = ""; refresh() }
                                .onFailure { error = it.message ?: "Unable to create watch" }
                        }
                    },
                ) { Text("Add watch") }
            }
        }
        jsonObjects(watches).take(20).forEach { watch ->
            VanPanel(dense = true) {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Text(watch.optString("title", "Watch"), style = tokens.type.headline, color = tokens.color.textPrimary)
                    StatusChip(label = watch.optString("status", "UNKNOWN"), role = statusRole(watch.optString("status")))
                    Text(watch.optString("target"), style = tokens.type.label, color = tokens.color.textSecondary)
                }
            }
        }

        SectionHeader("Suggestions", detail = "Evidence-backed ideas; nothing runs from a card")
        jsonObjects(suggestions).filter { it.optString("status") == "NEW" }.take(10).forEach { suggestion ->
            val id = suggestion.optString("suggestion_id")
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text(suggestion.optString("title", "Suggestion"), style = tokens.type.headline, color = tokens.color.textPrimary)
                    Text(suggestion.optString("rationale"), style = tokens.type.body, color = tokens.color.textSecondary)
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Button(onClick = {
                            scope.launch {
                                runCatching {
                                    app.gatewayClient.convergenceSuggestionDecision(id, "accept")
                                }.onSuccess { result ->
                                    val prompt = result.optString("fresh_owner_prompt")
                                    if (prompt.isNotBlank()) {
                                        // A second, normal signed command. Accepting a suggestion never
                                        // gives the suggestion service execution authority.
                                        app.commandController.submitText(prompt, VanCommandSource.CHAT)
                                        onBack()
                                    }
                                }.onFailure { error = it.message ?: "Unable to accept suggestion" }
                            }
                        }) { Text("Send to VAN") }
                        OutlinedButton(onClick = {
                            scope.launch {
                                runCatching {
                                    app.gatewayClient.convergenceSuggestionDecision(id, "dismiss")
                                }.onSuccess { refresh() }
                                    .onFailure { error = it.message ?: "Unable to dismiss suggestion" }
                            }
                        }) { Text("Dismiss") }
                    }
                }
            }
        }

        SectionHeader("Generated results", detail = "${artifacts.length()} owner artifact(s)")
        jsonObjects(artifacts).take(20).forEach { artifact ->
            VanPanel(dense = true) {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        StatusChip(label = artifact.optString("kind", "RESULT"), role = StatusSemantics.ROLE_COGNITION)
                        Text(artifact.optString("title", "Result"), style = tokens.type.headline, color = tokens.color.textPrimary)
                    }
                    val summary = artifact.optString("summary")
                    if (summary.isNotBlank()) {
                        Text(summary, style = tokens.type.body, color = tokens.color.textSecondary)
                    }
                    Text(
                        "Source ${artifact.optString("canonical_source_type")} • ${artifact.optString("canonical_source_digest").take(12)}",
                        style = tokens.type.label,
                        color = tokens.color.textTertiary,
                    )
                }
            }
        }

        SectionHeader("Conversation threads", detail = "${threads.length()} self-hosted thread(s)")
        VanPanel(dense = true) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                OutlinedTextField(
                    value = threadTitle,
                    onValueChange = { threadTitle = it },
                    label = { Text("New thread") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(
                    enabled = threadTitle.isNotBlank(),
                    onClick = {
                        val title = threadTitle.trim()
                        scope.launch {
                            runCatching { app.gatewayClient.convergenceCreateThread(title) }
                                .onSuccess { created ->
                                    threadTitle = ""
                                    refresh()
                                    created.optString("thread_id").takeIf { it.isNotBlank() }?.let(onOpenThread)
                                }
                                .onFailure { error = it.message ?: "Unable to create thread" }
                        }
                    },
                ) { Text("Create thread") }
            }
        }
        jsonObjects(threads).take(10).forEach { thread ->
            val threadId = thread.optString("thread_id")
            VanPressable(
                onClick = { if (threadId.isNotBlank()) onOpenThread(threadId) },
                modifier = Modifier.fillMaxWidth(),
                contentDescription = "Open ${thread.optString("title", "thread")}",
            ) {
                VanPanel(dense = true) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Text(thread.optString("title", "Thread"), style = tokens.type.headline, color = tokens.color.textPrimary)
                        StatusChip(label = thread.optString("status", "ACTIVE"), role = statusRole(thread.optString("status")))
                    }
                }
            }
        }
    }
}
