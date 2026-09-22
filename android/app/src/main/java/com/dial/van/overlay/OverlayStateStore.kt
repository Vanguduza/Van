package com.dial.van.overlay

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

data class OverlayPersistedState(
    val x: Int,
    val y: Int,
    val presentation: VanOverlayPresentation,
    val dock: DockEdge,
    val serviceRunning: Boolean,
)

class OverlayStateStore(context: Context) {
    /**
     * GAP-F-027 — this was the one plain `SharedPreferences` writer left in the app while
     * credentials, the command queue and the session outbox were all encrypted. The
     * contents are low-sensitivity (position, presentation, dock edge, running flag), but
     * one storage policy is easier to audit than one-with-an-exception, and the same
     * Keystore-backed scheme the gateway client uses costs nothing here.
     */
    private val prefs: SharedPreferences = EncryptedSharedPreferences.create(
        context.applicationContext,
        PREFS,
        MasterKey.Builder(context.applicationContext).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

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
