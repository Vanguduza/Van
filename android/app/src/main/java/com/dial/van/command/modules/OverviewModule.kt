package com.dial.van.command.modules

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminActionCard
import com.dial.van.command.AdminCard
import com.dial.van.command.CommandModule
import com.dial.van.command.TruthMessage
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.dial.van.command.DegradedPanel
import com.dial.van.degraded.DeviceSignals
import com.dial.van.status.OwnerOverview
import com.dial.van.trading.TradingCommandCentreActivity
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.rememberVanEffectBudget
import org.json.JSONObject

/** The Command Centre's home screen. Split out of `CommandCentreActivity` (P3-AND-009). */

@Composable
internal fun OverviewModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    navigate: (CommandModule) -> Unit,
) {
    var health by remember { mutableStateOf<JSONObject?>(null) }
    var decisions by remember { mutableStateOf<Int?>(null) }
    var projects by remember { mutableStateOf<Int?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var unfixable by remember { mutableStateOf<String?>(null) }
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
    // P3-AND-004 — re-read on every resume. A permission the owner revoked while VAN was in
    // the background is exactly the case the old hardcoded-healthy list could not report.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) app.refreshSubsystemHealth()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
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
                            if (health?.optBoolean("ok") == true) "VAN can reach its own machine" else "VAN cannot confirm it can reach its own machine",
                            color = if (health?.optBoolean("ok") == true) Color(VanGlassTokens.ACCENT_GREEN) else Color(VanGlassTokens.ACCENT_AMBER),
                            fontSize = 11.sp,
                        )
                    }
                }
            }
        }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        // P3-AND-005 — the restore actions the contract carried and no screen rendered.
        item {
            DegradedPanel(degraded.subsystems, glass) { subsystem ->
                if (!DeviceSignals.perform(context, app, subsystem)) {
                    // CONTACT_SUPPORT has nothing behind it by design, and a button that
                    // silently does nothing is worse than one that says so.
                    unfixable = subsystem.label
                }
                app.refreshSubsystemHealth()
            }
        }
        unfixable?.let { label ->
            item {
                TruthMessage(
                    "\"$label\" is not something VAN can fix from this phone.",
                    warning = true,
                )
            }
        }
        item {
            AdminActionCard("Chat", "Tell VAN what you want done", glass) { navigate(CommandModule.CHAT) }
        }
        item {
            AdminActionCard(
                "Waiting on you",
                decisions?.let { count ->
                    if (count == 1) "1 thing is waiting on you" else "$count things are waiting on you"
                } ?: "Checking…",
                glass,
            ) { navigate(CommandModule.DECISIONS) }
        }
        item {
            AdminActionCard(
                "Projects",
                projects?.let { count ->
                    if (count == 1) "1 project VAN knows about" else "$count projects VAN knows about"
                } ?: "Checking…",
                glass,
            ) { navigate(CommandModule.PROJECTS) }
        }
        item {
            AdminActionCard("Tasks", "What VAN is doing and what is queued", glass) { navigate(CommandModule.TASKS) }
        }
        item {
            AdminActionCard(
                "Browser & Automation",
                "What VAN is doing on the web, and what it is allowed to do",
                glass,
            ) { navigate(CommandModule.BROWSER_AUTOMATION) }
        }
        item {
            AdminActionCard("Systems", "Whether VAN's own machine and services are working", glass) { navigate(CommandModule.SYSTEMS) }
        }
        item {
            AdminActionCard("Connections", "How this phone is paired with VAN", glass) { navigate(CommandModule.CONNECTIONS) }
        }
        item {
            AdminActionCard("Settings", "The floating assistant and what it may do", glass) { navigate(CommandModule.SETTINGS) }
        }
        item {
            AdminActionCard("Trading", "Your accounts, trades and risk — read only", glass) {
                context.startActivity(TradingCommandCentreActivity.intent(context))
            }
        }
    }
}
