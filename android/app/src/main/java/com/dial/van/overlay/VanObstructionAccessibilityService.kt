package com.dial.van.overlay

import android.accessibilityservice.AccessibilityService
import android.content.ComponentName
import android.content.Intent
import android.graphics.Rect
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityWindowInfo

/**
 * Produces the two obstruction facts [OverlayVisibilityPolicy] already knows how to consume.
 *
 * Fable's closure left keyboard/full-screen handling as a policy with no producer. This
 * service observes only window metadata (type, bounds and foreground package) and never
 * traverses an accessibility node tree or reads text. Android still exposes this through the
 * Accessibility settings because cross-app interactive-window metadata is privileged.
 *
 * The owner explicitly enables the service during onboarding. If it is disabled VAN still
 * runs, but Settings reports that display awareness is unavailable.
 */
class VanObstructionAccessibilityService : AccessibilityService() {
    private var foregroundPackage: String? = null

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event?.packageName?.toString()?.takeIf { it.isNotBlank() }?.let {
            foregroundPackage = it
        }
        publishSnapshot()
    }

    override fun onInterrupt() {
        publish(keyboardVisible = false, keyboardTopPx = Int.MAX_VALUE, fullscreenAppActive = false)
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        publishSnapshot()
    }

    private fun publishSnapshot() {
        val currentWindows = runCatching { windows.orEmpty() }.getOrDefault(emptyList())
        val keyboard = currentWindows.firstOrNull { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
        val keyboardBounds = Rect()
        keyboard?.getBoundsInScreen(keyboardBounds)

        val fullscreen = detectImmersiveExternalWindow(currentWindows)
        publish(
            keyboardVisible = keyboard != null,
            keyboardTopPx = if (keyboard != null) keyboardBounds.top else Int.MAX_VALUE,
            fullscreenAppActive = fullscreen,
        )
    }

    /**
     * Infer immersive full-screen from window geometry plus the absence of visible system-bar
     * strips. A normal edge-to-edge application can fill the display while the status/navigation
     * bars remain visible; that must not freeze VAN. We only report full-screen when an external
     * foreground application covers the display and no system strip is present.
     */
    private fun detectImmersiveExternalWindow(currentWindows: List<AccessibilityWindowInfo>): Boolean {
        val pkg = foregroundPackage ?: return false
        if (pkg == packageName || pkg == "com.android.systemui") return false

        val metrics = resources.displayMetrics
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        if (width <= 0 || height <= 0) return false

        val activeApp = currentWindows.firstOrNull {
            it.type == AccessibilityWindowInfo.TYPE_APPLICATION && it.isActive
        } ?: return false
        val appBounds = Rect().also(activeApp::getBoundsInScreen)
        val tolerance = (4 * metrics.density).toInt().coerceAtLeast(2)
        val fillsDisplay =
            appBounds.left <= tolerance &&
                appBounds.top <= tolerance &&
                appBounds.right >= width - tolerance &&
                appBounds.bottom >= height - tolerance
        if (!fillsDisplay) return false

        val hasSystemBarStrip = currentWindows.any { window ->
            if (window.type != AccessibilityWindowInfo.TYPE_SYSTEM) return@any false
            val b = Rect().also(window::getBoundsInScreen)
            val horizontalStrip = b.width() >= (width * 0.75f) && b.height() in 1..(height / 5)
            horizontalStrip && (b.top <= tolerance || b.bottom >= height - tolerance)
        }
        return !hasSystemBarStrip
    }

    private fun publish(
        keyboardVisible: Boolean,
        keyboardTopPx: Int,
        fullscreenAppActive: Boolean,
    ) {
        sendBroadcast(
            Intent(ACTION_OBSTRUCTION_STATE)
                .setPackage(packageName)
                .putExtra(EXTRA_KEYBOARD_VISIBLE, keyboardVisible)
                .putExtra(EXTRA_KEYBOARD_TOP_PX, keyboardTopPx)
                .putExtra(EXTRA_FULLSCREEN_APP_ACTIVE, fullscreenAppActive),
        )
    }

    companion object {
        const val ACTION_OBSTRUCTION_STATE = "com.dial.van.overlay.OBSTRUCTION_STATE"
        const val EXTRA_KEYBOARD_VISIBLE = "keyboard_visible"
        const val EXTRA_KEYBOARD_TOP_PX = "keyboard_top_px"
        const val EXTRA_FULLSCREEN_APP_ACTIVE = "fullscreen_app_active"

        fun isEnabled(context: android.content.Context): Boolean {
            val enabled = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            ).orEmpty()
            val mine = ComponentName(context, VanObstructionAccessibilityService::class.java)
            return enabled.split(':').any {
                ComponentName.unflattenFromString(it) == mine
            }
        }
    }
}
