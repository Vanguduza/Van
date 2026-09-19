package com.dial.van.overlay

/**
 * The overlay's presentation and gesture arithmetic, with no window in sight.
 *
 * Rev 3.0 §41 and P3-AND-009: `FloatingOverlayService` is supposed to be responsible for
 * WindowManager and the foreground service, not for all domain state. It was 1,096 lines
 * and owned everything — the window, the Compose tree, the drag mechanics, the dismiss
 * hit-testing, the chat composer and the trade panel — which is how a service ends up with
 * geometry nobody can check.
 *
 * What moved here is the part that is arithmetic: where a drag is allowed to put the
 * avatar, whether the finger is over the dismiss target, and how big the thing being
 * dragged is. Every one of those is a source of bugs the owner experiences as "VAN went off
 * the edge of the screen and I couldn't get it back", and none of them needed a window to
 * be decided. It is pure, so it is executed in `android/verification`.
 *
 * The window manipulation stays in the service, because that genuinely is what a service
 * with a window is for.
 */
data class OverlayScreen(val widthPx: Int, val heightPx: Int)

data class OverlayPlacement(val x: Int, val y: Int)

object VanOverlayController {

    /**
     * The touch size of whatever is currently on screen.
     *
     * Three presentations, three sizes, and it was computed inline in two places with the
     * same `when` — which is the shape of a bug that only appears in one of them.
     */
    fun touchSizeFor(presentation: VanOverlayPresentation, dp: (Int) -> Int): Int = when (presentation) {
        VanOverlayPresentation.MINIMIZED -> dp(OverlayTheme.MINIMIZED_TOUCH_DP)
        VanOverlayPresentation.DOCKED -> dp(OverlayTheme.DOCK_WIDTH_DP)
        else -> dp(OverlayTheme.RESTING_HIT_DP)
    }

    /**
     * Where a drag is allowed to put the avatar.
     *
     * Clamped so that at least the whole touch target stays on screen: an avatar dragged
     * half off the edge is an avatar the owner cannot pick back up, and the only way out is
     * to force-stop the app.
     */
    fun clamp(x: Int, y: Int, touchSize: Int, screen: OverlayScreen): OverlayPlacement =
        OverlayPlacement(
            x = x.coerceIn(0, (screen.widthPx - touchSize).coerceAtLeast(0)),
            y = y.coerceIn(0, (screen.heightPx - touchSize).coerceAtLeast(0)),
        )

    /**
     * Whether the avatar's centre is over the dismiss target.
     *
     * Centre against centre, within half the hit size on each axis. Comparing corners is
     * the version that makes the target feel like it moves as the owner zooms VAN in and
     * out, because the corner of a 48dp avatar and the corner of a 96dp one are in
     * different places relative to the finger.
     */
    fun isInsideDismissTarget(
        x: Int,
        y: Int,
        avatarSize: Int,
        screen: OverlayScreen,
        dp: (Int) -> Int,
    ): Boolean {
        val hit = dp(OverlayTheme.DISMISS_HIT_DP)
        val bottom = dp(OverlayTheme.DISMISS_BOTTOM_MARGIN_DP)
        val centreX = x + avatarSize / 2
        val centreY = y + avatarSize / 2
        val targetX = screen.widthPx / 2
        val targetY = screen.heightPx - bottom - hit / 2
        return kotlin.math.abs(centreX - targetX) <= hit / 2 &&
            kotlin.math.abs(centreY - targetY) <= hit / 2
    }

    /**
     * Where the avatar lands when the finger lifts, and which edge it is docked to.
     *
     * Delegated to [EdgeDocking] rather than reimplemented: the service had the snap and
     * the edge detection as two consecutive calls with the same five arguments, which is
     * one argument-order slip away from an avatar that snaps to one edge and reports the
     * other.
     */
    fun settle(x: Int, y: Int, touchSize: Int, screen: OverlayScreen): Pair<OverlayPlacement, DockEdge> {
        val snapped = EdgeDocking.snap(x, y, touchSize, screen.widthPx, screen.heightPx)
        val edge = EdgeDocking.detectEdge(
            snapped.first, snapped.second, touchSize, screen.widthPx, screen.heightPx,
        )
        return OverlayPlacement(snapped.first, snapped.second) to edge
    }
}
