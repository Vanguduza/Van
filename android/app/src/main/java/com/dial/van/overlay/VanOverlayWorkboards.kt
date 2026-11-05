package com.dial.van.overlay

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.distinctUntilChanged
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.control.VanConversationMessage
import com.dial.van.trading.TradingCommandCentreActivity
import com.dial.van.visual.VanGlassStyle
import com.dial.van.visual.VanGlassSurface
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanVisualState
import com.dial.van.visual.rememberVanEffectBudget

/** Existing presentations share one bounded responsive board; no negative avatar offsets. */
@Composable
internal fun CompactWorkboard(state: VanOverlaySurfaceState, actions: VanOverlayActions,
    app: VanApplication, visualState: VanVisualState, glass: VanGlassStyle,
    caption: String, healthLine: String?, accent: Int, latestMessage: String?, messages: List<VanConversationMessage> = emptyList()) = AdaptiveWorkboard(
        state, actions, app, visualState, glass, "VAN", caption, healthLine.orEmpty(), accent,
        messages, latestMessage,
    )

@Composable
internal fun ExpandedWorkboard(state: VanOverlaySurfaceState, actions: VanOverlayActions,
    app: VanApplication, visualState: VanVisualState, glass: VanGlassStyle, headline: String,
    caption: String, systemLine: String, accent: Int, messages: List<VanConversationMessage>) = AdaptiveWorkboard(
        state, actions, app, visualState, glass, headline, caption, systemLine, accent, messages,
        messages.lastOrNull()?.text,
    )

@Composable
internal fun MaximizedWorkboard(state: VanOverlaySurfaceState, actions: VanOverlayActions,
    app: VanApplication, visualState: VanVisualState, glass: VanGlassStyle, headline: String,
    systemLine: String, accent: Int, messages: List<VanConversationMessage>) = AdaptiveWorkboard(
        state, actions, app, visualState, glass, headline, "Your workboard", systemLine, accent,
        messages, messages.lastOrNull()?.text,
    )

@Composable
private fun AdaptiveWorkboard(
    state: VanOverlaySurfaceState, actions: VanOverlayActions, app: VanApplication,
    visualState: VanVisualState, glass: VanGlassStyle, headline: String, caption: String,
    systemLine: String, accent: Int, messages: List<VanConversationMessage>, latestMessage: String?,
) {
    val compact = state.presentation == VanOverlayPresentation.WORKBOARD_COMPACT
    val listening by remember(app) { app.voiceUi.state.map { it.listening }.distinctUntilChanged() }.collectAsState(false)
    val voiceTurn by app.voiceSession.ownerTurnActive.collectAsState()
    val speaking by remember(app) { app.ttsOutput.visualState.map { it.speaking }.distinctUntilChanged() }.collectAsState(false)
    val voiceActive = listening || voiceTurn || speaking
    val fallbackWidth = when (state.presentation) {
        VanOverlayPresentation.WORKBOARD_MAXIMIZED -> state.maximizedWidthDp
        VanOverlayPresentation.WORKBOARD_EXPANDED -> OverlayTheme.EXPANDED_WIDTH_DP.toFloat()
        else -> OverlayTheme.COMPACT_WIDTH_DP.toFloat()
    }
    val fallbackHeight = when (state.presentation) {
        VanOverlayPresentation.WORKBOARD_MAXIMIZED -> state.maximizedHeightDp
        VanOverlayPresentation.WORKBOARD_EXPANDED -> OverlayTheme.EXPANDED_HEIGHT_DP.toFloat()
        else -> OverlayTheme.COMPACT_HEIGHT_DP.toFloat()
    }
    BoxWithConstraints(Modifier.width((state.boardWidthDp ?: fallbackWidth).coerceAtLeast(1f).dp)
        .height((state.boardHeightDp ?: fallbackHeight).coerceAtLeast(1f).dp)) {
        val verySmall = maxHeight < (180f + 80f * LocalDensity.current.fontScale.coerceIn(1f, 2f)).dp || maxWidth < 220.dp
        VanGlassSurface(style = glass, modifier = Modifier.fillMaxSize().vanWorkboardKeyboard(state, actions)) {
            if (verySmall) {
                // With a large IME / split window, controls remain scrollable and
                // actionable rather than drawing beyond the allocated native window.
                LazyColumn(Modifier.fillMaxSize().padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    item { Text("VAN · $headline", color = Color(accent), fontSize = 14.sp, fontWeight = FontWeight.Bold,
                        modifier = Modifier.then(actions.dragHandle).vanAccessibleMovement(actions).semantics { contentDescription = "Drag VAN workboard" }) }
                    item { Text("Limited screen space", color = Color(0xFFB8CBD2), fontSize = 12.sp) }
                    item { WorkChip("Open full view", accent) { actions.onCommandCentre(null) } }
                    item { WorkChip("Return to VAN", accent) { actions.onPresentation(VanOverlayPresentation.FULL_FLOATING) } }
                    if (voiceActive) item { WorkChip("Stop voice", accent) { actions.onStopVoice() } }
                }
            } else {
                Column(Modifier.fillMaxSize().padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    BoardHeader(state, actions, visualState, headline, caption, accent, compact)
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        WorkChip("Overview", accent, selected = state.workboardMode == VanWorkboardMode.CONTEXT) { actions.onWorkboardMode(VanWorkboardMode.CONTEXT) }
                        WorkChip("Chat", accent, selected = state.workboardMode == VanWorkboardMode.CHAT) { actions.onWorkboardMode(VanWorkboardMode.CHAT) }
                        WorkChip("Voice", accent, selected = state.workboardMode == VanWorkboardMode.VOICE) { actions.onWorkboardMode(VanWorkboardMode.VOICE) }
                        WorkChip("Trades", accent, selected = state.workboardMode == VanWorkboardMode.TRADES) { actions.onWorkboardMode(VanWorkboardMode.TRADES) }
                    }
                    if (state.workboardMode == VanWorkboardMode.VOICE || voiceActive) WorkboardVoiceControls(app, actions, accent)
                    when (state.workboardMode) {
                        VanWorkboardMode.CONTEXT -> {
                            LazyColumn(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                                if (systemLine.isNotBlank()) item { Text(systemLine, color = Color(0xFFB8CBD2), fontSize = 12.sp) }
                                if (!latestMessage.isNullOrBlank()) item { ContextAction("Recent conversation", latestMessage) { actions.onWorkboardMode(VanWorkboardMode.CHAT) } }
                                item { ContextAction("Projects", "Continue a project or inspect its context") { actions.onCommandCentre("projects") } }
                                item { ContextAction("Tasks", "Queued work, active tasks and results") { actions.onCommandCentre("tasks") } }
                                item { ContextAction("Decisions", "Your approvals and outstanding decisions") { actions.onCommandCentre("decisions") } }
                                item { ContextAction("Systems", "Connection and service health") { actions.onCommandCentre("systems") } }
                                item { ContextAction("Trading", "Portfolio, risk and accounts") { actions.onTradingRoute(TradingCommandCentreActivity.ROUTE_OVERVIEW) } }
                                item { ContextAction("Command Centre", "Open the complete workspace") { actions.onCommandCentre(null) } }
                            }
                        }
                        VanWorkboardMode.TRADES -> TradesWorkboardPanel(app, accent, state.tradeView, state.tradeRefreshTick,
                            actions.onTradeView, actions.onTradeRefresh, actions.onTradingRoute)
                        VanWorkboardMode.CHAT, VanWorkboardMode.VOICE -> {
                            WorkboardConversation(messages, latestMessage, accent, systemLine)
                            ChatComposer(app, accent, compact = compact, draft = state.chatDraft, onDraft = actions.onDraft)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun BoardHeader(state: VanOverlaySurfaceState, actions: VanOverlayActions,
    visualState: VanVisualState, headline: String, caption: String, accent: Int, compact: Boolean) {
    val budget = rememberVanEffectBudget()
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        LiveOverlayEmbodiment(state = visualState, animate = state.animate, budget = budget,
            presentation = VanPresentation.COMPACT, characterFraction = 0.55f,
            modifier = Modifier.size(if (compact) 64.dp else 76.dp).then(actions.gestures).vanAccessibleCharacter(visualState, actions))
        Column(Modifier.weight(1f).then(actions.dragHandle).vanAccessibleMovement(actions)
            .semantics { contentDescription = "Drag workboard. $headline. $caption" }) {
            Text(headline, color = Color(accent), fontSize = 14.sp, fontWeight = FontWeight.Bold, maxLines = 2)
            if (!compact) Text(caption, color = Color(0xFFB8CBD2), fontSize = 12.sp, maxLines = 2)
            Text("Drag to move", color = Color(0xFFB8CBD2), fontSize = 10.sp)
        }
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            WorkChip("Hide", accent) { actions.onPresentation(VanOverlayPresentation.FULL_FLOATING) }
            WorkChip(when (state.presentation) {
                VanOverlayPresentation.WORKBOARD_COMPACT -> "Expand"
                VanOverlayPresentation.WORKBOARD_EXPANDED -> "Full"
                else -> "Compact"
            }, accent) { actions.onPresentation(when (state.presentation) {
                VanOverlayPresentation.WORKBOARD_COMPACT -> VanOverlayPresentation.WORKBOARD_EXPANDED
                VanOverlayPresentation.WORKBOARD_EXPANDED -> VanOverlayPresentation.WORKBOARD_MAXIMIZED
                else -> VanOverlayPresentation.WORKBOARD_COMPACT
            }) }
        }
    }
}
