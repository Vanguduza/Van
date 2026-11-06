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
import androidx.compose.material3.OutlinedButton
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
import com.dial.van.command.owner.ownerTime
import com.dial.van.design.AttentionSeverity
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenState
import com.dial.van.design.ScreenStateMerge
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.mission.MissionParsing
import com.dial.van.mission.MissionSummary
import com.dial.van.status.OwnerOverview
import com.dial.van.status.OwnerOverviewSummary
import com.dial.van.status.OwnerSourceRead
import com.dial.van.status.readOwnerSource
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.rememberVanEffectBudget
import kotlinx.coroutines.launch
import kotlinx.coroutines.async
import kotlinx.coroutines.supervisorScope
import org.json.JSONArray
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
    val attention: OwnerSourceRead<JSONArray>,
    val briefing: OwnerSourceRead<JSONObject>,
    val active: OwnerSourceRead<List<MissionSummary>>,
    val waiting: OwnerSourceRead<List<MissionSummary>>,
    val reminders: OwnerSourceRead<List<JSONObject>>,
    val trading: OwnerSourceRead<JSONObject>,
)

@Composable
fun HomeRoute(
    app: VanApplication,
    onOpenAttention: () -> Unit,
    onOpenWork: () -> Unit,
    onOpenTrading: () -> Unit,
    onOpenMission: (String) -> Unit = { onOpenWork() },
    onOpenReminders: () -> Unit = onOpenAttention,
) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<HomeData?>(null) }
    var loading by remember { mutableStateOf(false) }
    val degradedMode by app.degradedModeStore.state.collectAsState()

    fun load() {
        if (loading) return
        loading = true
        val previous = data
        scope.launch {
            try {
                data = supervisorScope {
                    val attention = async { readOwnerSource(previous?.attention ?: OwnerSourceRead()) { app.gatewayClient.attention() } }
                    val briefing = async { readOwnerSource(previous?.briefing ?: OwnerSourceRead()) { app.gatewayClient.briefing() } }
                    val active = async { readOwnerSource(previous?.active ?: OwnerSourceRead()) {
                        MissionParsing.missionSummaries(app.gatewayClient.missions(activeOnly = true)).filter { it.isActive }
                    } }
                    val waiting = async { readOwnerSource(previous?.waiting ?: OwnerSourceRead()) {
                        val needs = app.gatewayClient.needsYou()
                        MissionParsing.missionSummaries(needs.optJSONArray("missions") ?: JSONArray())
                    } }
                    val reminders = async { readOwnerSource(previous?.reminders ?: OwnerSourceRead()) { app.gatewayClient.reminders().objectList() } }
                    val trading = async { readOwnerSource(previous?.trading ?: OwnerSourceRead()) { JSONObject(app.gatewayClient.tradingAssessment()) } }
                    HomeData(attention.await(), briefing.await(), active.await(), waiting.await(), reminders.await(), trading.await())
                }
            } finally {
                loading = false
            }
        }
    }
    LaunchedEffect(Unit) { load() }

    val state: ScreenState<HomeData> = ScreenStateMerge.merge(
        content = data,
        loading = data == null,
        degradedSubsystems = degradedMode.subsystems.filter { it.status.name != "WORKING" }.map { it.id },
        emptySentence = "Nothing needs you right now.",
    )

    VanScreen(state = state, onRetry = ::load) { home ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
            contentPadding = PaddingValues(vertical = tokens.space.space3),
        ) {
            item { OutlinedButton(enabled = !loading, onClick = ::load) { Text2(if (loading) "Refreshing…" else "Refresh", tokens.type.label, tokens.color.textSecondary) } }
            item { EmbodimentPanel(app) }
            item {
                SourceObservation("Attention", home.attention)
                SourceObservation("Briefing", home.briefing)
                if (home.attention.hasObservation) {
                    val overview = OwnerOverview.summarize(home.attention.value, home.briefing.value)
                    AttentionNowPanel(if (home.attention.unavailable) overview.copy(headline = "Last confirmed: ${overview.headline}") else overview, onOpenAttention)
                } else {
                    SectionHeader("Attention now")
                    VanPanel { Text2("Attention is unavailable; VAN cannot tell you what is waiting.", tokens.type.body, tokens.color.textSecondary) }
                }
            }
            item { ActiveWorkPanel(home.active, home.waiting, onOpenWork, onOpenMission) }
            item { SignificantTradePanel(home.trading, onOpenTrading) }
            item {
                SourceObservation("Reminders", home.reminders)
                UpcomingPanel(home.reminders.value?.filter { isDueToday(it.optLong("due_at_unix")) }, home.reminders.unavailable, onOpenReminders)
            }
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
private fun ActiveWorkPanel(active: OwnerSourceRead<List<MissionSummary>>, waiting: OwnerSourceRead<List<MissionSummary>>, onOpen: () -> Unit, onOpenMission: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    SectionHeader("Active work")
    SourceObservation("Running missions", active)
    SourceObservation("Waiting missions", waiting)
    OutlinedButton(onClick = onOpen) { Text2("All work", tokens.type.label, tokens.color.textSecondary) }
    VanPanel(modifier = Modifier.fillMaxWidth()) {
            if (active.value?.isEmpty() == true && waiting.value?.isEmpty() == true && !active.unavailable && !waiting.unavailable) {
                Text2("Nothing is running.", tokens.type.body, tokens.color.textSecondary)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    active.value?.take(3)?.forEach { mission ->
                        VanPressable(onClick = { onOpenMission(mission.missionId) }, modifier = Modifier.fillMaxWidth()) {
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                StatusChip(label = "RUNNING", role = StatusSemantics.ROLE_ENGAGED)
                                Text2(mission.title, tokens.type.body, tokens.color.textPrimary)
                            }
                        }
                    }
                    waiting.value?.take(3)?.forEach { mission ->
                        VanPressable(onClick = { onOpenMission(mission.missionId) }, modifier = Modifier.fillMaxWidth()) {
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
 * @DataSource("GET /v1/trading/assessment") — independent observation and refresh time.
 * An unavailable trading source leaves the other dashboard sources visible.
 */
@Composable
private fun SignificantTradePanel(assessment: OwnerSourceRead<JSONObject>, onOpen: () -> Unit) {
    val tokens = LocalVanTokens.current
    SectionHeader("Significant trade state")
    SourceObservation("Trading", assessment)
    VanPressable(onClick = onOpen, modifier = Modifier.fillMaxWidth()) {
        VanPanel(modifier = Modifier.fillMaxWidth()) {
            when {
                assessment.value != null -> {
                    val a = assessment.value
                    MetricTile(
                        label = a.optString("headline", "Portfolio"),
                        value = a.optString("value", "—"),
                        delta = if (a.has("delta")) a.optString("delta") else null,
                        deltaRole = if (a.has("role")) a.optString("role") else null,
                    )
                }
                else -> Text2("Trading data is unavailable.", tokens.type.body, tokens.color.textSecondary)
            }
        }
    }
}

/** @DataSource("GET /v1/reminders") — filtered to those due before local midnight tonight. */
@Composable
private fun UpcomingPanel(dueToday: List<JSONObject>?, unavailable: Boolean, onOpen: () -> Unit) {
    val tokens = LocalVanTokens.current
    SectionHeader("Upcoming")
    VanPressable(onClick = onOpen, modifier = Modifier.fillMaxWidth()) {
    VanPanel {
        if (dueToday == null) {
            Text2("Reminders are unavailable.", tokens.type.body, tokens.color.textSecondary)
        } else if (dueToday.isEmpty()) {
            Text2(if (unavailable) "Last confirmed: nothing due today." else "Nothing due today.", tokens.type.body, tokens.color.textSecondary)
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                dueToday.take(5).forEach { reminder ->
                    Text2("• ${reminder.optString("text")}", tokens.type.body, tokens.color.textPrimary)
                }
            }
        }
    }
    }
}

@Composable
private fun <T> SourceObservation(label: String, source: OwnerSourceRead<T>) {
    val tokens = LocalVanTokens.current
    if (source.unavailable) {
        Text2("$label could not refresh." + if (source.hasObservation) " Showing the last confirmed data." else " No confirmed data is available.", tokens.type.label, tokens.color.textSecondary)
    }
    source.observedAtMs?.let { Text2("$label last checked ${ownerTime(it)}", tokens.type.label, tokens.color.textSecondary) }
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
