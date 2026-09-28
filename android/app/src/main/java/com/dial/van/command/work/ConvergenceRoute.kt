package com.dial.van.command.work

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
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
import org.json.JSONObject
import java.io.File

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


private data class RenderedPdf(
    val bitmap: Bitmap,
    val pageIndex: Int,
    val pageCount: Int,
)


@Composable
fun DocumentRoute(
    app: VanApplication,
    documentId: String,
    onBack: () -> Unit,
) {
    val tokens = LocalVanTokens.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val textValues = remember(documentId) { mutableStateMapOf<String, String>() }
    val boolValues = remember(documentId) { mutableStateMapOf<String, Boolean>() }
    var document by remember(documentId) { mutableStateOf<JSONObject?>(null) }
    var preview by remember(documentId) { mutableStateOf<RenderedPdf?>(null) }
    var pageIndex by remember(documentId) { mutableStateOf(0) }
    var zoom by remember(documentId) { mutableStateOf(1f) }
    var loading by remember(documentId) { mutableStateOf(true) }
    var notice by remember(documentId) { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            loading = true
            runCatching { app.gatewayClient.convergenceDocument(documentId) }
                .onSuccess { doc ->
                    document = doc
                    val fields = doc.optJSONArray("fields")
                    jsonObjects(fields ?: JSONArray()).forEach { field ->
                        val name = field.optString("name")
                        when (field.optString("kind")) {
                            "CHECKBOX" -> boolValues.putIfAbsent(name, field.optBoolean("value", false))
                            else -> textValues.putIfAbsent(name, field.optString("value", ""))
                        }
                    }
                    val variant = if (doc.optString("output_artifact_id").isNotBlank()) "output" else "source"
                    runCatching {
                        val bytes = app.gatewayClient.convergenceDocumentContent(documentId, variant)
                        renderPdfPage(context, documentId, bytes, pageIndex, zoom)
                    }.onSuccess { preview = it }
                        .onFailure { notice = it.message ?: "Preview unavailable" }
                    loading = false
                }
                .onFailure {
                    notice = it.message ?: "Document unavailable"
                    loading = false
                }
        }
    }

    LaunchedEffect(documentId, pageIndex, zoom) { refresh() }

    Column(
        modifier = Modifier.fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        Button(onClick = onBack) { Text("← Documents") }
        SectionHeader(
            document?.optString("filename", "Document") ?: "Document",
            detail = if (loading) "Loading…" else "Source preserved; fills create a new copy",
        )
        notice?.let { Text(it, style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK)) }

        preview?.let { rendered ->
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Image(
                        bitmap = rendered.bitmap.asImageBitmap(),
                        contentDescription = "PDF page ${rendered.pageIndex + 1} of ${rendered.pageCount}",
                        modifier = Modifier.fillMaxWidth().heightIn(max = tokens.space.pageGutter * 40),
                        contentScale = ContentScale.Fit,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        OutlinedButton(
                            enabled = rendered.pageIndex > 0,
                            onClick = { pageIndex = (pageIndex - 1).coerceAtLeast(0) },
                        ) { Text("Previous") }
                        Text("${rendered.pageIndex + 1}/${rendered.pageCount}", style = tokens.type.label)
                        OutlinedButton(
                            enabled = rendered.pageIndex + 1 < rendered.pageCount,
                            onClick = { pageIndex += 1 },
                        ) { Text("Next") }
                        OutlinedButton(onClick = { zoom = (zoom - 0.25f).coerceAtLeast(0.75f) }) { Text("−") }
                        OutlinedButton(onClick = { zoom = (zoom + 0.25f).coerceAtMost(2f) }) { Text("+") }
                    }
                }
            }
        }

        val shareVariant = if (document?.optString("output_artifact_id").orEmpty().isNotBlank()) "output" else "source"
        OutlinedButton(
            enabled = document != null && !loading,
            onClick = {
                val filename = document?.optString("filename", "document.pdf") ?: "document.pdf"
                scope.launch {
                    runCatching {
                        val bytes = app.gatewayClient.convergenceDocumentContent(documentId, shareVariant)
                        stageAndSharePdf(context, documentId, filename, bytes)
                    }.onFailure { notice = it.message ?: "Unable to share document" }
                }
            },
        ) { Text("Share copy") }

        val fields = jsonObjects(document?.optJSONArray("fields") ?: JSONArray())
        if (fields.isNotEmpty()) {
            SectionHeader("Form fields", detail = "Review values before creating a filled copy")
            fields.forEach { field ->
                val name = field.optString("name")
                when (field.optString("kind")) {
                    "CHECKBOX" -> VanPanel(dense = true) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Checkbox(
                                checked = boolValues[name] ?: false,
                                onCheckedChange = { boolValues[name] = it },
                            )
                            Text(name, style = tokens.type.body, color = tokens.color.textPrimary)
                        }
                    }
                    else -> OutlinedTextField(
                        value = textValues[name] ?: "",
                        onValueChange = { textValues[name] = it },
                        label = { Text(name) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            Button(
                enabled = !loading,
                onClick = {
                    scope.launch {
                        loading = true
                        val values = JSONObject()
                        fields.forEach { field ->
                            val name = field.optString("name")
                            if (field.optString("kind") == "CHECKBOX") {
                                values.put(name, boolValues[name] ?: false)
                            } else {
                                values.put(name, textValues[name] ?: "")
                            }
                        }
                        runCatching {
                            app.gatewayClient.convergenceFillDocument(documentId, values)
                        }.onSuccess {
                            pageIndex = 0
                            notice = "Filled copy created and digest-verified."
                            refresh()
                        }.onFailure {
                            notice = it.message ?: "Unable to fill document"
                            loading = false
                        }
                    }
                },
            ) { Text("Create filled copy") }
        } else if (!loading) {
            Text("This PDF has no supported fillable fields.", style = tokens.type.body, color = tokens.color.textSecondary)
        }
    }
}


private suspend fun stageAndSharePdf(
    context: Context,
    documentId: String,
    filename: String,
    bytes: ByteArray,
) {
    val staged = withContext(Dispatchers.IO) {
        val signature = "%PDF-".toByteArray(Charsets.US_ASCII)
        require(bytes.size >= signature.size && bytes.copyOfRange(0, signature.size).contentEquals(signature)) {
            "pdf_signature_invalid"
        }
        val directory = File(context.cacheDir, "document_exports").apply {
            mkdirs()
            require(canonicalPath.startsWith(context.cacheDir.canonicalPath)) { "export_path_invalid" }
        }
        val safeId = documentId.filter { it.isLetterOrDigit() || it == '_' || it == '-' }.take(80)
        val safeName = filename.substringAfterLast('/').substringAfterLast('\\')
            .filter { it.isLetterOrDigit() || it in "._- " }
            .trim()
            .ifBlank { "document.pdf" }
            .let { if (it.lowercase().endsWith(".pdf")) it else "$it.pdf" }
            .take(120)
        File(directory, "$safeId-$safeName").apply { writeBytes(bytes) }
    }
    val uri = FileProvider.getUriForFile(
        context,
        "${context.packageName}.fileprovider",
        staged,
    )
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "application/pdf"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(send, "Share PDF"))
}


private suspend fun renderPdfPage(
    context: Context,
    documentId: String,
    bytes: ByteArray,
    requestedPage: Int,
    zoom: Float,
): RenderedPdf = withContext(Dispatchers.IO) {
    val safe = documentId.filter { it.isLetterOrDigit() || it == '_' || it == '-' }.take(80)
    val file = File(context.cacheDir, "van-document-$safe.pdf")
    file.writeBytes(bytes)
    val descriptor = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    try {
        val renderer = PdfRenderer(descriptor)
        try {
            require(renderer.pageCount > 0) { "pdf_has_no_pages" }
            val index = requestedPage.coerceIn(0, renderer.pageCount - 1)
            val page = renderer.openPage(index)
            try {
                val width = (page.width * zoom).toInt().coerceIn(1, 2400)
                val height = (page.height * zoom).toInt().coerceIn(1, 3200)
                val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                RenderedPdf(bitmap, index, renderer.pageCount)
            } finally {
                page.close()
            }
        } finally {
            renderer.close()
        }
    } finally {
        descriptor.close()
    }
}


private fun jsonObjects(array: JSONArray): List<JSONObject> = buildList {
    for (index in 0 until array.length()) {
        array.optJSONObject(index)?.let(::add)
    }
}


private fun statusRole(status: String): String = when (status.uppercase()) {
    "COMPLETED", "FILLED", "ACCEPTED", "ACTIVE" -> StatusSemantics.ROLE_FAVOURABLE
    "FAILED", "CANCELLED", "DISMISSED" -> StatusSemantics.ROLE_CRITICAL
    "PAUSED", "ARCHIVED", "WAITING" -> StatusSemantics.ROLE_EVENT_RISK
    else -> StatusSemantics.ROLE_MONITOR
}
