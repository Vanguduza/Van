package com.dial.van.overlay

import android.os.Build
import android.view.WindowManager
import com.dial.van.visual.VanGlassTokens

/**
 * What window flags each presentation needs, and whether this device can blur behind.
 *
 * P3-AND-009. Its own file because it is one job with one rule that is easy to get backwards
 * and invisible when you do: a workboard must be focusable so the owner can type into it,
 * and everything else must not be, or VAN steals focus from whatever app the owner is
 * actually using. That is a bug reported as "my keyboard keeps closing", never as "the
 * overlay window flags are wrong".
 */
internal object OverlayWindowFlags {

    fun base(presentation: VanOverlayPresentation): Int {
        var flags = WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
        if (presentation !in WORKBOARDS) {
            flags = flags or WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        }
        return flags
    }

    /** The presentations the owner can type into. */
    val WORKBOARDS = setOf(
        VanOverlayPresentation.WORKBOARD_COMPACT,
        VanOverlayPresentation.WORKBOARD_EXPANDED,
        VanOverlayPresentation.WORKBOARD_MAXIMIZED,
    )

    /** Cross-window blur is Android 12 and up, and the device may still refuse it. */
    fun blurSupported(windowManager: WindowManager): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
            runCatching { windowManager.isCrossWindowBlurEnabled }.getOrDefault(false)

    fun apply(params: WindowManager.LayoutParams, presentation: VanOverlayPresentation, blur: Boolean, dp: (Int) -> Int) {
        val blurFlag = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && blur) {
            WindowManager.LayoutParams.FLAG_BLUR_BEHIND
        } else {
            0
        }
        params.flags = base(presentation) or blurFlag
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            params.blurBehindRadius = if (blurFlag != 0) dp(VanGlassTokens.BLUR_DP.toInt()) else 0
        }
    }
}
