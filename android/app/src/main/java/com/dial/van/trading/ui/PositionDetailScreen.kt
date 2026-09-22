package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Text
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
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.PositionDirection
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.ThesisCard
import com.dial.van.design.components.TimelineEvent
import com.dial.van.design.components.TimelineRail
import com.dial.van.design.components.VanPanel
import com.dial.van.trading.ChartLevel
import com.dial.van.trading.ChartMarker
import com.dial.van.trading.EventsReadModel
import com.dial.van.trading.LevelKind
import com.dial.van.trading.Loaded
import com.dial.van.trading.MarketStateCard
import com.dial.van.trading.OpenPosition
import com.dial.van.trading.PositionsReadModel
import com.dial.van.trading.TradeDetail
import com.dial.van.trading.TradingFormat
import com.dial.van.trading.TradingReadModels
import com.dial.van.trading.TradingRepository

/**
 * DNA §4 Trading destination 3, "Position detail": the chart with entry/stop/target/
 * protection lines and event markers, the sealed [ThesisCard], the lifecycle [TimelineRail],
 * linked events ([EvidenceRow]), the latest adjustment proposal, a risk block, and the
 * execution/decision evidence carried on `/v1/trading/trades/{id}`.
 *
 * @DataSource("GET /v1/trading/positions")
 * @DataSource("GET /v1/trading/trades/{id}")
 * @DataSource("GET /v1/trading/events")
 * @DataSource("GET /v1/trading/market-state")
 */
@Composable
fun PositionDetailScreen(repo: TradingRepository, nav: TradingNav, tradeIntentId: String) {
    val tokens = LocalVanTokens.current
    var tick by remember { mutableIntStateOf(0) }
    var positions: Loaded<PositionsReadModel> by remember { mutableStateOf(Loaded.Loading) }
    var detail: Loaded<TradeDetail> by remember { mutableStateOf(Loaded.Loading) }
    var events: Loaded<EventsReadModel> by remember { mutableStateOf(Loaded.Loading) }
    var marketStates: Loaded<List<MarketStateCard>> by remember { mutableStateOf(Loaded.Loading) }

    LaunchedEffect(tradeIntentId, tick) {
        positions = repo.positions()
        detail = repo.tradeDetail(tradeIntentId)
        events = repo.events(200)
    }
    val position = (positions as? Loaded.Ready)?.value?.positions?.firstOrNull { it.tradeIntentId == tradeIntentId }
    LaunchedEffect(position?.symbol) {
        position?.symbol?.let { symbol -> marketStates = repo.marketStates(symbol) }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        item {
            SectionHeader(
                title = position?.symbol ?: (detail as? Loaded.Ready)?.value?.row?.symbol ?: "Position",
                detail = position?.direction,
                trailing = { TradingRefreshAction { tick += 1 } },
            )
        }
        if (position == null && positions is Loaded.Unavailable) {
            item {
                Text(
                    TradingFormat.unavailableState((positions as Loaded.Unavailable).reason),
                    style = tokens.type.body,
                    color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK),
                )
            }
        }

        item { PositionDetailChart(position, detail, events) }

        val pos = position
        if (pos != null && pos.thesis != null) {
            item {
                ThesisCard(
                    title = "Thesis",
                    state = pos.thesisState,
                    thesisSummary = pos.thesis.statement,
                    confirmation = pos.thesis.confirmation,
                    invalidation = pos.thesis.invalidation,
                )
            }
            pos.thesis.expectedPath?.let { path ->
                item {
                    VanPanel(dense = true) {
                        Text("Expected path", style = tokens.type.label, color = tokens.color.textTertiary)
                        Text(path, style = tokens.type.body, color = tokens.color.textSecondary)
                    }
                }
            }
        }

        item { PositionLifecycleTimeline(position, detail) }

        item { SectionHeader(title = "Linked events") }
        item { PositionLinkedEvents(position) }

        position?.latestProposal?.let { proposal ->
            item {
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text("Latest proposal", style = tokens.type.headline, color = tokens.color.textPrimary)
                            StatusChip(
                                label = proposal.action ?: "PROPOSAL",
                                role = if (proposal.requiresAuthority == true) StatusSemantics.ROLE_EVENT_RISK else StatusSemantics.ROLE_MONITOR,
                            )
                        }
                        proposal.rationale?.let { Text(it, style = tokens.type.body, color = tokens.color.textSecondary) }
                        if (proposal.reasons.isNotEmpty()) {
                            Text(proposal.reasons.joinToString(" · "), style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                        Text(
                            "The ledger records this as the most recent proposal; it does not record whether the " +
                                "owner or the trading authority accepted or rejected it separately from what the " +
                                "position later did.",
                            style = tokens.type.label,
                            color = tokens.color.textTertiary,
                        )
                    }
                }
            }
        }

        item { PositionRiskBlock(position) }

        val d = detail
        if (d is Loaded.Ready) {
            item {
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Text("Decision & execution evidence", style = tokens.type.headline, color = tokens.color.textPrimary)
                        Text(
                            "decision ${TradingFormat.hash8(d.value.decisionHash)} · market state " +
                                "${TradingFormat.hash8(d.value.marketSnapshotHash)}",
                            style = tokens.type.label,
                            color = tokens.color.textTertiary,
                        )
                        d.value.multipliers.forEach { (k, v) -> Text("$k = $v", style = tokens.type.label, color = tokens.color.textTertiary) }
                    }
                }
            }
        }

        val ms = (marketStates as? Loaded.Ready)?.value?.firstOrNull()
        if (ms != null && ms.features.isNotEmpty()) {
            item {
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Text("Related indicators", style = tokens.type.headline, color = tokens.color.textPrimary)
                        ms.features.entries.sortedBy { it.key }.chunked(2).forEach { pair ->
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                pair.forEach { (k, v) -> MetricTile(k, v.take(10), Modifier.weight(1f)) }
                            }
                        }
                    }
                }
            }
        }

        item {
            TradingDisclosure(
                "Read model of the VATI ledger; nothing here can place, size, modify or cancel a trade.",
            )
        }
    }
}

@Composable
private fun PositionDetailChart(position: OpenPosition?, detail: Loaded<TradeDetail>, events: Loaded<EventsReadModel>) {
    val tokens = LocalVanTokens.current
    val ready = detail as? Loaded.Ready
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Chart", style = tokens.type.headline, color = tokens.color.textPrimary)
            if (ready == null || ready.value.chart.isEmpty()) {
                Text(
                    TradingFormat.emptyState("bars"),
                    style = tokens.type.body,
                    color = tokens.color.textSecondary,
                )
            } else {
                val d = ready.value
                val digits = TradingFormat.digitsFor(d.row.symbol)
                val levels = buildList {
                    (d.fill ?: d.entry)?.let { add(ChartLevel(LevelKind.ENTRY, it, "ENTRY")) }
                    // DNA: "entry/stop/target/protection lines" — the position's own protective
                    // stop (from /v1/trading/positions) is the live "protection" line; the
                    // trade-detail levels are used only as a fallback when a position row was
                    // not found (e.g. a closed trade opened from history).
                    (position?.stop ?: d.stop)?.let { add(ChartLevel(LevelKind.STOP, it, "PROTECTION")) }
                    d.target?.let { add(ChartLevel(LevelKind.TARGET, it, "TARGET")) }
                    d.exit?.let { add(ChartLevel(LevelKind.EXIT, it, "EXIT")) }
                }
                val symbolEvents = (events as? Loaded.Ready)?.value?.impacts
                    ?.filter { it.symbol?.equals(d.row.symbol, ignoreCase = true) == true }
                    ?.map { ChartMarker(atMs = it.atMs, kind = "EVENT", price = null) }
                    ?: emptyList()
                TradeChartCanvas(
                    bars = d.chart,
                    levels = levels,
                    markers = d.markers + symbolEvents,
                    digits = digits,
                    heightDp = 260,
                )
            }
        }
    }
}

@Composable
private fun PositionLifecycleTimeline(position: OpenPosition?, detail: Loaded<TradeDetail>) {
    val tokens = LocalVanTokens.current
    val thesis = position?.thesis
    val assessment = position?.latestAssessment
    val health = position?.health
    val proposal = position?.latestProposal
    val thesisState = position?.thesisState
    val dated = buildList {
        val thesisCreatedMs = thesis?.createdMs
        if (thesisCreatedMs != null) {
            add(thesisCreatedMs to TimelineEvent("thesis-sealed", "Thesis sealed", "VAN", TradingFormat.timeHm(thesisCreatedMs), StatusSemantics.ROLE_MONITOR))
        }
        val assessedMs = assessment?.assessedMs
        if (assessedMs != null && assessment != null && thesisState != null) {
            add(
                assessedMs to TimelineEvent(
                    "assessment", "Assessment: ${assessment.state ?: "?"}", "VAN",
                    TradingFormat.timeHm(assessedMs), StatusSemantics.forThesisState(thesisState),
                    detail = assessment.reasons.joinToString(" · ").ifBlank { null },
                ),
            )
        }
        val healthMs = health?.assessedMs
        if (healthMs != null && health != null && thesisState != null) {
            add(
                healthMs to TimelineEvent(
                    "health", "Health: ${health.state ?: "?"}", "VAN", TradingFormat.timeHm(healthMs),
                    TradingReadModels.roleForHealth(thesisState, health.state),
                ),
            )
        }
        val proposedMs = proposal?.proposedMs
        if (proposedMs != null && proposal != null) {
            add(proposedMs to TimelineEvent("proposal", "Proposal: ${proposal.action ?: "?"}", "VAN", TradingFormat.timeHm(proposedMs), StatusSemantics.ROLE_EVENT_RISK))
        }
        (detail as? Loaded.Ready)?.value?.timeline?.forEach { entry ->
            add(entry.atMs to TimelineEvent(entry.hash.ifBlank { entry.kind + entry.atMs }, entry.kind, "Ledger", TradingFormat.timeHm(entry.atMs), StatusSemantics.ROLE_MONITOR, detail = entry.text.ifBlank { null }))
        }
    }.sortedByDescending { it.first }
    val events = dated.map { it.second }
    if (events.isEmpty()) return
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Lifecycle", style = tokens.type.headline, color = tokens.color.textPrimary)
            TimelineRail(events = events)
        }
    }
}

@Composable
private fun PositionLinkedEvents(position: OpenPosition?) {
    val tokens = LocalVanTokens.current
    val linked = position?.linkedEvents.orEmpty()
    if (linked.isEmpty()) {
        Text("No events linked to this position.", style = tokens.type.body, color = tokens.color.textSecondary)
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        linked.forEach { event ->
            EvidenceRow(
                source = event.headlineTitle ?: event.headlineId ?: (event.concern ?: "event"),
                trustTier = "materiality ${event.materiality?.let { TradingFormat.percent(it * 100, decimals = 0) } ?: "?"}",
                trustRole = if ((event.materiality ?: 0.0) >= 0.75) StatusSemantics.ROLE_CRITICAL else StatusSemantics.ROLE_EVENT_RISK,
                timeLabel = event.atMs?.let { TradingFormat.timeHm(it) } ?: "—",
            )
        }
    }
}

@Composable
private fun PositionRiskBlock(position: OpenPosition?) {
    val tokens = LocalVanTokens.current
    if (position == null) return
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Risk", style = tokens.type.headline, color = tokens.color.textPrimary)
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                MetricTile("Approved risk", position.approvedRiskPct?.let { TradingFormat.percent(it * 100) } ?: "—", Modifier.weight(1f))
                MetricTile("Heat after", position.portfolioHeatAfter?.let { TradingFormat.percent(it * 100) } ?: "—", Modifier.weight(1f))
                MetricTile("Protection", if (position.protectionConfirmed) "Confirmed" else "Not confirmed", Modifier.weight(1f))
            }
        }
    }
}
