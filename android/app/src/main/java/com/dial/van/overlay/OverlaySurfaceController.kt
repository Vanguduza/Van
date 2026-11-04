package com.dial.van.overlay

import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.trading.TradeView
import com.dial.van.visual.rememberVanEffectBudget

/** Owns workboard selection/drafts, not the native service or its window. */
internal class OverlaySurfaceController {
    private var workboardMode by mutableStateOf(VanWorkboardMode.CONTEXT)
    private var chatDraft by mutableStateOf("")
    private var tradeView by mutableStateOf(TradeView.CURRENT)
    private var tradeRefreshTick by mutableStateOf(0)

    @Composable
    fun Content(
        app: VanApplication,
        uiState: VanOverlayUiState,
        visibility: OverlayVisibility,
        blurBehindActive: Boolean,
        widthDp: Float,
        heightDp: Float,
        gestures: Modifier,
        onUiChange: (VanOverlayUiState) -> Unit,
        onCommandCentre: (String?) -> Unit,
        onTradingRoute: (String) -> Unit,
        onClose: () -> Unit,
        onBlurAllowed: (Boolean) -> Unit,
    ) {
        val budget = rememberVanEffectBudget()
        SideEffect { onBlurAllowed(budget.allowLiveBlur) }
        fun present(presentation: VanOverlayPresentation) = onUiChange(
            uiState.copy(presentation = presentation, quickControls = VanQuickControlsState.HIDDEN),
        )
        fun chat(expanded: Boolean) {
            workboardMode = VanWorkboardMode.CHAT
            present(if (expanded) VanOverlayPresentation.WORKBOARD_EXPANDED else VanOverlayPresentation.WORKBOARD_COMPACT)
        }
        fun voice() {
            workboardMode = VanWorkboardMode.VOICE
            present(VanOverlayPresentation.WORKBOARD_EXPANDED)
            app.voiceSession.beginOwnerTurn()
        }
        val actions = VanOverlayActions(
            gestures = gestures,
            onQuickControl = { label ->
                when (label) {
                    "Chat" -> chat(true)
                    "Voice" -> voice()
                    "Minimize" -> onUiChange(VanOverlayReducer.minimize(uiState))
                    "Command Centre" -> onCommandCentre(null)
                    "Dock" -> onUiChange(VanOverlayReducer.dock(uiState))
                    "Close" -> onClose()
                }
            },
            onChat = ::chat, onVoice = ::voice, onPresentation = ::present,
            onCommandCentre = onCommandCentre, onTradingRoute = onTradingRoute,
            onWorkboardMode = { workboardMode = it }, onTradeView = { tradeView = it },
            onTradeRefresh = { tradeRefreshTick += 1 }, onDraft = { chatDraft = it },
        )
        VanOverlaySurface(
            app = app,
            state = VanOverlaySurfaceState(
                presentation = uiState.presentation,
                quickControlsVisible = uiState.quickControls == VanQuickControlsState.VISIBLE,
                workboardMode = workboardMode, chatDraft = chatDraft, tradeView = tradeView,
                tradeRefreshTick = tradeRefreshTick,
                animate = OverlayVisibilityPolicy.shouldAnimate(visibility),
                blurBehindActive = blurBehindActive,
                maximizedWidthDp = widthDp - OverlayTheme.MAXIMIZED_HORIZONTAL_MARGIN_DP * 2,
                maximizedHeightDp = heightDp * OverlayTheme.MAXIMIZED_HEIGHT_FRACTION,
            ),
            actions = actions,
        )
    }
}
