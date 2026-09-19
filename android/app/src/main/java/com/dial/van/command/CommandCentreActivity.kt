package com.dial.van.command

import android.os.Bundle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
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
import com.dial.van.events.EventPage
import com.dial.van.events.EventRecord
import com.dial.van.events.EventStream
import com.dial.van.events.EventStreamState
import com.dial.van.events.PreferencesEventCursorStore
import com.dial.van.status.OwnerOverview
import com.dial.van.status.VanCommandStatus
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
import kotlinx.coroutines.delay
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
    BROWSER_AUTOMATION("browser_automation", "Browser & Automation"),
    BROWSER_TASKS("browser_tasks", "Browser Tasks"),
    BROWSER_ESCALATIONS("browser_escalations", "Browser Escalations"),
    BROWSER_SESSIONS("browser_sessions", "Browser Sessions"),
    BROWSER_POLICY("browser_policy", "Browser Policy"),
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

    fun navigate(module: CommandModule) {
        selected = module
    }

    BackHandler(enabled = selected != CommandModule.OVERVIEW) {
        selected = when (selected) {
            CommandModule.BROWSER_TASKS,
            CommandModule.BROWSER_ESCALATIONS,
            CommandModule.BROWSER_SESSIONS,
            CommandModule.BROWSER_POLICY,
            -> CommandModule.BROWSER_AUTOMATION
            else -> CommandModule.OVERVIEW
        }
    }

    val primaryModules = listOf(
        CommandModule.OVERVIEW,
        CommandModule.CHAT,
        CommandModule.TASKS,
        CommandModule.ACTIVITY,
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(padding),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            primaryModules.forEach { module ->
                val isSelected = selected == module
                Button(
                    onClick = { navigate(module) },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isSelected) {
                            Color(VanGlassTokens.BABY_CYAN).copy(alpha = 0.24f)
                        } else {
                            Color(VanGlassTokens.TINT_NAVY).copy(alpha = 0.72f)
                        },
                        contentColor = if (isSelected) Color(VanGlassTokens.ICE_CYAN) else Color(0xFFBCD1D8),
                    ),
                    shape = RoundedCornerShape(10.dp),
                    contentPadding = PaddingValues(horizontal = 5.dp, vertical = 5.dp),
                ) {
                    Text(module.title, fontSize = 10.sp, maxLines = 1)
                }
            }
        }

        when (selected) {
            CommandModule.OVERVIEW -> OverviewModule(app, glass, ::navigate)
            CommandModule.CHAT -> ChatModule(app, glass)
            CommandModule.DECISIONS -> DecisionsModule(app, glass)
            CommandModule.TASKS -> TasksModule(app, glass) { navigate(CommandModule.CHAT) }
            CommandModule.PROJECTS -> ProjectsModule(app, glass) { projectId ->
                app.commandController.selectProject(projectId)
                navigate(CommandModule.CHAT)
            }
            CommandModule.ACTIVITY -> ActivityModule(app, glass)
            CommandModule.BROWSER_AUTOMATION -> BrowserAutomationModule(app, glass, ::navigate)
            CommandModule.BROWSER_TASKS -> BrowserTasksPage(app, glass) { navigate(CommandModule.BROWSER_AUTOMATION) }
            CommandModule.BROWSER_ESCALATIONS -> BrowserEscalationsPage(app, glass) { navigate(CommandModule.BROWSER_AUTOMATION) }
            CommandModule.BROWSER_SESSIONS -> BrowserSessionsPage(app, glass) { navigate(CommandModule.BROWSER_AUTOMATION) }
            CommandModule.BROWSER_POLICY -> BrowserPolicyPage(app, glass) { navigate(CommandModule.BROWSER_AUTOMATION) }
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
    // P3-AND-003 — attention() and briefing() were declared on the client and called by
    // nothing: the gateway maintained an attention queue and built a briefing, and the app
    // had no surface that read either. This is the surface.
    var overview by remember {
        mutableStateOf(OwnerOverview.summarize(null, null, error = "not loaded yet"))
    }
    val context = LocalContext.current

    LaunchedEffect(Unit) {
        runCatching {
            health = app.gatewayClient.health()
            decisions = app.gatewayClient.decisions().length()
            projects = app.gatewayClient.projects().length()
        }.onFailure { error = it.message ?: "Gateway unavailable" }
        runCatching {
            OwnerOverview.summarize(app.gatewayClient.attention(), app.gatewayClient.briefing())
        }.onSuccess { overview = it }
            .onFailure {
                // "Nothing is waiting for you" is a claim about the world and VAN has not
                // looked, so the failure is reported rather than rendered as calm.
                overview = OwnerOverview.summarize(
                    null, null, error = it.message ?: "Gateway unavailable",
                )
            }
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
                Column {
                    Text(
                        overview.headline,
                        color = if (overview.waitingCount > 0) {
                            Color(VanGlassTokens.ACCENT_AMBER)
                        } else {
                            Color.White
                        },
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    overview.briefingLine?.let { line ->
                        Text(line, color = Color(0xFFBCD1D8), fontSize = 12.sp)
                    }
                    overview.items.take(4).forEach { item ->
                        Text(
                            "${if (item.needsOwner) "•" else "·"} ${item.title}",
                            color = if (item.needsOwner) Color.White else Color(0xFF9AA7B6),
                            fontSize = 12.sp,
                        )
                    }
                    overview.error?.let { reason ->
                        Text(reason, color = Color(VanGlassTokens.ACCENT_AMBER), fontSize = 11.sp)
                    }
                }
            }
        }
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
            AdminActionCard(
                "Browser & Automation",
                "Runtime summary, owner escalations, browser tasks, managed sessions and governed policy",
                glass,
            ) { navigate(CommandModule.BROWSER_AUTOMATION) }
        }
        item {
            AdminActionCard("Systems", "Hermes, gateway and Google mesh health", glass) { navigate(CommandModule.SYSTEMS) }
        }
        item {
            AdminActionCard("Connections", "Gateway enrollment, device pairing and secure transport state", glass) { navigate(CommandModule.CONNECTIONS) }
        }
        item {
            AdminActionCard("Settings", "Floating VAN and owner-facing runtime controls", glass) { navigate(CommandModule.SETTINGS) }
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
    val activity = LocalContext.current as? FragmentActivity

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
        state.pendingA4Approval?.let { pending ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        "Owner approval required",
                        color = Color(VanGlassTokens.ACCENT_AMBER),
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        pending.resolvedActionId,
                        color = Color.White,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "This action is A4. Approval signs the gateway-issued one-time challenge with the paired device key after BIOMETRIC_STRONG authentication.",
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                    Button(
                        enabled = activity != null && !state.submitting,
                        onClick = { activity?.let { app.commandController.approvePendingA4(it) } },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF6D4514)),
                    ) {
                        Text("Approve A4 action")
                    }
                    if (activity == null) {
                        Text(
                            "Biometric approval is unavailable on this surface.",
                            color = Color(VanGlassTokens.ACCENT_AMBER),
                            fontSize = 10.sp,
                        )
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
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

/**
 * P3-AND-002 — the event stream, actually streamed.
 *
 * This was a single `events(0)` in the initial composition with a hardcoded cursor. Anything
 * the gateway published afterwards never reached the screen. It now restores a persisted
 * cursor, polls continuously, catches up immediately on a truncated page and backs off on
 * failure — all decided by [EventStream], which is pure and tested on the JVM.
 */
@Composable
private fun ActivityModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val context = LocalContext.current
    val cursorStore = remember(context) { PreferencesEventCursorStore(context) }
    var stream by remember { mutableStateOf(EventStreamState(cursor = cursorStore.load())) }
    val events = if (stream.loaded) stream.events else null
    val error = stream.error
        ?: if (!app.gatewayClient.isEnrolled()) {
            "Device is not enrolled; event replay requires an enrolled device identity."
        } else {
            null
        }

    LaunchedEffect(Unit) {
        if (!app.gatewayClient.isEnrolled()) return@LaunchedEffect
        while (true) {
            var truncated = false
            runCatching { app.gatewayClient.events(stream.cursor) }
                .onSuccess { body ->
                    val page = EventPage(
                        events = body.optJSONArray("events")?.objectList().orEmpty().map {
                            EventRecord(
                                seq = it.optLong("seq"),
                                type = it.optString("event_type", "event"),
                                payloadJson = it.optJSONObject("payload")?.toString() ?: "",
                                createdAtUnix = it.optLong("created_at_unix"),
                            )
                        },
                        nextCursor = body.optLong("next_cursor", stream.cursor),
                        truncated = body.optBoolean("truncated", false),
                    )
                    truncated = page.truncated
                    stream = EventStream.applyPage(stream, page)
                    cursorStore.save(stream.cursor)
                }
                .onFailure { failure ->
                    stream = EventStream.applyFailure(
                        stream, failure.message ?: "Unable to load activity",
                    )
                }
            delay(EventStream.nextDelayMillis(stream, truncated))
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
        items(events.orEmpty(), key = { it.seq }) { event ->
            AdminCard(glass) {
                Column {
                    Text(event.type, color = Color.White, fontWeight = FontWeight.Bold)
                    Text(
                        event.payloadJson.take(360).ifEmpty { "No payload" },
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun BrowserAutomationModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    navigate: (CommandModule) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf<JSONObject?>(null) }
    var tasks by remember { mutableStateOf<List<JSONObject>?>(null) }
    var escalations by remember { mutableStateOf<List<JSONObject>?>(null) }
    var policy by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching {
                status = app.gatewayClient.browserStatus()
                tasks = app.gatewayClient.browserTasks().objectList()
                escalations = app.gatewayClient.browserEscalations().objectList()
                policy = app.gatewayClient.browserPolicy()
                error = null
            }.onFailure { error = it.message ?: "Browser/automation truth unavailable" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item {
            SectionHeader(
                "Browser & Automation",
                "Summary dashboard. Open a card for the full operational page.",
            )
        }
        if (status == null && error == null) item { TruthMessage("Loading browser and automation state…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }

        status?.let { s ->
            item {
                AdminCard(glass) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Runtime overview", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                        Text(
                            "Browser ${if (s.optBoolean("enabled")) "enabled" else "disabled"} • worker ${if (s.optBoolean("worker_configured")) "configured" else "not configured"}",
                            color = Color(0xFFD7E7EC),
                            fontSize = 11.sp,
                        )
                        Text(
                            "${s.optInt("waiting_for_owner")} waiting for owner • ${s.optInt("admitted_automation_capabilities")} admitted automations",
                            color = Color(VanGlassTokens.EDGE_CYAN),
                            fontSize = 11.sp,
                        )
                    }
                }
            }
        }

        item {
            AdminActionCard(
                "Owner escalations",
                escalations?.let { rows ->
                    val open = rows.count { it.optString("decision_status", it.optString("status")) == "OPEN" }
                    "$open awaiting owner decision • ${rows.size} returned"
                } ?: "Loading escalation summary…",
                glass,
            ) { navigate(CommandModule.BROWSER_ESCALATIONS) }
        }
        item {
            AdminActionCard(
                "Browser tasks & evidence",
                tasks?.let { rows ->
                    val waiting = rows.count { it.optString("status") == "WAITING_FOR_OWNER" }
                    "${rows.size} active/recent task(s) • $waiting resumably waiting"
                } ?: "Loading task summary…",
                glass,
            ) { navigate(CommandModule.BROWSER_TASKS) }
        }
        item {
            val profiles = status?.optJSONArray("profiles")?.objectList().orEmpty()
            AdminActionCard(
                "Sessions & profiles",
                if (status == null) "Loading managed browser profiles…" else {
                    val active = profiles.count { !it.isNull("lease_holder") }
                    "${profiles.size} managed profile(s) • $active active lease(s)"
                },
                glass,
            ) { navigate(CommandModule.BROWSER_SESSIONS) }
        }
        item {
            AdminActionCard(
                "Policy & capabilities",
                policy?.let {
                    "Policy ${it.optString("policy_version", "unknown")} • max autonomy ${it.optString("max_autonomy_tier", "unknown")}"
                } ?: "Loading authority policy…",
                glass,
            ) { navigate(CommandModule.BROWSER_POLICY) }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh summary") } }
    }
}

@Composable
private fun BrowserEscalationsPage(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    back: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var escalations by remember { mutableStateOf<List<JSONObject>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var resolving by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching { app.gatewayClient.browserEscalations().objectList() }
                .onSuccess { escalations = it; error = null }
                .onFailure { error = it.message ?: "Unable to load browser escalations" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { DashboardPageHeader("Owner escalations", "Browser & Automation", back) }
        if (escalations == null && error == null) item { TruthMessage("Loading owner escalations…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (escalations?.isEmpty() == true) item { TruthMessage("No browser escalation is waiting for owner action.") }
        items(escalations.orEmpty(), key = { it.optString("escalation_id") }) { esc ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    val decisionId = esc.optString("decision_id")
                    val decisionStatus = esc.optString("decision_status", esc.optString("status"))
                    Text(esc.optString("summary", "Browser boundary escalation"), color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text("Reason: ${esc.optString("reason_code")} • $decisionStatus", color = Color(VanGlassTokens.ACCENT_AMBER), fontSize = 11.sp)
                    Text(esc.optString("why_required"), color = Color(0xFFD7E7EC), fontSize = 11.sp)
                    Text("Current: ${esc.optString("current_scope_json").take(300)}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    Text("Requested extension: ${esc.optString("requested_scope_delta_json").take(300)}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    if (decisionStatus == "OPEN" && decisionId.isNotBlank()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                enabled = resolving == null,
                                onClick = {
                                    resolving = decisionId
                                    scope.launch {
                                        runCatching { app.gatewayClient.resolveDecision(decisionId, true) }.onFailure { error = it.message }
                                        resolving = null
                                        refresh()
                                    }
                                },
                            ) { Text(if (resolving == decisionId) "Applying…" else "Approve scope") }
                            Button(
                                enabled = resolving == null,
                                onClick = {
                                    resolving = decisionId
                                    scope.launch {
                                        runCatching { app.gatewayClient.resolveDecision(decisionId, false) }.onFailure { error = it.message }
                                        resolving = null
                                        refresh()
                                    }
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF5B2730)),
                            ) { Text("Reject") }
                        }
                        Button(
                            onClick = {
                                val taskId = esc.optString("task_id")
                                val reason = esc.optString("reason_code")
                                app.commandController.submitText(
                                    "Replan browser task $taskId without crossing the blocked boundary $reason. Preserve completed evidence and propose the safest authorized alternative.",
                                    VanCommandSource.CHAT,
                                )
                            },
                        ) { Text("Ask VAN to replan") }
                    }
                }
            }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh escalations") } }
    }
}

@Composable
private fun BrowserTasksPage(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    back: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var tasks by remember { mutableStateOf<List<JSONObject>?>(null) }
    var evidenceByTask by remember { mutableStateOf<Map<String, List<JSONObject>>>(emptyMap()) }
    var error by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching { app.gatewayClient.browserTasks().objectList() }
                .onSuccess { tasks = it; error = null }
                .onFailure { error = it.message ?: "Unable to load browser tasks" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { DashboardPageHeader("Browser tasks & evidence", "Browser & Automation", back) }
        if (tasks == null && error == null) item { TruthMessage("Loading browser tasks…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (tasks?.isEmpty() == true) item { TruthMessage("No browser tasks returned by the gateway.") }
        items(tasks.orEmpty(), key = { it.optString("task_id") }) { task ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(task.optString("goal", "Browser task"), color = Color.White, fontWeight = FontWeight.Bold)
                    Text(
                        "${task.optString("status")} • ${task.optString("strategy")} • ${task.optString("autonomy_tier")}",
                        color = if (task.optString("status") == "WAITING_FOR_OWNER") Color(VanGlassTokens.ACCENT_AMBER) else Color(0xFFD7E7EC),
                        fontSize = 11.sp,
                    )
                    Text("${task.optString("target_domain")} • ${task.optString("action_class")}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    task.optString("error_code").takeIf { it.isNotBlank() }?.let {
                        Text("State reason: $it", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    }
                    val taskId = task.optString("task_id")
                    Button(
                        onClick = {
                            scope.launch {
                                runCatching { app.gatewayClient.browserEvidence(taskId).objectList() }
                                    .onSuccess { records -> evidenceByTask = evidenceByTask + (taskId to records) }
                                    .onFailure { error = it.message }
                            }
                        },
                    ) { Text("Open evidence") }
                    evidenceByTask[taskId]?.let { records ->
                        Text("${records.size} evidence receipt(s)", color = Color(VanGlassTokens.EDGE_CYAN), fontSize = 10.sp)
                        records.takeLast(8).forEach { evidence ->
                            Text(
                                "${evidence.optString("kind")} • ${evidence.optString("source_trust")} • ${evidence.optString("injection_assessment")}",
                                color = Color(0xFFBCD1D8),
                                fontSize = 9.sp,
                            )
                        }
                    }
                }
            }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh tasks") } }
    }
}

@Composable
private fun BrowserSessionsPage(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    back: () -> Unit,
) {
    var status by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { app.gatewayClient.browserStatus() }
            .onSuccess { status = it; error = null }
            .onFailure { error = it.message ?: "Unable to load browser sessions" }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { DashboardPageHeader("Sessions & profiles", "Browser & Automation", back) }
        if (status == null && error == null) item { TruthMessage("Loading managed browser profiles…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        val profiles = status?.optJSONArray("profiles")?.objectList().orEmpty()
        if (status != null && profiles.isEmpty()) item { TruthMessage("No managed browser profiles returned.") }
        items(profiles, key = { it.optString("profile_alias") }) { profile ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(profile.optString("profile_alias"), color = Color.White, fontWeight = FontWeight.Bold)
                    Text(
                        "${profile.optString("persistence")} • ${profile.optString("authentication")} • ${profile.optString("mutation_policy")}",
                        color = Color(0xFFD7E7EC),
                        fontSize = 11.sp,
                    )
                    Text(
                        if (profile.isNull("lease_holder")) "No active lease" else "Active managed lease",
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                }
            }
        }
        item {
            TruthMessage("Managed aliases only. Raw cookies, credentials and provider tokens are never displayed.")
        }
    }
}

@Composable
private fun BrowserPolicyPage(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    back: () -> Unit,
) {
    var policy by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { app.gatewayClient.browserPolicy() }
            .onSuccess { policy = it; error = null }
            .onFailure { error = it.message ?: "Unable to load browser policy" }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { DashboardPageHeader("Policy & capabilities", "Browser & Automation", back) }
        if (policy == null && error == null) item { TruthMessage("Loading browser policy…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        policy?.let { p ->
            item {
                AdminCard(glass) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Browser policy ${p.optString("policy_version")}", color = Color.White, fontWeight = FontWeight.Bold)
                        Text("Max autonomy: ${p.optString("max_autonomy_tier")}", color = Color(0xFFD7E7EC), fontSize = 11.sp)
                        Text("Session leases required: ${p.optBoolean("session_leases_required")}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                        Text("Mutation default deny: ${p.optBoolean("mutation_default_deny")}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                        Text("Download default deny: ${p.optBoolean("download_default_deny")}", color = Color(0xFFBCD1D8), fontSize = 10.sp)
                    }
                }
            }
            item {
                AdminCard(glass) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Admitted domains", color = Color.White, fontWeight = FontWeight.Bold)
                        p.optJSONArray("admitted_domains")?.stringList().orEmpty().forEach {
                            Text("• $it", color = Color(0xFFD7E7EC), fontSize = 11.sp)
                        }
                    }
                }
            }
            item {
                AdminCard(glass) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Hard prohibitions", color = Color(VanGlassTokens.ACCENT_AMBER), fontWeight = FontWeight.Bold)
                        p.optJSONArray("hard_prohibitions")?.stringList().orEmpty().forEach {
                            Text("• $it", color = Color(0xFFD7E7EC), fontSize = 11.sp)
                        }
                    }
                }
            }
        }
        item { TruthMessage("This page is read-only. Policy changes remain governed VAN actions, not local toggles.") }
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
private fun DashboardPageHeader(
    title: String,
    parent: String,
    back: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(vertical = 4.dp)) {
        Button(
            onClick = back,
            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color(VanGlassTokens.TINT_NAVY).copy(alpha = 0.72f)),
        ) {
            Text("← $parent", fontSize = 10.sp)
        }
        Text(title, color = Color.White, fontSize = 19.sp, fontWeight = FontWeight.Bold)
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

/**
 * Exhaustive on purpose (P0-EXEC-003). The `else` branch this replaces painted every
 * status it did not name in the working colour, so an unknown or unverified outcome looked
 * to the owner exactly like one under way.
 */
private fun statusColor(status: VanCommandStatus): Color = when (status) {
    VanCommandStatus.SUCCEEDED -> Color(VanGlassTokens.ACCENT_GREEN)
    VanCommandStatus.FAILED,
    VanCommandStatus.CANCELLED,
    VanCommandStatus.EXPIRED,
    VanCommandStatus.REFUSED,
    -> Color(VanGlassTokens.ACCENT_RED)
    // Finished, but not cleanly. Amber is the colour that asks the owner to look.
    VanCommandStatus.PARTIALLY_SUCCEEDED,
    VanCommandStatus.COULD_NOT_VERIFY,
    VanCommandStatus.APPROVAL_REQUIRED,
    VanCommandStatus.UNKNOWN,
    -> Color(VanGlassTokens.ACCENT_AMBER)
    VanCommandStatus.LOCAL_DRAFT,
    VanCommandStatus.SUBMITTING,
    VanCommandStatus.ACCEPTED,
    VanCommandStatus.IN_FLIGHT,
    -> Color(VanGlassTokens.EDGE_CYAN)
}

private fun JSONArray.objectList(): List<JSONObject> = buildList {
    for (index in 0 until length()) optJSONObject(index)?.let(::add)
}

private fun JSONArray.stringList(): List<String> = buildList {
    for (index in 0 until length()) {
        optString(index).takeIf { it.isNotBlank() }?.let(::add)
    }
}
