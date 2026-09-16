package com.dial.van.overlay

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

enum class OverlayMode {
    /** Frameless rest: VAN and his living aura only. No glass until interaction. */
    RESTING,

    /** Glass condenses from the aura; VAN overlaps the panel; 1–3 quick actions. */
    COMPACT,

    /** Working surface: glass grown from VAN, status, mesh cue and the action rail. */
    EXPANDED,

    /** Intentional edge dock: crescent aura, face/visor preserved, 88dp hit target. */
    DOCKED,
}

enum class DockEdge {
    NONE,
    LEFT,
    RIGHT,
    TOP,
    BOTTOM,
}

data class OverlayPersistedState(
    val x: Int,
    val y: Int,
    val mode: OverlayMode,
    val dock: DockEdge,
    val serviceRunning: Boolean,
)

class OverlayStateStore(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun save(state: OverlayPersistedState) {
        prefs.edit {
            putInt(KEY_X, state.x)
            putInt(KEY_Y, state.y)
            putString(KEY_MODE, state.mode.name)
            putString(KEY_DOCK, state.dock.name)
            putBoolean(KEY_RUNNING, state.serviceRunning)
        }
    }

    fun load(defaultX: Int, defaultY: Int): OverlayPersistedState = OverlayPersistedState(
        x = prefs.getInt(KEY_X, defaultX),
        y = prefs.getInt(KEY_Y, defaultY),
        mode = runCatching { OverlayMode.valueOf(prefs.getString(KEY_MODE, OverlayMode.RESTING.name)!!) }
            .getOrDefault(OverlayMode.RESTING),
        dock = runCatching { DockEdge.valueOf(prefs.getString(KEY_DOCK, DockEdge.NONE.name)!!) }
            .getOrDefault(DockEdge.NONE),
        serviceRunning = prefs.getBoolean(KEY_RUNNING, false),
    )

    fun markRunning(running: Boolean) {
        prefs.edit { putBoolean(KEY_RUNNING, running) }
    }

    companion object {
        private const val PREFS = "van_overlay_state"
        private const val KEY_X = "x"
        private const val KEY_Y = "y"
        private const val KEY_MODE = "mode"
        private const val KEY_DOCK = "dock"
        private const val KEY_RUNNING = "running"
    }
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
        return nx to ny
    }

    fun detectEdge(x: Int, y: Int, avatarSize: Int, screenW: Int, screenH: Int): DockEdge = when {
        x <= 0 -> DockEdge.LEFT
        y <= 0 -> DockEdge.TOP
        x + avatarSize >= screenW -> DockEdge.RIGHT
        y + avatarSize >= screenH -> DockEdge.BOTTOM
        else -> DockEdge.NONE
    }
}
