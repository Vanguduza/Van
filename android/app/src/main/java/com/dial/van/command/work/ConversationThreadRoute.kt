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
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

@Composable
fun ConversationThreadRoute(
    app: VanApplication,
    threadId: String,
    onBack: () -> Unit,
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var thread by remember(threadId) { mutableStateOf<JSONObject?>(null) }
    var title by remember(threadId) { mutableStateOf("") }
    var draft by remember(threadId) { mutableStateOf("") }
    var newFollowUp by remember(threadId) { mutableStateOf("") }
    var notice by remember(threadId) { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching { app.gatewayClient.convergenceThread(threadId) }
                .onSuccess {
                    thread = it
                    title = it.optString("title")
                    draft = it.optString("draft_text")
                    notice = null
                }
                .onFailure { notice = it.message ?: "Thread unavailable" }
        }
    }

    LaunchedEffect(threadId) { refresh() }

    Column(
        modifier = Modifier.fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        Button(onClick = onBack) { Text("← Threads") }
        SectionHeader(
            thread?.optString("title", "Conversation") ?: "Conversation",
            detail = "Self-hosted context only; replay never re-executes actions",
        )
        notice?.let {
            Text(it, style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
        }

        OutlinedTextField(
            value = title,
            onValueChange = { title = it },
            label = { Text("Thread title") },
            modifier = Modifier.fillMaxWidth(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            OutlinedButton(
                enabled = title.isNotBlank(),
                onClick = {
                    scope.launch {
                        runCatching { app.gatewayClient.convergenceRenameThread(threadId, title.trim()) }
                            .onSuccess { refresh() }
                            .onFailure { notice = it.message ?: "Rename failed" }
                    }
                },
            ) { Text("Rename") }
            val archived = thread?.optString("status") == "ARCHIVED"
            OutlinedButton(onClick = {
                scope.launch {
                    runCatching {
                        app.gatewayClient.convergenceSetThreadStatus(
                            threadId,
                            if (archived) "ACTIVE" else "ARCHIVED",
                        )
                    }.onSuccess { refresh() }
                        .onFailure { notice = it.message ?: "Status change failed" }
                }
            }) { Text(if (archived) "Restore" else "Archive") }
        }

        SectionHeader("Draft", detail = "Stored locally in VAN's thread state until you decide what to do")
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it },
            label = { Text("Draft") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedButton(onClick = {
            scope.launch {
                runCatching { app.gatewayClient.convergenceSaveThreadDraft(threadId, draft) }
                    .onSuccess { notice = "Draft saved." }
                    .onFailure { notice = it.message ?: "Unable to save draft" }
            }
        }) { Text("Save draft") }

        SectionHeader("Queued follow-ups", detail = "Promotion returns a fresh owner prompt; it never executes here")
        OutlinedTextField(
            value = newFollowUp,
            onValueChange = { newFollowUp = it },
            label = { Text("Follow-up prompt") },
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            enabled = newFollowUp.isNotBlank() && thread?.optString("status") != "ARCHIVED",
            onClick = {
                val prompt = newFollowUp.trim()
                scope.launch {
                    runCatching { app.gatewayClient.convergenceQueueThreadFollowUp(threadId, prompt) }
                        .onSuccess { newFollowUp = ""; refresh() }
                        .onFailure { notice = it.message ?: "Unable to queue follow-up" }
                }
            },
        ) { Text("Queue follow-up") }

        jsonObjects(thread?.optJSONArray("followups") ?: JSONArray()).forEach { item ->
            VanPanel(dense = true) {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text(item.optString("prompt"), style = tokens.type.body, color = tokens.color.textPrimary)
                    StatusChip(label = item.optString("status", "QUEUED"), role = statusRole(item.optString("status")))
                    if (item.optString("status") == "QUEUED") {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Button(onClick = {
                                scope.launch {
                                    runCatching {
                                        app.gatewayClient.convergenceDecideThreadFollowUp(
                                            threadId, item.optString("followup_id"), "promote"
                                        )
                                    }.onSuccess { result ->
                                        val prompt = result.optString("fresh_owner_prompt")
                                        if (prompt.isNotBlank()) {
                                            app.commandController.submitText(prompt, VanCommandSource.CHAT)
                                            notice = "Follow-up sent through the normal VAN command path."
                                        }
                                        refresh()
                                    }.onFailure { notice = it.message ?: "Unable to promote follow-up" }
                                }
                            }) { Text("Send to VAN") }
                            OutlinedButton(onClick = {
                                scope.launch {
                                    runCatching {
                                        app.gatewayClient.convergenceDecideThreadFollowUp(
                                            threadId, item.optString("followup_id"), "dismiss"
                                        )
                                    }.onSuccess { refresh() }
                                        .onFailure { notice = it.message ?: "Unable to dismiss follow-up" }
                                }
                            }) { Text("Dismiss") }
                        }
                    }
                }
            }
        }

        SectionHeader("Messages", detail = "${thread?.optJSONArray("messages")?.length() ?: 0} stored")
        jsonObjects(thread?.optJSONArray("messages") ?: JSONArray()).forEach { message ->
            VanPanel(dense = true) {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Text(message.optString("role", "VAN"), style = tokens.type.label, color = tokens.color.textSecondary)
                    Text(message.optString("body"), style = tokens.type.body, color = tokens.color.textPrimary)
                    if (message.optBoolean("terminal", false)) {
                        StatusChip(label = "TERMINAL", role = StatusSemantics.ROLE_FAVOURABLE)
                    }
                }
            }
        }
    }
}
