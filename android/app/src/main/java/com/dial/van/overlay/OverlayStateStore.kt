package com.dial.van.overlay

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

/** Edge dock is distinct from the circular minimized representation. */
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
    val presentation: VanOverlayPresentation,
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
            putString(KEY_PRESENTATION, state.presentation.name)
            putString(KEY_DOCK, state.dock.name)
            putBoolean(KEY_RUNNING, state.serviceRunning)
        }
    }

    fun load(defaultX: Int, defaultY: Int): OverlayPersistedState {
        val presentation = runCatching {
            VanOverlayPresentation.valueOf(
                prefs.getString(KEY_PRESENTATION, null)
                    ?: legacyPresentation(prefs.getString(KEY_LEGACY_MODE, null)).name,
            )
        }.getOrDefault(VanOverlayPresentation.FULL_FLOATING)

        return OverlayPersistedState(
            x = prefs.getInt(KEY_X, defaultX),
            y = prefs.getInt(KEY_Y, defaultY),
            presentation = presentation,
            dock = runCatching {
                DockEdge.valueOf(prefs.getString(KEY_DOCK, DockEdge.NONE.name)!!)
            }.getOrDefault(DockEdge.NONE),
            serviceRunning = prefs.getBoolean(KEY_RUNNING, false),
        )
    }

    fun markRunning(running: Boolean) {
        prefs.edit { putBoolean(KEY_RUNNING, running) }
    }

    private fun legacyPresentation(value: String?): VanOverlayPresentation = when (value) {
        "COMPACT" -> VanOverlayPresentation.WORKBOARD_COMPACT
        "EXPANDED" -> VanOverlayPresentation.WORKBOARD_EXPANDED
        "DOCKED" -> VanOverlayPresentation.DOCKED
        else -> VanOverlayPresentation.FULL_FLOATING
    }

    companion object {
        private const val PREFS = "van_overlay_state"
        private const val KEY_X = "x"
        private const val KEY_Y = "y"
        private const val KEY_PRESENTATION = "presentation"
        private const val KEY_LEGACY_MODE = "mode"
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
