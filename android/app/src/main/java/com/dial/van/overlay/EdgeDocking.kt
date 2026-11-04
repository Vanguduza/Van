package com.dial.van.overlay

/** Edge dock is distinct from the circular minimized representation. */
enum class DockEdge {
    NONE,
    LEFT,
    RIGHT,
    TOP,
    BOTTOM,
}

object EdgeDocking {
    private const val DOCK_THRESHOLD_PX = 48
    private const val FLING_VELOCITY_THRESHOLD_PX_PER_MS = 1.3f

    fun snap(x: Int, y: Int, avatarSize: Int, screenW: Int, screenH: Int): Pair<Int, Int> =
        snap(x, y, avatarSize, avatarSize, screenW, screenH)

    fun snap(
        x: Int, y: Int, avatarWidth: Int, avatarHeight: Int, screenW: Int, screenH: Int,
    ): Pair<Int, Int> {
        val maxX = maximum(screenW, avatarWidth)
        val maxY = maximum(screenH, avatarHeight)
        var nx = x.coerceIn(0, maxX)
        var ny = y.coerceIn(0, maxY)
        if (nx <= DOCK_THRESHOLD_PX) nx = 0
        if (ny <= DOCK_THRESHOLD_PX) ny = 0
        // Preserve the original right/bottom priority when both thresholds are near.
        if (x.toLong() >= maxX.toLong() - DOCK_THRESHOLD_PX) nx = maxX
        if (y.toLong() >= maxY.toLong() - DOCK_THRESHOLD_PX) ny = maxY
        return nx to ny
    }

    fun detectEdge(x: Int, y: Int, avatarSize: Int, screenW: Int, screenH: Int): DockEdge =
        detectEdge(x, y, avatarSize, avatarSize, screenW, screenH)

    fun detectEdge(
        x: Int, y: Int, avatarWidth: Int, avatarHeight: Int, screenW: Int, screenH: Int,
    ): DockEdge = when {
        x <= 0 -> DockEdge.LEFT
        y <= 0 -> DockEdge.TOP
        x >= maximum(screenW, avatarWidth) -> DockEdge.RIGHT
        y >= maximum(screenH, avatarHeight) -> DockEdge.BOTTOM
        else -> DockEdge.NONE
    }

    fun flingSnap(
        x: Int,
        y: Int,
        velocityXPxPerMs: Float,
        velocityYPxPerMs: Float,
        avatarSize: Int,
        screenW: Int,
        screenH: Int,
    ): Pair<Int, Int> = flingSnap(
        x, y, velocityXPxPerMs, velocityYPxPerMs, avatarSize, avatarSize, screenW, screenH,
    )

    fun flingSnap(
        x: Int,
        y: Int,
        velocityXPxPerMs: Float,
        velocityYPxPerMs: Float,
        avatarWidth: Int,
        avatarHeight: Int,
        screenW: Int,
        screenH: Int,
    ): Pair<Int, Int> {
        val snapped = snap(x, y, avatarWidth, avatarHeight, screenW, screenH)
        if (detectEdge(snapped.first, snapped.second, avatarWidth, avatarHeight, screenW, screenH) != DockEdge.NONE) {
            return snapped
        }
        if (!velocityXPxPerMs.isFinite() || !velocityYPxPerMs.isFinite()) return snapped
        val speed = kotlin.math.hypot(velocityXPxPerMs, velocityYPxPerMs)
        if (speed < FLING_VELOCITY_THRESHOLD_PX_PER_MS) return snapped
        val maxX = maximum(screenW, avatarWidth)
        val maxY = maximum(screenH, avatarHeight)
        return if (kotlin.math.abs(velocityXPxPerMs) >= kotlin.math.abs(velocityYPxPerMs)) {
            (if (velocityXPxPerMs < 0f) 0 else maxX) to snapped.second
        } else {
            snapped.first to (if (velocityYPxPerMs < 0f) 0 else maxY)
        }
    }

    private fun maximum(screen: Int, size: Int): Int =
        (screen.coerceAtLeast(0).toLong() - size.coerceAtLeast(0)).coerceAtLeast(0L).toInt()
}
