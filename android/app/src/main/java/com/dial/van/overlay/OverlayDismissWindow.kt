package com.dial.van.overlay

import android.content.Context
import android.graphics.PixelFormat
import android.view.Gravity
import android.view.WindowManager
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.ComposeView
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner

/**
 * The second window: the target the owner drops VAN onto to close it.
 *
 * P3-AND-009 and Rev 3.0 s41. The overlay manages two windows, and the service managed both
 * of them inline, so "is the dismiss target up" was a pair of nullable fields checked in
 * four places. Two windows, two owners.
 *
 * [show] is idempotent, which is the property that matters: `addView` on a view that is
 * already added throws, and the drag calls this on every gesture start.
 */
internal class OverlayDismissWindow<T>(
    private val host: T,
    private val windowManager: WindowManager,
    private val dp: (Int) -> Int,
) where T : Context, T : LifecycleOwner, T : SavedStateRegistryOwner {

    private var view: ComposeView? = null

    fun show(content: @Composable () -> Unit) {
        if (view != null) return
        val composeView = ComposeView(host).apply {
            setViewTreeLifecycleOwner(host)
            setViewTreeSavedStateRegistryOwner(host)
            setContent(content)
        }
        val params = WindowManager.LayoutParams(
            dp(OverlayTheme.DISMISS_HIT_DP),
            dp(OverlayTheme.DISMISS_HIT_DP),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            // NOT_TOUCHABLE: this window is a drop target, not a button. Making it touchable
            // would let it steal the drag it exists to receive.
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = dp(OverlayTheme.DISMISS_BOTTOM_MARGIN_DP)
        }
        view = composeView
        windowManager.addView(composeView, params)
    }

    /** Compose reads the armed flag; invalidation keeps it in sync without a second window. */
    fun refresh() {
        view?.invalidate()
    }

    fun hide() {
        // runCatching: removeView throws if the window has already gone, which happens when
        // the service is being destroyed mid-drag.
        view?.let { runCatching { windowManager.removeView(it) } }
        view = null
    }
}
