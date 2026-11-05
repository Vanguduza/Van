package com.dial.van.overlay

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.content.Context
import android.os.Build
import android.os.SystemClock
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.view.animation.LinearInterpolator

internal interface OverlayInteractionHost {
    val context: Context
    val manager: WindowManager?
    val view: View?
    val params: WindowManager.LayoutParams?
    val keyboardTopPx: Int
    var uiState: VanOverlayUiState
    var visibility: OverlayVisibility
    var dockEdge: DockEdge
    fun canUseWindow(): Boolean
    fun updateWindow(): Boolean
    fun moveWindow(placement: OverlayPlacement): Boolean
    fun persistState()
    fun applyVisibilityLifecycle()
    fun showDismissTarget()
    fun refreshDismissTarget()
    fun hideDismissTarget()
    fun dismissBounds(): OverlayRect?
    fun dismissOverlay()
    fun failWindow()
    fun environmentChanged()
    fun boardSizeChanged(size: OverlaySize?)
    fun imeObserved(visible: Boolean, topPx: Int)
}

/** Native interaction/geometry binding. No foreground-service or product authority lives here. */
internal class OverlayWindowInteraction(private val host: OverlayInteractionHost) {
    private val windowManager get() = requireNotNull(host.manager)
    private val overlayView get() = requireNotNull(host.view)
    private val layoutParams get() = requireNotNull(host.params)
    private val resources get() = host.context.resources
    private val keyboardTopPx get() = host.keyboardTopPx
    private var uiState: VanOverlayUiState
        get() = host.uiState
        set(value) { host.uiState = value }
    private var visibility: OverlayVisibility
        get() = host.visibility
        set(value) { host.visibility = value }
    private var dockEdge: DockEdge
        get() = host.dockEdge
        set(value) { host.dockEdge = value }
    private var lastScreen: OverlayScreen? = null
    private var settleAnimator: ValueAnimator? = null
    private var settleMotion: OverlaySettleMotion? = null
    private var dragPointer: OverlayPoint? = null
    private val boards = OverlayWorkboardWindow(host, ::screenBounds, ::windowSize, ::dp)
    fun preparePresentation(previous: VanOverlayPresentation, next: VanOverlayPresentation) = boards.prepare(previous, next)
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun canUseWindow() = host.canUseWindow()
    private fun updateWindow() = host.updateWindow()
    private fun moveWindow(placement: OverlayPlacement) = host.moveWindow(placement)
    private fun persistState() = host.persistState()
    private fun applyVisibilityLifecycle() = host.applyVisibilityLifecycle()
    private fun showDismissTarget() = host.showDismissTarget()
    private fun refreshDismissTarget() = host.refreshDismissTarget()
    private fun hideDismissTarget() { dragPointer = null; host.hideDismissTarget() }
    private fun failWindow() = host.failWindow()
    private fun syncPosition() { uiState = uiState.copy(xPx = layoutParams.x, yPx = layoutParams.y) }
    private fun observeOwnWindowId(view: View) {
        // Public SDK API: metadata for OUR OWN view only. Do not read text,
        // children or another application's accessibility nodes.
        val id = runCatching {
            val info = view.createAccessibilityNodeInfo()
            try { info.windowId } finally {
                @Suppress("DEPRECATION")
                info.recycle()
            }
        }.getOrDefault(-1)
        OverlayOwnWindowIdentity.observed(id)
    }

    fun onWindowInsets(view: View, insets: WindowInsets): WindowInsets {
        observeOwnWindowId(view)
        val next = screenBounds()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val ime = insets.getInsets(WindowInsets.Type.ime())
            val visible = insets.isVisible(WindowInsets.Type.ime())
            // Direct insets keep chat keyboard placement working even without the
            // optional obstruction accessibility service. Never inspect UI content.
            if (!visible || ime.bottom > 0) host.imeObserved(visible,
                if (visible) next.heightPx - ime.bottom else Int.MAX_VALUE)
        }
        if (next != lastScreen) {
            lastScreen = next
            view.post { host.environmentChanged() }
        }
        return insets
    }
    val layoutListener = View.OnLayoutChangeListener { _, left, top, right, bottom,
        oldLeft, oldTop, oldRight, oldBottom ->
        host.view?.let { observeOwnWindowId(it) }
        if (right - left != oldRight - oldLeft || bottom - top != oldBottom - oldTop) {
            stopInteraction()
            reconcileWindow()
        }
    }

    val attachListener = object : View.OnAttachStateChangeListener {
        override fun onViewAttachedToWindow(view: View) { observeOwnWindowId(view) }
        override fun onViewDetachedFromWindow(view: View) {
            OverlayOwnWindowIdentity.detached()
            if (canUseWindow() && !visibility.destroying) failWindow()
        }
    }

    fun screenBounds(): OverlayScreen {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && (host.manager != null)) {
            val metrics = windowManager.currentWindowMetrics
            val bounds = metrics.bounds
            val insets = metrics.windowInsets.getInsetsIgnoringVisibility(
                WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout(),
            )
            return OverlayScreen(
                bounds.width(), bounds.height(),
                leftPx = insets.left,
                topPx = insets.top,
                rightPx = bounds.width() - insets.right,
                bottomPx = bounds.height() - insets.bottom,
            )
        }
        val metrics = resources.displayMetrics
        // API < 30: the root window's system insets supply the safe rectangle when attached.
        val insets = if ((host.view != null)) overlayView.rootWindowInsets else null
        @Suppress("DEPRECATION")
        return OverlayScreen(
            metrics.widthPixels, metrics.heightPixels,
            leftPx = insets?.systemWindowInsetLeft ?: 0,
            topPx = insets?.systemWindowInsetTop ?: 0,
            rightPx = metrics.widthPixels - (insets?.systemWindowInsetRight ?: 0),
            bottomPx = metrics.heightPixels - (insets?.systemWindowInsetBottom ?: 0),
        )
    }

    fun windowSize(): OverlaySize {
        val fallback = VanOverlayController.fallbackSizeFor(uiState.presentation, ::dp, screenBounds())
        return OverlaySize(
            if ((host.view != null) && overlayView.width > 0) overlayView.width else fallback.widthPx,
            if ((host.view != null) && overlayView.height > 0) overlayView.height else fallback.heightPx,
        )
    }

    fun refreshKeyboardOverlap() {
        val overlap = if ((host.params != null)) {
            OverlayVisibilityPolicy.keyboardOverlaps(
                visibility.keyboardVisible, keyboardTopPx,
                OverlayPlacement(layoutParams.x, layoutParams.y), windowSize(), screenBounds(),
            )
        } else false
        visibility = visibility.copy(keyboardOverlapping = overlap)
    }

    /** Clamp both dimensions, then lift above a known IME when the window can fit there. */
    fun reconcileWindow() {
        if (!canUseWindow()) return
        val screen = screenBounds()
        lastScreen = screen
        if (boards.reconcile()) {
            refreshKeyboardOverlap(); applyVisibilityLifecycle(); return
        }
        val size = windowSize()
        val availableWidth = screen.safeWidth.coerceAtLeast(1)
        val availableHeight = screen.safeHeight.coerceAtLeast(1)
        var resized = false
        if (size.widthPx > availableWidth) {
            layoutParams.width = availableWidth
            resized = true
        }
        if (size.heightPx > availableHeight) {
            layoutParams.height = availableHeight
            resized = true
        }
        val boundedSize = OverlaySize(
            size.widthPx.coerceIn(1, availableWidth),
            size.heightPx.coerceIn(1, availableHeight),
        )
        var placement = VanOverlayController.clamp(
            layoutParams.x, layoutParams.y, boundedSize.widthPx, boundedSize.heightPx, screen,
        )
        if (visibility.keyboardVisible && keyboardTopPx != Int.MAX_VALUE) {
            val above = (keyboardTopPx.toLong() - boundedSize.heightPx - dp(12))
                .coerceIn(screen.safeTop.toLong(), Int.MAX_VALUE.toLong()).toInt()
            placement = VanOverlayController.clamp(
                placement.x, minOf(placement.y, above),
                boundedSize.widthPx, boundedSize.heightPx, screen,
            )
        }
        val moved = placement != OverlayPlacement(layoutParams.x, layoutParams.y)
        if (resized || moved) {
            layoutParams.x = placement.x
            layoutParams.y = placement.y
            if (!updateWindow()) return
            recordActualEdge()
            persistState()
        }
        refreshKeyboardOverlap()
        applyVisibilityLifecycle()
    }

    fun captureDragPointer(point: OverlayPoint?) {
        dragPointer = point?.takeIf {
            canUseWindow() && overlayView.isAttachedToWindow && it.x.isFinite() && it.y.isFinite()
        }
    }

    fun beginDrag() {
        if (!canUseWindow() || !OverlayVisibilityPolicy.shouldAnimate(visibility)) {
            dragPointer = null
            return
        }
        // begin cancels the native animator before it reads the actual placement.
        boards.dragged()
        val next = dragController.begin(uiState, SystemClock.uptimeMillis())
        uiState = if (canUseWindow() && OverlayVisibilityPolicy.shouldAnimate(visibility)) next
        else next.copy(dragging = false, dismissTargetVisible = false, dismissTargetArmed = false)
    }

    fun dragBy(dx: Int, dy: Int) = dragBy(dx.toFloat(), dy.toFloat())

    fun dragBy(dx: Float, dy: Float) {
        if (!canUseWindow() || !uiState.dragging) return
        val next = dragController.drag(uiState, dx, dy, SystemClock.uptimeMillis())
        boards.dragged()
        uiState = if (canUseWindow() && OverlayVisibilityPolicy.shouldAnimate(visibility)) next
        else next.copy(dragging = false, dismissTargetVisible = false, dismissTargetArmed = false)
    }

    fun finishDrag() {
        try {
            if (!canUseWindow() || !uiState.dragging) return
            val next = dragController.finish(uiState, reducedMotion = host.context.systemReducedMotionEnabled())
            uiState = next ?: uiState.copy(
                dragging = false, dismissTargetVisible = false, dismissTargetArmed = false,
            )
        } finally {
            dragPointer = null
        }
    }

    fun cancelDrag() {
        dragPointer = null
        if (!(host.params != null)) return
        uiState = dragController.cancel(uiState)
        persistState()
    }

    fun stopInteraction() {
        cancelSettle()
        if (uiState.dragging && (host.params != null)) {
            uiState = dragController.cancel(uiState)
            persistState()
        }
        hideDismissTarget()
    }

    private val dragWindow = object : OverlayWindowPort {
        override fun screen() = screenBounds()
        override fun dp(value: Int) = this@OverlayWindowInteraction.dp(value)
        override fun size(presentation: VanOverlayPresentation) = windowSize()
        override fun position() = OverlayPlacement(layoutParams.x, layoutParams.y)
        override fun dismissHitTest(size: OverlaySize): Boolean =
            canUseWindow() && uiState.dragging &&
                OverlayVisibilityPolicy.shouldAnimate(visibility) &&
                VanOverlayController.isInsideDismissTarget(
                    dragPointer,
                    host.dismissBounds(),
                )
        override fun dismissArmedOnRelease(armed: Boolean): Boolean =
            armed && dismissHitTest(windowSize())
        override fun cancelSettle() = this@OverlayWindowInteraction.cancelSettle()
        override fun moveTo(x: Int, y: Int) {
            moveWindow(OverlayPlacement(x, y))
        }
        override fun settleTo(target: OverlayPlacement, edge: DockEdge, durationMs: Int) {
            startSettle(target, edge, durationMs)
        }
        override fun armedFeedback() {
            if (canUseWindow()) overlayView.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        }
        override fun showDismissTarget() = this@OverlayWindowInteraction.showDismissTarget()
        override fun refreshDismissTarget() = this@OverlayWindowInteraction.refreshDismissTarget()
        override fun hideDismissTarget() = this@OverlayWindowInteraction.hideDismissTarget()
        override fun dismissOverlay() {
            host.dismissOverlay()
        }
        override fun dockedTo(edge: DockEdge, durationMs: Int) { dockEdge = edge }
        // The controller calls this immediately for legacy synchronous ports.
        // Native feedback belongs to successful settle completion, including duration zero.
        override fun dockFeedback() = Unit
    }

    private val dragController = OverlayDragController(dragWindow)

    private fun completeDock(edge: DockEdge) {
        boards.dragged()
        dockEdge = edge
        persistState()
        if (edge != DockEdge.NONE && canUseWindow()) {
            overlayView.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        }
    }

    private fun startSettle(target: OverlayPlacement, edge: DockEdge, durationMs: Int) {
        cancelSettle()
        if (!canUseWindow()) return
        val start = OverlayPlacement(layoutParams.x, layoutParams.y)
        if (durationMs <= 0 || start == target || !OverlayVisibilityPolicy.shouldAnimate(visibility)) {
            if (moveWindow(target)) completeDock(edge)
            return
        }
        val motion = OverlaySettleMotion(start, target, durationMs, SystemClock.uptimeMillis())
        val animator = ValueAnimator.ofFloat(0f, 1f)
        animator.duration = durationMs.toLong()
        animator.interpolator = LinearInterpolator()
        animator.addUpdateListener {
            if (settleAnimator === animator) {
                moveWindow(motion.positionAtFraction(animator.animatedFraction.toDouble()))
            }
        }
        animator.addListener(object : AnimatorListenerAdapter() {
            override fun onAnimationEnd(animation: Animator) {
                if (settleAnimator !== animator) return
                val completed = moveWindow(motion.positionAtFraction(1.0))
                // Moving may synchronously pause or fail the window and cancel this motion.
                if (settleAnimator !== animator) return
                settleAnimator = null
                settleMotion = null
                animator.removeAllUpdateListeners()
                animator.removeAllListeners()
                if (completed) completeDock(edge)
            }
        })
        settleMotion = motion
        settleAnimator = animator
        animator.start()
    }

    fun cancelSettle() {
        val animator = settleAnimator ?: return
        settleAnimator = null
        settleMotion?.cancel()
        settleMotion = null
        // Remove the end callback before cancel: cancellation must never write the target.
        animator.removeAllUpdateListeners()
        animator.removeAllListeners()
        animator.cancel()
        if ((host.params != null)) {
            syncPosition()
            recordActualEdge()
            persistState()
        }
    }

    private fun recordActualEdge() {
        if (host.params == null) return
        val size = windowSize()
        dockEdge = VanOverlayController.edgeAt(
            layoutParams.x, layoutParams.y, size.widthPx, size.heightPx, screenBounds(),
        )
    }
}
