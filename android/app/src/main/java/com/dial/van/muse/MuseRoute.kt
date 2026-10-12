package com.dial.van.muse

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import com.dial.van.VanApplication
import com.dial.van.security.BiometricGate
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

private enum class Pane(val label: String) { CHAT("Chat"), TASKS("Tasks"), APPROVALS("Approvals"), PROJECTS("Projects"), INBOX("Inbox") }
private fun JSONObject.rows(key: String): List<JSONObject> = (optJSONArray(key) ?: JSONArray()).let { a ->
    (0 until a.length()).mapNotNull { a.optJSONObject(it) }
}
private fun unwrap(value: JSONObject): JSONObject = if (value.optBoolean("ok") && value.optJSONObject("result") != null) value.getJSONObject("result") else value
private fun JSONObject.nullable(key: String): Any = if (isNull(key) || !has(key)) JSONObject.NULL else get(key)
private fun JSONObject.binding(): JSONObject = JSONObject().also { body ->
    listOf("session_id", "thread_id", "task_id", "project_id", "scope_binding_sha256", "control_generation").forEach { body.put(it, nullable(it)) }
}
private fun JSONObject.live(now: Long): Boolean {
    val relay = optJSONObject("relay") ?: return false
    return MuseSourceHealth(
        sessionGreen = optJSONObject("health")?.optString("state") == "GREEN",
        watchdogGreen = optJSONObject("watchdog")?.optString("state") == "GREEN",
        relayLive = relay.optString("state") == "live",
        lastSourceAtEpochMs = relay.optLong("last_source_at_ms", -1).takeIf { it > 0 },
    ).fresh(now)
}

/** The provider's current prompt is the only source of selectable permission choices. */
private fun JSONObject.approvalFence(): MuseApprovalFence {
    val offered = optJSONArray("allowed_actions") ?: JSONArray()
    val choices = (0 until offered.length()).mapNotNull {
        runCatching { MuseDecision.valueOf(offered.optString(it)) }.getOrNull()
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
        actionClass = optString("action_class"),
        description = optString("description"),
        allowed = choices,
    )
}

/** Native VAN UI. Typed actions and data are shared with the Site; no web page is embedded. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MuseRoute(app: VanApplication, onBack: () -> Unit, initialApprovalId: String? = null) {
    val activity = LocalContext.current as? FragmentActivity
    val scope = rememberCoroutineScope()
    var pane by rememberSaveable { mutableStateOf(if (initialApprovalId != null) Pane.APPROVALS else Pane.TASKS) }
    var current by remember { mutableStateOf<JSONObject?>(null) }
    var taskData by remember { mutableStateOf<JSONObject?>(null) }
    var sourceError by remember { mutableStateOf<String?>(null) }
    var tasksError by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    var busy by remember { mutableStateOf(false) }
    var selectedThread by rememberSaveable { mutableStateOf("") }
    var selectedProject by rememberSaveable { mutableStateOf("") }
    var draft by rememberSaveable { mutableStateOf("") }
    var messageKey by rememberSaveable { mutableStateOf(UUID.randomUUID().toString()) }
    var pendingCommand by rememberSaveable { mutableStateOf("") }
    var pendingIntent by rememberSaveable { mutableStateOf("") }
    var taskDetail by remember { mutableStateOf<JSONObject?>(null) }
    var cancelJob by remember { mutableStateOf<JSONObject?>(null) }
    var showTaskForm by rememberSaveable { mutableStateOf(false) }
    var showProjectForm by rememberSaveable { mutableStateOf(false) }
    var parentJob by rememberSaveable { mutableStateOf("") }
    val notifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        notice = if (granted) "Muse notifications enabled for this device." else "Notifications remain off; the inbox is still available."
    }

    suspend fun refreshSource() {
        try { current = app.gatewayClient.museOverview(); sourceError = null }
        catch (c: CancellationException) { throw c }
        catch (_: Exception) { sourceError = "Live Muse interaction is unavailable. Last observations are read-only." }
    }
    suspend fun refreshTasks() {
        try { taskData = unwrap(app.gatewayClient.museTasks()); tasksError = null }
        catch (c: CancellationException) { throw c }
        catch (_: Exception) { tasksError = "The shared task registry connection is unavailable." }
    }
    suspend fun checkReceipt() {
        if (pendingIntent.isBlank()) return
        try {
            val request = JSONObject(pendingIntent)
            val receipt = if (pendingCommand.isNotBlank()) app.gatewayClient.museReceipt(pendingCommand)
                else app.gatewayClient.museReceiptByKey(request.getString("idempotency_key"))
            pendingCommand = receipt.optString("command_id")
            when (receipt.optString("state")) {
                "CONFIRMED" -> {
                    notice = "Muse confirmed this interaction."
                    if (request.optString("action") == "SEND_MESSAGE" && request.optString("text") == draft) {
                        draft = ""; messageKey = UUID.randomUUID().toString()
                    }
                    pendingCommand = ""; pendingIntent = ""
                }
                "REJECTED", "EXPIRED" -> { notice = "Muse did not apply this request."; pendingCommand = ""; pendingIntent = "" }
                "UNKNOWN" -> notice = "The outcome needs reconciliation. This request will not be sent again automatically."
                else -> notice = "Request received; waiting for Muse's own confirmation."
            }
        } catch (c: CancellationException) { throw c }
        catch (_: Exception) { notice = "The original request has not been confirmed. Refresh or retry the same request; no duplicate is assumed safe." }
    }

    LaunchedEffect(app, activity) {
        if (activity == null) return@LaunchedEffect
        activity.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            coroutineScope {
                launch {
                    while (true) { now = System.currentTimeMillis(); delay(1000) }
                }
                launch {
                    while (true) {
                        refreshSource(); refreshTasks(); checkReceipt(); delay(10_000)
                    }
                }
                launch {
                    var cursor = 0L
                    var reconnect = 1000L
                    while (true) {
                        try {
                            app.gatewayClient.museEvents(cursor).collect { event ->
                                refreshSource()
                                // Re-fetch is applied before acknowledging this stream cursor.
                                if (sourceError == null) { cursor = event.cursor; checkReceipt(); reconnect = 1000L }
                            }
                        } catch (c: CancellationException) { throw c }
                        catch (_: Exception) { /* Last-good data remains visibly stale. */ }
                        delay(reconnect); reconnect = (reconnect * 2).coerceAtMost(15_000L)
                    }
                }
            }
        }
    }

    val fresh = sourceError == null && current?.live(now) == true && current?.optBoolean("control_admitted") == true
    val tasksLive = tasksError == null && taskData?.optJSONObject("capabilities")?.optBoolean("live_controls") == true
    val approvals = current?.rows("approvals").orEmpty().sortedBy { it.optString("id") != initialApprovalId }
    val threads = current?.rows("threads").orEmpty()
    val thread = threads.firstOrNull { it.optString("thread_id") == selectedThread } ?: threads.firstOrNull()
    val taskRows = taskData?.rows("jobs").orEmpty()
    val projects = taskData?.rows("projects").orEmpty()

    fun submitInteraction(body: JSONObject, stepUp: Boolean = false) {
        if (!fresh || busy) return
        busy = true
        val original = body.toString()
        fun dispatch(request: JSONObject) {
            scope.launch {
                pendingIntent = original
                try {
                    val receipt = app.gatewayClient.museOwnerAction(request)
                    pendingCommand = receipt.optString("command_id")
                    notice = "Request received; waiting for Muse to confirm."
                    refreshSource(); checkReceipt()
                } catch (c: CancellationException) { throw c }
                catch (_: Exception) { notice = "Delivery is uncertain or refused. The original request is preserved for reconciliation." }
                finally { busy = false }
            }
        }
        if (!stepUp) { dispatch(body); return }
        scope.launch {
            try {
                val host = activity ?: error("Activity unavailable")
                val challenge = app.gatewayClient.museChallenge(body)
                val signature = app.gatewayClient.newA4ApprovalSignature()
                BiometricGate(host).requestA4CommandApproval(
                    signature = signature, challenge = challenge.getString("canonical"),
                    title = "Allow this Muse action once", subtitle = "Approve only the exact action shown in VAN",
                    onApproved = { signed ->
                        dispatch(JSONObject(original).put("challenge_id", challenge.getString("challenge_id")).put("signature_b64", signed))
                    },
                    onDenied = { notice = "Not approved. No permission was granted."; busy = false },
                )
            } catch (c: CancellationException) { throw c }
            catch (_: Exception) { notice = "A fresh owner verification is required; the action was not approved."; busy = false }
        }
    }
    fun taskCall(operation: String, args: JSONObject, done: (JSONObject) -> Unit = {}) {
        if (busy || !tasksLive) return
        busy = true
        scope.launch {
            try { done(unwrap(app.gatewayClient.museTaskCall(operation, args))); refreshTasks() }
            catch (c: CancellationException) { throw c }
            catch (_: Exception) { notice = "Task request refused or unavailable. Its existing request identity is retained." }
            finally { busy = false }
        }
    }

    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = onBack) { Text("← Work") }
                TextButton(onClick = { scope.launch { refreshSource(); refreshTasks(); checkReceipt() } }) { Text("Refresh") }
            }
            Text("Muse", style = MaterialTheme.typography.headlineMedium)
            Text(if (fresh) "Live interaction" else "Live interaction unavailable", color = if (fresh) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)
            Text(if (tasksLive) "Task registry connected" else "Task registry not connected", style = MaterialTheme.typography.bodySmall)
            notice?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        }
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Pane.entries.forEach { tab -> FilterChip(selected = pane == tab, onClick = { pane = tab }, label = { Text(tab.label + if (tab == Pane.APPROVALS && approvals.isNotEmpty()) " (${approvals.size})" else "") }) }
            }
        }
        if (pendingIntent.isNotBlank()) item {
            Card { Column(Modifier.fillMaxWidth().padding(16.dp)) {
                Text("Interaction pending", style = MaterialTheme.typography.titleMedium)
                Text("Accepted is not the same as applied. No automatic re-click occurs after a lost connection.")
                TextButton(onClick = { scope.launch { checkReceipt() } }) { Text("Check original receipt") }
                if (pendingCommand.isBlank()) TextButton(enabled = fresh && !busy, onClick = {
                    val original = JSONObject(pendingIntent)
                    val p = approvals.firstOrNull { it.optString("id") == original.optString("approval_id") }
                    val stepUp = original.optString("choice") == "ALLOW_ONCE" && p?.optString("action_class") !in setOf("A1", "A2", "A3")
                    submitInteraction(original, stepUp)
                }) { Text("Retry the same request") }
            } }
        }
        when (pane) {
            Pane.CHAT -> {
                if (threads.isEmpty()) item { Text("No current-job conversation is available. New work starts from Tasks.") }
                item { Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    threads.forEach { t -> FilterChip(selected = t == thread, onClick = { selectedThread = t.optString("thread_id") }, label = { Text(t.optString("title", "Conversation").take(32)) }) }
                } }
                val messages = current?.rows("messages").orEmpty().filter { it.optString("thread_id") == thread?.optString("thread_id") }
                items(messages, key = { it.optString("id") }) { message -> Card { Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(if (message.optString("role") == "user") "You" else "Muse", style = MaterialTheme.typography.labelLarge)
                    Text(message.optString("text"))
                    if (message.optBoolean("streaming")) Text("Responding…", style = MaterialTheme.typography.labelSmall)
                    if (message.optBoolean("truncated")) Text("This preview is truncated. Read the full captured result in Tasks.")
                } } }
                item {
                    OutlinedTextField(value = draft, onValueChange = { draft = it.take(4000) }, label = { Text("Message Muse") }, enabled = pendingIntent.isBlank(), modifier = Modifier.fillMaxWidth(), minLines = 2)
                    Button(enabled = fresh && thread != null && thread.optBoolean("can_send") && !busy && draft.isNotBlank() && pendingIntent.isBlank(), onClick = {
                        thread?.let { t -> submitInteraction(t.binding().put("action", "SEND_MESSAGE").put("expected_revision", t.optLong("revision")).put("text", draft).put("idempotency_key", "message:$messageKey")) }
                    }) { Text("Send") }
                }
            }
            Pane.APPROVALS -> {
                if (approvals.isEmpty()) item { Text(if (fresh) "Nothing is waiting for your decision." else "Reconnect to read current permission requests.") }
                items(approvals, key = { it.optString("id") }) { p -> Card { Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Permission requested", style = MaterialTheme.typography.titleLarge)
                    Text(p.optString("description"))
                    Text("Task: ${p.optString("task_id")}", style = MaterialTheme.typography.bodySmall)
                    val state = p.optString("state")
                    val fence = remember(p.toString()) { p.approvalFence() }
                    Text(state.replace('_', ' '), style = MaterialTheme.typography.labelMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        listOf(MuseDecision.ALLOW_ONCE, MuseDecision.DENY).forEach { decision ->
                            val choice = decision.name
                            val isAllow = decision == MuseDecision.ALLOW_ONCE
                            val stepUp = isAllow && fence.actionClass == "A4"
                            val valid = (fence.canAct(decision, now, fresh) ||
                                (stepUp && fence.canRequestStepUp(now, fresh))) &&
                                pendingIntent.isBlank() && !busy
                            val key = "approval:" + UUID.nameUUIDFromBytes((p.optString("id")+":"+p.optLong("revision")+":"+p.optLong("control_generation")+":"+choice).toByteArray())
                            OutlinedButton(enabled = valid, onClick = {
                                submitInteraction(p.binding().put("action", "DECIDE_APPROVAL").put("approval_id", p.optString("id")).put("expected_revision", p.optLong("revision")).put("action_fingerprint", p.optString("action_fingerprint")).put("choice", choice).put("idempotency_key", key), stepUp)
                            }) { Text(if (isAllow) (if (stepUp) "Allow once · verify" else "Allow once") else "Deny") }
                        }
                    }
                } } }
            }
            Pane.TASKS -> {
                item { Button(enabled = tasksLive && !busy, onClick = { parentJob = ""; showTaskForm = true }) { Text("New task") } }
                tasksError?.let { item { Text(it) } }
                if (taskRows.isEmpty()) item { Text("No task records available.") }
                items(taskRows, key = { it.optString("id") }) { task -> Card { Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(task.optString("title"), style = MaterialTheme.typography.titleMedium)
                    Text("${task.optString("state")} · ${task.optString("project_title", "Independent task")}")
                    task.optString("progress_summary").takeIf { it.isNotBlank() }?.let { Text(it.take(400), maxLines = 5) }
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(enabled = tasksLive && !busy, onClick = { taskCall("muse_get_job", JSONObject().put("job_id", task.optString("id"))) { taskDetail = it.optJSONObject("job") ?: it } }) { Text("Details / result") }
                        if (task.optString("state") in setOf("SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "INCOMPLETE")) {
                            TextButton(enabled = tasksLive && !busy, onClick = { parentJob = task.optString("id"); selectedProject = task.optString("project_id"); showTaskForm = true }) { Text("Follow up") }
                        } else TextButton(enabled = tasksLive && !busy, onClick = { cancelJob = task }) { Text("Cancel") }
                    }
                } } }
            }
            Pane.PROJECTS -> {
                item { Button(enabled = tasksLive && !busy, onClick = { showProjectForm = true }) { Text("Create project") } }
                items(projects, key = { it.optString("id") }) { project -> Card { Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(project.optString("title"), style = MaterialTheme.typography.titleMedium)
                    Text(project.optString("description"), maxLines = 4)
                    TextButton(enabled = tasksLive && !busy, onClick = { selectedProject = project.optString("id"); parentJob = ""; showTaskForm = true }) { Text("Assign Muse work") }
                } } }
            }
            Pane.INBOX -> {
                item {
                    Text("Muse notifications", style = MaterialTheme.typography.titleLarge)
                    Button(onClick = { if (Build.VERSION.SDK_INT >= 33) notifications.launch(Manifest.permission.POST_NOTIFICATIONS) else notice = "Notification channels are managed in Android settings." }) { Text("Enable device notifications") }
                    Text("Tapping an alert opens VAN for a fresh read. It never silently approves an action.")
                }
                val alerts = taskData?.rows("notifications").orEmpty()
                if (alerts.isEmpty()) item { Text("No recorded task alerts.") }
                items(alerts, key = { it.optString("id") }) { alert -> Card { Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(alert.optString("title", "Muse update"), style = MaterialTheme.typography.titleMedium)
                    Text(alert.optString("body").ifBlank { alert.optString("message") })
                } } }
            }
        }
        item { Spacer(Modifier.height(24.dp)) }
    }

    cancelJob?.let { job -> AlertDialog(onDismissRequest = { cancelJob = null }, title = { Text("Cancel this task?") }, text = { Text(job.optString("title")) }, confirmButton = {
        TextButton(enabled = !busy, onClick = {
            taskCall("muse_cancel_task", JSONObject().put("idempotency_key", "cancel:"+job.optString("id")).put("job_id", job.optString("id")).put("confirmed_job_id", job.optString("id"))) { notice = "Cancellation requested; watch the source-confirmed task state."; cancelJob = null }
        }) { Text("Cancel task") }
    }, dismissButton = { TextButton(onClick = { cancelJob = null }) { Text("Keep task") } }) }
    taskDetail?.let { task -> ModalBottomSheet(onDismissRequest = { taskDetail = null }) {
        LazyColumn(Modifier.fillMaxWidth().heightIn(max = 650.dp).padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Text(task.optString("title", "Task result"), style = MaterialTheme.typography.titleLarge) }
            item { Text("${task.optString("state")} · Capture: ${task.optJSONObject("capture")?.optString("state") ?: "Unobserved"}") }
            item { Text(task.optJSONObject("result")?.optString("text") ?: task.optString("progress_summary", "The full captured result is not yet available. Reopen to check its original request.")) }
            item { Spacer(Modifier.height(24.dp)) }
        }
    } }
    if (showTaskForm) MuseTaskForm(app, projects, selectedProject, parentJob, onDismiss = { showTaskForm = false }, onDone = { notice = "Task request recorded. Its Muse job receipt is shown in the shared task registry."; showTaskForm = false; scope.launch { refreshTasks() } })
    if (showProjectForm) MuseProjectForm(app, onDismiss = { showProjectForm = false }, onDone = { showProjectForm = false; scope.launch { refreshTasks() } })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MuseTaskForm(app: VanApplication, projects: List<JSONObject>, initialProject: String, parentJob: String, onDismiss: () -> Unit, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var title by rememberSaveable { mutableStateOf("") }
    var instruction by rememberSaveable { mutableStateOf("") }
    var project by rememberSaveable { mutableStateOf(initialProject) }
    var repository by rememberSaveable { mutableStateOf("") }
    var branch by rememberSaveable { mutableStateOf("") }
    var mutating by rememberSaveable { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var intent by rememberSaveable { mutableStateOf("") }
    var previewId by rememberSaveable { mutableStateOf("") }
    var key by rememberSaveable { mutableStateOf(UUID.randomUUID().toString()) }
    var preview by remember { mutableStateOf<JSONObject?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    fun payload(): JSONObject {
        val repo = projects.firstOrNull { it.optString("id") == project }?.optString("repository_url").orEmpty().ifBlank { repository.trim() }
        val access = JSONObject().put("mode", if (mutating) "MUTATING" else "READ_ONLY")
        if (repo.isNotBlank()) access.put("repository", repo)
        if (branch.isNotBlank()) access.put("branch", branch.trim())
        return JSONObject().put("idempotency_key", "resolve:$key").put("title", title.trim()).put("instruction", instruction)
            .put("project_mode", if (project.isNotBlank()) "PROJECT" else if (repo.isNotBlank()) "REPOSITORY_SCOPED" else "NON_PROJECT")
            .put("repository_access", access).put("mutation_authorized", mutating).put("timeout_seconds", 21600)
            .also { if (project.isNotBlank()) it.put("project_id", project) else if (repo.isNotBlank()) it.put("repository", repo); if (parentJob.isNotBlank()) it.put("parent_job_id", parentJob) }
    }
    suspend fun readPreview() {
        if (previewId.isBlank()) return
        val result = unwrap(app.gatewayClient.museTaskCall("muse_get_command", JSONObject().put("command_id", previewId)))
        val command = result.optJSONObject("command") ?: result
        preview = command
        message = if (command.optString("state") == "completed") "Scope checked. Review the exact scope below, then submit." else "Scope request recorded; check its original receipt."
    }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        LazyColumn(Modifier.fillMaxWidth().heightIn(max = 700.dp).padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Text(if (parentJob.isBlank()) "New Muse task" else "Follow up on existing task", style = MaterialTheme.typography.titleLarge) }
            item { OutlinedTextField(title, { title = it.take(180); preview = null; intent = ""; previewId = ""; key = UUID.randomUUID().toString() }, label = { Text("Task title") }, modifier = Modifier.fillMaxWidth()) }
            item { OutlinedTextField(instruction, { instruction = it.take(30000); preview = null; intent = ""; previewId = ""; key = UUID.randomUUID().toString() }, label = { Text("Instructions") }, minLines = 3, modifier = Modifier.fillMaxWidth()) }
            item { Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip(project.isBlank(), onClick = { project = ""; preview = null; previewId = ""; intent = ""; key = UUID.randomUUID().toString() }, label = { Text("Independent / repository") })
                projects.forEach { p -> FilterChip(project == p.optString("id"), onClick = { project = p.optString("id"); preview = null; previewId = ""; intent = ""; key = UUID.randomUUID().toString() }, label = { Text(p.optString("title")) }) }
            } }
            if (project.isBlank()) item { OutlinedTextField(repository, { repository = it; preview = null; previewId = ""; intent = ""; key = UUID.randomUUID().toString() }, label = { Text("GitHub repository URL (optional)") }, modifier = Modifier.fillMaxWidth()) }
            item { Row { Checkbox(mutating, { mutating = it; preview = null; previewId = ""; intent = ""; key = UUID.randomUUID().toString() }); Text("Permit repository edits on an explicit working branch") } }
            if (mutating) item { OutlinedTextField(branch, { branch = it; preview = null; previewId = ""; intent = ""; key = UUID.randomUUID().toString() }, label = { Text("Working branch — never main/master") }, modifier = Modifier.fillMaxWidth()) }
            item { message?.let { Text(it) }; preview?.optJSONObject("result")?.let { Text(it.toString(2), style = MaterialTheme.typography.bodySmall) } }
            item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(enabled = !busy && title.isNotBlank() && instruction.isNotBlank() && (!mutating || branch.isNotBlank()), onClick = {
                    busy = true
                    scope.launch { try {
                        val body = payload()
                        if (intent != body.toString()) { previewId = ""; preview = null; intent = body.toString() }
                        if (previewId.isBlank()) {
                            val response = unwrap(app.gatewayClient.museTaskCall("muse_resolve_project", body))
                            previewId = response.optString("command_id").ifBlank { response.optString("id") }.ifBlank { response.optJSONObject("command")?.optString("id").orEmpty() }
                        }
                        readPreview()
                    } catch (_: Exception) { message = "Scope preview unavailable. No task was submitted." } finally { busy = false } }
                }) { Text(if (previewId.isBlank()) "Check scope" else "Refresh scope") }
                Button(enabled = !busy && preview?.optString("state") == "completed" && previewId.isNotBlank(), onClick = {
                    busy = true
                    scope.launch { try {
                        val body = JSONObject(intent).put("resolution_command_id", previewId).put("idempotency_key", "submit:$key")
                        app.gatewayClient.museTaskCall(if (parentJob.isBlank()) "muse_submit_task" else "muse_continue_task", body)
                        onDone()
                    } catch (_: Exception) { message = "Submission not confirmed. Retrying preserves the same request." } finally { busy = false } }
                }) { Text("Submit task") }
            } }
            item { Spacer(Modifier.height(28.dp)) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MuseProjectForm(app: VanApplication, onDismiss: () -> Unit, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var title by rememberSaveable { mutableStateOf("") }
    var description by rememberSaveable { mutableStateOf("") }
    var repository by rememberSaveable { mutableStateOf("") }
    var defaultBranch by rememberSaveable { mutableStateOf("") }
    val key = rememberSaveable { UUID.randomUUID().toString() }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        LazyColumn(Modifier.fillMaxWidth().heightIn(max = 650.dp).padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Text("Register a project", style = MaterialTheme.typography.titleLarge); Text("Creates the shared tracker record, not a GitHub repository or provider workspace.") }
            item { OutlinedTextField(title, { title = it.take(180) }, label = { Text("Project name") }, modifier = Modifier.fillMaxWidth()) }
            item { OutlinedTextField(description, { description = it.take(4000) }, label = { Text("Purpose") }, modifier = Modifier.fillMaxWidth()) }
            item { OutlinedTextField(repository, { repository = it }, label = { Text("GitHub repository URL (optional)") }, modifier = Modifier.fillMaxWidth()) }
            item { OutlinedTextField(defaultBranch, { defaultBranch = it }, label = { Text("Known default branch (optional)") }, modifier = Modifier.fillMaxWidth()) }
            item { message?.let { Text(it) }; Button(enabled = !busy && title.isNotBlank(), onClick = { busy = true; scope.launch { try {
                app.gatewayClient.museTaskCall("muse_create_project", JSONObject().put("idempotency_key", "project:$key").put("title", title.trim()).put("description", description).put("repository_url", repository.trim()).put("default_branch", defaultBranch.trim()))
                onDone()
            } catch (_: Exception) { message = "Project registration not confirmed. The original request key is retained." } finally { busy = false } } }) { Text("Create project") } }
            item { Spacer(Modifier.height(28.dp)) }
        }
    }
}
