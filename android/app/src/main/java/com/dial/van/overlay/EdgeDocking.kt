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
}
