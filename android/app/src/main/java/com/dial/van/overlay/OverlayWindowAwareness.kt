package com.dial.van.overlay

/** Own-window identifier only. No screen contents, package access or external UI nodes. */
internal object OverlayOwnWindowIdentity {
    @Volatile var id: Int = -1
        private set
    fun observed(windowId: Int) { id = windowId.takeIf { it >= 0 } ?: -1 }
    fun detached() { id = -1 }
}

/** A full-screen background app is not proof that the assistant above it is hidden. */
object OverlayWindowAwareness {
    fun externalFullscreenCoversOverlay(
        externalFillsDisplay: Boolean,
        systemBarVisible: Boolean,
        externalLayer: Int,
        ownOverlayLayer: Int?,
    ): Boolean = externalFillsDisplay && !systemBarVisible &&
        (ownOverlayLayer == null || ownOverlayLayer <= externalLayer)
}
