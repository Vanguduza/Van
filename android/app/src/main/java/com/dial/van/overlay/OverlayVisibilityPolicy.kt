package com.dial.van.overlay

/**
 * When the overlay should be animating, and when it must not be.
 *
 * P1-PERF-002. `FloatingOverlayService` drove its lifecycle registry to STARTED when the
 * view was added and never below it while the service lived. There was no
 * `ACTION_SCREEN_OFF` receiver and no visibility check, so the infinite transition kept
 * running with the screen off: VAN animated a field nobody could see, on a battery the owner
 * needs, for as long as the service was up. A floating assistant that costs battery while
 * the phone is in a pocket is a floating assistant people uninstall.
 *
 * The policy is separated from the service because the service is untestable here — it needs
 * a WindowManager, a Looper and a real Lifecycle — while the decision is a pure function of
 * four booleans and is exactly the part that was wrong.
 *
 * CREATED rather than STOPPED for the paused case: the Compose composition is retained, so
 * returning to visible does not rebuild the whole overlay, but no frame callback runs. The
 * view stays attached, so the owner's overlay does not visibly disappear and reappear when
 * they wake the phone.
 */
enum class OverlayLifecycleTarget {
    /** Attached and composed, no frames. Nothing animates. */
    PAUSED,

    /** Visible and animating. */
    ANIMATING,

    /** On the way down. */
    DESTROYED,
}

data class OverlayVisibility(
    /** `Intent.ACTION_SCREEN_ON`/`ACTION_SCREEN_OFF`, seeded from `PowerManager.isInteractive`. */
    val screenOn: Boolean = true,
    /** The overlay's own view is attached to the window manager. */
    val attached: Boolean = true,
    /**
     * The owner sent the overlay to its minimized portrait. It is still visible, so it still
     * animates — minimized is a size, not a pause. Kept as an input because it was tempting
     * to treat it as one, and doing so would freeze a dot the owner is looking at.
     */
    val minimized: Boolean = false,
    /** Something is covering the overlay entirely — a full-screen app, the keyguard shade. */
    val occluded: Boolean = false,
    val destroying: Boolean = false,
)

object OverlayVisibilityPolicy {
    fun target(visibility: OverlayVisibility): OverlayLifecycleTarget = when {
        visibility.destroying -> OverlayLifecycleTarget.DESTROYED
        !visibility.attached -> OverlayLifecycleTarget.PAUSED
        !visibility.screenOn -> OverlayLifecycleTarget.PAUSED
        visibility.occluded -> OverlayLifecycleTarget.PAUSED
        else -> OverlayLifecycleTarget.ANIMATING
    }

    /** True when frame callbacks should be requested at all. */
    fun shouldAnimate(visibility: OverlayVisibility): Boolean =
        target(visibility) == OverlayLifecycleTarget.ANIMATING

    /**
     * Why VAN is not animating, for the diagnostics surface.
     *
     * A frozen overlay with no explanation is indistinguishable from a crashed one, and
     * "the overlay is stuck" is the support report this would otherwise generate.
     */
    fun describe(visibility: OverlayVisibility): String = when {
        visibility.destroying -> "overlay is shutting down"
        !visibility.attached -> "overlay view is not attached"
        !visibility.screenOn -> "screen is off"
        visibility.occluded -> "overlay is fully covered"
        visibility.minimized -> "minimized portrait, still animating"
        else -> "visible and animating"
    }
}
