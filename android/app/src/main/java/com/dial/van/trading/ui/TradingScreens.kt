package com.dial.van.trading.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.trading.AccountCard
import com.dial.van.trading.ChartGeometry
import com.dial.van.trading.ChartLevel
import com.dial.van.trading.DataState
import com.dial.van.trading.LevelKind
import com.dial.van.trading.Loaded
import com.dial.van.trading.MarketStateCard
import com.dial.van.trading.PortfolioSummary
import com.dial.van.trading.RiskView
import com.dial.van.trading.TradeDetail
import com.dial.van.trading.TradeRow
import com.dial.van.trading.TradeView
import com.dial.van.trading.TradingFormat
import com.dial.van.trading.TradingRepository
import com.dial.van.trading.BarSeries
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanGlassStyle
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanVisualState

/** Navigation callbacks the screens need; the activity binds them to NavController routes. */
class TradingNav(val openTrade: (String) -> Unit, val openInstrument: (String) -> Unit, val openTrades: (TradeView) -> Unit, val openRisk: () -> Unit, val openAccounts: () -> Unit, val openChat: () -> Unit)

class ScreenEnv(val repo: TradingRepository, val glass: VanGlassStyle, val budget: VanEffectBudget, val vanState: VanVisualState, val vanHeadline: String, val now: () -> Long)

@Composable
private fun RefreshAction(onClick: () -> Unit) {
    Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = TradingColors.accent, modifier = Modifier.size(18.dp).clickable(onClick = onClick))
}

// ---------------------------------------------------------------- Overview / Command Center
@Composable
fun OverviewScreen(env: ScreenEnv, nav: TradingNav, padding: PaddingValues) {
    var tick by remember { mutableIntStateOf(0) }
    var portfolio: Loaded<PortfolioSummary> by remember { mutableStateOf(Loaded.Loading) }
    var states: Loaded<List<MarketStateCard>> by remember { mutableStateOf(Loaded.Loading) }
    var scope by remember { mutableStateOf("ALL") }

    LaunchedEffect(tick) {
        portfolio = Loaded.Loading
        states = Loaded.Loading
        portfolio = env.repo.portfolio()
        states = env.repo.marketStates()
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 10.dp),
    ) {
        item {
            LoadedBox(portfolio) { p ->
                val scoped = if (scope == "ALL") p.accounts else p.accounts.filter { it.alias == scope }
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TabRowChips(listOf("ALL") + p.accounts.map { it.alias }, scope) { scope = it }
                        Spacer(Modifier.weight(1f))
                        RefreshAction { tick += 1 }
                    }
                    Spacer(Modifier.height(6.dp))
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(
                            "Scope: ${if (scope == "ALL") "All accounts" else scoped.firstOrNull()?.label ?: scope}",
                            color = TradingColors.text,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                        scoped.firstOrNull()?.let { if (scope != "ALL") SafetyChip(it.safety) }
                        DataStateChip(if (scope == "ALL") p.overallDataState else scoped.firstOrNull()?.connection ?: DataState.UNKNOWN)
                        if (!p.ledgerAvailable) Chip("LEDGER UNAVAILABLE", DataState.OFFLINE.argb, filled = true)
                    }
                    Spacer(Modifier.height(8.dp))
                    val eq = if (scope == "ALL") p.equity else scoped.firstOrNull()?.equity
                    val bal = if (scope == "ALL") p.balance else scoped.firstOrNull()?.balance
                    val fl = if (scope == "ALL") p.floatingPnl else scoped.firstOrNull()?.floatingPnl
                    val day = if (scope == "ALL") p.dayPnl else scoped.firstOrNull()?.dayPnl
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricTile("Balance ${p.reportingCurrency}", bal?.plain ?: "—", Modifier.weight(1f))
                        MetricTile("Equity", eq?.plain ?: "—", Modifier.weight(1f))
                        MetricTile("Floating P&L", fl?.signed ?: "—", Modifier.weight(1f), tint = TradingColors.signed(fl?.value))
                    }
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricTile("Today P&L", day?.signed ?: "—", Modifier.weight(1f), tint = TradingColors.signed(day?.value))
                        MetricTile("Risk used", p.portfolioHeat.label, Modifier.weight(1f), tint = TradingColors.warning)
                        MetricTile(
                            "Drawdown",
                            (if (scope == "ALL") p.accounts.mapNotNull { it.drawdown.fraction }.maxOrNull()?.let {
                                TradingFormat.percent(it * 100)
                            } else scoped.firstOrNull()?.drawdown?.label) ?: "—",
                            Modifier.weight(1f),
                        )
                    }
                }
            }
        }

        item {
            LoadedBox(portfolio) { p ->
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        QuickAccess(
                            "Open positions",
                            "${p.openPositions.size} current/working",
                            Modifier.weight(1f),
                        ) { nav.openTrades(TradeView.CURRENT) }
                        QuickAccess(
                            "Potential trades",
                            "${p.potential.size} candidate setup(s)",
                            Modifier.weight(1f),
                        ) { nav.openTrades(TradeView.POTENTIAL) }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        QuickAccess(
                            "Recent trades",
                            "${p.recent.size} ledger result(s)",
                            Modifier.weight(1f),
                        ) { nav.openTrades(TradeView.PAST) }
                        QuickAccess(
                            "Risk Center",
                            "Exposure, heat & limits",
                            Modifier.weight(1f),
                        ) { nav.openRisk() }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        QuickAccess(
                            "Accounts",
                            "${p.accounts.size} registered account(s)",
                            Modifier.weight(1f),
                        ) { nav.openAccounts() }
                        val market = (states as? Loaded.Ready)?.value?.firstOrNull()
                        QuickAccess(
                            "Market workspace",
                            market?.let { "${it.symbol} · ${it.trend}/${it.vol}" } ?: "Open instrument analysis",
                            Modifier.weight(1f),
                        ) {
                            market?.symbol?.let(nav.openInstrument)
                        }
                    }
                }
            }
        }

        item {
            SectionPanel(title = "Van market brief", glass = env.glass) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    VanEmbodiment(
                        state = env.vanState,
                        budget = env.budget,
                        presentation = VanPresentation.COMPACT,
                        modifier = Modifier.size(76.dp),
                    )
                    Spacer(Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(env.vanHeadline, color = TradingColors.accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                        LoadedBox(states, empty = "No market state yet.") { ms ->
                            val m = ms.firstOrNull()
                            if (m == null) {
                                EmptyState(TradingFormat.emptyState("bars"))
                            } else {
                                Text(m.summary, color = TradingColors.text, fontSize = 11.sp)
                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    DataStateChip(m.dataState)
                                    Chip(m.session, 0xFF5C6BC0L)
                                }
                            }
                        }
                        Spacer(Modifier.height(5.dp))
                        Text(
                            "Ask Van →",
                            color = TradingColors.accent,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.clickable { nav.openChat() },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun QuickAccess(title: String, sub: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Column(modifier = modifier.clip(RoundedCornerShape(12.dp)).background(Color.White.copy(alpha = 0.05f)).clickable(onClick = onClick).padding(12.dp)) {
        Text(title, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        Text(sub, color = TradingColors.muted, fontSize = 10.sp)
    }
}

@Composable
fun AccountRow(a: AccountCard, nowMs: Long) {
    Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(Color.White.copy(alpha = 0.04f)).padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(modifier = Modifier.weight(1f)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) { Text(a.label, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold); SafetyChip(a.safety); DataStateChip(a.connection) }
            Text("${a.broker} · ${a.mode} · ${a.currency} · ${a.openPositions} open · synced ${TradingFormat.age(nowMs, a.lastSyncMs)}", color = TradingColors.muted, fontSize = 10.sp)
            if (a.killSwitch.isNotEmpty()) Text("Kill switch: ${a.killSwitch.joinToString()}", color = TradingColors.negative, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(a.equity.plain, color = TradingColors.text, fontSize = 13.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
            Text(a.dayPnl.signed, color = TradingColors.signed(a.dayPnl.value), fontSize = 11.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

// ---------------------------------------------------------------- Trades list
@Composable
fun TradesScreen(env: ScreenEnv, nav: TradingNav, padding: PaddingValues, initial: TradeView) {
    var view by remember { mutableStateOf(initial) }
    var tick by remember { mutableIntStateOf(0) }
    var rows: Loaded<List<TradeRow>> by remember { mutableStateOf(Loaded.Loading) }
    LaunchedEffect(view, tick) { rows = Loaded.Loading; rows = env.repo.trades(view) }
    LazyColumn(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 10.dp)) {
        item { Row(verticalAlignment = Alignment.CenterVertically) { TabRowChips(TradeView.entries.map { it.label }, view.label) { l -> view = TradeView.entries.first { it.label == l } }; Spacer(Modifier.weight(1f)); RefreshAction { tick += 1 } } }
        item {
            LoadedBox(rows) { rs ->
                if (rs.isEmpty()) EmptyState(view.emptyCopy, if (view == TradeView.POTENTIAL) "Candidates appear here as soon as a session assesses a bar." else null)
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { rs.forEach { r -> TradeRowCard(r) { r.tradeIntentId?.let(nav.openTrade) ?: nav.openInstrument(r.symbol) } } }
            }
        }
        item { Text("Read model of the VATI ledger · confidence is an uncalibrated rule score · nothing here can place, size, modify or cancel a trade", color = TradingColors.muted, fontSize = 9.sp) }
    }
}

// ---------------------------------------------------------------- Trade detail
@Composable
fun TradeDetailScreen(env: ScreenEnv, nav: TradingNav, padding: PaddingValues, tradeIntentId: String) {
    var tick by remember { mutableIntStateOf(0) }
    var detail: Loaded<TradeDetail> by remember { mutableStateOf(Loaded.Loading) }
    LaunchedEffect(tradeIntentId, tick) { detail = Loaded.Loading; detail = env.repo.tradeDetail(tradeIntentId) }
    LazyColumn(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(vertical = 10.dp)) {
        item {
            LoadedBox(detail) { d ->
                val digits = TradingFormat.digitsFor(d.row.symbol)
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("${d.row.symbol} ${d.row.direction}", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                        Chip(d.row.state, if (d.view == TradeView.PAST) 0xFF78909CL else 0xFF00E5FFL)
                        ConfidenceChip(d.row.confidence)
                        Spacer(Modifier.weight(1f)); RefreshAction { tick += 1 }
                    }
                    Text("${d.row.strategyId} · account ${d.accountAlias ?: "?"} · capsule ${d.strategyState ?: "?"} · decided ${d.decidedMs?.let { TradingFormat.dateShort(it) + " " + TradingFormat.timeHm(it) } ?: "—"}", color = TradingColors.muted, fontSize = 10.sp)
                    SectionPanel(title = "Chart · ${d.chartTimeframe ?: "no lake data"}", glass = env.glass) {
                        val levels = listOfNotNull(d.fill?.let { ChartLevel(LevelKind.ENTRY, it, "ENTRY") } ?: d.entry?.let { ChartLevel(LevelKind.ENTRY, it, "ENTRY") }, d.stop?.let { ChartLevel(LevelKind.STOP, it, "STOP") }, d.target?.let { ChartLevel(LevelKind.TARGET, it, "TARGET") }, d.exit?.let { ChartLevel(LevelKind.EXIT, it, "EXIT") })
                        if (d.chart.isEmpty()) EmptyState(TradingFormat.emptyState("bars"), "The levels below come from the ledger and are shown whether or not there is a chart.")
                        else TradeChartCanvas(d.chart, levels = levels, markers = d.markers, digits = digits, heightDp = 240)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricTile("Entry", TradingFormat.price(d.fill ?: d.entry, digits), Modifier.weight(1f))
                        MetricTile("Stop", TradingFormat.price(d.stop, digits), Modifier.weight(1f), tint = TradingColors.negative)
                        MetricTile("Target", TradingFormat.price(d.target, digits), Modifier.weight(1f), tint = TradingColors.positive)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricTile("Size", d.approvedSize ?: "—", Modifier.weight(1f))
                        MetricTile("Risk", d.approvedRisk.label, Modifier.weight(1f))
                        MetricTile("R:R", ChartGeometry.riskReward(d.fill ?: d.entry, d.stop, d.target)?.let { String.format(java.util.Locale.ROOT, "1:%.1f", it) } ?: "—", Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricTile("P&L", d.pnl.signed, Modifier.weight(1f), tint = TradingColors.signed(d.pnl.value))
                        MetricTile("R multiple", TradingFormat.r(d.rMultiple), Modifier.weight(1f), tint = TradingColors.signed(d.rMultiple))
                        MetricTile("Outcome", d.outcome ?: d.riskDecision ?: "—", Modifier.weight(1f), sub = d.polarity)
                    }
                    SectionPanel(title = "Timeline", glass = env.glass) {
                        if (d.timeline.isEmpty()) EmptyState("Nothing has happened on this trade yet.")
                        d.timeline.forEach { t ->
                            Row(modifier = Modifier.padding(vertical = 3.dp)) {
                                Text(TradingFormat.timeHm(t.atMs), color = TradingColors.muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace, modifier = Modifier.width(44.dp))
                                Column { Text(t.kind, color = TradingColors.accent, fontSize = 10.sp, fontWeight = FontWeight.SemiBold); Text(t.text, color = TradingColors.text, fontSize = 11.sp) }
                            }
                        }
                    }
                    SectionPanel(title = "Van's interpretation", glass = env.glass) {
                        d.interpretation.forEach { Text("• $it", color = TradingColors.text, fontSize = 11.sp, modifier = Modifier.padding(vertical = 2.dp)) }
                        if (d.lessons.isNotEmpty()) { Spacer(Modifier.height(4.dp)); Text("Review lessons", color = TradingColors.muted, fontSize = 10.sp); d.lessons.forEach { Text("• $it", color = TradingColors.text, fontSize = 11.sp) } }
                        Spacer(Modifier.height(6.dp))
                        Text("Ask Van about this trade →", color = TradingColors.accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable { nav.openChat() })
                    }
                    SectionPanel(title = "Evidence", glass = env.glass) {
                        Text("decision ${TradingFormat.hash8(d.decisionHash)} · market state ${TradingFormat.hash8(d.marketSnapshotHash)} · intent ${d.tradeIntentId.take(8)}", color = TradingColors.muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                        d.multipliers.forEach { (k, v) -> Text("$k = $v", color = TradingColors.muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace) }
                        d.costRatio?.let { Text("execution cost ratio ${String.format(java.util.Locale.ROOT, "%.2f", it)}×", color = if (it > 1.2) TradingColors.warning else TradingColors.muted, fontSize = 10.sp) }
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------- Instrument workspace
@Composable
fun InstrumentScreen(env: ScreenEnv, nav: TradingNav, padding: PaddingValues, symbol: String) {
    var tf by remember { mutableStateOf("H1") }
    var tick by remember { mutableIntStateOf(0) }
    var bars: Loaded<BarSeries> by remember { mutableStateOf(Loaded.Loading) }
    var state: Loaded<List<MarketStateCard>> by remember { mutableStateOf(Loaded.Loading) }
    var potential: Loaded<List<TradeRow>> by remember { mutableStateOf(Loaded.Loading) }
    var current: Loaded<List<TradeRow>> by remember { mutableStateOf(Loaded.Loading) }
    LaunchedEffect(symbol, tf, tick) { bars = Loaded.Loading; bars = env.repo.bars(symbol, tf, 300) }
    LaunchedEffect(symbol, tick) { state = env.repo.marketStates(symbol); potential = env.repo.trades(TradeView.POTENTIAL); current = env.repo.trades(TradeView.CURRENT) }
    val digits = TradingFormat.digitsFor(symbol)
    LazyColumn(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(vertical = 10.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(symbol, color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.width(10.dp)); TabRowChips(listOf("M15", "H1", "H4", "D1"), tf) { tf = it }
                Spacer(Modifier.weight(1f)); RefreshAction { tick += 1 }
            }
        }
        item {
            SectionPanel(title = "Chart", glass = env.glass) {
                LoadedBox(bars) { b ->
                    Column {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            DataStateChip(b.dataState); if (b.isSimulated) Chip("SIMULATED DATA", DataState.SIMULATED.argb)
                            b.bars.lastOrNull()?.let { Text("last ${TradingFormat.price(it.c, digits)}", color = TradingColors.text, fontSize = 11.sp, fontFamily = FontFamily.Monospace) }
                        }
                        val levels = (current as? Loaded.Ready)?.value?.filter { it.symbol == symbol }?.mapNotNull { it.stopPrice?.let { s -> ChartLevel(LevelKind.STOP, s, "STOP") } } ?: emptyList()
                        TradeChartCanvas(b.bars, levels = levels, digits = digits, heightDp = 260, maxVisible = 150)
                    }
                }
            }
        }
        item {
            SectionPanel(title = "Market context", glass = env.glass) {
                LoadedBox(state) { ms ->
                    val m = ms.firstOrNull()
                    if (m == null) EmptyState("No price information for $symbol yet. VAN shows what the trading system has recorded; it does not fetch prices itself.")
                    else Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(m.summary, color = TradingColors.text, fontSize = 12.sp)
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { DataStateChip(m.dataState); Chip(m.session, 0xFF5C6BC0L); Chip("integrity ${m.integrity}", 0xFF78909CL); Chip("events ${m.eventWindow}", 0xFFFFB300L) }
                        m.lastDecision?.let { Text("Last assessment: $it${m.lastDecisionReason?.let { r -> " — $r" } ?: ""}", color = TradingColors.muted, fontSize = 10.sp) }
                        m.minutesToEvent?.let { Text("Next Tier-1 event in $it min", color = TradingColors.warning, fontSize = 10.sp) }
                        Spacer(Modifier.height(4.dp))
                        Text("Indicators", color = TradingColors.muted, fontSize = 10.sp)
                        m.features.entries.sortedBy { it.key }.chunked(2).forEach { pair ->
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { pair.forEach { (k, v) -> MetricTile(k, v.take(10), Modifier.weight(1f)) } }
                        }
                    }
                }
            }
        }
        item {
            SectionPanel(title = "Setups & positions on $symbol", glass = env.glass) {
                LoadedBox(potential) { ps ->
                    val mine = ps.filter { it.symbol == symbol }
                    if (mine.isEmpty()) EmptyState("No setup on $symbol in the latest look.")
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { mine.forEach { r -> TradeRowCard(r) { r.tradeIntentId?.let(nav.openTrade) } } }
                }
                LoadedBox(current) { cs ->
                    val mine = cs.filter { it.symbol == symbol }
                    if (mine.isNotEmpty()) { Spacer(Modifier.height(6.dp)); Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { mine.forEach { r -> TradeRowCard(r) { r.tradeIntentId?.let(nav.openTrade) } } } }
                }
                Spacer(Modifier.height(6.dp))
                Text("Ask Van about $symbol →", color = TradingColors.accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable { nav.openChat() })
            }
        }
    }
}

// ---------------------------------------------------------------- Risk Center
@Composable
fun RiskScreen(env: ScreenEnv, nav: TradingNav, padding: PaddingValues) {
    var tick by remember { mutableIntStateOf(0) }
    var risk: Loaded<RiskView> by remember { mutableStateOf(Loaded.Loading) }
    LaunchedEffect(tick) { risk = Loaded.Loading; risk = env.repo.risk() }
    LazyColumn(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(vertical = 10.dp)) {
        item { Row(verticalAlignment = Alignment.CenterVertically) { Text("Risk Center", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold); Spacer(Modifier.weight(1f)); RefreshAction { tick += 1 } } }
        item {
            LoadedBox(risk) { r ->
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (r.killSwitch.isNotEmpty()) Chip("KILL SWITCH: ${r.killSwitch.joinToString()}", DataState.OFFLINE.argb, filled = true)
                    SectionPanel(title = "Portfolio risk", glass = env.glass) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            MetricTile("Heat (open stop risk)", r.portfolioHeat.label, Modifier.weight(1f), tint = TradingColors.warning, sub = r.limits["max_open_stop_risk"]?.let { "cap ${TradingFormat.percent(it.toDoubleOrNull()?.times(100))}" })
                            MetricTile("Drawdown from peak", r.drawdownFromPeak.label, Modifier.weight(1f), sub = r.limits["max_weekly_drawdown"]?.let { "weekly cap ${TradingFormat.percent(it.toDoubleOrNull()?.times(100))}" })
                            MetricTile("Equity", r.equity.plain, Modifier.weight(1f))
                        }
                        Spacer(Modifier.height(8.dp))
                        r.heatUtilisation?.let { u ->
                            Text("Heat utilisation ${TradingFormat.percent(u * 100, decimals = 0)} of your risk ceiling", color = TradingColors.muted, fontSize = 10.sp)
                            Box(modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(Color.White.copy(alpha = 0.08f))) {
                                Box(modifier = Modifier.fillMaxWidth(u.coerceIn(0.0, 1.0).toFloat()).height(8.dp).background(if (u > 0.8) TradingColors.negative else if (u > 0.5) TradingColors.warning else TradingColors.positive))
                            }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                            MetricTile("Today", r.dayPnlPct.label, Modifier.weight(1f), tint = TradingColors.signed(r.dayPnlPct.fraction), sub = r.limits["max_daily_loss"]?.let { "daily loss cap ${TradingFormat.percent(it.toDoubleOrNull()?.times(100))}" })
                            MetricTile("Week", r.weekPnlPct.label, Modifier.weight(1f), tint = TradingColors.signed(r.weekPnlPct.fraction))
                            MetricTile("Consecutive losses", r.consecutiveLosses?.toString() ?: "—", Modifier.weight(1f), sub = r.limits["max_consecutive_losses"]?.let { "cap $it" })
                        }
                        r.lastDecision?.let { Text("Last Risk Authority decision: $it${r.lastReasonCode?.takeIf { c -> c.isNotBlank() }?.let { c -> " ($c)" } ?: ""}", color = TradingColors.muted, fontSize = 10.sp, modifier = Modifier.padding(top = 6.dp)) }
                    }
                    SectionPanel(title = "Concentration", glass = env.glass) {
                        if (r.bySymbol.isEmpty()) EmptyState(TradingFormat.emptyState("risk"))
                        ConcentrationBars("By instrument", r.bySymbol); ConcentrationBars("By currency leg", r.byCurrency)
                        if (r.byDirection.isNotEmpty()) Text("Direction: " + r.byDirection.entries.joinToString { "${it.key} ${it.value}" }, color = TradingColors.muted, fontSize = 10.sp)
                    }
                    SectionPanel(title = "Position risk", glass = env.glass) {
                        if (r.positions.isEmpty()) EmptyState(TradingFormat.emptyState("open"))
                        r.positions.forEach { p ->
                            Row(modifier = Modifier.fillMaxWidth().clickable { nav.openTrade(p.tradeIntentId) }.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text("${p.symbol} ${p.direction.lowercase()}", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                Text("risk ${p.riskPct.label} · size ${p.size ?: "?"} · stop ${p.stop ?: "?"}", color = TradingColors.neutral, fontSize = 10.sp)
                            }
                        }
                    }
                    SectionPanel(title = "Mandate limits", glass = env.glass) {
                        if (r.limits.isEmpty()) EmptyState(TradingFormat.emptyState("risk"))
                        // P3-AND-010 — this printed `max_open_stop_risk = 0.02` in a
                        // monospace font. The owner was reading the trading system's
                        // internal vocabulary off their own risk screen.
                        r.limits.forEach { (k, v) ->
                            Row(modifier = Modifier.fillMaxWidth()) {
                                Text(TradingFormat.label(k), color = TradingColors.text, fontSize = 11.sp, modifier = Modifier.weight(1f))
                                Text(
                                    v.toDoubleOrNull()?.let { TradingFormat.percent(it * 100) } ?: v,
                                    color = TradingColors.neutral,
                                    fontSize = 11.sp,
                                )
                            }
                        }
                        Text("Limits are owner-signed (A4); this screen reads them and can never change them.", color = TradingColors.muted, fontSize = 9.sp, modifier = Modifier.padding(top = 4.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun ConcentrationBars(title: String, values: Map<String, Double>) {
    if (values.isEmpty()) return
    val max = values.values.maxOrNull()?.takeIf { it > 0 } ?: 1.0
    Text(title, color = TradingColors.muted, fontSize = 10.sp, modifier = Modifier.padding(top = 4.dp))
    values.entries.sortedByDescending { it.value }.forEach { (k, v) ->
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 2.dp)) {
            Text(k, color = TradingColors.text, fontSize = 11.sp, modifier = Modifier.width(64.dp))
            Box(modifier = Modifier.weight(1f).height(8.dp).clip(RoundedCornerShape(4.dp)).background(Color.White.copy(alpha = 0.08f))) { Box(modifier = Modifier.fillMaxWidth((v / max).toFloat().coerceIn(0.02f, 1f)).height(8.dp).background(TradingColors.violet)) }
            Spacer(Modifier.width(6.dp)); Text(TradingFormat.percent(v * 100), color = TradingColors.muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

// ---------------------------------------------------------------- Accounts
@Composable
fun AccountsScreen(env: ScreenEnv, padding: PaddingValues, onAdd: () -> Unit = {}, onVerify: ((String) -> Unit)? = null) {
    var tick by remember { mutableIntStateOf(0) }
    var accounts: Loaded<List<AccountCard>> by remember { mutableStateOf(Loaded.Loading) }
    LaunchedEffect(tick) { accounts = Loaded.Loading; accounts = env.repo.accounts() }
    LazyColumn(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 10.dp)) {
        item { Row(verticalAlignment = Alignment.CenterVertically) { Text("Accounts", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold); Spacer(Modifier.weight(1f)); Text("+ Add account", color = TradingColors.accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable(onClick = onAdd).padding(end = 10.dp)); RefreshAction { tick += 1 } } }
        item {
            LoadedBox(accounts) { list ->
                if (list.isEmpty()) EmptyState(TradingFormat.emptyState("accounts"), "Tap + Add account to link Deriv, cTrader or MT5, or create a Deriv demo account here.")
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { list.forEach { AccountRow(it, env.now()) } }
            }
        }
        item { Text("Connection health, balances and risk state come from ACCOUNT_SNAPSHOT events written by each session. Credentials are never exposed in UI state or logs.", color = TradingColors.muted, fontSize = 9.sp) }
    }
}
