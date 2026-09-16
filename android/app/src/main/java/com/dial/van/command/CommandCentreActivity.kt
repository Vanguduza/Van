package com.dial.van.command

import android.os.Bundle
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.degraded.RestoreAction
import com.dial.van.degraded.SubsystemStatus
import com.dial.van.overlay.FloatingOverlayService
import com.dial.van.queue.CommandKind
import com.dial.van.queue.CommandSensitivity
import com.dial.van.queue.QueueEnqueueRequest
import com.dial.van.security.BiometricGate
import com.dial.van.visual.VanCaptions
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanGlassSurface
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanStatusPalette
import com.dial.van.visual.rememberVanEffectBudget
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Command Centre.
 *
 * §14 of `docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md` governs this surface: glass stays
 * the top-level material language, panels are more opaque than the floating compact shell, Van
 * remains present without dominating operational content, and critical actions switch from
 * translucent to solid controls.
 */
class CommandCentreActivity : FragmentActivity() {

    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication

        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Color(VanGlassTokens.ACCENT_CYAN))) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        // §10 step 1: the app background the glass samples against.
                        .background(
                            Brush.verticalGradient(
                                listOf(Color(0xFF060A14), Color(0xFF0B1424), Color(0xFF04070F)),
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
                        CommandCentreScreen(
                            padding = padding,
                            app = app,
                            onA4Approve = { gate, onDone ->
                                gate.requestA4Approval(onApproved = onDone, onDenied = { })
                            },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun CommandCentreScreen(
    padding: PaddingValues,
    app: VanApplication,
    onA4Approve: (BiometricGate, () -> Unit) -> Unit,
) {
    val activity = LocalContext.current as FragmentActivity
    val gate = remember(activity) { BiometricGate(activity) }
    var meshSummary by remember { mutableStateOf("Google mesh: awaiting gateway evidence") }
    var statusMessage by remember { mutableStateOf("") }
    var sections by remember { mutableStateOf(commandSections(app, meshSummary, VanPresence.cue(app.degradedModeStore.snapshot()))) }

    LaunchedEffect(Unit) {
        try {
            val health = withContext(Dispatchers.IO) { app.gatewayClient.health() }
            val mesh = health.optJSONObject("google_mesh")
            val configured = mesh?.optInt("configured_capabilities") ?: 0
            val total = mesh?.optInt("total_capabilities") ?: 0
            val principal = mesh?.optJSONObject("principal")?.optBoolean("registered") == true
            app.degradedModeStore.applyGoogleMesh(configured, total, principal)
            if (!health.optBoolean("ok", false)) {
                app.degradedModeStore.markBroken("hermes", "Hermes offline from /health", RestoreAction.RETRY_CONNECTION)
            } else {
                app.degradedModeStore.markWorking("hermes")
                app.degradedModeStore.markWorking("gateway")
            }
            meshSummary = "Google mesh configured=$configured/$total principal=${if (principal) "registered" else "missing"}"
        } catch (exc: Exception) {
            app.degradedModeStore.markBroken("gateway", "health unreachable: ${exc.message}", RestoreAction.RETRY_CONNECTION)
            meshSummary = "Google mesh: gateway unreachable"
        }
        sections = commandSections(app, meshSummary, VanPresence.cue(app.degradedModeStore.snapshot()))
    }

    val degraded = app.degradedModeStore.snapshot()
    val cue = VanPresence.cue(degraded)
    val budget = rememberVanEffectBudget()
    val panelGlass = VanGlassTokens.forState(
        state = cue.durableState,
        panel = true,
        liveBlurAvailable = false,
        budget = budget,
    )

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(padding)
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        contentPadding = PaddingValues(vertical = 12.dp),
    ) {
        item {
            VanHeroPanel(
                app = app,
                glass = panelGlass,
                budget = budget,
                cue = cue,
                meshCue = VanPresence.meshCue(degraded),
            )
        }
        items(sections) { section ->
            CommandSectionPanel(section = section, glass = panelGlass)
        }
        item {
            // Non-destructive control: translucent glass is fine here.
            Button(
                onClick = { FloatingOverlayService.start(app) },
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color(VanGlassTokens.ACCENT_CYAN).copy(alpha = 0.18f),
                    contentColor = Color(VanGlassTokens.EDGE_CYAN),
                ),
                shape = RoundedCornerShape(VanGlassTokens.CORNER_RADIUS_DP.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Start floating Van")
            }
        }
        item {
            // §14: critical actions switch from translucent to solid controls.
            Button(
                onClick = {
                    onA4Approve(gate) {
                        app.commandQueue.enqueue(
                            QueueEnqueueRequest(
                                kind = CommandKind.HERMES_DISPATCH,
                                payloadJson = Json.encodeToString(
                                    buildJsonObject { put("action", "owner_approved_a4") },
                                ),
                                sensitivity = CommandSensitivity.DESTRUCTIVE,
                            ),
                        )
                        statusMessage = "A4 action queued with biometric approval"
                    }
                },
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color(VanGlassTokens.ACCENT_AMBER),
                    contentColor = Color(0xFF10151F),
                ),
                shape = RoundedCornerShape(VanGlassTokens.CORNER_RADIUS_DP.dp),
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                Text("Approve A4 action (biometric)", fontWeight = FontWeight.Bold)
            }
        }
        if (statusMessage.isNotEmpty()) {
            item { Text(statusMessage, color = Color(0xFFB6C2D0), fontSize = 12.sp) }
        }
    }
}

/** Hero panel: Van present and expressive, but sized so operational content still leads. */
@Composable
private fun VanHeroPanel(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    budget: com.dial.van.visual.VanEffectBudget,
    cue: VanPresence.Cue,
    meshCue: String,
) {
    val palette = VanStatusPalette.forState(cue.durableState)
    VanGlassSurface(style = glass, modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            VanEmbodiment(
                state = VanPresence.visualState(cue),
                budget = budget,
                presentation = VanPresentation.EXPANDED,
                modifier = Modifier.size(112.dp),
            )
            Spacer(modifier = Modifier.size(12.dp))
            Column {
                Text("Van", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text(
                    text = cue.headline,
                    color = Color(palette.accent),
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = VanCaptions.forState(cue.durableState),
                    color = Color(0xFFD5DEE8),
                    fontSize = 12.sp,
                )
                Spacer(modifier = Modifier.height(6.dp))
                Text(text = cue.detail, color = Color(0xFF9AA7B6), fontSize = 11.sp)
                Text(text = meshCue, color = Color(0xFF8A97A6), fontSize = 11.sp)
            }
        }
    }
}

private data class CommandSection(
    val id: String,
    val title: String,
    val summary: String,
    val items: List<String>,
    /** Degraded/attention panels get amber emphasis and higher contrast copy (§6, §12). */
    val alert: Boolean = false,
)

private fun commandSections(app: VanApplication, meshSummary: String, cue: VanPresence.Cue): List<CommandSection> {
    val queueSize = app.commandQueue.size()
    val degraded = app.degradedModeStore.snapshot()
    val attentionItems = buildList {
        if (degraded.active) {
            add(degraded.reason)
            degraded.subsystems.filter { it.status != SubsystemStatus.WORKING }.forEach { sub ->
                add("${sub.label}: ${sub.status} — ${sub.detail}")
            }
        } else {
            add("No attention items")
        }
    }
    return listOf(
        CommandSection(
            "mission",
            "State / Mission",
            cue.headline,
            listOf(VanCaptions.forState(cue.durableState), cue.detail),
        ),
        CommandSection(
            "attention",
            "Attention",
            if (degraded.active) "Owner focus required" else "Nothing waiting on you",
            attentionItems,
            alert = degraded.active,
        ),
        CommandSection("decisions", "Decisions", "Open decisions awaiting input", listOf("No pending decisions")),
        CommandSection("tasks", "Tasks", "Actionable work", listOf("$queueSize queued commands")),
        CommandSection("projects", "Projects", "Mounted Project Truth registries", listOf("Synced from registries/projects.json")),
        CommandSection(
            "connections",
            "Connections",
            "Device + Hermes uplink",
            listOf("Hermes profile: van", meshSummary),
        ),
    )
}

/** §14: structured glass cards for project status, commands, approvals and tool output. */
@Composable
private fun CommandSectionPanel(
    section: CommandSection,
    glass: com.dial.van.visual.VanGlassStyle,
) {
    val style = if (section.alert) {
        glass.copy(
            borderColor = VanGlassTokens.ACCENT_AMBER,
            borderAlpha = 0.42f,
            backgroundAlpha = (glass.backgroundAlpha + 0.06f).coerceAtMost(0.97f),
        )
    } else {
        glass
    }
    VanGlassSurface(style = style, modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = section.title,
                color = Color.White,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = section.summary,
                // §12: text never relies on translucency alone for legibility.
                color = if (section.alert) Color(VanGlassTokens.ACCENT_AMBER) else Color(0xFF9AA7B6),
                fontSize = 12.sp,
                modifier = Modifier.padding(bottom = 8.dp),
            )
            section.items.forEach { item ->
                Text(text = "• $item", color = Color(0xFFD5DEE8), fontSize = 13.sp)
            }
        }
    }
}

/** Kept for reference by tests: the durable state whose panels must be solid. */
internal val SOLID_CONTROL_STATES = setOf(
    VanDurableState.WAITING_FOR_OWNER,
    VanDurableState.URGENT,
    VanDurableState.WARNING,
    VanDurableState.ERROR,
)
