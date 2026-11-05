package com.dial.van.overlay

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
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
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
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
    var state: TradeBookState by remember(view, refresh) { mutableStateOf(TradeBookState.Loading) }
    LaunchedEffect(view, refresh) {
        // Never leave a previous account/view's rows under the newly selected tab.
        state = TradeBookState.Loading
        state = runCatching {
            val response = app.gatewayClient.tradingTrades(view.query)
            currentCoroutineContext().ensureActive()
            response
        }.fold(
            onSuccess = { TradeBookParser.parse(view, it) },
            onFailure = { failure ->
                if (failure is kotlinx.coroutines.CancellationException) throw failure
                TradeBookState.Unavailable(view, TradingFormat.unavailableState(null))
            },
        )
    }
    Column(modifier = Modifier.fillMaxWidth().weight(1f)) {
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
            TradeView.entries.forEach { candidate ->
                WorkChip(candidate.label, accent, selected = candidate == view) { onView(candidate) }
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
                Text(current.reason, color = Color(0xFFFFB300), fontSize = 12.sp, maxLines = 3)
            is TradeBookState.Ready -> {
                if (!current.ledgerAvailable) {
                    Text(TradingFormat.unavailableState(null), color = Color(0xFFFFB300), fontSize = 12.sp, maxLines = 3)
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
            fontSize = 12.sp,
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
    val conversation by app.commandController.state.collectAsState()
    var sendError by remember { mutableStateOf<String?>(null) }
    val draftGate = remember { OverlaySubmissionGuard() }
    val draftLease = draftGate.observe(draft)
    fun send() {
        // Read the controller now, not a stale composition. The controller marks
        // submitting synchronously, so a double-click/IME replay cannot resend.
        runCatching {
            draftGate.submit(draft, draftLease, app.commandController.state.value.submitting) { text ->
                val previous = app.commandController.state.value.messages.map { it.id }.toSet()
                app.commandController.submitText(text, VanCommandSource.CHAT)
                app.commandController.state.value.messages.any {
                    it.id !in previous && it.role == VanMessageRole.OWNER && it.text == text
                }
            }
        }.onSuccess { result ->
            if (result == OverlaySubmissionGuard.Result.LOCALLY_RECORDED) { draftGate.observe(""); sendError = null; onDraft("") }
            if (result == OverlaySubmissionGuard.Result.NOT_RECORDED) sendError = "Message not submitted. Your draft is still here."
        }.onFailure { sendError = "Message not submitted. Your draft is still here." }
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(3.dp)) {
    val feedback = sendError ?: when {
        conversation.submitting -> "Sending your message…"
        conversation.pendingA4Approval != null -> "Approval is required. Review the exact action in Command Centre."
        conversation.lastError != null -> "Request needs attention. Check its status in the conversation before sending again."
        else -> null
    }
    if (feedback != null) Text(feedback, color = Color(0xFFB8CBD2), fontSize = 12.sp,
        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        OutlinedTextField(
            value = draft,
            onValueChange = { draftGate.observe(it); sendError = null; onDraft(it) },
            modifier = Modifier.weight(1f),
            singleLine = compact,
            maxLines = if (compact) 1 else 3,
            label = { Text("Message VAN", fontSize = 12.sp) },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { send() }),
        )
        WorkChip("Send", accent, enabled = OverlayUsabilityPolicy.canSubmit(draft, conversation.submitting)) { send() }
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
        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(when (role) { VanMessageRole.OWNER -> "You"; VanMessageRole.VAN -> "VAN"; VanMessageRole.SYSTEM -> "Status" },
                color = Color(0xFFB8CBD2), fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
            SelectionContainer { Text(text, color = Color(0xFFF4FCFF), fontSize = 13.sp) }
        }
    }
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
