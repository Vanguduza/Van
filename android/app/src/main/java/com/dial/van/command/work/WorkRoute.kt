package com.dial.van.command.work

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.command.owner.ownerTime
import com.dial.van.control.VanCommandSource
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.mission.MissionRepository
import com.dial.van.mission.MissionParsing
import com.dial.van.mission.MissionSelection
import com.dial.van.mission.MissionSummary
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

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
    onOpenArtemis: () -> Unit,
    onOpenActivity: () -> Unit,
    onOpenDevelopment: () -> Unit = {},
    requestedMissionId: String? = null,
    onOpenKnowledge: () -> Unit = {},
    onOpenResearch: () -> Unit = {},
    onOpenAutomation: () -> Unit = {},
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    val activity = LocalContext.current as? FragmentActivity
    val conversation by app.commandController.state.collectAsState()
    val approval = conversation.pendingA4Approval
    val isGmailSend = approval?.resolvedActionId == "google.gmail.send"
    var gmailPreview by remember(approval?.challengeId) { mutableStateOf<GmailApprovalPreview?>(null) }
    var gmailPreviewError by remember(approval?.challengeId) { mutableStateOf<String?>(null) }
    var gmailPreviewAttempt by remember(approval?.challengeId) { mutableStateOf(0) }
    LaunchedEffect(approval?.challengeId, gmailPreviewAttempt) {
        if (!isGmailSend || approval == null) return@LaunchedEffect
        gmailPreview = null
        gmailPreviewError = null
        try {
            val parameters = JSONObject(approval.resolvedParametersJson ?: error("Missing sealed parameters"))
            val observed = app.gatewayClient.googleGmailDraftPreview(parameters.getString("draft_id"))
            gmailPreview = GmailApprovalPreview.parse(parameters, observed)
            if (gmailPreview == null) gmailPreviewError = "This draft could not be matched to the exact approval. Request a new approval if its contents changed."
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            gmailPreviewError = "The draft could not be read for review. Retry the preview before approving."
        }
    }
    val voice by app.voiceUi.state.collectAsState()
    val voiceTurnActive by app.voiceSession.ownerTurnActive.collectAsState()
    var draft by rememberSaveable { mutableStateOf("") }

    val repository = remember(app) { MissionRepository(app.gatewayClient) }
    var active by remember { mutableStateOf<List<MissionSummary>>(emptyList()) }
    var waiting by remember { mutableStateOf<List<MissionSummary>>(emptyList()) }
    var completed by remember { mutableStateOf<List<MissionSummary>>(emptyList()) }
    var missionsLoading by remember { mutableStateOf(true) }
    var missionsError by remember { mutableStateOf<String?>(null) }
    var missionNotice by remember { mutableStateOf<String?>(null) }
    var requestedMission by remember(requestedMissionId) { mutableStateOf<MissionSummary?>(null) }
    var requestedMissionError by remember(requestedMissionId) { mutableStateOf<String?>(null) }

    fun refreshMissions() {
        scope.launch {
            missionsLoading = true
            runCatching { repository.missions() }
                .onSuccess {
                    active = it.filter { mission -> mission.isActive }
                    waiting = it.filter { mission -> !mission.isTerminal && mission.state == "WAITING_FOR_OWNER" }
                    completed = it.filter { mission -> mission.isTerminal }
                    requestedMission = it.firstOrNull { mission -> mission.missionId == requestedMissionId }
                    missionsError = null
                }
                .onFailure {
                    if (it is CancellationException) throw it
                    missionsError = it.message ?: "Unable to reach VAN"
                }
            missionsLoading = false
            if (!requestedMissionId.isNullOrBlank()) {
                if (requestedMission?.missionId != requestedMissionId) {
                    runCatching {
                        MissionParsing.missionSummary(repository.mission(requestedMissionId)).also {
                            check(it.missionId == requestedMissionId) { "VAN returned a different mission." }
                        }
                    }
                        .onSuccess { requestedMission = it; requestedMissionError = null }
                        .onFailure {
                            if (it is CancellationException) throw it
                            requestedMissionError = it.message ?: "VAN could not open this mission."
                        }
                } else {
                    requestedMissionError = null
                }
            }
        }
    }
    LaunchedEffect(requestedMissionId) { refreshMissions() }
    val missions = MissionSelection.present(requestedMissionId, active, waiting, requestedMission)
    fun missionChanged(updated: MissionSummary?, notice: String) {
        missionNotice = notice
        if (updated != null) {
            active = active.filterNot { it.missionId == updated.missionId }
            waiting = waiting.filterNot { it.missionId == updated.missionId }
            completed = listOf(updated) + completed.filterNot { it.missionId == updated.missionId }
            if (requestedMissionId == updated.missionId) requestedMission = updated
        }
        refreshMissions()
    }

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
        missionNotice?.let { item { Text(it, style = tokens.type.label, color = tokens.color.textSecondary) } }
        if (!requestedMissionId.isNullOrBlank()) {
            item { SectionHeader("Requested mission") }
            missions.requested?.let { mission ->
                item(key = "requested-${mission.missionId}") {
                    MissionRow(app, mission, StatusSemantics.ROLE_COGNITION, "SELECTED", initiallyExpanded = true, onChanged = ::missionChanged, onRefresh = ::refreshMissions)
                }
            } ?: item {
                Text(
                    requestedMissionError ?: "Opening mission…",
                    style = tokens.type.body,
                    color = tokens.color.textSecondary,
                )
                if (requestedMissionError != null) {
                    OutlinedButton(onClick = ::refreshMissions) { Text("Retry") }
                }
            }
        }

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
                        Button(enabled = !voiceTurnActive, onClick = { app.voiceSession.beginOwnerTurn() }) { Text("Voice") }
                    }
                    if (voice.listening) {
                        Text(voice.partialTranscript.ifBlank { "Listening…" }, style = tokens.type.body, color = tokens.color.textSecondary)
                        OutlinedButton(onClick = { app.voiceSession.endOwnerTurn() }) { Text("Finish speaking") }
                    }
                    if (voiceTurnActive) {
                        if (!voice.listening) Text("Finishing voice recognition…", style = tokens.type.label, color = tokens.color.textSecondary)
                        OutlinedButton(onClick = { app.voiceSession.cancelOwnerTurn() }) { Text("Cancel speaking") }
                    }
                    voice.finalTranscript?.let { Text("Heard: $it", style = tokens.type.label, color = tokens.color.textSecondary) }
                    voice.errorCode?.let {
                        Text("VAN could not complete voice recognition (code $it). You can try voice again or type your request.", style = tokens.type.label, color = tokens.color.textSecondary)
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
                        Text(pending.command.text, style = tokens.type.body, color = tokens.color.textPrimary)
                        pending.resolvedParametersJson?.let {
                            Text("Exact resolved parameters", style = tokens.type.label, color = tokens.color.textSecondary)
                            Text(it, style = tokens.type.body, color = tokens.color.textPrimary)
                        }
                        if (isGmailSend) {
                            val preview = gmailPreview
                            if (preview != null) {
                                Text("From: ${preview.sender}")
                                Text("To: ${preview.to.joinToString()}")
                                if (preview.cc.isNotEmpty()) Text("Cc: ${preview.cc.joinToString()}")
                                if (preview.bcc.isNotEmpty()) Text("Bcc: ${preview.bcc.joinToString()}")
                                Text("Subject: ${preview.subject}")
                                Text(preview.body, style = tokens.type.body, color = tokens.color.textPrimary)
                                Text("This sends the reviewed content as an immutable message. The source draft is retained; its later state is not verified.", style = tokens.type.label, color = tokens.color.textSecondary)
                            } else {
                                Text(gmailPreviewError ?: "Reading the draft for your review…", style = tokens.type.body)
                                if (gmailPreviewError != null) OutlinedButton(onClick = { gmailPreviewAttempt++ }) { Text("Retry preview") }
                            }
                        }
                        Text("Approval expires ${ownerTime(pending.expiresAtUnix * 1_000L)}. Only this exact action is being approved.", style = tokens.type.label, color = tokens.color.textSecondary)
                        Button(
                            enabled = activity != null && !conversation.submitting && pending.expiresAtUnix > System.currentTimeMillis() / 1_000L && (!isGmailSend || gmailPreview != null),
                            onClick = { activity?.let { app.commandController.approvePendingA4(it, reviewedGmailDraftDigest = gmailPreview?.contentDigest) } },
                        ) { Text("Approve") }
                        OutlinedButton(
                            enabled = !conversation.submitting,
                            onClick = { app.commandController.discardPendingA4(pending.challengeId) },
                        ) { Text("Decline") }
                    }
                }
            }
        }

        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                item { OutlinedButton(onClick = onOpenKnowledge) { Text("Knowledge") } }
                item { OutlinedButton(onClick = onOpenResearch) { Text("Research") } }
                item { OutlinedButton(onClick = onOpenAutomation) { Text("Automation") } }
            }
        }
        item {
            OutlinedButton(onClick = onOpenBrowser) {
                Text("Browser & Automation")
            }
        }

        item {
            OutlinedButton(onClick = onOpenArtemis) {
                Text("ARTEMIS Android Lab")
            }
        }

        // VAN-DEVCC-R1 §2.1 — the Development hub lives under Work (`work/dev`), not as a
        // ninth destination. VAN shows DIAL's development state and forwards typed owner
        // commands; it plans and executes none of that work itself.
        item {
            OutlinedButton(onClick = onOpenDevelopment) {
                Text("Development — DIAL projects, tasks, agents, workspaces")
            }
        }

        // §20.15 — commands held during an outage, which do not run until the owner
        // confirms them here. This was the old Tasks module's whole reason to exist; it
        // moves onto Work rather than disappearing with TasksModule.kt.
        item { ReconfirmationPanel(app) }

        item { SectionHeader("Missions", detail = "Running, waiting, and what happened") }
        missionsError?.let { item {
            Text("VAN could not refresh missions. Last known records remain available. $it", style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
            OutlinedButton(onClick = ::refreshMissions, enabled = !missionsLoading) { Text("Retry") }
        } }
        item { OutlinedButton(onClick = ::refreshMissions, enabled = !missionsLoading) { Text(if (missionsLoading) "Refreshing missions…" else "Refresh missions") } }
        if (missions.waiting.isNotEmpty()) {
            item { SectionHeader("Waiting on you", detail = "Not progressing") }
            items(missions.waiting, key = { "wait-${it.missionId}" }) { mission -> MissionRow(app, mission, StatusSemantics.ROLE_HYPOTHESIS, "WAITING", onChanged = ::missionChanged, onRefresh = ::refreshMissions) }
        }
        item { SectionHeader("Running") }
        if (active.isEmpty() && !missionsLoading && missionsError == null) {
            item { Text("Nothing is running.", style = tokens.type.body, color = tokens.color.textSecondary) }
        }
        items(missions.running, key = { "run-${it.missionId}" }) { mission -> MissionRow(app, mission, StatusSemantics.ROLE_ENGAGED, "RUNNING", onChanged = ::missionChanged, onRefresh = ::refreshMissions) }
        if (completed.any { it.missionId != requestedMissionId }) {
            item { SectionHeader("Finished", detail = "Verified, partial, failed and cancelled outcomes") }
            items(completed.filterNot { it.missionId == requestedMissionId }.take(30), key = { "done-${it.missionId}" }) { mission ->
                MissionRow(app, mission, StatusSemantics.ROLE_MONITOR, mission.state.replace('_', ' '), onChanged = ::missionChanged, onRefresh = ::refreshMissions)
            }
        }

        item {
            OutlinedButton(onClick = onOpenActivity) {
                Text("Activity — delegated agents and the owner timeline")
            }
        }
    }
}
