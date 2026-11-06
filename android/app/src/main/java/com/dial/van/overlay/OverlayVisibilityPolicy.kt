package com.dial.van.overlay

enum class OverlayLifecycleTarget {
    PAUSED,
    ANIMATING,
    DESTROYED,
}

data class OverlayVisibility(
    val screenOn: Boolean = true,
    val attached: Boolean = true,
    /** Minimized remains visible and may animate. */
    val minimized: Boolean = false,
    val occluded: Boolean = false,
    val keyboardVisible: Boolean = false,
    val fullscreenAppActive: Boolean = false,
    val destroying: Boolean = false,
    /**
     * Explicit geometry result. Legacy callers used keyboardVisible to mean covering VAN,
     * so its default preserves their semantics and positional constructor arguments.
     * Window owners supplying presence must also supply the measured overlap result.
     */
    val keyboardOverlapping: Boolean = keyboardVisible,
)

object OverlayVisibilityPolicy {
    /** Hidden or unknown IME geometry cannot obstruct the overlay. */
    fun keyboardTop(keyboardVisible: Boolean, keyboardTopPx: Int): Int =
        if (keyboardVisible && keyboardTopPx >= 0) keyboardTopPx else Int.MAX_VALUE

    /** Accessibility also reports our own window moves; identical facts require no work. */
    fun obstructionChanged(
        previous: OverlayVisibility,
        previousKeyboardTopPx: Int,
        keyboardVisible: Boolean,
        keyboardTopPx: Int,
        fullscreenAppActive: Boolean,
    ): Boolean = previous.keyboardVisible != keyboardVisible ||
        previous.fullscreenAppActive != fullscreenAppActive ||
        keyboardTop(previous.keyboardVisible, previousKeyboardTopPx) !=
        keyboardTop(keyboardVisible, keyboardTopPx)

    /** The existing producer supplies a full-width keyboard top, not accessibility text. */
    fun keyboardOverlaps(
        keyboardVisible: Boolean,
        keyboardTopPx: Int,
        placement: OverlayPlacement,
        size: OverlaySize,
        screen: OverlayScreen,
    ): Boolean {
        val knownTop = keyboardTop(keyboardVisible, keyboardTopPx)
        if (knownTop == Int.MAX_VALUE) return false
        val top = maxOf(knownTop, screen.safeTop)
        if (top >= screen.safeBottom || size.widthPx <= 0 || size.heightPx <= 0) return false
        return placement.x.toLong() < screen.safeRight &&
            placement.x.toLong() + size.widthPx > screen.safeLeft &&
            placement.y.toLong() < screen.safeBottom &&
            placement.y.toLong() + size.heightPx > top
    }

    fun target(visibility: OverlayVisibility): OverlayLifecycleTarget = when {
        visibility.destroying -> OverlayLifecycleTarget.DESTROYED
        !visibility.attached -> OverlayLifecycleTarget.PAUSED
        !visibility.screenOn -> OverlayLifecycleTarget.PAUSED
        visibility.occluded -> OverlayLifecycleTarget.PAUSED
        visibility.fullscreenAppActive -> OverlayLifecycleTarget.PAUSED
        visibility.keyboardVisible && visibility.keyboardOverlapping -> OverlayLifecycleTarget.PAUSED
        else -> OverlayLifecycleTarget.ANIMATING
    }

    fun shouldAnimate(visibility: OverlayVisibility): Boolean =
        target(visibility) == OverlayLifecycleTarget.ANIMATING

    fun describe(visibility: OverlayVisibility): String = when {
        visibility.destroying -> "overlay is shutting down"
        !visibility.attached -> "overlay view is not attached"
        !visibility.screenOn -> "screen is off"
        visibility.occluded -> "overlay is fully covered"
        visibility.fullscreenAppActive -> "a full-screen app is in front"
        visibility.keyboardVisible && visibility.keyboardOverlapping -> "the keyboard is covering VAN"
        visibility.minimized -> "minimized portrait, still animating"
        else -> "visible and animating"
    }
}
