package com.dial.van.command.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
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
import androidx.compose.ui.unit.dp
import com.dial.van.VanApplication
import com.dial.van.command.objectList
import com.dial.van.design.AttentionSeverity
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenState
import com.dial.van.design.ScreenStateMerge
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.LiveBadge
import com.dial.van.design.components.LiveBadgeState
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.mission.MissionRepository
import com.dial.van.mission.MissionSummary
import com.dial.van.status.OwnerOverview
import com.dial.van.status.OwnerOverviewSummary
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.rememberVanEffectBudget
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.Calendar

/**
 * DNA §4 destination 1: Home — "embodiment, VAN's current state sentence, attention now (top
 * 3), active work, significant trade state, upcoming, recent change."
 *
 * Every panel below carries its own `@DataSource` — this is a dashboard of independent reads,
 * not one screen-state: a trading endpoint this build's backend does not yet serve must not
 * blank the rest of Home, and the panels each declare that on their own function.
 */
private data class HomeData(
    val overview: OwnerOverviewSummary,
    val activeMissions: List<MissionSummary>,
    val waitingMissions: List<MissionSummary>,
    val remindersDueToday: List<JSONObject>,
)

@Composable
fun HomeRoute(
    app: VanApplication,
    onOpenAttention: () -> Unit,
    onOpenWork: () -> Unit,
    onOpenTrading: () -> Unit,
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<HomeData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    val degradedMode by app.degradedModeStore.state.collectAsState()

    fun load() {
        scope.launch {
            loading = true
            runCatching {
                val repository = MissionRepository(app.gatewayClient)
                val snapshot = repository.home()
                // P3-AND-003 — the two capabilities that existed end to end apart from the
                // last ten lines: the gateway builds an attention queue and a briefing, and
                // OwnerOverview is the one place their JSON becomes what a home screen says
                // about them ("nothing is waiting" is never the same sentence as "VAN could
                // not reach the gateway").
                val attentionJson = app.gatewayClient.attention()
                val briefingJson = runCatching { app.gatewayClient.briefing() }.getOrNull()
                val overview = OwnerOverview.summarize(attentionJson, briefingJson)
                val reminders = app.gatewayClient.reminders().objectList().filter { isDueToday(it.optLong("due_at_unix")) }
                HomeData(
                    overview = overview,
                    activeMissions = snapshot.activeMissions,
                    waitingMissions = snapshot.waitingMissions,
                    remindersDueToday = reminders,
                )
            }.onSuccess { data = it; error = null; loading = false }
                .onFailure { error = it.message ?: "VAN could not reach its own gateway."; loading = false }
        }
    }
    LaunchedEffect(Unit) { load() }

    val state: ScreenState<HomeData> = ScreenStateMerge.merge(
        content = data,
        loading = loading,
        errorMessage = error,
        degradedSubsystems = degradedMode.subsystems.filter { it.status.name != "WORKING" }.map { it.id },
        emptySentence = "Nothing needs you right now.",
    )

    VanScreen(state = state, onRetry = ::load) { home ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
            contentPadding = PaddingValues(vertical = tokens.space.space3),
        ) {
            item { EmbodimentPanel(app) }
            item { AttentionNowPanel(home.overview, onOpenAttention) }
            item { ActiveWorkPanel(home.activeMissions, home.waitingMissions, onOpenWork) }
            item { SignificantTradePanel(app, onOpenTrading) }
            item { UpcomingPanel(home.remindersDueToday) }
            item { RecentChangePanel(app) }
        }
    }
}

/** @DataSource("live embodiment state; VanLiveVisualState/VanCaptions") */
@Composable
private fun EmbodimentPanel(app: VanApplication) {
    val tokens = LocalVanTokens.current
    val degraded by app.degradedModeStore.state.collectAsState()
    val live = VanLiveVisualState.frame
    val cue = VanPresence.cue(degraded, live = live)
    val budget = rememberVanEffectBudget()
    VanPanel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            VanEmbodiment(
                state = VanPresence.visualState(cue, live),
                budget = budget,
                presentation = VanPresentation.EXPANDED,
                modifier = Modifier.size(96.dp),
            )
            Column(modifier = Modifier.padding(start = tokens.space.space3).fillMaxWidth()) {
                Text2("VAN", tokens.type.title, tokens.color.textPrimary)
                Text2(cue.headline, tokens.type.headline, tokens.color.accentCyan)
                Text2(cue.detail, tokens.type.body, tokens.color.textSecondary)
            }
        }
    }
}

/**
 * @DataSource("GET /v1/attention, GET /v1/briefing") — top 3, via
 * `com.dial.van.status.OwnerOverview.summarize` (P3-AND-003): the one place attention items
 * and the briefing become the sentence a home screen says, and the one that keeps "nothing
 * is waiting for you" from ever meaning "VAN could not reach the gateway".
 */
@Composable
private fun AttentionNowPanel(overview: OwnerOverviewSummary, onOpen: () -> Unit) {
    val tokens = LocalVanTokens.current
    val top3 = overview.items.take(3)
    SectionHeader("Attention now", detail = overview.headline)
    overview.briefingLine?.let { line ->
        Text2(line, tokens.type.body, tokens.color.textSecondary)
    }
    if (top3.isEmpty()) {
        VanPanel { Text2(overview.headline, tokens.type.body, tokens.color.textSecondary) }
        return
    }
    VanPressable(onClick = onOpen, modifier = Modifier.fillMaxWidth()) {
        VanPanel(modifier = Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                top3.forEach { item ->
                    val severity = runCatching { AttentionSeverity.valueOf(item.severity) }
                        .getOrDefault(AttentionSeverity.INFO)
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2), verticalAlignment = Alignment.CenterVertically) {
                        StatusChip(label = severity.name.replace('_', ' '), role = StatusSemantics.forAttentionSeverity(severity))
                        Text2(item.title, tokens.type.body, tokens.color.textPrimary)
                    }
                }
            }
        }
    }
}

/** @DataSource("GET /v1/missions?active=true, GET /v1/needs-you") — RUNNING and WAITING. */
@Composable
private fun ActiveWorkPanel(active: List<MissionSummary>, waiting: List<MissionSummary>, onOpen: () -> Unit) {
    val tokens = LocalVanTokens.current
    SectionHeader("Active work")
    VanPressable(onClick = onOpen, modifier = Modifier.fillMaxWidth()) {
        VanPanel(modifier = Modifier.fillMaxWidth()) {
            if (active.isEmpty() && waiting.isEmpty()) {
                Text2("Nothing is running.", tokens.type.body, tokens.color.textSecondary)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    active.take(3).forEach { mission ->
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            StatusChip(label = "RUNNING", role = StatusSemantics.ROLE_ENGAGED)
                            Text2(mission.title, tokens.type.body, tokens.color.textPrimary)
                        }
                    }
                    waiting.take(3).forEach { mission ->
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            StatusChip(label = "WAITING", role = StatusSemantics.ROLE_HYPOTHESIS)
                            Text2(mission.title, tokens.type.body, tokens.color.textPrimary)
                        }
                    }
                }
            }
        }
    }
}

/**
 * @DataSource("GET /v1/trading/assessment") — a `MetricTile` row on 200, `LiveBadge`
 * unavailable otherwise. Independent of Home's aggregate load: this route does not exist on
 * every backend yet, and that must never blank the rest of the dashboard.
 */
@Composable
private fun SignificantTradePanel(app: VanApplication, onOpen: () -> Unit) {
    val tokens = LocalVanTokens.current
    var assessment by remember { mutableStateOf<JSONObject?>(null) }
    var unavailable by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        runCatching { JSONObject(app.gatewayClient.tradingAssessment()) }
            .onSuccess { assessment = it }
            .onFailure { unavailable = true }
    }
    SectionHeader("Significant trade state")
    VanPressable(onClick = onOpen, modifier = Modifier.fillMaxWidth()) {
        VanPanel(modifier = Modifier.fillMaxWidth()) {
            when {
                assessment != null -> {
                    val a = assessment!!
                    MetricTile(
                        label = a.optString("headline", "Portfolio"),
                        value = a.optString("value", "—"),
                        delta = if (a.has("delta")) a.optString("delta") else null,
                        deltaRole = if (a.has("role")) a.optString("role") else null,
                    )
                }
                unavailable -> LiveBadge(state = LiveBadgeState.Offline)
                else -> Text2("Checking…", tokens.type.body, tokens.color.textSecondary)
            }
        }
    }
}

/** @DataSource("GET /v1/reminders") — filtered to those due before local midnight tonight. */
@Composable
private fun UpcomingPanel(dueToday: List<JSONObject>) {
    val tokens = LocalVanTokens.current
    SectionHeader("Upcoming")
    VanPanel {
        if (dueToday.isEmpty()) {
            Text2("Nothing due today.", tokens.type.body, tokens.color.textSecondary)
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                dueToday.take(5).forEach { reminder ->
                    Text2("• ${reminder.optString("text")}", tokens.type.body, tokens.color.textPrimary)
                }
            }
        }
    }
}

/** @DataSource("device event store, com.dial.van.events.VanEventStreamStore") — last 5. */
@Composable
private fun RecentChangePanel(app: VanApplication) {
    val tokens = LocalVanTokens.current
    val stream by app.eventStream.state.collectAsState()
    val recent = stream.events.takeLast(5).asReversed()
    SectionHeader("Recent change")
    VanPanel {
        if (recent.isEmpty()) {
            Text2("Nothing has changed recently.", tokens.type.body, tokens.color.textSecondary)
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                recent.forEach { event ->
                    Text2("• ${event.type}", tokens.type.body, tokens.color.textPrimary)
                }
            }
        }
    }
}

@Composable
private fun Text2(text: String, style: androidx.compose.ui.text.TextStyle, color: androidx.compose.ui.graphics.Color) {
    androidx.compose.material3.Text(text = text, style = style, color = color)
}

private fun isDueToday(dueAtUnix: Long): Boolean {
    if (dueAtUnix <= 0L) return false
    val now = Calendar.getInstance()
    val due = Calendar.getInstance().apply { timeInMillis = dueAtUnix * 1000L }
    return now.get(Calendar.YEAR) == due.get(Calendar.YEAR) && now.get(Calendar.DAY_OF_YEAR) == due.get(Calendar.DAY_OF_YEAR)
}
