package com.dial.van.command

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.control.VanCommandSource
import com.dial.van.control.VanCommandStatus
import com.dial.van.control.VanConversationMessage
import com.dial.van.control.VanMessageRole
import com.dial.van.overlay.FloatingOverlayService
import com.dial.van.trading.TradingCommandCentreActivity
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanGlassSurface
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.rememberVanEffectBudget
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

private enum class CommandModule(val id: String, val title: String) {
    OVERVIEW("overview", "Home"),
    CHAT("chat", "Chat"),
    DECISIONS("decisions", "Decisions"),
    TASKS("tasks", "Tasks"),
    PROJECTS("projects", "Projects"),
    ACTIVITY("activity", "Activity"),
    SYSTEMS("systems", "Systems"),
    CONNECTIONS("connections", "Connections"),
    SETTINGS("settings", "Settings"),
    ;

    companion object {
        fun fromId(id: String?): CommandModule = entries.firstOrNull { it.id == id } ?: OVERVIEW
    }
}

class CommandCentreActivity : FragmentActivity() {
    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        val initial = CommandModule.fromId(intent.getStringExtra(EXTRA_MODULE))

        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Color(VanGlassTokens.ACCENT_CYAN))) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(
                            Brush.verticalGradient(
                                listOf(Color(0xFF051018), Color(0xFF071722), Color(0xFF040A10)),
                            ),
                        ),
                ) {
                    Scaffold(
                        containerColor = Color.Transparent,
                        topBar = {
                            TopAppBar(
                                title = { Text("Van Command Centre") },
                                colors = TopAppBarDefaults.topAppBarColors(
                                    containerColor = Color.Transparent,
                                    titleContentColor = Color.White,
                                ),
                            )
                        },
                    ) { padding ->
                        CommandCentreScreen(padding, app, initial)
                    }
                }
            }
        }
    }

    companion object {
        const val EXTRA_MODULE = "module"
    }
}

@Composable
private fun CommandCentreScreen(
    padding: PaddingValues,
    app: VanApplication,
    initial: CommandModule,
) {
    var selected by remember { mutableStateOf(initial) }
    val degraded by app.degradedModeStore.state.collectAsState()
    val live = VanLiveVisualState.frame
    val cue = VanPresence.cue(degraded, live = live)
    val budget = rememberVanEffectBudget()
    val glass = VanGlassTokens.forState(
        state = cue.durableState,
        panel = true,
        liveBlurAvailable = false,
        budget = budget,
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(padding),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 12.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            CommandModule.entries.forEach { module ->
                Button(
                    onClick = { selected = module },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (selected == module) {
                            Color(VanGlassTokens.BABY_CYAN).copy(alpha = 0.24f)
                        } else {
                            Color(VanGlassTokens.TINT_NAVY).copy(alpha = 0.72f)
                        },
                        contentColor = if (selected == module) Color(VanGlassTokens.ICE_CYAN) else Color(0xFFBCD1D8),
                    ),
                    shape = RoundedCornerShape(10.dp),
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                ) {
                    Text(module.title, fontSize = 11.sp)
                }
            }
        }

        when (selected) {
            CommandModule.OVERVIEW -> OverviewModule(app, glass) { selected = it }
            CommandModule.CHAT -> ChatModule(app, glass)
            CommandModule.DECISIONS -> DecisionsModule(app, glass)
            CommandModule.TASKS -> TasksModule(app, glass) { selected = CommandModule.CHAT }
            CommandModule.PROJECTS -> ProjectsModule(app, glass) { projectId ->
                app.commandController.selectProject(projectId)
                selected = CommandModule.CHAT
            }
            CommandModule.ACTIVITY -> ActivityModule(app, glass)
            CommandModule.SYSTEMS -> SystemsModule(app, glass)
            CommandModule.CONNECTIONS -> ConnectionsModule(app, glass)
            CommandModule.SETTINGS -> SettingsModule(app, glass)
        }
    }
}

@Composable
private fun OverviewModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    navigate: (CommandModule) -> Unit,
) {
    var health by remember { mutableStateOf<JSONObject?>(null) }
    var decisions by remember { mutableStateOf<Int?>(null) }
    var projects by remember { mutableStateOf<Int?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current

    LaunchedEffect(Unit) {
        runCatching {
            health = app.gatewayClient.health()
            decisions = app.gatewayClient.decisions().length()
            projects = app.gatewayClient.projects().length()
        }.onFailure { error = it.message ?: "Gateway unavailable" }
    }

    val degraded by app.degradedModeStore.state.collectAsState()
    val live = VanLiveVisualState.frame
    val cue = VanPresence.cue(degraded, live = live)
    val budget = rememberVanEffectBudget()

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item {
            AdminCard(glass) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    VanEmbodiment(
                        state = VanPresence.visualState(cue, live),
                        budget = budget,
                        presentation = VanPresentation.EXPANDED,
                        modifier = Modifier.size(116.dp),
                    )
                    Column(modifier = Modifier.padding(start = 10.dp)) {
                        Text("VAN", color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Bold)
                        Text(cue.headline, color = Color(VanGlassTokens.ACCENT_CYAN), fontSize = 14.sp)
                        Text(cue.detail, color = Color(0xFFBCD1D8), fontSize = 11.sp)
                        Text(
                            if (health?.optBoolean("ok") == true) "Hermes / gateway reachable" else "Hermes / gateway not confirmed",
                            color = if (health?.optBoolean("ok") == true) Color(VanGlassTokens.ACCENT_GREEN) else Color(VanGlassTokens.ACCENT_AMBER),
                            fontSize = 11.sp,
                        )
                    }
                }
            }
        }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        item {
            AdminActionCard("Chat", "Issue an owner instruction through the signed gateway", glass) { navigate(CommandModule.CHAT) }
        }
        item {
            AdminActionCard(
                "Decisions",
                decisions?.let { "$it open decision(s) returned by the gateway" } ?: "Loading authoritative decisions…",
                glass,
            ) { navigate(CommandModule.DECISIONS) }
        }
        item {
            AdminActionCard(
                "Projects",
                projects?.let { "$it registered project context(s)" } ?: "Loading project registry…",
                glass,
            ) { navigate(CommandModule.PROJECTS) }
        }
        item {
            AdminActionCard("Tasks", "Inspect local queued and dispatched owner work", glass) { navigate(CommandModule.TASKS) }
        }
        item {
            AdminActionCard("Systems", "Inspect Hermes, gateway and Google mesh truth", glass) { navigate(CommandModule.SYSTEMS) }
        }
        item {
            AdminActionCard("Trading", "Open the read-first VATI trading command center", glass) {
                context.startActivity(TradingCommandCentreActivity.intent(context))
            }
        }
    }
}

@Composable
private fun ChatModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val state by app.commandController.state.collectAsState()
    var draft by remember { mutableStateOf("") }

    Column(modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp, vertical = 8.dp)) {
        AdminCard(glass) {
            Column {
                Text("Owner chat", color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                Text(
                    state.selectedProjectId?.let { "Project context: $it" } ?: "Global owner context",
                    color = Color(VanGlassTokens.EDGE_CYAN),
                    fontSize = 11.sp,
                )
                Text(
                    "Typed and voice input share the same signed command controller.",
                    color = Color(0xFFBCD1D8),
                    fontSize = 10.sp,
                )
            }
        }
        Spacer(Modifier.height(8.dp))
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(7.dp),
            contentPadding = PaddingValues(vertical = 6.dp),
        ) {
            if (state.messages.isEmpty()) {
                item { TruthMessage("No conversation messages yet.") }
            }
            items(state.messages, key = { it.id }) { message ->
                CommandMessageBubble(message, glass)
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it },
                modifier = Modifier.weight(1f),
                label = { Text("Owner command") },
                maxLines = 4,
            )
            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Button(onClick = {
                    val text = draft.trim()
                    if (text.isNotEmpty()) {
                        app.commandController.submitText(text, VanCommandSource.CHAT)
                        draft = ""
                    }
                }) { Text("Send") }
                Button(onClick = { app.voiceSession.beginOwnerTurn() }) { Text("Voice") }
            }
        }
        if (state.submitting) {
            Text("Dispatching through VAN gateway…", color = Color(VanGlassTokens.EDGE_CYAN), fontSize = 10.sp)
        }
    }
}

@Composable
private fun DecisionsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val scope = rememberCoroutineScope()
    var records by remember { mutableStateOf<List<JSONObject>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching { app.gatewayClient.decisions().objectList() }
                .onSuccess { records = it; error = null }
                .onFailure { error = it.message ?: "Unable to load decisions" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Decisions", "Owner escalations returned by /v1/decisions") }
        if (records == null && error == null) item { TruthMessage("Loading decisions…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (records?.isEmpty() == true) item { TruthMessage("No open decisions returned by the gateway.") }
        items(records.orEmpty(), key = { it.optString("id") }) { record ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(record.optString("title", "Decision"), color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text(record.optString("body"), color = Color(0xFFD7E7EC), fontSize = 12.sp)
                    Text(
                        "Source: ${record.optString("source", "unknown")} • ${record.optString("status", "OPEN")}",
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = {
                            scope.launch {
                                runCatching { app.gatewayClient.resolveDecision(record.getString("id"), true) }
                                    .onSuccess { refresh() }
                                    .onFailure { error = it.message }
                            }
                        }) { Text("Approve") }
                        Button(
                            onClick = {
                                scope.launch {
                                    runCatching { app.gatewayClient.resolveDecision(record.getString("id"), false) }
                                        .onSuccess { refresh() }
                                        .onFailure { error = it.message }
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF5B2730)),
                        ) { Text("Reject") }
                    }
                }
            }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh") } }
    }
}

@Composable
private fun TasksModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    openChat: () -> Unit,
) {
    val conversation by app.commandController.state.collectAsState()
    val operational = conversation.messages.filter { it.status != null && it.role != VanMessageRole.OWNER }
    val queueCount = app.commandQueue.size()

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Tasks", "Real local queue + owner command lifecycle; no fabricated Hermes progress") }
        item {
            AdminCard(glass) {
                Column {
                    Text("Encrypted offline queue", color = Color.White, fontWeight = FontWeight.Bold)
                    Text("$queueCount command(s) currently queued", color = Color(0xFFBCD1D8), fontSize = 12.sp)
                }
            }
        }
        if (operational.isEmpty()) item { TruthMessage("No dispatched owner work is present in this session.") }
        items(operational.reversed(), key = { it.id }) { message ->
            CommandMessageBubble(message, glass)
        }
        item { Button(onClick = openChat) { Text("Send instruction") } }
    }
}

@Composable
private fun ProjectsModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    selectForChat: (String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var projects by remember { mutableStateOf<List<String>?>(null) }
    var truthSummary by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { app.gatewayClient.projects().stringList() }
            .onSuccess { projects = it }
            .onFailure { error = it.message ?: "Unable to load project registry" }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Projects", "Authoritative registry returned by VAN gateway") }
        if (projects == null && error == null) item { TruthMessage("Loading project registry…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (projects?.isEmpty() == true) item { TruthMessage("Gateway returned no registered projects.") }
        items(projects.orEmpty(), key = { it }) { projectId ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(projectId, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    truthSummary[projectId]?.let { Text(it, color = Color(0xFFBCD1D8), fontSize = 10.sp, maxLines = 4) }
                    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                        Button(onClick = { selectForChat(projectId) }) { Text("Select + Chat") }
                        Button(onClick = {
                            scope.launch {
                                runCatching { app.gatewayClient.projectTruth(projectId) }
                                    .onSuccess { obj ->
                                        val summary = if (obj.optBoolean("ok")) {
                                            "Truth ${obj.optString("truth_sha").take(12)} • repo ${obj.optString("repo_sha").take(12)}"
                                        } else {
                                            "Truth unavailable: ${obj.optString("error", obj.optString("degraded", "unknown"))}"
                                        }
                                        truthSummary = truthSummary + (projectId to summary)
                                    }
                                    .onFailure { t -> truthSummary = truthSummary + (projectId to "Truth load failed: ${t.message}") }
                            }
                        }) { Text("Truth") }
                    }
                }
            }
        }
    }
}

@Composable
private fun ActivityModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    var events by remember { mutableStateOf<List<JSONObject>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        if (!app.gatewayClient.isEnrolled()) {
            error = "Device is not enrolled; event replay requires an enrolled device identity."
        } else {
            runCatching { app.gatewayClient.events(0).optJSONArray("events")?.objectList().orEmpty() }
                .onSuccess { events = it }
                .onFailure { error = it.message ?: "Unable to load activity" }
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Activity", "Gateway event replay") }
        if (events == null && error == null) item { TruthMessage("Loading activity…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (events?.isEmpty() == true) item { TruthMessage("No gateway events returned.") }
        items(events.orEmpty(), key = { it.optLong("seq") }) { event ->
            AdminCard(glass) {
                Column {
                    Text(event.optString("event_type", "event"), color = Color.White, fontWeight = FontWeight.Bold)
                    Text(
                        event.optJSONObject("payload")?.toString()?.take(360) ?: "No payload",
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun SystemsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val scope = rememberCoroutineScope()
    var health by remember { mutableStateOf<JSONObject?>(null) }
    var mesh by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching {
                health = app.gatewayClient.health()
                mesh = app.gatewayClient.googleMesh()
            }.onFailure { error = it.message ?: "System health unavailable" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Systems / Hermes", "Live gateway health and Google mesh truth") }
        if (health == null && error == null) item { TruthMessage("Loading system health…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        health?.let { h ->
            item {
                AdminCard(glass) {
                    Column {
                        Text("Gateway / Hermes", color = Color.White, fontWeight = FontWeight.Bold)
                        Text("Overall ok: ${h.optBoolean("ok", false)}", color = Color(0xFFD7E7EC))
                        Text("Degraded: ${h.optJSONArray("degraded")?.toString() ?: h.opt("degraded")?.toString().orEmpty()}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    }
                }
            }
        }
        mesh?.let { m ->
            item {
                AdminCard(glass) {
                    Column {
                        Text("Google mesh", color = Color.White, fontWeight = FontWeight.Bold)
                        Text("Registry: ${m.optString("registry_version", "unknown")}", color = Color(0xFFD7E7EC), fontSize = 11.sp)
                        Text("Principal: ${m.optJSONObject("principal")?.toString()?.take(260) ?: "not returned"}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    }
                }
            }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh systems") } }
    }
}

@Composable
private fun ConnectionsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    var endpointDraft by remember { mutableStateOf(app.gatewayClient.baseUrl) }
    var pairingDraft by remember { mutableStateOf("") }
    var connectionMessage by remember { mutableStateOf<String?>(null) }
    var pairingBusy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Connections", "One-time owner pairing; persistent credentials are encrypted and never displayed") }
        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val paired = app.gatewayClient.isPaired()
                    Text("VAN gateway", color = Color.White, fontWeight = FontWeight.Bold)
                    Text(app.gatewayClient.baseUrl, color = Color(0xFFD7E7EC), fontSize = 12.sp)
                    Text("Paired: $paired", color = Color(0xFFBCD1D8), fontSize = 11.sp)
                    Text("Device: ${app.gatewayClient.deviceId ?: "not enrolled"}", color = Color(0xFFBCD1D8), fontSize = 11.sp)
                    if (!paired) {
                        OutlinedTextField(
                            value = endpointDraft,
                            onValueChange = { endpointDraft = it },
                            label = { Text("HTTPS gateway URL") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        OutlinedTextField(
                            value = pairingDraft,
                            onValueChange = { pairingDraft = it },
                            label = { Text("One-time pairing token") },
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Button(
                            enabled = pairingDraft.trim().length >= 32 && !pairingBusy,
                            onClick = {
                                pairingBusy = true
                                scope.launch {
                                    connectionMessage = runCatching {
                                        app.gatewayClient.pairThisDevice(endpointDraft, pairingDraft)
                                        pairingDraft = ""
                                        "Device paired securely"
                                    }.getOrElse {
                                        "Pairing failed: ${it.message ?: it.javaClass.simpleName}"
                                    }
                                    pairingBusy = false
                                }
                            },
                        ) { Text(if (pairingBusy) "Pairing…" else "Pair this device") }
                    } else {
                        Text(
                            "Ingress, revocable device access, and the command HMAC credential are active.",
                            color = Color(0xFFBCD1D8),
                            fontSize = 11.sp,
                        )
                    }
                    connectionMessage?.let {
                        Text(it, color = Color(0xFFBCD1D8), fontSize = 11.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun SettingsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Settings", "Owner-facing runtime controls") }
        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Floating VAN", color = Color.White, fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { FloatingOverlayService.start(app) }) { Text("Start") }
                        Button(onClick = { FloatingOverlayService.stop(app) }) { Text("Stop") }
                    }
                }
            }
        }
        item {
            TruthMessage("A4 privileged commands remain fail-closed and require the existing biometric approval path. No secret or approval token is displayed here.")
        }
    }
}

@Composable
private fun SectionHeader(title: String, detail: String) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Text(title, color = Color.White, fontSize = 19.sp, fontWeight = FontWeight.Bold)
        Text(detail, color = Color(0xFFBCD1D8), fontSize = 11.sp)
    }
}

@Composable
private fun AdminCard(
    glass: com.dial.van.visual.VanGlassStyle,
    content: @Composable () -> Unit,
) {
    VanGlassSurface(style = glass, modifier = Modifier.fillMaxWidth()) {
        Box(modifier = Modifier.padding(14.dp)) { content() }
    }
}

@Composable
private fun AdminActionCard(
    title: String,
    detail: String,
    glass: com.dial.van.visual.VanGlassStyle,
    onClick: () -> Unit,
) {
    AdminCard(glass) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(title, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                Text(detail, color = Color(0xFFBCD1D8), fontSize = 11.sp)
            }
            Button(onClick = onClick) { Text("Open") }
        }
    }
}

@Composable
private fun TruthMessage(text: String, warning: Boolean = false) {
    Text(
        text,
        color = if (warning) Color(VanGlassTokens.ACCENT_AMBER) else Color(0xFFBCD1D8),
        fontSize = 12.sp,
        modifier = Modifier.padding(vertical = 8.dp),
    )
}

@Composable
private fun CommandMessageBubble(
    message: VanConversationMessage,
    glass: com.dial.van.visual.VanGlassStyle,
) {
    val tint = when (message.role) {
        VanMessageRole.OWNER -> Color(VanGlassTokens.ACCENT_CYAN)
        VanMessageRole.VAN -> Color(VanGlassTokens.BABY_CYAN)
        VanMessageRole.SYSTEM -> Color(VanGlassTokens.ACCENT_AMBER)
    }
    VanGlassSurface(
        style = glass.copy(
            backgroundAlpha = (glass.backgroundAlpha - 0.08f).coerceAtLeast(0.52f),
            contaminationAlpha = 0.08f,
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Text(
                when (message.role) {
                    VanMessageRole.OWNER -> "You"
                    VanMessageRole.VAN -> "Van"
                    VanMessageRole.SYSTEM -> "System"
                },
                color = tint,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(message.text, color = Color(0xFFF4FCFF), fontSize = 12.sp)
            message.status?.let {
                Text(it.name, color = statusColor(it), fontSize = 9.sp)
            }
        }
    }
}

private fun statusColor(status: VanCommandStatus): Color = when (status) {
    VanCommandStatus.SUCCEEDED -> Color(VanGlassTokens.ACCENT_GREEN)
    VanCommandStatus.FAILED,
    VanCommandStatus.CANCELLED,
    VanCommandStatus.EXPIRED,
    -> Color(VanGlassTokens.ACCENT_RED)
    VanCommandStatus.APPROVAL_REQUIRED -> Color(VanGlassTokens.ACCENT_AMBER)
    else -> Color(VanGlassTokens.EDGE_CYAN)
}

private fun JSONArray.objectList(): List<JSONObject> = buildList {
    for (index in 0 until length()) optJSONObject(index)?.let(::add)
}

private fun JSONArray.stringList(): List<String> = buildList {
    for (index in 0 until length()) {
        optString(index).takeIf { it.isNotBlank() }?.let(::add)
    }
}
