package com.dial.van.overlay
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.trading.TradingCommandCentreActivity
import com.dial.van.visual.VanGlassSurface

/**
 * The three workboard presentations: compact, expanded and maximized.
 *
 * Split from `VanOverlaySurface` for the same reason that file was split from the service
 * (P3-AND-009): one file per thing you would go looking for. The router and the surface
 * contract are next door; these are the bodies.
 */

@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun CompactWorkboard(
    state: VanOverlaySurfaceState,
    actions: VanOverlayActions,
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    caption: String,
    healthLine: String?,
    accent: Int,
    latestMessage: String?,
) {
    Box(modifier = Modifier.fillMaxSize()) {
        VanGlassSurface(
            style = glass,
            modifier = Modifier.fillMaxSize(),
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(start = 12.dp, end = 10.dp, top = 12.dp, bottom = 8.dp),
                verticalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Text(caption, color = Color(accent), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                if (!healthLine.isNullOrBlank()) {
                    Text(healthLine, color = Color(0xFFB8CBD2), fontSize = 10.sp, maxLines = 1)
                }
                if (!latestMessage.isNullOrBlank()) {
                    Text(latestMessage, color = Color(0xFFF4FCFF), fontSize = 11.sp, maxLines = 2)
                }
                if (state.workboardMode == VanWorkboardMode.CHAT) {
                    ChatComposer(app, accent, compact = true, draft = state.chatDraft, onDraft = actions.onDraft)
                } else {
                    ChipFlow {
                        WorkChip("Chat", accent) { actions.onChat(false) }
                        WorkChip("Voice", accent) { actions.onVoice() }
                        WorkChip("More", accent) { actions.onPresentation(VanOverlayPresentation.WORKBOARD_EXPANDED) }
                        WorkChip("Projects", accent) { actions.onCommandCentre("projects") }
                        WorkChip("Tasks", accent) { actions.onCommandCentre("tasks") }
                        WorkChip("Decisions", accent) { actions.onCommandCentre("decisions") }
                    }
                }
            }
        }
        Text(
            "Expand",
            color = Color(0xFFBDEFFF),
            fontSize = 10.sp,
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(9.dp)
                .clip(RoundedCornerShape(8.dp))
                .combinedClickable(onClick = { actions.onPresentation(VanOverlayPresentation.WORKBOARD_EXPANDED) })
                .padding(horizontal = 7.dp, vertical = 4.dp),
        )
    }
}

@Composable
internal fun ExpandedWorkboard(
    state: VanOverlaySurfaceState,
    actions: VanOverlayActions,
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    headline: String,
    caption: String,
    systemLine: String,
    accent: Int,
    messages: List<com.dial.van.control.VanConversationMessage>,
) {
    Box(modifier = Modifier.fillMaxSize()) {
        VanGlassSurface(
            style = glass,
            modifier = Modifier.fillMaxSize(),
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(start = 12.dp, end = 12.dp, top = 12.dp, bottom = 10.dp),
            ) {
                Text(headline, color = Color(accent), fontSize = 14.sp, fontWeight = FontWeight.Bold)
                Text(caption, color = Color(0xFFF4FCFF), fontSize = 11.sp, maxLines = 2)
                Text(systemLine, color = Color(0xFFB8CBD2), fontSize = 10.sp, maxLines = 1)
                Spacer(Modifier.height(6.dp))
                ChipFlow {
                    WorkChip("Chat", accent) { actions.onChat(true) }
                    WorkChip("Voice", accent) { actions.onVoice() }
                    WorkChip("Trades", accent) { actions.onWorkboardMode(VanWorkboardMode.TRADES) }
                    WorkChip("Max", accent) { actions.onPresentation(VanOverlayPresentation.WORKBOARD_MAXIMIZED) }
                }
                Spacer(Modifier.height(6.dp))
                when (state.workboardMode) {
                    VanWorkboardMode.CHAT,
                    VanWorkboardMode.VOICE,
                    -> {
                        LazyColumn(
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                            verticalArrangement = Arrangement.spacedBy(5.dp),
                        ) {
                            items(messages.takeLast(20), key = { it.id }) { message ->
                                ConversationBubble(message.role, message.text, accent)
                            }
                        }
                        ChatComposer(app, accent, compact = false, draft = state.chatDraft, onDraft = actions.onDraft)
                    }
                    VanWorkboardMode.TRADES -> {
                        TradesWorkboardPanel(
                            app = app,
                            accent = accent,
                            view = state.tradeView,
                            refresh = state.tradeRefreshTick,
                            onView = actions.onTradeView,
                            onRefresh = actions.onTradeRefresh,
                            onOpenRoute = actions.onTradingRoute,
                        )
                    }
                    VanWorkboardMode.CONTEXT -> {
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .fillMaxWidth()
                                .verticalScroll(rememberScrollState()),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            ContextAction("Projects", "Open mounted Project Truth contexts") { actions.onCommandCentre("projects") }
                            ContextAction("Tasks", "Inspect queued and active work") { actions.onCommandCentre("tasks") }
                            ContextAction("Decisions", "Review owner decisions and approvals") { actions.onCommandCentre("decisions") }
                            ContextAction("Systems", "Inspect Hermes, gateway and mesh health") { actions.onCommandCentre("systems") }
                            ContextAction("Trading", "Open VATI portfolio, trades, risk and accounts") {
                                actions.onTradingRoute(TradingCommandCentreActivity.ROUTE_OVERVIEW)
                            }
                            ContextAction("Command Centre", "Open the full owner admin surface") { actions.onCommandCentre(null) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
internal fun MaximizedWorkboard(
    state: VanOverlaySurfaceState,
    actions: VanOverlayActions,
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    headline: String,
    systemLine: String,
    accent: Int,
    messages: List<com.dial.van.control.VanConversationMessage>,
) {
    // Sized by the placement the service measured, like every board: the outer Box fills it.
    Box(modifier = Modifier.fillMaxSize()) {
        VanGlassSurface(style = glass, modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(start = 14.dp, end = 14.dp, top = 14.dp, bottom = 12.dp),
            ) {
                Text("Van • $headline", color = Color(accent), fontSize = 15.sp, fontWeight = FontWeight.Bold)
                Text(systemLine, color = Color(0xFFB8CBD2), fontSize = 10.sp)
                Spacer(Modifier.height(6.dp))
                ChipFlow {
                    WorkChip("Chat", accent) { actions.onWorkboardMode(VanWorkboardMode.CHAT) }
                    WorkChip("Voice", accent) { actions.onVoice() }
                    WorkChip("Trades", accent) {
                        actions.onTradingRoute(TradingCommandCentreActivity.ROUTE_OVERVIEW)
                    }
                    WorkChip("Collapse", accent) { actions.onPresentation(VanOverlayPresentation.WORKBOARD_EXPANDED) }
                    WorkChip("Admin", accent) { actions.onCommandCentre(null) }
                }
                Spacer(Modifier.height(8.dp))
                LazyColumn(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    items(messages, key = { it.id }) { message ->
                        ConversationBubble(message.role, message.text, accent)
                    }
                }
                ChatComposer(app, accent, compact = false, draft = state.chatDraft, onDraft = actions.onDraft)
            }
        }
    }
}
