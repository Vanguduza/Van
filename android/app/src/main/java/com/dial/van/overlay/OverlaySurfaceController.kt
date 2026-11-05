package com.dial.van.overlay

import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import com.dial.van.visual.LocalVanPresentationPreferences
import com.dial.van.visual.VanPresentationPreferences
import com.dial.van.visual.VanDoubleTapAction
import java.security.MessageDigest
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
    private var modeChosenByOwner = false
    private var localSession: OverlaySessionRuntime? = null
    private var attachedApp: VanApplication? = null
    private var ownedVoiceTurn: String? = null
    fun attach(app: VanApplication, store: OverlayStateStore) {
        check(localSession == null)
        attachedApp = app
        localSession = OverlaySessionRuntime(store, ownerScope = {
            runCatching {
                if (!app.gatewayClient.isEnrolled()) null else MessageDigest.getInstance("SHA-256")
                    .digest((app.gatewayClient.permissionProfileIdentity() + "\n" + app.gatewayClient.deviceId).toByteArray())
                    .joinToString("") { "%02x".format(it) }
            }.getOrNull()
        }, listenOwner = { changed -> app.gatewayClient.observeLocalOwnerIdentity(changed) },
            ownerInvalidated = ::pauseOwnerCapture)
    }
    fun pauseOwnerCapture() {
        val turn = ownedVoiceTurn; ownedVoiceTurn = null
        if (turn != null) attachedApp?.voiceSession?.cancelOwnerTurnIf(turn)
    }
    fun close() { pauseOwnerCapture(); localSession?.close(); localSession = null; attachedApp = null }
    fun onDoubleTap(ui: VanOverlayUiState, change: (VanOverlayUiState) -> Unit, workspace: () -> Unit) {
        when (localSession?.session?.preferences?.doubleTap ?: VanDoubleTapAction.WORKSPACE) {
            VanDoubleTapAction.WORKSPACE -> workspace()
            VanDoubleTapAction.CHAT -> { modeChosenByOwner = true; workboardMode = VanWorkboardMode.CHAT; change(ui.copy(presentation = VanOverlayPresentation.WORKBOARD_EXPANDED, quickControls = VanQuickControlsState.HIDDEN)) }
            VanDoubleTapAction.NONE -> Unit
        }
    }
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
        dragHandle: Modifier = Modifier,
        onMove: (Int, Int) -> Boolean = { _, _ -> false },
        boardWidthDp: Float? = null,
        boardHeightDp: Float? = null,
        onUiChange: (VanOverlayUiState) -> Unit,
        onCommandCentre: (String?) -> Unit,
        onTradingRoute: (String) -> Unit,
        onClose: () -> Unit,
        onBlurAllowed: (Boolean) -> Unit,
    ) {
        val local = localSession
        val safeOwner = local?.scopeCurrent() != false
        val preferences = if (safeOwner) local?.session?.preferences ?: VanPresentationPreferences() else VanPresentationPreferences()
        val ready = local?.ready == true && safeOwner
        LaunchedEffect(local, ready) {
            if (ready && !modeChosenByOwner) workboardMode = runCatching {
                VanWorkboardMode.valueOf(local?.session?.mode ?: "CONTEXT")
            }.getOrDefault(VanWorkboardMode.CONTEXT)
        }
        val draft = if (safeOwner) local?.session?.draft.orEmpty() else ""
        val budget = rememberVanEffectBudget()
        SideEffect { onBlurAllowed(budget.allowLiveBlur) }
        fun present(presentation: VanOverlayPresentation) = onUiChange(
            uiState.copy(presentation = presentation, quickControls = VanQuickControlsState.HIDDEN),
        )
        fun chat(expanded: Boolean) {
            modeChosenByOwner = true
            workboardMode = VanWorkboardMode.CHAT
            present(if (expanded) VanOverlayPresentation.WORKBOARD_EXPANDED else VanOverlayPresentation.WORKBOARD_COMPACT)
        }
        fun stopVoice() {
            ownedVoiceTurn = null
            app.commandController.invalidateVoiceContext()
            app.voiceSession.cancelOwnerTurn()
            app.ttsOutput.onBargeInRequested()
        }
        fun voice() {
            if (!safeOwner) return
            modeChosenByOwner = true
            workboardMode = VanWorkboardMode.VOICE
            present(VanOverlayPresentation.WORKBOARD_EXPANDED)
            if (!app.voiceSession.ownerTurnActive.value) ownedVoiceTurn = app.voiceSession.beginOwnerTurn()
        }
        val actions = VanOverlayActions(
            gestures = gestures, dragHandle = dragHandle, onMove = onMove,
            onQuickControl = { label ->
                when (label) {
                    "Chat" -> chat(true)
                    "Voice" -> voice()
                    "Settings" -> { modeChosenByOwner = true; workboardMode = VanWorkboardMode.SETTINGS; present(VanOverlayPresentation.WORKBOARD_EXPANDED) }
                    "Minimize" -> onUiChange(VanOverlayReducer.minimize(uiState))
                    "Command Centre" -> onCommandCentre(null)
                    "Dock" -> onUiChange(VanOverlayReducer.dock(uiState))
                    "Close" -> { stopVoice(); onClose() }
                }
            },
            onChat = ::chat, onVoice = ::voice, onStopVoice = ::stopVoice, onPresentation = ::present,
            onCommandCentre = onCommandCentre, onTradingRoute = onTradingRoute,
            onWorkboardMode = {
                modeChosenByOwner = true
                workboardMode = it
                local?.selectMode(it.name)
                if (it == VanWorkboardMode.VOICE && uiState.presentation == VanOverlayPresentation.WORKBOARD_COMPACT) {
                    present(VanOverlayPresentation.WORKBOARD_EXPANDED)
                }
            }, onTradeView = { tradeView = it },
            onTradeRefresh = { tradeRefreshTick += 1 }, onDraft = { local?.updateDraft(it) },
            onPreferences = { local?.preferences(it) },
            onResumeDraft = { local?.resumeDraft(); workboardMode = VanWorkboardMode.CHAT },
            onDiscardDraft = { local?.discardDraft() }, onRetrySave = { local?.retrySave() },
        )
        CompositionLocalProvider(LocalVanPresentationPreferences provides preferences) {
        VanOverlaySurface(
            app = app,
            state = VanOverlaySurfaceState(
                presentation = uiState.presentation,
                quickControlsVisible = uiState.quickControls == VanQuickControlsState.VISIBLE,
                workboardMode = workboardMode, chatDraft = draft, tradeView = tradeView,
                tradeRefreshTick = tradeRefreshTick,
                animate = OverlayVisibilityPolicy.shouldAnimate(visibility),
                blurBehindActive = blurBehindActive,
                maximizedWidthDp = widthDp - OverlayTheme.MAXIMIZED_HORIZONTAL_MARGIN_DP * 2,
                maximizedHeightDp = heightDp * OverlayTheme.MAXIMIZED_HEIGHT_FRACTION,
                boardWidthDp = boardWidthDp,
                boardHeightDp = boardHeightDp,
                keyboardVisible = visibility.keyboardVisible,
                preferences = preferences, localReady = ready, ownerScopeValid = safeOwner,
                recoveredDraftAvailable = safeOwner && local?.recoveredDraft != null,
                storageMessage = if (safeOwner) local?.storageMessage.orEmpty() else "Owner changed. Reopen VAN before editing.",
            ),
            actions = actions,
        )
        }
    }
}
