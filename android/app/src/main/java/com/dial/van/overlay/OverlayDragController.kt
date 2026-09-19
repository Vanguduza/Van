package com.dial.van.overlay

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

    /** Remember which edge VAN ended up docked to. */
    fun dockedTo(edge: DockEdge)
}

internal class OverlayDragController(private val window: OverlayWindowPort) {

    fun begin(state: VanOverlayUiState): VanOverlayUiState {
        window.showDismissTarget()
        return state.copy(
            dragging = true,
            dismissTargetVisible = true,
            // Quick controls during a drag are a menu that follows the finger.
            quickControls = VanQuickControlsState.HIDDEN,
        )
    }

    fun drag(state: VanOverlayUiState, dx: Int, dy: Int): VanOverlayUiState {
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
     */
    fun finish(state: VanOverlayUiState): VanOverlayUiState? {
        window.hideDismissTarget()
        if (state.dismissTargetArmed) {
            window.dismissOverlay()
            return null
        }
        val touch = VanOverlayController.touchSizeFor(state.presentation, window::dp)
        val at = window.position()
        val (snapped, edge) = VanOverlayController.settle(at.x, at.y, touch, window.screen())
        window.moveTo(snapped.x, snapped.y)
        window.dockedTo(edge)
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
}
