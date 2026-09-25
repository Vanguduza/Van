package com.dial.van.overlay

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.control.VanCommandSource
import com.dial.van.control.VanMessageRole
import com.dial.van.trading.TradeBookParser
import com.dial.van.trading.TradeBookState
import com.dial.van.trading.TradeRow
import com.dial.van.trading.TradeView
import com.dial.van.trading.TradingCommandCentreActivity
import com.dial.van.trading.TradingFormat
import com.dial.van.visual.VanGlassTokens

/**
 * The overlay's panels, as composables rather than as members of a Service.
 *
 * Rev 3.0 §41 and P3-AND-009. `FloatingOverlayService` was 1,096 lines: a foreground
 * service, a WindowManager client, a drag controller and an entire Compose tree, all in one
 * class, with every panel reading the service's own mutable fields directly. These are the
 * pieces that never needed to: given their inputs they draw, and what used to be a field
 * read is now a parameter.
 *
 * The service keeps the window and the lifecycle, which is what §41 says it is for. What
 * remains inside it are the panels that genuinely drive presentation transitions, and the
 * gesture arithmetic now lives in `VanOverlayController`, where it is executed in
 * `android/verification`.
 */

@Composable
internal fun ColumnScope.TradesWorkboardPanel(
    app: VanApplication,
    accent: Int,
    view: TradeView,
    refresh: Int,
    onView: (TradeView) -> Unit,
    onRefresh: () -> Unit,
    onOpenRoute: (String) -> Unit,
) {
    var state: TradeBookState by remember { mutableStateOf(TradeBookState.Loading) }
    LaunchedEffect(view, refresh) {
        state = runCatching { app.gatewayClient.tradingTrades(view.query) }.fold(
            onSuccess = { TradeBookParser.parse(view, it) },
            onFailure = { TradeBookState.Unavailable(view, TradingFormat.unavailableState(null)) },
        )
    }
    Column(modifier = Modifier.fillMaxWidth().weight(1f)) {
        ChipFlow {
            TradeView.entries.forEach { candidate ->
                WorkChip(candidate.label, accent) { onView(candidate) }
            }
            WorkChip("Refresh", accent) { onRefresh() }
            WorkChip("Open", accent) {
                onOpenRoute(TradingCommandCentreActivity.tradesRoute(view))
            }
        }
        Spacer(Modifier.height(5.dp))
        when (val current = state) {
            TradeBookState.Loading -> Text("Reading the trading ledger…", color = Color(0xFFB6C2D0), fontSize = 10.sp)
            is TradeBookState.Unavailable ->
                Text(current.reason, color = Color(0xFFFFB300), fontSize = 10.sp, maxLines = 3)
            is TradeBookState.Ready -> {
                if (!current.ledgerAvailable) {
                    Text(TradingFormat.unavailableState(null), color = Color(0xFFFFB300), fontSize = 10.sp, maxLines = 3)
                } else if (current.rows.isEmpty()) {
                    Text(view.emptyCopy, color = Color(0xFFB6C2D0), fontSize = 10.sp)
                } else {
                    LazyColumn(modifier = Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        items(current.rows.take(8)) { row -> TradeWorkboardRow(row, accent, onOpenRoute) }
                    }
                }
            }
        }
        // P2-UX-001 — was "Read-only preview · confidence is an uncalibrated rule score ·
        // Risk Authority owns sizing", which is three internal terms in one line of 8sp text.
        Text(
            "Shown here only. Van does not place or change trades.",
            color = Color(0xFF7F9099),
            fontSize = 8.sp,
            maxLines = 2,
        )
    }
}


@Composable
internal fun TradeWorkboardRow(row: TradeRow, accent: Int, onOpenRoute: (String) -> Unit) {
    ContextAction(row.headline, "${row.confidence.percentLabel} ${row.confidence.band.label}") {
        onOpenRoute(
            row.tradeIntentId?.let { TradingCommandCentreActivity.tradeRoute(it) }
                ?: "instrument/${row.symbol}",
        )
    }
}


@Composable
internal fun ChatComposer(
    app: VanApplication,
    accent: Int,
    compact: Boolean,
    draft: String,
    onDraft: (String) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        OutlinedTextField(
            value = draft,
            onValueChange = onDraft,
            modifier = Modifier.weight(1f),
            singleLine = compact,
            maxLines = if (compact) 1 else 3,
            label = { Text("Command", fontSize = 10.sp) },
        )
        WorkChip("Send", accent) {
            val text = draft.trim()
            if (text.isNotEmpty()) {
                app.commandController.submitText(text, VanCommandSource.CHAT)
                onDraft("")
            }
        }
    }
}


@Composable
internal fun ConversationBubble(role: VanMessageRole, text: String, accent: Int) {
    val background = when (role) {
        VanMessageRole.OWNER -> Color(accent).copy(alpha = 0.18f)
        VanMessageRole.VAN -> Color(0xFFBDEFFF).copy(alpha = 0.11f)
        VanMessageRole.SYSTEM -> Color(0xFFFFB300).copy(alpha = 0.12f)
    }
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(background)
            .padding(8.dp),
    ) {
        Text(text, color = Color(0xFFF4FCFF), fontSize = 11.sp)
    }
}


@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun ContextAction(title: String, detail: String, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Color(VanGlassTokens.BABY_CYAN).copy(alpha = 0.08f))
            .combinedClickable(onClick = onClick)
            .padding(9.dp),
    ) {
        Column {
            Text(title, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
            Text(detail, color = Color(0xFFB8CBD2), fontSize = 10.sp)
        }
    }
}


@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun WorkChip(label: String, accent: Int, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .height(30.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(Color(accent).copy(alpha = 0.16f))
            .combinedClickable(onClick = onClick)
            .padding(horizontal = 7.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = Color(0xFFF4FCFF), fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
    }
}


/**
 * A board's chips, wrapping onto a second line rather than running past its edge: a board
 * is as narrow as the room beside VAN, and a chip clipped by the glass is a chip nobody can
 * press.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun ChipFlow(content: @Composable () -> Unit) {
    FlowRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(5.dp),
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) { content() }
}


@Composable
internal fun DismissTarget(armed: Boolean) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(
            modifier = Modifier
                .size((if (armed) OverlayTheme.DISMISS_VISUAL_DP + 8 else OverlayTheme.DISMISS_VISUAL_DP).dp)
                .clip(CircleShape),
        ) {
            drawCircle(
                color = if (armed) Color(0xFFEF4444).copy(alpha = 0.92f)
                else Color(0xFF101820).copy(alpha = 0.84f),
            )
            val inset = size.minDimension * 0.31f
            val width = (size.minDimension * 0.065f).coerceAtLeast(2f)
            drawLine(
                Color.White,
                Offset(inset, inset),
                Offset(size.width - inset, size.height - inset),
                width,
                StrokeCap.Round,
            )
            drawLine(
                Color.White,
                Offset(size.width - inset, inset),
                Offset(inset, size.height - inset),
                width,
                StrokeCap.Round,
            )
        }
    }
}
