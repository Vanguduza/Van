package com.dial.van.command.work

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.command.modules.ActivityModule
import com.dial.van.control.VanCommandSource
import com.dial.van.control.VanConversationMessage
import com.dial.van.control.VanMessageRole
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.TimelineEvent
import com.dial.van.design.components.TimelineRail
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.mission.MissionRepository
import com.dial.van.mission.MissionSummary
import com.dial.van.session.OwnerReconfirmationRequest
import com.dial.van.status.VanCommandStatus
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPresence
import com.dial.van.visual.rememberVanEffectBudget
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * DNA §4 destination 3: the Command Centre — "command bar (text + voice), missions (running /
 * waiting / done), delegated agents, activity feed, browser & automation tasks as children."
 *
 * GAP-F-011's fix lives here: the conversation thread updates on completion, polling every 4s
 * while any message is unfinished ([ConversationReducer]/`VanCommandController.pollUnfinishedCommands`).
 *
 * @DataSource("com.dial.van.control.VanCommandController.state") — the conversation.
 * @DataSource("GET /v1/missions?active=true, GET /v1/needs-you") — the missions list.
 * @DataSource("GET /v1/missions/{id}/activity") — a mission's expanded timeline.
 */
@Composable
fun WorkRoute(
    app: VanApplication,
    onOpenBrowser: () -> Unit,
    onOpenActivity: () -> Unit,
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    val activity = LocalContext.current as? FragmentActivity
    val conversation by app.commandController.state.collectAsState()
    var draft by rememberSaveable { mutableStateOf("") }

    val repository = remember(app) { MissionRepository(app.gatewayClient) }
    var active by remember { mutableStateOf<List<MissionSummary>>(emptyList()) }
    var waiting by remember { mutableStateOf<List<MissionSummary>>(emptyList()) }
    var missionsError by remember { mutableStateOf<String?>(null) }

    fun refreshMissions() {
        scope.launch {
            runCatching { repository.home() }
                .onSuccess { active = it.activeMissions; waiting = it.waitingMissions; missionsError = null }
                .onFailure { missionsError = it.message ?: "Unable to reach VAN" }
        }
    }
    LaunchedEffect(Unit) { refreshMissions() }

    // GAP-F-011 — while any VAN message is unfinished, ask the gateway again every 4s.
    LaunchedEffect(Unit) {
        while (true) {
            delay(4_000L)
            app.commandController.pollUnfinishedCommands()
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
        contentPadding = PaddingValues(vertical = tokens.space.space3),
    ) {
        item { SectionHeader("Work", detail = "Command Centre") }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                if (conversation.messages.isEmpty()) {
                    Text("Nothing sent yet in this session.", style = tokens.type.body, color = tokens.color.textSecondary)
                }
                conversation.messages.takeLast(20).forEach { message ->
                    ConversationBubble(message)
                }
            }
        }

        item {
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    OutlinedTextField(
                        value = draft,
                        onValueChange = { draft = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Tell VAN what you want done") },
                        maxLines = 4,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Button(onClick = {
                            val text = draft.trim()
                            if (text.isNotEmpty()) {
                                app.commandController.submitText(text, VanCommandSource.CHAT)
                                draft = ""
                            }
                        }) { Text("Send") }
                        Button(onClick = { app.voiceSession.beginOwnerTurn() }) { Text("Voice") }
                    }
                    if (conversation.submitting) {
                        Text("Sending…", style = tokens.type.label, color = tokens.color.accentCyan)
                    }
                }
            }
        }

        conversation.pendingA4Approval?.let { pending ->
            item {
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text("Owner approval required", style = tokens.type.headline, color = tokens.color.textPrimary)
                            StatusChip(label = "PENDING", role = StatusSemantics.ROLE_EVENT_RISK)
                        }
                        Text(pending.resolvedActionId, style = tokens.type.body, color = tokens.color.textSecondary)
                        Button(
                            enabled = activity != null && !conversation.submitting,
                            onClick = { activity?.let { app.commandController.approvePendingA4(it) } },
                        ) { Text("Approve") }
                    }
                }
            }
        }

        item {
            OutlinedButton(onClick = onOpenBrowser) {
                Text("Browser & Automation")
            }
        }

        // §20.15 — commands held during an outage, which do not run until the owner
        // confirms them here. This was the old Tasks module's whole reason to exist; it
        // moves onto Work rather than disappearing with TasksModule.kt.
        item { ReconfirmationPanel(app) }

        item { SectionHeader("Missions", detail = "Running, waiting, and what happened") }
        missionsError?.let { item { Text(it, style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK)) } }
        if (waiting.isNotEmpty()) {
            item { SectionHeader("Waiting on you", detail = "Not progressing") }
            items(waiting, key = { "wait-${it.missionId}" }) { mission -> MissionRow(app, mission, StatusSemantics.ROLE_HYPOTHESIS, "WAITING") }
        }
        item { SectionHeader("Running") }
        if (active.isEmpty()) {
            item { Text("Nothing is running.", style = tokens.type.body, color = tokens.color.textSecondary) }
        }
        items(active, key = { "run-${it.missionId}" }) { mission -> MissionRow(app, mission, StatusSemantics.ROLE_ENGAGED, "RUNNING") }

        item {
            OutlinedButton(onClick = onOpenActivity) {
                Text("Activity — delegated agents and the owner timeline")
            }
        }
    }
}

/**
 * `work/activity` — the delegated agents/activity feed DNA §4 lists alongside missions.
 * `ActivityModule` is itself a `LazyColumn { fillMaxSize() }` (P3-AND-002's event stream),
 * so — same reason as Settings' voice/notifications children — it gets its own destination
 * rather than being nested as an item inside Work's own list.
 */
@Composable
fun WorkActivityRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    val degraded by app.degradedModeStore.state.collectAsState()
    val cue = VanPresence.cue(degraded)
    val budget = rememberVanEffectBudget()
    val glass = VanGlassTokens.forState(state = cue.durableState, panel = true, liveBlurAvailable = false, budget = budget)
    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = tokens.space.pageGutter, vertical = tokens.space.space2),
            horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
        ) {
            Button(onClick = onBack) { Text("← Work", style = tokens.type.label) }
        }
        ActivityModule(app, glass)
    }
}

/**
 * §20.15 — work the outbox will not send until the owner says so again. Held over from the
 * old Tasks module: a queue-depth change (arrived, expired, flushed, cancelled) is the
 * signal to re-read `pendingOwnerReconfirmations()`; reconfirmation itself leaves the depth
 * unchanged, so the button handlers below refresh explicitly after the durable write.
 */
@Composable
private fun ReconfirmationPanel(app: VanApplication) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    val sessionState by app.vanSession.state.collectAsState()
    var confirmations by remember { mutableStateOf<List<OwnerReconfirmationRequest>>(emptyList()) }
    var notice by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        confirmations = app.vanSession.pendingOwnerReconfirmations()
    }
    LaunchedEffect(sessionState.outboxDepth) { refresh() }

    if (confirmations.isEmpty()) return

    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        SectionHeader("Waiting for you", detail = "Held during an outage; will not run until you confirm them")
        confirmations.forEach { request ->
            VanPanel {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    Text(request.commandText, style = tokens.type.headline, color = tokens.color.textPrimary)
                    Text(request.ownerReadableState, style = tokens.type.label, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
                    Text(
                        "Action ${request.actionClass} • ${request.commandId.takeLast(8)}",
                        style = tokens.type.label,
                        color = tokens.color.textTertiary,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Button(onClick = {
                            scope.launch {
                                val accepted = withContext(Dispatchers.IO) { app.vanSession.reconfirmAndFlush(request.messageId) }
                                notice = if (accepted) {
                                    "Confirmed. VAN will send it on the current path, or the next one that becomes available."
                                } else {
                                    "That queued command is no longer waiting for confirmation."
                                }
                                refresh()
                            }
                        }) { Text("Confirm") }
                        OutlinedButton(onClick = {
                            scope.launch {
                                val cancelled = withContext(Dispatchers.IO) { app.vanSession.cancelReconfirmation(request.messageId) }
                                notice = if (cancelled) {
                                    "Cancelled. VAN will not send that queued command."
                                } else {
                                    "That queued command is no longer waiting for confirmation."
                                }
                                refresh()
                            }
                        }) { Text("Cancel") }
                    }
                }
            }
        }
        notice?.let { Text(it, style = tokens.type.label, color = tokens.color.textSecondary) }
    }
}

@Composable
private fun ConversationBubble(message: VanConversationMessage) {
    val tokens = LocalVanTokens.current
    val role = when (message.role) {
        VanMessageRole.OWNER -> "You"
        VanMessageRole.VAN -> "VAN"
        VanMessageRole.SYSTEM -> "System"
    }
    VanPanel(dense = true) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2), verticalAlignment = Alignment.CenterVertically) {
                Text(role, style = tokens.type.label, color = tokens.color.accentCyan)
                message.status?.let { status ->
                    StatusChip(label = status.name.replace('_', ' '), role = statusRole(status))
                }
            }
            Text(message.text, style = tokens.type.body, color = tokens.color.textPrimary)
            message.contextGapsSentence?.let {
                Text(it, style = tokens.type.label, color = tokens.color.textTertiary)
            }
        }
    }
}

/** Exhaustive, mirroring `com.dial.van.command.statusColor` (P0-EXEC-003's own rule). */
private fun statusRole(status: VanCommandStatus): String = when (status) {
    VanCommandStatus.SUCCEEDED -> StatusSemantics.ROLE_FAVOURABLE
    VanCommandStatus.FAILED, VanCommandStatus.CANCELLED, VanCommandStatus.EXPIRED, VanCommandStatus.REFUSED ->
        StatusSemantics.ROLE_CRITICAL
    VanCommandStatus.PARTIALLY_SUCCEEDED, VanCommandStatus.COULD_NOT_VERIFY, VanCommandStatus.APPROVAL_REQUIRED, VanCommandStatus.UNKNOWN ->
        StatusSemantics.ROLE_EVENT_RISK
    VanCommandStatus.LOCAL_DRAFT, VanCommandStatus.SUBMITTING, VanCommandStatus.ACCEPTED, VanCommandStatus.IN_FLIGHT, VanCommandStatus.QUEUED ->
        StatusSemantics.ROLE_MONITOR
}

@Composable
private fun MissionRow(app: VanApplication, mission: MissionSummary, role: String, label: String) {
    val tokens = LocalVanTokens.current
    var expanded by rememberSaveable(mission.missionId) { mutableStateOf(false) }
    var timeline by remember(mission.missionId) { mutableStateOf<List<TimelineEvent>>(emptyList()) }
    val scope = rememberCoroutineScope()

    VanPressable(onClick = {
        expanded = !expanded
        if (expanded && timeline.isEmpty()) {
            scope.launch {
                runCatching { app.gatewayClient.missionActivity(mission.missionId) }
                    .onSuccess { body ->
                        val events = body.optJSONArray("events")
                        timeline = buildList {
                            if (events != null) {
                                for (i in 0 until events.length()) {
                                    val e = events.optJSONObject(i) ?: continue
                                    add(
                                        TimelineEvent(
                                            id = e.optString("event_id", i.toString()),
                                            title = e.optString("summary", e.optString("event_type", "Event")),
                                            actor = e.optString("actor", "van"),
                                            timeLabel = formatTime(e.optLong("occurred_at_ms", 0L)),
                                            severityRole = severityRole(e.optString("severity", "INFO")),
                                        ),
                                    )
                                }
                            }
                        }
                    }
            }
        }
    }, modifier = Modifier.fillMaxWidth()) {
        VanPanel(modifier = Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2), verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(label = label, role = role)
                    Text(mission.title, style = tokens.type.body, color = tokens.color.textPrimary)
                }
                Text(mission.ownerReadableStatus, style = tokens.type.label, color = tokens.color.textSecondary)
                if (expanded) {
                    if (timeline.isEmpty()) {
                        Text("Loading timeline…", style = tokens.type.label, color = tokens.color.textTertiary)
                    } else {
                        TimelineRail(events = timeline)
                    }
                }
            }
        }
    }
}

private fun severityRole(severity: String): String = when (severity.uppercase()) {
    "CRITICAL", "ERROR" -> StatusSemantics.ROLE_CRITICAL
    "WARNING", "BLOCKER" -> StatusSemantics.ROLE_EVENT_RISK
    else -> StatusSemantics.ROLE_MONITOR
}

private fun formatTime(epochMs: Long): String =
    if (epochMs <= 0L) "" else SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(epochMs))
