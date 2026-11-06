package com.dial.van.overlay

/** Screen coordinates and the safe rectangle within them; old two-argument callers remain valid. */
data class OverlayScreen(
    val widthPx: Int,
    val heightPx: Int,
    val leftPx: Int = 0,
    val topPx: Int = 0,
    val rightPx: Int = widthPx,
    val bottomPx: Int = heightPx,
) {
    val safeLeft: Int get() = leftPx.coerceIn(0, widthPx.coerceAtLeast(0))
    val safeTop: Int get() = topPx.coerceIn(0, heightPx.coerceAtLeast(0))
    val safeRight: Int get() = rightPx.coerceIn(safeLeft, widthPx.coerceAtLeast(0))
    val safeBottom: Int get() = bottomPx.coerceIn(safeTop, heightPx.coerceAtLeast(0))
    val safeWidth: Int get() = safeRight - safeLeft
    val safeHeight: Int get() = safeBottom - safeTop
}

data class OverlayPlacement(val x: Int, val y: Int)
data class OverlaySize(val widthPx: Int, val heightPx: Int)

/** Absolute screen coordinates, independent of window gravity. */
data class OverlayPoint(val x: Double, val y: Double)
data class OverlayRect(val left: Double, val top: Double, val right: Double, val bottom: Double)

object VanOverlayController {
    /** Compose has already transformed the gesture-local point into window coordinates. */
    internal fun windowPointToScreen(
        pointInWindow: OverlayPoint?,
        viewOnScreen: OverlayPoint,
        viewInWindow: OverlayPoint,
    ): OverlayPoint? {
        val point = pointInWindow ?: return null
        if (!point.x.isFinite() || !point.y.isFinite() ||
            !viewOnScreen.x.isFinite() || !viewOnScreen.y.isFinite() ||
            !viewInWindow.x.isFinite() || !viewInWindow.y.isFinite()) return null
        val x = point.x + (viewOnScreen.x - viewInWindow.x)
        val y = point.y + (viewOnScreen.y - viewInWindow.y)
        return if (x.isFinite() && y.isFinite()) OverlayPoint(x, y) else null
    }

    fun isInsideDismissTarget(pointer: OverlayPoint?, target: OverlayRect?): Boolean {
        if (pointer == null || target == null) return false
        if (!pointer.x.isFinite() || !pointer.y.isFinite() ||
            !target.left.isFinite() || !target.top.isFinite() ||
            !target.right.isFinite() || !target.bottom.isFinite() ||
            target.right <= target.left || target.bottom <= target.top) return false
        return pointer.x >= target.left && pointer.x <= target.right &&
            pointer.y >= target.top && pointer.y <= target.bottom
    }

    /** Compatibility square touch API; real windows provide measured rectangular dimensions. */
    fun touchSizeFor(presentation: VanOverlayPresentation, dp: (Int) -> Int): Int = when (presentation) {
        VanOverlayPresentation.MINIMIZED -> dp(OverlayTheme.MINIMIZED_TOUCH_DP)
        VanOverlayPresentation.DOCKED -> dp(OverlayTheme.DOCK_WIDTH_DP)
        else -> dp(OverlayTheme.RESTING_HIT_DP)
    }

    /** Used only until the Compose window has measured its actual bounds. */
    fun fallbackSizeFor(
        presentation: VanOverlayPresentation,
        dp: (Int) -> Int,
        screen: OverlayScreen,
    ): OverlaySize = when (presentation) {
        VanOverlayPresentation.WORKBOARD_COMPACT -> OverlaySize(
            dp(OverlayTheme.COMPACT_WIDTH_DP), dp(OverlayTheme.COMPACT_HEIGHT_DP),
        )
        VanOverlayPresentation.WORKBOARD_EXPANDED -> OverlaySize(
            dp(OverlayTheme.EXPANDED_WIDTH_DP), dp(OverlayTheme.EXPANDED_HEIGHT_DP),
        )
        VanOverlayPresentation.WORKBOARD_MAXIMIZED -> OverlaySize(
            (screen.safeWidth - dp(OverlayTheme.MAXIMIZED_HORIZONTAL_MARGIN_DP) * 2).coerceAtLeast(1),
            (screen.safeHeight * OverlayTheme.MAXIMIZED_HEIGHT_FRACTION).toInt().coerceAtLeast(1),
        )
        else -> touchSizeFor(presentation, dp).let { OverlaySize(it, it) }
    }

    fun clamp(x: Int, y: Int, touchSize: Int, screen: OverlayScreen): OverlayPlacement =
        clamp(x, y, touchSize, touchSize, screen)

    fun clamp(x: Int, y: Int, width: Int, height: Int, screen: OverlayScreen): OverlayPlacement =
        clamp(x.toDouble(), y.toDouble(), width, height, screen)

    fun clamp(x: Double, y: Double, width: Int, height: Int, screen: OverlayScreen): OverlayPlacement {
        val maxX = maxOf(screen.safeLeft.toLong(), screen.safeRight.toLong() - width.coerceAtLeast(0)).toInt()
        val maxY = maxOf(screen.safeTop.toLong(), screen.safeBottom.toLong() - height.coerceAtLeast(0)).toInt()
        return OverlayPlacement(
            (if (x.isFinite()) x else screen.safeLeft.toDouble())
                .coerceIn(screen.safeLeft.toDouble(), maxX.toDouble()).toInt(),
            (if (y.isFinite()) y else screen.safeTop.toDouble())
                .coerceIn(screen.safeTop.toDouble(), maxY.toDouble()).toInt(),
        )
    }

    fun isInsideDismissTarget(
        x: Int,
        y: Int,
        avatarSize: Int,
        screen: OverlayScreen,
        dp: (Int) -> Int,
    ): Boolean = isInsideDismissTarget(x, y, avatarSize, avatarSize, screen, dp)

    fun isInsideDismissTarget(
        x: Int,
        y: Int,
        width: Int,
        height: Int,
        screen: OverlayScreen,
        dp: (Int) -> Int,
    ): Boolean {
        val hit = dp(OverlayTheme.DISMISS_HIT_DP).coerceAtLeast(0)
        val bottom = dp(OverlayTheme.DISMISS_BOTTOM_MARGIN_DP)
        val centreX = x.toDouble() + width.coerceAtLeast(0) / 2.0
        val centreY = y.toDouble() + height.coerceAtLeast(0) / 2.0
        // Dismiss window remains bottom-centre on the physical screen, as before.
        val targetX = screen.widthPx / 2.0
        val targetY = screen.heightPx.toDouble() - bottom - hit / 2.0
        return kotlin.math.abs(centreX - targetX) <= hit / 2.0 &&
            kotlin.math.abs(centreY - targetY) <= hit / 2.0
    }

    fun settle(
        x: Int,
        y: Int,
        touchSize: Int,
        screen: OverlayScreen,
        velocityXPxPerMs: Float = 0f,
        velocityYPxPerMs: Float = 0f,
    ): Pair<OverlayPlacement, DockEdge> = settle(
        x, y, touchSize, touchSize, screen, velocityXPxPerMs, velocityYPxPerMs,
    )

    fun settle(
        x: Int,
        y: Int,
        width: Int,
        height: Int,
        screen: OverlayScreen,
        velocityXPxPerMs: Float = 0f,
        velocityYPxPerMs: Float = 0f,
    ): Pair<OverlayPlacement, DockEdge> {
        val at = clamp(x, y, width, height, screen)
        val snapped = EdgeDocking.flingSnap(
            at.x - screen.safeLeft, at.y - screen.safeTop,
            velocityXPxPerMs, velocityYPxPerMs,
            width, height, screen.safeWidth, screen.safeHeight,
        )
        val placement = OverlayPlacement(snapped.first + screen.safeLeft, snapped.second + screen.safeTop)
        return placement to edgeAt(placement.x, placement.y, width, height, screen)
    }

    fun edgeAt(x: Int, y: Int, width: Int, height: Int, screen: OverlayScreen): DockEdge =
        EdgeDocking.detectEdge(
            x - screen.safeLeft, y - screen.safeTop,
            width, height, screen.safeWidth, screen.safeHeight,
        )
}
