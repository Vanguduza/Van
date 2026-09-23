package com.dial.van.overlay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Settings

/** Parses screen broadcasts; the service remains the owner of lifecycle transitions. */
internal class OverlayScreenStateReceiver(
    private val onScreenOn: (Boolean) -> Unit,
) : BroadcastReceiver() {
    override fun onReceive(context: Context?, intent: Intent?) {
        when (intent?.action) {
            Intent.ACTION_SCREEN_ON, Intent.ACTION_USER_PRESENT -> onScreenOn(true)
            Intent.ACTION_SCREEN_OFF -> onScreenOn(false)
        }
    }
}

internal data class OverlayObstructionState(
    val keyboardVisible: Boolean,
    val fullscreenAppActive: Boolean,
    val keyboardTopPx: Int,
)

/** Converts accessibility broadcasts into typed obstruction state without owning policy. */
internal class OverlayObstructionReceiver(
    private val onState: (OverlayObstructionState) -> Unit,
) : BroadcastReceiver() {
    override fun onReceive(context: Context?, intent: Intent?) {
        if (intent?.action != VanObstructionAccessibilityService.ACTION_OBSTRUCTION_STATE) return
        onState(
            OverlayObstructionState(
                keyboardVisible = intent.getBooleanExtra(
                    VanObstructionAccessibilityService.EXTRA_KEYBOARD_VISIBLE, false,
                ),
                fullscreenAppActive = intent.getBooleanExtra(
                    VanObstructionAccessibilityService.EXTRA_FULLSCREEN_APP_ACTIVE, false,
                ),
                keyboardTopPx = intent.getIntExtra(
                    VanObstructionAccessibilityService.EXTRA_KEYBOARD_TOP_PX, Int.MAX_VALUE,
                ),
            ),
        )
    }
}

/** DNA §2 reduced-motion signal for non-Compose window movement. */
internal fun Context.systemReducedMotionEnabled(): Boolean = runCatching {
    Settings.Global.getFloat(
        contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f,
    ) == 0f
}.getOrDefault(false)
