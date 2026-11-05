package com.dial.van.overlay

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.res.Configuration
import android.graphics.PixelFormat
import android.os.IBinder
import android.os.PowerManager
import android.provider.Settings
import android.view.Gravity
import android.view.WindowManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.ComposeView
import androidx.core.content.ContextCompat
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
    private var boardSize by mutableStateOf<OverlaySize?>(null)
    private var visibility by mutableStateOf(OverlayVisibility(attached = false))

    private var windowAttached = false
    private var windowFailed = false
    private var screenReceiverRegistered = false
    private var obstructionReceiverRegistered = false
    private var keyboardTopPx = Int.MAX_VALUE
    private var lastAppliedPlacement = OverlayPlacement(0, 0)

    private val screenReceiver = OverlayScreenStateReceiver(::setScreenOn)
    private val obstructionReceiver = OverlayObstructionReceiver { state ->
        if (OverlayVisibilityPolicy.obstructionChanged(
                visibility, keyboardTopPx, state.keyboardVisible,
                state.keyboardTopPx, state.fullscreenAppActive,
            )) {
            keyboardTopPx = OverlayVisibilityPolicy.keyboardTop(state.keyboardVisible, state.keyboardTopPx)
            visibility = visibility.copy(
                keyboardVisible = state.keyboardVisible,
                fullscreenAppActive = state.fullscreenAppActive,
            )
            interaction.cancelSettle()
            reconcileWindow()
            refreshKeyboardOverlap()
            applyVisibilityLifecycle()
        }
    }

    private val interaction = OverlayWindowInteraction(object : OverlayInteractionHost {
        override val context get() = this@FloatingOverlayService
        override val manager get() = if (::windowManager.isInitialized) windowManager else null
        override val view get() = if (::overlayView.isInitialized) overlayView else null
        override val params get() = if (::layoutParams.isInitialized) layoutParams else null
        override val keyboardTopPx get() = this@FloatingOverlayService.keyboardTopPx
        override var uiState: VanOverlayUiState
            get() = this@FloatingOverlayService.uiState
            set(value) { this@FloatingOverlayService.uiState = value }
        override var visibility: OverlayVisibility
            get() = this@FloatingOverlayService.visibility
            set(value) { this@FloatingOverlayService.visibility = value }
        override var dockEdge: DockEdge
            get() = this@FloatingOverlayService.dockEdge
            set(value) { this@FloatingOverlayService.dockEdge = value }
        override fun canUseWindow() = this@FloatingOverlayService.canUseWindow()
        override fun updateWindow() = this@FloatingOverlayService.updateWindow()
        override fun moveWindow(placement: OverlayPlacement) = this@FloatingOverlayService.moveWindow(placement)
        override fun persistState() = this@FloatingOverlayService.persistState()
        override fun applyVisibilityLifecycle() = this@FloatingOverlayService.applyVisibilityLifecycle()
        override fun showDismissTarget() = this@FloatingOverlayService.showDismissTarget()
        override fun refreshDismissTarget() = this@FloatingOverlayService.refreshDismissTarget()
        override fun hideDismissTarget() = this@FloatingOverlayService.hideDismissTarget()
        override fun dismissBounds() = if (::dismissWindow.isInitialized) dismissWindow.boundsOnScreen() else null
        override fun dismissOverlay() {
            running = false
            this@FloatingOverlayService.persistState(running = false)
            stopSelf()
        }
        override fun failWindow() = this@FloatingOverlayService.failWindow()
        override fun environmentChanged() = this@FloatingOverlayService.environmentChanged()
        override fun boardSizeChanged(size: OverlaySize?) { boardSize = size }
        override fun imeObserved(visible: Boolean, topPx: Int) {
            if (visibility.keyboardVisible == visible && keyboardTopPx == topPx) return
            this@FloatingOverlayService.keyboardTopPx = topPx
            visibility = visibility.copy(keyboardVisible = visible)
            if (::overlayView.isInitialized) overlayView.post { reconcileWindow() }
        }
    })
    private val surfaceController = OverlaySurfaceController()
    private fun screenBounds() = interaction.screenBounds()
    private fun refreshKeyboardOverlap() = interaction.refreshKeyboardOverlap()
    private fun reconcileWindow(): Unit = interaction.reconcileWindow()
    private fun stopInteraction() = interaction.stopInteraction()

    @Composable
    private fun OverlayContent() {
        val metrics = resources.displayMetrics
        val gestures = remember {
            Modifier.vanGestures(interaction, ::onVanTap, { openCommandCentre() }, ::showQuickControls)
        }
        val dragHandle = remember { Modifier.vanGestures(interaction, {}, {}, {}, clicks = false) }
        surfaceController.Content(
            dragHandle = dragHandle,
            onMove = interaction::moveAccessibly,
            app = application as VanApplication, uiState = uiState, visibility = visibility,
            blurBehindActive = blurBehindActive, widthDp = metrics.widthPixels / metrics.density,
            heightDp = metrics.heightPixels / metrics.density, gestures = gestures,
            boardWidthDp = boardSize?.widthPx?.div(metrics.density),
            boardHeightDp = boardSize?.heightPx?.div(metrics.density),
            onUiChange = ::updateUiState, onCommandCentre = ::openCommandCentre,
            onTradingRoute = ::openTradingRoute, onClose = ::stopSelf,
            onBlurAllowed = ::setBlurAllowed,
        )
    }

    private fun setBlurAllowed(allowed: Boolean) {
        if (!canUseWindow()) return
        val next = allowed && OverlayWindowFlags.blurSupported(windowManager)
        if (next == blurBehindActive) return
        blurBehindActive = next
        applyWindowFlags()
        updateWindow()
    }

    private fun environmentChanged() {
        if (!canUseWindow()) return
        stopInteraction()
        layoutParams.width = WindowManager.LayoutParams.WRAP_CONTENT
        layoutParams.height = WindowManager.LayoutParams.WRAP_CONTENT
        if (updateWindow()) reconcileWindow()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        environmentChanged()
    }

    private fun setScreenOn(on: Boolean) {
        visibility = visibility.copy(screenOn = on)
        if (on && canUseWindow()) reconcileWindow()
        applyVisibilityLifecycle()
    }

    private fun applyVisibilityLifecycle() {
        if (lifecycleRegistry.currentState == Lifecycle.State.DESTROYED) return
        val target = OverlayVisibilityPolicy.target(visibility)
        if (target != OverlayLifecycleTarget.ANIMATING) stopInteraction()
        lifecycleRegistry.currentState = when (target) {
            OverlayLifecycleTarget.ANIMATING -> Lifecycle.State.STARTED
            OverlayLifecycleTarget.PAUSED -> Lifecycle.State.CREATED
            OverlayLifecycleTarget.DESTROYED -> Lifecycle.State.DESTROYED
        }
        OverlayTradeAura.hold(application, target == OverlayLifecycleTarget.ANIMATING)
    }

    override fun onCreate() {
        super.onCreate()
        running = false
        runCatching {
            startForeground(NOTIFICATION_ID, OverlayNotification.build(this))
            savedStateController.performRestore(null)
            lifecycleRegistry.currentState = Lifecycle.State.CREATED
            stateStore = OverlayStateStore(this)
            stateStore.markRunning(false)
            if (!Settings.canDrawOverlays(this)) {
                stopSelf()
                return
            }
            windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
            dismissWindow = OverlayDismissWindow(this, windowManager, ::dp)
            val screen = screenBounds()
            val restored = stateStore.load(screen.widthPx / 2, screen.heightPx / 3)
            val fallback = VanOverlayController.fallbackSizeFor(restored.presentation, ::dp, screen)
            val placement = VanOverlayController.clamp(
                restored.x, restored.y, fallback.widthPx, fallback.heightPx, screen,
            )
            uiState = VanOverlayUiState(
                presentation = restored.presentation, xPx = placement.x, yPx = placement.y,
            )
            dockEdge = restored.dock
            lastAppliedPlacement = placement
            layoutParams = WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                OverlayWindowFlags.base(uiState.presentation),
                PixelFormat.TRANSLUCENT,
            ).apply {
                // Absolute screen coordinates, including on RTL devices.
                gravity = Gravity.TOP or Gravity.LEFT
                x = placement.x
                y = placement.y
            }
            blurBehindActive = OverlayWindowFlags.blurSupported(windowManager)
            applyWindowFlags()
            overlayView = ComposeView(this).apply {
                setViewTreeLifecycleOwner(this@FloatingOverlayService)
                setViewTreeSavedStateRegistryOwner(this@FloatingOverlayService)
                addOnLayoutChangeListener(interaction.layoutListener)
                addOnAttachStateChangeListener(interaction.attachListener)
                setOnApplyWindowInsetsListener { view, insets -> interaction.onWindowInsets(view, insets) }
                setContent { OverlayContent() }
            }
            windowManager.addView(overlayView, layoutParams)
            windowAttached = true
            val power = getSystemService(PowerManager::class.java)
            visibility = visibility.copy(attached = true, screenOn = power?.isInteractive != false)
            registerReceiver(
                screenReceiver,
                IntentFilter().apply {
                    addAction(Intent.ACTION_SCREEN_ON)
                    addAction(Intent.ACTION_SCREEN_OFF)
                    addAction(Intent.ACTION_USER_PRESENT)
                },
            )
            screenReceiverRegistered = true
            ContextCompat.registerReceiver(
                this, obstructionReceiver,
                IntentFilter(VanObstructionAccessibilityService.ACTION_OBSTRUCTION_STATE),
                ContextCompat.RECEIVER_NOT_EXPORTED,
            )
            obstructionReceiverRegistered = true
            reconcileWindow()
            if (canUseWindow()) {
                running = true
                persistState()
                overlayView.requestApplyInsets()
            }
        }.onFailure { failWindow() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!canUseWindow() || !Settings.canDrawOverlays(this)) {
            failWindow()
            return START_NOT_STICKY
        }
        when (intent?.action) {
            ACTION_TOGGLE_MODE -> onVanTap()
            ACTION_OPEN_COMMAND -> openCommandCentre()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        visibility = visibility.copy(destroying = true, attached = false)
        running = false
        stopInteraction()
        if (screenReceiverRegistered) {
            runCatching { unregisterReceiver(screenReceiver) }
            screenReceiverRegistered = false
        }
        if (obstructionReceiverRegistered) {
            runCatching { unregisterReceiver(obstructionReceiver) }
            obstructionReceiverRegistered = false
        }
        persistState(running = false)
        hideDismissTarget()
        OverlayTradeAura.hold(application, visible = false)
        if (::overlayView.isInitialized) {
            overlayView.removeOnLayoutChangeListener(interaction.layoutListener)
            overlayView.removeOnAttachStateChangeListener(interaction.attachListener)
            overlayView.setOnApplyWindowInsetsListener(null)
            if (::windowManager.isInitialized && (windowAttached || overlayView.isAttachedToWindow)) {
                runCatching { windowManager.removeView(overlayView) }
            }
            overlayView.disposeComposition()
        }
        windowAttached = false
        OverlayOwnWindowIdentity.detached()
        if (lifecycleRegistry.currentState == Lifecycle.State.INITIALIZED) {
            lifecycleRegistry.currentState = Lifecycle.State.CREATED
        }
        lifecycleRegistry.currentState = Lifecycle.State.DESTROYED
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
    override val lifecycle: Lifecycle get() = lifecycleRegistry
    override val savedStateRegistry: SavedStateRegistry get() = savedStateController.savedStateRegistry

    private fun onVanTap() = updateUiState(VanOverlayReducer.onVanTapped(uiState))
    private fun showQuickControls() = updateUiState(VanOverlayReducer.showQuickControls(uiState))

    private fun updateUiState(next: VanOverlayUiState) {
        stopInteraction()
        val presentationChanged = next.presentation != uiState.presentation
        if (presentationChanged && canUseWindow()) interaction.preparePresentation(uiState.presentation, next.presentation)
        OverlayVisualCueBridge.publishPresentationChange(
            previous = uiState.presentation,
            next = next.presentation,
        )
        uiState = next.copy(
            xPx = uiState.xPx, yPx = uiState.yPx,
            dragging = false, dismissTargetVisible = false, dismissTargetArmed = false,
        )
        if (canUseWindow()) {
            applyWindowFlags()
            if (updateWindow()) {
                reconcileWindow()
                overlayView.post { reconcileWindow() }
                persistState()
            }
        }
    }

    private fun canUseWindow(): Boolean = windowAttached && !windowFailed && !visibility.destroying

    private fun moveWindow(placement: OverlayPlacement): Boolean {
        if (!canUseWindow()) return false
        layoutParams.x = placement.x
        layoutParams.y = placement.y
        if (!updateWindow()) return false
        refreshKeyboardOverlap()
        applyVisibilityLifecycle()
        return canUseWindow()
    }

    private fun syncPosition() {
        uiState = uiState.copy(xPx = layoutParams.x, yPx = layoutParams.y)
    }

    private fun recordActualEdge() {
        if (!::layoutParams.isInitialized) return
        val size = interaction.windowSize()
        dockEdge = VanOverlayController.edgeAt(
            layoutParams.x, layoutParams.y, size.widthPx, size.heightPx, screenBounds(),
        )
    }

    /** Failed updates retain the last successfully applied coordinates and stop once. */
    private fun updateWindow(): Boolean {
        if (!canUseWindow()) return false
        val success = runCatching {
            check(Settings.canDrawOverlays(this))
            windowManager.updateViewLayout(overlayView, layoutParams)
        }.isSuccess
        if (success) {
            lastAppliedPlacement = OverlayPlacement(layoutParams.x, layoutParams.y)
            syncPosition()
        } else {
            layoutParams.x = lastAppliedPlacement.x
            layoutParams.y = lastAppliedPlacement.y
            syncPosition()
            failWindow()
        }
        return success
    }

    private fun failWindow() {
        if (windowFailed) return
        windowFailed = true
        running = false
        visibility = visibility.copy(attached = false)
        stopInteraction()
        if (::stateStore.isInitialized) runCatching { stateStore.markRunning(false) }
        persistState(running = false)
        if (lifecycleRegistry.currentState != Lifecycle.State.INITIALIZED) applyVisibilityLifecycle()
        stopSelf()
    }

    private fun showDismissTarget() {
        if (canUseWindow() && ::dismissWindow.isInitialized) {
            runCatching { dismissWindow.show { DismissTarget(uiState.dismissTargetArmed) } }
                .onFailure { failWindow() }
        }
    }

    private fun refreshDismissTarget() {
        if (::dismissWindow.isInitialized) {
            runCatching { dismissWindow.refresh() }.onFailure { failWindow() }
        }
    }

    private fun hideDismissTarget() {
        if (::dismissWindow.isInitialized) runCatching { dismissWindow.hide() }
    }

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

    private fun applyWindowFlags() {
        OverlayWindowFlags.apply(layoutParams, uiState.presentation, blurBehindActive, ::dp)
        layoutParams.flags = (layoutParams.flags and WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS.inv()) or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
    }

    private fun persistState(running: Boolean = isRunning()) {
        if (!::stateStore.isInitialized) return
        if (::layoutParams.isInitialized) syncPosition()
        runCatching {
            stateStore.save(
                OverlayPersistedState(
                    x = uiState.xPx, y = uiState.yPx, presentation = uiState.presentation,
                    dock = dockEdge, serviceRunning = running,
                ),
            )
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        const val ACTION_TOGGLE_MODE = "com.dial.van.overlay.TOGGLE"
        const val ACTION_OPEN_COMMAND = "com.dial.van.overlay.OPEN_COMMAND"
        private const val NOTIFICATION_ID = 1001
        @Volatile private var running: Boolean = false
        fun isRunning(): Boolean = running
        fun start(context: Context) {
            context.startForegroundService(Intent(context, FloatingOverlayService::class.java))
        }
        fun stop(context: Context) {
            context.stopService(Intent(context, FloatingOverlayService::class.java))
        }
    }
}
