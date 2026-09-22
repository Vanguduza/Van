package com.dial.van.overlay

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.provider.Settings
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.WindowManager
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.savedstate.SavedStateRegistry
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import com.dial.van.VanApplication
import com.dial.van.command.CommandCentreActivity
import com.dial.van.trading.TradeView
import com.dial.van.trading.TradingCommandCentreActivity

class FloatingOverlayService : Service(), LifecycleOwner, SavedStateRegistryOwner {
    private lateinit var windowManager: WindowManager
    private lateinit var overlayView: ComposeView
    private lateinit var layoutParams: WindowManager.LayoutParams
    private lateinit var stateStore: OverlayStateStore
    private lateinit var dismissWindow: OverlayDismissWindow<FloatingOverlayService>


    private val lifecycleRegistry = LifecycleRegistry(this)
    private val savedStateController = SavedStateRegistryController.create(this)

    private var uiState by mutableStateOf(VanOverlayUiState())
    private var dockEdge by mutableStateOf(DockEdge.NONE)
    private var blurBehindActive by mutableStateOf(false)
    private var workboardMode by mutableStateOf(VanWorkboardMode.CONTEXT)
    private var chatDraft by mutableStateOf("")
    private var tradeView by mutableStateOf(TradeView.CURRENT)
    private var tradeRefreshTick by mutableStateOf(0)

    /** Broadcast parsing is isolated; the service owns lifecycle state and policy. */
    private val screenReceiver = OverlayScreenStateReceiver(::setScreenOn)

    private val obstructionReceiver = OverlayObstructionReceiver { state ->
        visibility = visibility.copy(
            keyboardVisible = state.keyboardVisible,
            fullscreenAppActive = state.fullscreenAppActive,
        )
        if (state.keyboardVisible) moveAboveKeyboard(state.keyboardTopPx)
        applyVisibilityLifecycle()
    }

    private fun moveAboveKeyboard(keyboardTopPx: Int) {
        if (
            keyboardTopPx == Int.MAX_VALUE ||
            !::overlayView.isInitialized ||
            !::layoutParams.isInitialized ||
            !::windowManager.isInitialized
        ) return
        val measuredHeight = overlayView.height.takeIf { it > 0 } ?: dp(180)
        val safeY = (keyboardTopPx - measuredHeight - dp(12)).coerceAtLeast(0)
        if (layoutParams.y <= safeY) return
        layoutParams.y = safeY
        uiState = uiState.copy(yPx = safeY)
        runCatching { windowManager.updateViewLayout(overlayView, layoutParams) }
        persistState()
    }

    private fun setScreenOn(on: Boolean) {
        if (visibility.screenOn == on) return
        visibility = visibility.copy(screenOn = on)
        applyVisibilityLifecycle()
    }

    /**
     * CREATED rather than STOPPED when paused: the composition is retained, so waking the
     * phone does not rebuild the whole overlay, but no frame callback runs. The view stays
     * attached, so the overlay does not visibly disappear and reappear.
     */
    private fun applyVisibilityLifecycle() {
        if (lifecycleRegistry.currentState == Lifecycle.State.DESTROYED) return
        lifecycleRegistry.currentState = when (OverlayVisibilityPolicy.target(visibility)) {
            OverlayLifecycleTarget.ANIMATING -> Lifecycle.State.STARTED
            OverlayLifecycleTarget.PAUSED -> Lifecycle.State.CREATED
            OverlayLifecycleTarget.DESTROYED -> Lifecycle.State.DESTROYED
        }
    }

    override fun onCreate() {
        super.onCreate()
        // Foreground first: a slow or failing addView below must not spend the seconds
        // startForegroundService allows, and an ungranted overlay stops honestly (running=false).
        startForeground(NOTIFICATION_ID, OverlayNotification.build(this))
        if (!Settings.canDrawOverlays(this)) {
            stopSelf()
            return
        }
        running = true
        savedStateController.performRestore(null)
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
        stateStore = OverlayStateStore(this)
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        dismissWindow = OverlayDismissWindow(this, windowManager, ::dp)

        val metrics = resources.displayMetrics
        val restored = stateStore.load(metrics.widthPixels / 2, metrics.heightPixels / 3)
        uiState = VanOverlayUiState(
            presentation = restored.presentation,
            xPx = restored.x,
            yPx = restored.y,
        )
        dockEdge = restored.dock

        layoutParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            OverlayWindowFlags.base(uiState.presentation),
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = uiState.xPx
            y = uiState.yPx
        }
        applyBackdropBlur()

        overlayView = ComposeView(this).apply {
            setViewTreeLifecycleOwner(this@FloatingOverlayService)
            setViewTreeSavedStateRegistryOwner(this@FloatingOverlayService)
            setContent { OverlayContent() }
        }
        windowManager.addView(overlayView, layoutParams)
        // Seed from the real screen state rather than assuming on: a service started while
        // the phone is locked would otherwise animate immediately.
        val power = getSystemService(PowerManager::class.java)
        visibility = visibility.copy(
            attached = true,
            screenOn = power?.isInteractive != false,
        )
        registerReceiver(
            screenReceiver,
            IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_SCREEN_OFF)
                addAction(Intent.ACTION_USER_PRESENT)
            },
        )
        val obstructionFilter = IntentFilter(
            VanObstructionAccessibilityService.ACTION_OBSTRUCTION_STATE,
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(obstructionReceiver, obstructionFilter, RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(obstructionReceiver, obstructionFilter)
        }
        applyVisibilityLifecycle()
        stateStore.markRunning(true)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_TOGGLE_MODE -> onVanTap()
            ACTION_OPEN_COMMAND -> openCommandCentre()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        visibility = visibility.copy(destroying = true, attached = false)
        runCatching { unregisterReceiver(screenReceiver) }
        runCatching { unregisterReceiver(obstructionReceiver) }
        stateStore.markRunning(false)
        persistState(running = false)
        hideDismissTarget()
        if (::overlayView.isInitialized) runCatching { windowManager.removeView(overlayView) }
        lifecycleRegistry.currentState = Lifecycle.State.DESTROYED
        running = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
    override val lifecycle: Lifecycle get() = lifecycleRegistry
    override val savedStateRegistry: SavedStateRegistry get() = savedStateController.savedStateRegistry

    /**
     * The overlay's presentation, handed everything it needs and nothing it does not.
     *
     * P3-AND-009 / Rev 3.0 s41. This used to be the whole Compose tree, inline, reading
     * these fields and calling these methods directly. What is left is the adapter: the
     * service measures the window and owns the state, `VanOverlaySurface` draws.
     */
    @Composable
    private fun OverlayContent() {
        val metrics = resources.displayMetrics
        val density = metrics.density
        // One gesture chain for every presentation, so dragging VAN feels the same whatever
        // it happens to be showing.
        val gestures = remember { Modifier.vanGestures() }
        val actions = remember(gestures) {
            VanOverlayActions(
                gestures = gestures,
                onQuickControl = ::handleQuickControl,
                onChat = ::openChat,
                onVoice = { beginVoice(application as VanApplication) },
                onPresentation = ::setPresentation,
                onCommandCentre = ::openCommandCentre,
                onTradingRoute = ::openTradingRoute,
                onWorkboardMode = { workboardMode = it },
                onTradeView = { tradeView = it },
                onTradeRefresh = { tradeRefreshTick += 1 },
                onDraft = { chatDraft = it },
            )
        }
        VanOverlaySurface(
            app = application as VanApplication,
            state = VanOverlaySurfaceState(
                presentation = uiState.presentation,
                quickControlsVisible = uiState.quickControls == VanQuickControlsState.VISIBLE,
                workboardMode = workboardMode,
                chatDraft = chatDraft,
                tradeView = tradeView,
                tradeRefreshTick = tradeRefreshTick,
                animate = OverlayVisibilityPolicy.shouldAnimate(visibility),
                blurBehindActive = blurBehindActive,
                maximizedWidthDp = metrics.widthPixels / density -
                    OverlayTheme.MAXIMIZED_HORIZONTAL_MARGIN_DP * 2,
                maximizedHeightDp = metrics.heightPixels / density *
                    OverlayTheme.MAXIMIZED_HEIGHT_FRACTION,
            ),
            actions = actions,
        )
    }

    @OptIn(ExperimentalFoundationApi::class)
    private fun Modifier.vanGestures(): Modifier = this
        .pointerInput(Unit) {
            detectDragGestures(
                onDragStart = { beginDrag() },
                onDrag = { change, amount ->
                    change.consume()
                    dragBy(amount.x.toInt(), amount.y.toInt())
                },
                onDragEnd = { finishDrag() },
                onDragCancel = { cancelDrag() },
            )
        }
        .combinedClickable(
            onClick = { onVanTap() },
            onDoubleClick = { openCommandCentre() },
            onLongClick = { showQuickControls() },
        )

    private fun onVanTap() {
        updateUiState(VanOverlayReducer.onVanTapped(uiState))
    }

    private fun showQuickControls() {
        updateUiState(VanOverlayReducer.showQuickControls(uiState))
    }

    private fun openChat(expanded: Boolean) {
        workboardMode = VanWorkboardMode.CHAT
        setPresentation(
            if (expanded) VanOverlayPresentation.WORKBOARD_EXPANDED
            else VanOverlayPresentation.WORKBOARD_COMPACT,
        )
    }

    private fun beginVoice(app: VanApplication) {
        workboardMode = VanWorkboardMode.VOICE
        setPresentation(VanOverlayPresentation.WORKBOARD_EXPANDED)
        app.voiceSession.beginOwnerTurn()
    }

    private fun handleQuickControl(label: String) {
        val app = application as VanApplication
        when (label) {
            "Chat" -> openChat(expanded = true)
            "Voice" -> beginVoice(app)
            "Minimize" -> updateUiState(VanOverlayReducer.minimize(uiState))
            "Command Centre" -> openCommandCentre()
            "Dock" -> updateUiState(VanOverlayReducer.dock(uiState))
            "Close" -> stopSelf()
        }
    }

    private fun setPresentation(presentation: VanOverlayPresentation) {
        updateUiState(uiState.copy(presentation = presentation, quickControls = VanQuickControlsState.HIDDEN))
    }

    private fun updateUiState(next: VanOverlayUiState) {
        uiState = next
        if (::layoutParams.isInitialized && ::overlayView.isInitialized) {
            updateWindowFlags()
            persistState()
        }
    }

    private fun beginDrag() = updateUiState(dragController.begin(uiState))

    private fun dragBy(dx: Int, dy: Int) {
        // Assigned directly rather than through updateUiState: that also writes the window
        // position, and the drag has just written it.
        uiState = dragController.drag(uiState, dx, dy)
    }

    private fun finishDrag() {
        dragController.finish(uiState, reducedMotion = isReducedMotion())?.let(::updateUiState)
    }

    private fun isReducedMotion(): Boolean = systemReducedMotionEnabled()

    private fun cancelDrag() = updateUiState(dragController.cancel(uiState))

    /**
     * The service's side of [OverlayWindowPort] (Rev 3.0 s41): everything the drag needs
     * that genuinely requires a window, and nothing else.
     */
    private val dragWindow = object : OverlayWindowPort {
        override fun screen(): OverlayScreen = resources.displayMetrics.let {
            OverlayScreen(widthPx = it.widthPixels, heightPx = it.heightPixels)
        }

        override fun dp(value: Int): Int = this@FloatingOverlayService.dp(value)

        override fun position(): OverlayPlacement = OverlayPlacement(layoutParams.x, layoutParams.y)

        override fun moveTo(x: Int, y: Int) {
            layoutParams.x = x
            layoutParams.y = y
            windowManager.updateViewLayout(overlayView, layoutParams)
        }

        override fun armedFeedback() {
            overlayView.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        }

        override fun showDismissTarget() = this@FloatingOverlayService.showDismissTarget()

        override fun refreshDismissTarget() = this@FloatingOverlayService.refreshDismissTarget()

        override fun hideDismissTarget() = this@FloatingOverlayService.hideDismissTarget()

        override fun dismissOverlay() {
            stateStore.markRunning(false)
            stopSelf()
        }

        override fun dockedTo(edge: DockEdge, durationMs: Int) {
            dockEdge = edge
            // Placement is already snapped; this callback records the owning edge.
        }

        override fun dockFeedback() {
            overlayView.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        }
    }

    private val dragController = OverlayDragController(dragWindow)

    private fun showDismissTarget() =
        dismissWindow.show { DismissTarget(uiState.dismissTargetArmed) }

    private fun refreshDismissTarget() = dismissWindow.refresh()

    private fun hideDismissTarget() = dismissWindow.hide()

    /** The one place the overlay leaves for the trading surface (Rev 3.0 §41). */
    private fun openTradingRoute(route: String) {
        startActivity(TradingCommandCentreActivity.intent(this, route))
    }

    private fun openCommandCentre(module: String? = null) {
        startActivity(
            Intent(this, CommandCentreActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                if (!module.isNullOrBlank()) putExtra("module", module)
            },
        )
    }

    private fun updateWindowFlags() {
        OverlayWindowFlags.apply(layoutParams, uiState.presentation, blurBehindActive, ::dp)
        runCatching { windowManager.updateViewLayout(overlayView, layoutParams) }
    }

    private fun applyBackdropBlur() {
        blurBehindActive = OverlayWindowFlags.blurSupported(windowManager)
        OverlayWindowFlags.apply(layoutParams, uiState.presentation, blurBehindActive, ::dp)
    }

    private fun persistState(running: Boolean = true) {
        stateStore.save(
            OverlayPersistedState(
                x = uiState.xPx,
                y = uiState.yPx,
                presentation = uiState.presentation,
                dock = dockEdge,
                serviceRunning = running,
            ),
        )
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        const val ACTION_TOGGLE_MODE = "com.dial.van.overlay.TOGGLE"
        const val ACTION_OPEN_COMMAND = "com.dial.van.overlay.OPEN_COMMAND"
        private const val NOTIFICATION_ID = 1001

        /** Explicit service health; never inferred from deprecated ActivityManager state. */
        @Volatile
        private var running: Boolean = false

        fun isRunning(): Boolean = running

        fun start(context: Context) {
            context.startForegroundService(Intent(context, FloatingOverlayService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, FloatingOverlayService::class.java))
        }
    }
}
