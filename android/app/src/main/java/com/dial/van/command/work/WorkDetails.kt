package com.dial.van.command.work

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
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
import com.dial.van.VanApplication
import com.dial.van.command.modules.ActivityModule
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
import com.dial.van.mission.MissionSummary
import com.dial.van.session.OwnerReconfirmationRequest
import com.dial.van.status.VanCommandStatus
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPresence
import com.dial.van.visual.rememberVanEffectBudget
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

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
internal fun ReconfirmationPanel(app: VanApplication) {
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
internal fun ConversationBubble(message: VanConversationMessage) {
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
            message.memoryEffectReceipt?.takeIf { it.mayRender(message.status == VanCommandStatus.SUCCEEDED) }?.let { receipt ->
                Text("Verified memory erasure", style = tokens.type.label, color = tokens.color.textSecondary)
                receipt.removedCounts.forEach { (store, count) -> Text("${store.replace('_', ' ')}: $count removed", style = tokens.type.label, color = tokens.color.textSecondary) }
                Text("Evidence: ${receipt.evidenceRef}", style = tokens.type.label, color = tokens.color.textTertiary)
                receipt.retainedReasons.forEach { Text(it, style = tokens.type.label, color = tokens.color.textTertiary) }
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
internal fun MissionRow(app: VanApplication, mission: MissionSummary, role: String, label: String, initiallyExpanded: Boolean = false, onChanged: (MissionSummary?, String) -> Unit, onRefresh: () -> Unit) {
    val tokens = LocalVanTokens.current
    var expanded by rememberSaveable(mission.missionId) { mutableStateOf(initiallyExpanded) }
    var timeline by remember(mission.missionId) { mutableStateOf<List<TimelineEvent>?>(null) }
    var timelineError by remember(mission.missionId) { mutableStateOf<String?>(null) }
    var retry by remember(mission.missionId) { mutableStateOf(0) }

    LaunchedEffect(mission.missionId, mission.updatedAtMs, expanded, retry) {
        if (expanded) {
            timelineError = null
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
                .onFailure {
                    if (it is CancellationException) throw it
                    timelineError = it.message ?: "VAN could not load this mission's timeline."
                }
        }
    }
    VanPanel(modifier = Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            VanPressable(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth()) {
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2), verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(label = label, role = role)
                    Text(mission.title, style = tokens.type.body, color = tokens.color.textPrimary)
                }
            }
                Text(mission.ownerReadableStatus, style = tokens.type.label, color = tokens.color.textSecondary)
                if (expanded) {
                    when {
                        timelineError != null -> {
                            Text(timelineError!!, style = tokens.type.label, color = tokens.color.textTertiary)
                            OutlinedButton(onClick = { retry += 1 }) { Text("Retry timeline") }
                        }
                        timeline == null -> Text("Loading timeline…", style = tokens.type.label, color = tokens.color.textTertiary)
                        timeline!!.isEmpty() -> Text("No timeline events recorded yet.", style = tokens.type.label, color = tokens.color.textTertiary)
                        else -> TimelineRail(events = timeline!!)
                    }
                    MissionControls(app, mission, onChanged = { updated, notice -> timeline = null; retry += 1; onChanged(updated, notice) }, onRefresh = { timeline = null; retry += 1; onRefresh() })
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
