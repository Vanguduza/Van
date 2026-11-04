package com.dial.van.overlay

import com.dial.van.visual.VanMotionMap

internal interface OverlayWindowPort {
    fun screen(): OverlayScreen
    fun dp(value: Int): Int
    fun position(): OverlayPlacement
    fun moveTo(x: Int, y: Int)
    fun armedFeedback()
    fun showDismissTarget()
    fun refreshDismissTarget()
    fun hideDismissTarget()
    fun dismissOverlay()
    fun dockedTo(edge: DockEdge, durationMs: Int)
    fun dockFeedback()

    /** Legacy ports retain their square geometry and immediate settle behaviour. */
    fun size(presentation: VanOverlayPresentation): OverlaySize {
        val side = VanOverlayController.touchSizeFor(presentation, ::dp)
        return OverlaySize(side, side)
    }

    /** Old ports retain centre-based hit testing; native ports use their active pointer. */
    fun dismissHitTest(size: OverlaySize): Boolean {
        val at = position()
        return VanOverlayController.isInsideDismissTarget(
            at.x, at.y, size.widthPx, size.heightPx, screen(), ::dp,
        )
    }

    /** Native ports may revalidate measured geometry before the target is hidden. */
    fun dismissArmedOnRelease(armed: Boolean): Boolean = armed

    /** Must leave position() at the actual current window, never the pending target. */
    fun cancelSettle() = Unit

    /** The real window owner animates this; synchronous ports remain source compatible. */
    fun settleTo(target: OverlayPlacement, edge: DockEdge, durationMs: Int) {
        moveTo(target.x, target.y)
        dockedTo(edge, durationMs)
    }
}

/** Pure interpolation; Android supplies ValueAnimator's duration-scale-aware fraction. */
internal class OverlaySettleMotion(
    private val start: OverlayPlacement,
    private val target: OverlayPlacement,
    private val durationMs: Int,
    private val startedAtMs: Long = System.nanoTime() / 1_000_000L,
) {
    private var elapsedMs = 0.0
    private var progress = 0.0
    private var current = start
    private var cancelled = false

    fun position(nowMs: Long = System.nanoTime() / 1_000_000L): OverlayPlacement {
        if (cancelled) return current
        elapsedMs = maxOf(elapsedMs, nowMs.toDouble() - startedAtMs.toDouble(), 0.0)
        return positionAtFraction(if (durationMs <= 0) 1.0 else elapsedMs / durationMs)
    }

    fun positionAtFraction(fraction: Double): OverlayPlacement {
        if (cancelled || !fraction.isFinite()) return current
        val bounded = fraction.coerceIn(0.0, 1.0)
        if (bounded < progress) return current
        progress = bounded
        current = if (progress >= 1.0) target else OverlayPlacement(
            (start.x.toDouble() + (target.x.toDouble() - start.x) * progress).toInt(),
            (start.y.toDouble() + (target.y.toDouble() - start.y) * progress).toInt(),
        )
        return current
    }

    fun cancel(): OverlayPlacement {
        cancelled = true
        return current
    }
}

internal class OverlayDragController(private val window: OverlayWindowPort) {
    private var velocityX = 0f
    private var velocityY = 0f
    private var lastDragAtMs: Long? = null
    private var residualX = 0.0
    private var residualY = 0.0

    fun begin(
        state: VanOverlayUiState,
        nowMs: Long = System.nanoTime() / 1_000_000L,
    ): VanOverlayUiState {
        window.cancelSettle()
        resetInput()
        lastDragAtMs = nowMs
        val at = window.position()
        window.showDismissTarget()
        return state.copy(
            xPx = at.x, yPx = at.y,
            dragging = true, dismissTargetVisible = true, dismissTargetArmed = false,
            quickControls = VanQuickControlsState.HIDDEN,
        )
    }

    fun drag(
        state: VanOverlayUiState,
        dx: Int,
        dy: Int,
        nowMs: Long = System.nanoTime() / 1_000_000L,
    ): VanOverlayUiState = drag(state, dx.toFloat(), dy.toFloat(), nowMs)

    fun drag(
        state: VanOverlayUiState,
        dx: Float,
        dy: Float,
        nowMs: Long = System.nanoTime() / 1_000_000L,
    ): VanOverlayUiState {
        if (!dx.isFinite() || !dy.isFinite()) {
            resetInput()
            lastDragAtMs = nowMs
            val at = window.position()
            return state.copy(xPx = at.x, yPx = at.y, dismissTargetArmed = false)
        }
        val previous = lastDragAtMs
        val elapsed = if (previous == null) 0.0 else nowMs.toDouble() - previous.toDouble()
        if (elapsed > 0.0) {
            val sampleX = (dx.toDouble() / elapsed).toFloat()
            val sampleY = (dy.toDouble() / elapsed).toFloat()
            velocityX = velocityX * VELOCITY_SMOOTHING + sampleX * (1f - VELOCITY_SMOOTHING)
            velocityY = velocityY * VELOCITY_SMOOTHING + sampleY * (1f - VELOCITY_SMOOTHING)
        } else {
            velocityX = 0f
            velocityY = 0f
        }
        lastDragAtMs = nowMs

        // Accumulate delta fractions, including negative fractions, before integer placement.
        val accumulatedX = residualX + dx.toDouble()
        val accumulatedY = residualY + dy.toDouble()
        val wholeX = accumulatedX.toInt()
        val wholeY = accumulatedY.toInt()
        residualX = if (accumulatedX in Int.MIN_VALUE.toDouble()..Int.MAX_VALUE.toDouble()) {
            accumulatedX - wholeX
        } else 0.0
        residualY = if (accumulatedY in Int.MIN_VALUE.toDouble()..Int.MAX_VALUE.toDouble()) {
            accumulatedY - wholeY
        } else 0.0
        val size = window.size(state.presentation)
        val at = window.position()
        val wantedX = at.x.toDouble() + wholeX
        val wantedY = at.y.toDouble() + wholeY
        val placed = VanOverlayController.clamp(
            wantedX, wantedY, size.widthPx, size.heightPx, window.screen(),
        )
        if (placed.x.toDouble() != wantedX) residualX = 0.0
        if (placed.y.toDouble() != wantedY) residualY = 0.0
        window.moveTo(placed.x, placed.y)
        val actual = window.position()
        val armed = window.dismissHitTest(size)
        if (armed && !state.dismissTargetArmed) window.armedFeedback()
        window.refreshDismissTarget()
        return state.copy(xPx = actual.x, yPx = actual.y, dismissTargetArmed = armed)
    }

    fun finish(state: VanOverlayUiState, reducedMotion: Boolean = false): VanOverlayUiState? {
        // Consult the pointer and attached target before hiding releases either of them.
        val armed = window.dismissArmedOnRelease(state.dismissTargetArmed)
        window.hideDismissTarget()
        if (armed) {
            resetInput()
            window.cancelSettle()
            window.dismissOverlay()
            return null
        }
        val size = window.size(state.presentation)
        val at = window.position()
        val (target, edge) = VanOverlayController.settle(
            at.x, at.y, size.widthPx, size.heightPx, window.screen(), velocityX, velocityY,
        )
        val speed = kotlin.math.hypot(velocityX, velocityY)
        resetInput()
        window.settleTo(target, edge, VanMotionMap.flingDockDurationMs(speed, reducedMotion))
        if (edge != DockEdge.NONE) window.dockFeedback()
        val actual = window.position()
        return state.copy(
            xPx = actual.x, yPx = actual.y, dragging = false,
            dismissTargetVisible = false, dismissTargetArmed = false,
        )
    }

    fun cancel(state: VanOverlayUiState): VanOverlayUiState {
        window.cancelSettle()
        resetInput()
        window.hideDismissTarget()
        val at = window.position()
        return state.copy(
            xPx = at.x, yPx = at.y, dragging = false,
            dismissTargetVisible = false, dismissTargetArmed = false,
        )
    }

    private fun resetInput() {
        velocityX = 0f
        velocityY = 0f
        lastDragAtMs = null
        residualX = 0.0
        residualY = 0.0
    }

    private companion object {
        const val VELOCITY_SMOOTHING = 0.7f
    }
}
