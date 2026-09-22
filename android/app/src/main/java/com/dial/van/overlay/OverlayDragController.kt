package com.dial.van.overlay

import com.dial.van.visual.VanMotionMap

/**
 * Dragging VAN around the screen.
 *
 * P3-AND-009 and Rev 3.0 s41, which puts gestures with the controller rather than with the
 * service. This was four private methods in a 1,096-line Service, interleaved with window
 * plumbing, and it is the part of the overlay an owner interacts with most and the part
 * that fails most visibly: a drag that walks VAN off the edge, a dismiss target that arms
 * when the finger is nowhere near it, a flick that closes the assistant the owner meant to
 * move.
 *
 * The window work is behind [OverlayWindowPort] rather than removed, because moving a view
 * genuinely does need a WindowManager. What that leaves here is the sequence — when the
 * dismiss target appears, when the haptic fires, when a lift closes the overlay instead of
 * docking it — which is pure, and is executed in `android/verification` against a fake port.
 */
internal interface OverlayWindowPort {
    /** The screen the overlay is being dragged around. */
    fun screen(): OverlayScreen

    /** Density-independent pixels to real ones. */
    fun dp(value: Int): Int

    /** Where the overlay window currently sits. */
    fun position(): OverlayPlacement

    /** Move the overlay window. */
    fun moveTo(x: Int, y: Int)

    /** The tick the owner feels when the dismiss target arms. */
    fun armedFeedback()

    fun showDismissTarget()
    fun refreshDismissTarget()
    fun hideDismissTarget()

    /** Close the overlay: the owner dropped VAN on the dismiss target. */
    fun dismissOverlay()

    /**
     * Remember which edge VAN ended up docked to.
     *
     * [durationMs] is item 3's velocity-based fling duration ([VanMotionMap.flingDockDurationMs]
     * — quicker after a fast flick, the ordinary dock speed otherwise, zero under reduced
     * motion) so a caller that animates the settle rather than snapping it instantly has the
     * number to animate with.
     */
    fun dockedTo(edge: DockEdge, durationMs: Int)

    /** DNA §2 — "tick on dock/snap". Fired once a drag actually ends in a dock, never on a dismiss. */
    fun dockFeedback()
}

internal class OverlayDragController(private val window: OverlayWindowPort) {

    /** Smoothed release velocity, in pixels per millisecond, reset at every [begin]. */
    private var velocityX = 0f
    private var velocityY = 0f
    private var lastDragAtMs = 0L

    fun begin(state: VanOverlayUiState, nowMs: Long = System.currentTimeMillis()): VanOverlayUiState {
        velocityX = 0f
        velocityY = 0f
        lastDragAtMs = nowMs
        window.showDismissTarget()
        return state.copy(
            dragging = true,
            dismissTargetVisible = true,
            // Quick controls during a drag are a menu that follows the finger.
            quickControls = VanQuickControlsState.HIDDEN,
        )
    }

    fun drag(state: VanOverlayUiState, dx: Int, dy: Int, nowMs: Long = System.currentTimeMillis()): VanOverlayUiState {
        // Item 3 — velocity for the release, exponentially smoothed so one jittery frame
        // (a pointer sample with an unusually small or large elapsed time) does not by
        // itself decide whether the release reads as a flick.
        val elapsedMs = (nowMs - lastDragAtMs).coerceAtLeast(1L)
        val sampleVx = dx / elapsedMs.toFloat()
        val sampleVy = dy / elapsedMs.toFloat()
        velocityX = velocityX * VELOCITY_SMOOTHING + sampleVx * (1f - VELOCITY_SMOOTHING)
        velocityY = velocityY * VELOCITY_SMOOTHING + sampleVy * (1f - VELOCITY_SMOOTHING)
        lastDragAtMs = nowMs

        val touch = VanOverlayController.touchSizeFor(state.presentation, window::dp)
        val at = window.position()
        val placed = VanOverlayController.clamp(at.x + dx, at.y + dy, touch, window.screen())
        window.moveTo(placed.x, placed.y)

        val armed = VanOverlayController.isInsideDismissTarget(
            placed.x, placed.y, touch, window.screen(), window::dp,
        )
        // Only on the transition. A tick per frame while the finger hovers the target is a
        // phone buzzing continuously, which owners read as a fault.
        if (armed && !state.dismissTargetArmed) window.armedFeedback()
        window.refreshDismissTarget()
        return state.copy(xPx = placed.x, yPx = placed.y, dismissTargetArmed = armed)
    }

    /**
     * Returns null when the drag closed the overlay, because there is then no state to
     * render into: a copy() applied to a service that has just called `stopSelf` is an
     * update to a window that is going away.
     *
     * [reducedMotion] only affects [VanMotionMap.flingDockDurationMs]'s reported duration —
     * the placement itself (including whether a fast flick docks to an edge it did not
     * start near) is unaffected, matching DNA §2's rule that reduced motion changes how long
     * a transition takes, never what it communicates.
     */
    fun finish(state: VanOverlayUiState, reducedMotion: Boolean = false): VanOverlayUiState? {
        window.hideDismissTarget()
        if (state.dismissTargetArmed) {
            window.dismissOverlay()
            return null
        }
        val touch = VanOverlayController.touchSizeFor(state.presentation, window::dp)
        val at = window.position()
        val (snapped, edge) = VanOverlayController.settle(at.x, at.y, touch, window.screen(), velocityX, velocityY)
        val speed = kotlin.math.hypot(velocityX, velocityY)
        window.moveTo(snapped.x, snapped.y)
        window.dockedTo(edge, VanMotionMap.flingDockDurationMs(speed, reducedMotion))
        if (edge != DockEdge.NONE) window.dockFeedback()
        return state.copy(
            xPx = snapped.x,
            yPx = snapped.y,
            dragging = false,
            dismissTargetVisible = false,
            dismissTargetArmed = false,
        )
    }

    fun cancel(state: VanOverlayUiState): VanOverlayUiState {
        window.hideDismissTarget()
        return state.copy(
            dragging = false,
            dismissTargetVisible = false,
            // Cleared: a cancelled drag that leaves the target armed is an overlay that
            // closes on the owner's next, unrelated touch.
            dismissTargetArmed = false,
        )
    }

    private companion object {
        /** How much of the previous smoothed velocity survives each new sample. */
        const val VELOCITY_SMOOTHING = 0.7f
    }
}
