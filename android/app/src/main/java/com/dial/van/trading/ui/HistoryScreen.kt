package com.dial.van.trading.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
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
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.trading.ClosedTrade
import com.dial.van.trading.HistoryReadModel
import com.dial.van.trading.Loaded
import com.dial.van.trading.TradingFormat
import com.dial.van.trading.TradingReadModels
import com.dial.van.trading.TradingRepository

/**
 * DNA §4 Trading destination 5, "History & intelligence": closed trades with the decision
 * quadrant (never P&L alone, DNA §2/§6), attribution and lessons, and a small quadrant
 * distribution visual built from [TradingReadModels.quadrantTally]. There is no equity-curve
 * `Sparkline` here: `history()`'s response carries per-trade `r_multiple`/`pnl`, not a
 * ready-made R sequence, and this screen does not derive one — DNA's live-data rule is that a
 * panel shows what its `@DataSource` actually returned, never a value this screen computed to
 * fill the space.
 *
 * @DataSource("GET /v1/trading/history")
 */
@Composable
fun HistoryScreen(repo: TradingRepository, nav: TradingNav) {
    val tokens = LocalVanTokens.current
    var tick by remember { mutableIntStateOf(0) }
    var history: Loaded<HistoryReadModel> by remember { mutableStateOf(Loaded.Loading) }
    LaunchedEffect(tick) { history = repo.history(100) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        item {
            SectionHeader(
                title = "History & intelligence",
                detail = (history as? Loaded.Ready)?.value?.let { "${it.count} closed trade(s)" },
                trailing = { TradingRefreshAction { tick += 1 } },
            )
        }
        val loaded = history
        when (loaded) {
            Loaded.Loading -> item { Text("Reading the ledger…", style = tokens.type.body, color = tokens.color.textSecondary) }
            is Loaded.Unavailable -> item {
                Text(TradingFormat.unavailableState(loaded.reason), style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
            }
            is Loaded.Ready -> {
                item { QuadrantDistribution(loaded.value) }
                if (loaded.value.trades.isEmpty()) {
                    item { Text("No closed trades yet.", style = tokens.type.body, color = tokens.color.textSecondary) }
                } else {
                    items(loaded.value.trades, key = { it.tradeIntentId }) { trade -> ClosedTradeCard(trade) }
                }
            }
        }
        item {
            TradingDisclosure(
                "The decision quadrant, not the P&L sign, is the axis that changes what VAN " +
                    "does next (DNA §6). Read model of the VATI ledger.",
            )
        }
    }
}

@Composable
private fun QuadrantDistribution(model: HistoryReadModel) {
    val tokens = LocalVanTokens.current
    val counts = model.byQuadrant.ifEmpty { TradingReadModels.quadrantTally(model.trades) }
    if (counts.isEmpty()) return
    val total = counts.values.sum().coerceAtLeast(1)
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Decision quality distribution", style = tokens.type.headline, color = tokens.color.textPrimary)
            counts.entries.sortedByDescending { it.value }.forEach { (quadrant, count) ->
                QuadrantBar(quadrant, count, total)
            }
        }
    }
}

/**
 * A fraction bar tinted by the quadrant's own decision-quality role
 * ([TradingReadModels.roleForQuadrant]) rather than [com.dial.van.design.components.HeatBar]'s
 * magnitude-based escalation — a 90% share of GOOD_DECISION_GOOD_OUTCOME must read as
 * favourable, not as an over-budget warning the way a large fraction would on a heat bar.
 */
@Composable
private fun QuadrantBar(quadrant: String?, count: Int, total: Int) {
    val tokens = LocalVanTokens.current
    val fraction = (count.toFloat() / total).coerceIn(0f, 1f)
    val color = tokens.color.forStatusRole(TradingReadModels.roleForQuadrant(quadrant))
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Text(TradingReadModels.quadrantLabel(quadrant), style = tokens.type.label, color = tokens.color.textTertiary)
            Text("$count of $total", style = tokens.type.label, color = tokens.color.textTertiary)
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(6.dp)
                .clip(RoundedCornerShape(tokens.radius.s))
                .background(tokens.color.surface2),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(fraction)
                    .clip(RoundedCornerShape(tokens.radius.s))
                    .background(color),
            )
        }
    }
}

@Composable
private fun ClosedTradeCard(trade: ClosedTrade) {
    val tokens = LocalVanTokens.current
    val quadrantRole = TradingReadModels.roleForQuadrant(trade.quadrant?.quadrant)
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Text(trade.strategyId ?: trade.tradeIntentId.take(8), style = tokens.type.headline, color = tokens.color.textPrimary, modifier = Modifier.weight(1f))
                StatusChip(label = TradingReadModels.quadrantLabel(trade.quadrant?.quadrant), role = quadrantRole)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space4)) {
                Column { Text("R multiple", style = tokens.type.label, color = tokens.color.textTertiary); Text(TradingFormat.r(trade.rMultiple), style = tokens.type.data, color = tokens.color.textPrimary) }
                Column { Text("Outcome", style = tokens.type.label, color = tokens.color.textTertiary); Text(trade.outcome ?: "—", style = tokens.type.data, color = tokens.color.textPrimary) }
                trade.exitReason?.let { Column { Text("Exit", style = tokens.type.label, color = tokens.color.textTertiary); Text(it, style = tokens.type.data, color = tokens.color.textPrimary) } }
            }
            trade.attribution?.dominantBucket?.let {
                Text("Dominant attribution: $it", style = tokens.type.body, color = tokens.color.textSecondary)
            }
            if (trade.lessons.isNotEmpty()) {
                Text("Lessons", style = tokens.type.label, color = tokens.color.textTertiary)
                trade.lessons.forEach { lesson ->
                    Column {
                        lesson.keep?.let { Text("Keep: $it", style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_FAVOURABLE)) }
                        lesson.avoid?.let { Text("Avoid: $it", style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_DETERIORATING)) }
                    }
                }
            }
        }
    }
}
