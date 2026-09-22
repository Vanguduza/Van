package com.dial.van.overlay

/**
 * Where a dragged avatar lands, and which edge it ends up against.
 *
 * P3-AND-009 — this was at the bottom of `OverlayStateStore.kt`, below a
 * `SharedPreferences` class, which meant that a pure, arithmetic, easily-wrong piece of
 * geometry could not be executed anywhere: the file it lived in imports `android.content`,
 * so the JVM harness could not compile it. Its own file, with no Android in it, is the
 * whole reason `VanOverlayControllerTest` can exist.
 */

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

    fun snap(x: Int, y: Int, avatarSize: Int, screenW: Int, screenH: Int): Pair<Int, Int> {
        var nx = x
        var ny = y
        if (x <= DOCK_THRESHOLD_PX) nx = 0
        if (y <= DOCK_THRESHOLD_PX) ny = 0
        if (x + avatarSize >= screenW - DOCK_THRESHOLD_PX) nx = screenW - avatarSize
        if (y + avatarSize >= screenH - DOCK_THRESHOLD_PX) ny = screenH - avatarSize
        return nx.coerceAtLeast(0) to ny.coerceAtLeast(0)
    }

    fun detectEdge(x: Int, y: Int, avatarSize: Int, screenW: Int, screenH: Int): DockEdge = when {
        x <= 0 -> DockEdge.LEFT
        y <= 0 -> DockEdge.TOP
        x + avatarSize >= screenW -> DockEdge.RIGHT
        y + avatarSize >= screenH -> DockEdge.BOTTOM
        else -> DockEdge.NONE
    }

    /**
     * Item 3 — velocity-based fling-to-edge. [snap] alone only docks a release that already
     * landed within [DOCK_THRESHOLD_PX] of an edge; a fast flick released mid-screen has no
     * position-only reason to dock anywhere, and stranding VAN wherever the finger happened
     * to lift reads as the overlay fighting the gesture rather than continuing it (the same
     * complaint [VanMotionMap.flingDockDurationMs] exists to answer for how *fast* the dock
     * animates, this answers for *whether* one happens at all).
     *
     * Falls straight through to [snap] whenever the release is already close enough to an
     * edge to dock on position alone, or the release carries no clearly-directional speed —
     * a slow drag that happens to end mid-screen must stay exactly where the owner left it.
     * Direction is decided by whichever axis' velocity dominates, which keeps a mostly-
     * horizontal flick from being read as a vertical one on a few stray pixels of jitter.
     */
    fun flingSnap(
        x: Int,
        y: Int,
        velocityXPxPerMs: Float,
        velocityYPxPerMs: Float,
        avatarSize: Int,
        screenW: Int,
        screenH: Int,
    ): Pair<Int, Int> {
        val (snappedX, snappedY) = snap(x, y, avatarSize, screenW, screenH)
        if (detectEdge(snappedX, snappedY, avatarSize, screenW, screenH) != DockEdge.NONE) {
            return snappedX to snappedY
        }
        val speed = kotlin.math.hypot(velocityXPxPerMs, velocityYPxPerMs)
        if (speed < FLING_VELOCITY_THRESHOLD_PX_PER_MS) return snappedX to snappedY
        val maxX = (screenW - avatarSize).coerceAtLeast(0)
        val maxY = (screenH - avatarSize).coerceAtLeast(0)
        return if (kotlin.math.abs(velocityXPxPerMs) >= kotlin.math.abs(velocityYPxPerMs)) {
            (if (velocityXPxPerMs < 0f) 0 else maxX) to snappedY.coerceIn(0, maxY)
        } else {
            snappedX.coerceIn(0, maxX) to (if (velocityYPxPerMs < 0f) 0 else maxY)
        }
    }

    /** Same flick threshold [VanMotionMap.flingDockDurationMs] uses for how fast to dock. */
    private const val FLING_VELOCITY_THRESHOLD_PX_PER_MS = 1.3f
}
