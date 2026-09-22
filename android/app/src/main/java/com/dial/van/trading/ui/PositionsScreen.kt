package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.dial.van.design.ThesisState
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPressable
import com.dial.van.trading.Loaded
import com.dial.van.trading.OpenPosition
import com.dial.van.trading.PositionsReadModel
import com.dial.van.trading.TradingFormat
import com.dial.van.trading.TradingRepository

/**
 * DNA §4 Trading destination 2, "Positions": [com.dial.van.design.components.PositionCard]s
 * (direction, exposure, unrealised R, protection state, thesis state chip, linked events
 * count, VAN's interpretation line), filterable by thesis state.
 *
 * @DataSource("GET /v1/trading/positions")
 */
@Composable
fun PositionsScreen(repo: TradingRepository, nav: TradingNav) {
    val tokens = LocalVanTokens.current
    var tick by remember { mutableIntStateOf(0) }
    var positions: Loaded<PositionsReadModel> by remember { mutableStateOf(Loaded.Loading) }
    var filter by remember { mutableStateOf<ThesisState?>(null) }

    LaunchedEffect(tick) { positions = repo.positions() }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        item {
            SectionHeader(
                title = "Positions",
                detail = (positions as? Loaded.Ready)?.value?.let { "${it.count} open" },
                trailing = { TradingRefreshAction { tick += 1 } },
            )
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                VanPressable(onClick = { filter = null }, contentDescription = "All") {
                    StatusChip(label = "All", role = StatusSemantics.ROLE_ENGAGED, filled = filter == null)
                }
                ThesisState.entries.forEach { state ->
                    val role = StatusSemantics.forThesisState(state)
                    VanPressable(onClick = { filter = state }, contentDescription = state.name) {
                        StatusChip(label = state.name.lowercase().replaceFirstChar { it.uppercase() }, role = role, filled = filter == state)
                    }
                }
            }
        }
        val loaded = positions
        when (loaded) {
            Loaded.Loading -> item { Text("Reading the ledger…", style = tokens.type.body, color = tokens.color.textSecondary) }
            is Loaded.Unavailable -> item {
                Text(
                    TradingFormat.unavailableState(loaded.reason),
                    style = tokens.type.body,
                    color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK),
                )
            }
            is Loaded.Ready -> {
                val rows = loaded.value.positions.filter { filter == null || it.thesisState == filter }
                if (rows.isEmpty()) {
                    item { Text("No positions match this filter.", style = tokens.type.body, color = tokens.color.textSecondary) }
                } else {
                    items(rows, key = { it.tradeIntentId }) { position -> PositionRow(position, nav) }
                }
            }
        }
        item {
            TradingDisclosure(
                "Read model of the VATI ledger; confidence and interpretation are VAN's own " +
                    "reading, never a permission. Nothing here can place, size, modify or cancel a trade.",
            )
        }
    }
}

@Composable
private fun PositionRow(position: OpenPosition, nav: TradingNav) {
    val tokens = LocalVanTokens.current
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
        OverviewPositionCard(position, nav)
        val interpretation = interpretationLine(position)
        if (interpretation != null) {
            Text(interpretation, style = tokens.type.label, color = tokens.color.textTertiary)
        }
        if (position.linkedEvents.isNotEmpty()) {
            Text("${position.linkedEvents.size} linked event(s)", style = tokens.type.label, color = tokens.color.textTertiary)
        }
    }
}

/** VAN's own short read on a position, from the same reasons the assessment read model gives. */
internal fun interpretationLine(position: OpenPosition): String? {
    val reasons = position.latestAssessment?.reasons
    if (!reasons.isNullOrEmpty()) return reasons.joinToString(" · ")
    val health = position.health?.reasons
    if (!health.isNullOrEmpty()) return health.joinToString(" · ")
    return position.thesis?.statement
}
