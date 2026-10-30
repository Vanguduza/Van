package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.EvidenceRow
import com.dial.van.design.components.FindingAction
import com.dial.van.design.components.FindingCard
import com.dial.van.design.components.HeatBar
import com.dial.van.design.components.LiveBadge
import com.dial.van.design.components.LiveBadgeState
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.PositionCard
import com.dial.van.design.components.PositionDirection
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.trading.AssessmentReadModel
import com.dial.van.trading.EventsReadModel
import com.dial.van.trading.Loaded
import com.dial.van.trading.OpenPosition
import com.dial.van.trading.PortfolioSummary
import com.dial.van.trading.PositionsReadModel
import com.dial.van.trading.TradingFormat
import com.dial.van.trading.TradingReadModels
import com.dial.van.trading.TradingRepository
import com.dial.van.trading.TradingRuntimeReadModel
import com.dial.van.command.owner.ownerTime

/**
 * DNA §4 Trading overview: accounts strip, equity + risk headroom + portfolio heat + open
 * exposure, active positions with thesis state, significant events, VAN's own read of the
 * book, and the urgent-risks rail. `LiveBadge` staleness is read from the newest timestamp
 * actually present in `/v1/trading/status`; missing or failed integrity/freshness
 * observations are explicitly unknown, never live.
 *
 * @DataSource("GET /v1/trading/portfolio")
 * @DataSource("GET /v1/trading/risk")
 * @DataSource("GET /v1/trading/assessment")
 * @DataSource("GET /v1/trading/positions")
 * @DataSource("GET /v1/trading/events")
 */
@Composable
fun OverviewScreen(repo: TradingRepository, nav: TradingNav, nowMs: () -> Long) {
    val tokens = LocalVanTokens.current
    var tick by remember { mutableIntStateOf(0) }
    var runtime: Loaded<TradingRuntimeReadModel> by remember { mutableStateOf(Loaded.Loading) }
    var refreshing by remember { mutableStateOf(false) }
    var observedAt by remember { mutableStateOf(0L) }
    var portfolio: Loaded<PortfolioSummary> by remember { mutableStateOf(Loaded.Loading) }
    var assessment: Loaded<AssessmentReadModel> by remember { mutableStateOf(Loaded.Loading) }
    var positions: Loaded<PositionsReadModel> by remember { mutableStateOf(Loaded.Loading) }
    var events: Loaded<EventsReadModel> by remember { mutableStateOf(Loaded.Loading) }

    LaunchedEffect(tick) {
        refreshing = true
        try {
            runtime = repo.status()
            portfolio = repo.portfolio()
            assessment = repo.assessment()
            positions = repo.positions()
            events = repo.events(30)
            observedAt = nowMs()
        } finally { refreshing = false }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Overview", style = tokens.type.title, color = tokens.color.textPrimary)
                Column {
                    OverviewLiveBadge(runtime, nowMs())
                    if (!refreshing) TradingRefreshAction { tick++ }
                }
            }
        }

        item {
            if (refreshing) Text("Refreshing trading information…", style = tokens.type.label, color = tokens.color.textSecondary)
            if (observedAt > 0L) Text("Last read ${ownerTime(observedAt)}", style = tokens.type.label, color = tokens.color.textTertiary)
            for ((name, value) in listOf("Runtime and control" to runtime, "Portfolio" to portfolio, "Assessment" to assessment, "Positions" to positions, "Events" to events)) {
                if (value is Loaded.Unavailable) Text("$name could not be read. ${TradingFormat.unavailableState(value.reason)}", style = tokens.type.body, color = tokens.color.textSecondary)
            }
            (runtime as? Loaded.Ready)?.value?.let { status ->
                VanPanel { Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    SectionHeader("Trading authority & controls")
                    Text(when (status.killSwitchActive) { true -> "Kill switch recorded active: ${status.killSwitchTriggers.joinToString().ifBlank { "trigger not supplied" }}"; false -> "The latest ledger read records no active kill switch."; null -> "Current kill switch state could not be confirmed." }, style = tokens.type.body, color = tokens.color.textSecondary)
                    Text(when (status.ownerHaltRecorded) { true -> "An owner halt is recorded in the ledger. This alone does not certify the trading worker or broker observed it."; false -> "The current ledger read does not record an active owner halt."; null -> "Owner halt state is unknown." }, style = tokens.type.label, color = tokens.color.textSecondary)
                    Text(when (status.chainOk) { true -> "Ledger chain verified."; false -> "Ledger chain verification failed; treat its results as untrusted."; null -> "Ledger chain integrity could not be confirmed." }, style = tokens.type.label, color = tokens.color.textTertiary)
                    status.staleReason?.let { Text(it, style = tokens.type.label, color = tokens.color.textSecondary) }
                    status.head?.let { Text("Ledger receipt: $it", style = tokens.type.label, color = tokens.color.textTertiary) }
                } }
            }
        }
        item { AccountsStrip(portfolio, nav) }
        item {
            TextButton(onClick = nav.openTickets) {
                Text("Owner broker tickets", style = tokens.type.label, color = tokens.color.accentCyan)
            }
        }

        item { EquityAndRiskPanel(portfolio, assessment) }

        item {
            SectionHeader(
                title = "Active positions",
                detail = (positions as? Loaded.Ready)?.value?.let { "${it.count} open" },
                trailing = {
                    TextButton(onClick = nav.openPositions) {
                        Text("See all", style = tokens.type.label, color = tokens.color.accentCyan)
                    }
                },
            )
        }
        item { ActivePositionsList(positions, nav) }

        item { SectionHeader(title = "Significant events", detail = "materiality ≥ ${TradingReadModels.DEFAULT_MATERIALITY_THRESHOLD}") }
        item { SignificantEventsList(events) }

        item { VanAssessmentPanel(assessment, nav) }

        item {
            TradingDisclosure(
                "Read model of the VATI ledger. Nothing on this screen can place, size, modify " +
                    "or cancel a trade.",
            )
        }
    }
}

@Composable
private fun OverviewLiveBadge(runtime: Loaded<TradingRuntimeReadModel>, nowMs: Long) {
    val state = (runtime as? Loaded.Ready)?.value
    val freshness = state?.freshness(nowMs) ?: TradingRuntimeReadModel.Freshness.UNKNOWN
    when (freshness) {
        TradingRuntimeReadModel.Freshness.UNKNOWN -> StatusChip(label = "FRESHNESS UNKNOWN", role = StatusSemantics.ROLE_DISABLED)
        TradingRuntimeReadModel.Freshness.OFFLINE -> LiveBadge(LiveBadgeState.Offline)
        TradingRuntimeReadModel.Freshness.STALE -> {
            val time = state?.lastEventMs?.takeIf { it > 0 }
            if (time == null) StatusChip(label = "STALE · TIME UNKNOWN", role = StatusSemantics.ROLE_EVENT_RISK)
            else LiveBadge(LiveBadgeState.Stale((nowMs - time).coerceAtLeast(0L)))
        }
        TradingRuntimeReadModel.Freshness.LIVE -> LiveBadge(LiveBadgeState.Live)
    }
}

@Composable
private fun AccountsStrip(portfolio: Loaded<PortfolioSummary>, nav: TradingNav) {
    val tokens = LocalVanTokens.current
    val ready = portfolio as? Loaded.Ready ?: return
    if (ready.value.accounts.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            items(ready.value.accounts, key = { it.alias }) { account ->
                VanPanel(dense = true, modifier = Modifier) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text(account.label, style = tokens.type.body, color = tokens.color.textPrimary)
                        Text(account.equity.plain, style = tokens.type.data, color = tokens.color.textPrimary)
                        StatusChip(
                            label = account.connection.label,
                            role = if (account.connection.name == "LIVE") StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_DISABLED,
                        )
                    }
                }
            }
        }
        TextButton(onClick = nav.openAccounts) {
            Text("Manage accounts →", style = tokens.type.label, color = tokens.color.accentCyan)
        }
    }
}

@Composable
private fun EquityAndRiskPanel(portfolio: Loaded<PortfolioSummary>, assessment: Loaded<AssessmentReadModel>) {
    val tokens = LocalVanTokens.current
    val p = (portfolio as? Loaded.Ready)?.value
    val a = (assessment as? Loaded.Ready)?.value
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                MetricTile("Equity", p?.equity?.plain ?: "—", Modifier.weight(1f))
                MetricTile(
                    "Available risk",
                    a?.availableRisk?.let { TradingFormat.percent(it * 100) } ?: "—",
                    Modifier.weight(1f),
                )
                MetricTile("Open positions", (a?.openPositions ?: p?.openPositions?.size)?.toString() ?: "—", Modifier.weight(1f))
            }
            val fraction = a?.heatFraction ?: p?.portfolioHeat?.fraction?.toFloat()
            if (fraction != null) {
                val heat = a?.portfolioHeat
                val ceiling = a?.maxOpenStopRisk
                HeatBar(
                    label = "Portfolio heat",
                    fraction = fraction,
                    detail = if (heat != null) "of ${ceiling?.let { TradingFormat.percent(it * 100) } ?: "?"} ceiling" else null,
                )
            }
            val killSwitch = a?.killSwitchActive
            if (!killSwitch.isNullOrEmpty()) {
                StatusChip(label = "KILL SWITCH: ${killSwitch.joinToString()}", role = StatusSemantics.ROLE_CRITICAL, filled = true)
            }
        }
    }
}

@Composable
private fun ActivePositionsList(positions: Loaded<PositionsReadModel>, nav: TradingNav) {
    val tokens = LocalVanTokens.current
    when (positions) {
        Loaded.Loading -> Text("Reading the ledger…", style = tokens.type.body, color = tokens.color.textSecondary)
        is Loaded.Unavailable -> Text(TradingFormat.unavailableState(positions.reason), style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
        is Loaded.Ready -> {
            val rows = positions.value.positions
            if (rows.isEmpty()) {
                Text("No open positions.", style = tokens.type.body, color = tokens.color.textSecondary)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    rows.take(5).forEach { position -> OverviewPositionCard(position, nav) }
                }
            }
        }
    }
}

@Composable
internal fun OverviewPositionCard(position: OpenPosition, nav: TradingNav) {
    PositionCard(
        symbol = position.symbol,
        direction = if (position.direction?.uppercase() == "SHORT") PositionDirection.SHORT else PositionDirection.LONG,
        exposureLabel = position.approvedSize ?: position.quantity?.let { TradingFormat.lots(it) } ?: "—",
        rMultipleLabel = TradingFormat.r(position.unrealisedR),
        thesisState = position.thesisState,
        protectionLabel = if (position.protectionConfirmed) "Confirmed" else "Not confirmed",
        onClick = { nav.openPosition(position.tradeIntentId) },
    )
}

@Composable
private fun SignificantEventsList(events: Loaded<EventsReadModel>) {
    val tokens = LocalVanTokens.current
    val ready = events as? Loaded.Ready ?: run {
        if (events is Loaded.Unavailable) {
            Text(TradingFormat.unavailableState(events.reason), style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
        }
        return
    }
    val significant = TradingReadModels.significantImpacts(ready.value.impacts)
    if (significant.isEmpty()) {
        Text("No materially significant events recorded.", style = tokens.type.body, color = tokens.color.textSecondary)
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        significant.take(5).forEach { impact ->
            EvidenceRow(
                source = impact.symbol?.let { "$it — ${impact.concern ?: "event impact"}" } ?: (impact.concern ?: "event impact"),
                trustTier = "materiality ${impact.materiality?.let { TradingFormat.percent(it * 100, decimals = 0) } ?: "?"}",
                trustRole = if ((impact.materiality ?: 0.0) >= 0.75) StatusSemantics.ROLE_CRITICAL else StatusSemantics.ROLE_EVENT_RISK,
                timeLabel = TradingFormat.timeHm(impact.atMs),
            )
        }
    }
}

@Composable
private fun VanAssessmentPanel(assessment: Loaded<AssessmentReadModel>, nav: TradingNav) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text("VAN's read of the book", style = tokens.type.headline, color = tokens.color.textPrimary)
            }
            when (assessment) {
                Loaded.Loading -> Text("Reading the ledger…", style = tokens.type.body, color = tokens.color.textSecondary)
                is Loaded.Unavailable -> Text(TradingFormat.unavailableState(assessment.reason), style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
                is Loaded.Ready -> {
                    val a = assessment.value
                    if (a.urgentRisks.isEmpty()) {
                        Text("No urgent risks right now.", style = tokens.type.body, color = tokens.color.textSecondary)
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            a.urgentRisks.forEach { risk ->
                                val id = risk.tradeIntentId
                                FindingCard(
                                    title = risk.symbol ?: "Kill switch",
                                    severityRole = StatusSemantics.ROLE_CRITICAL,
                                    detail = risk.reasons.joinToString(" · ").ifBlank { null },
                                    actions = if (id != null) {
                                        listOf(FindingAction("Open", { nav.openPosition(id) }, emphasized = true))
                                    } else emptyList(),
                                )
                            }
                        }
                    }
                    Text(
                        "Active theses: " + (a.activeTheses.takeIf { it.isNotEmpty() }?.entries?.joinToString { "${it.key} ${it.value}" } ?: "none"),
                        style = tokens.type.body,
                        color = tokens.color.textSecondary,
                    )
                    // DNA-honest invoker read: shown verbatim, e.g. "Cognition: not configured"
                    // for MODEL_INVOKER_UNCONFIGURED — never dressed up as "connected".
                    Text(
                        "Cognition: " + cognitionSentence(a.cognition.invoker, a.cognition.state),
                        style = tokens.type.body,
                        color = tokens.color.textSecondary,
                    )
                }
            }
            TextButton(onClick = nav.openCognition) {
                Text("Cognition & research →", style = tokens.type.label, color = tokens.color.accentCyan)
            }
            TextButton(onClick = nav.openStrategies) {
                Text("Strategies →", style = tokens.type.label, color = tokens.color.accentCyan)
            }
        }
    }
}

private fun cognitionSentence(invoker: String, state: String): String = when (state) {
    "MODEL_INVOKER_UNCONFIGURED" -> "not configured"
    else -> if (invoker == "none") state.lowercase().replace('_', ' ') else "$invoker (${state.lowercase().replace('_', ' ')})"
}
