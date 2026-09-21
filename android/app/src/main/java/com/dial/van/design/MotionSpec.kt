package com.dial.van.design

/**
 * VAN's motion tokens (DNA §2 "Motion"), as pure numbers.
 *
 * Kept out of Compose entirely so the reduced-motion collapse — every duration going to
 * zero while state is still communicated by colour and shape — is a fact the JVM can check,
 * the same reasoning `VanEffectBudget`/`VanAnimationClock` already apply to the aura. The
 * Compose-facing wrapper (`com.dial.van.design.VanMotion` in `VanTokens.kt`) turns
 * [VanCubicEasing] into `androidx.compose.animation.core.Easing` and these durations into
 * `tween<T>()`; nothing here imports Compose.
 */
data class VanMotionDurations(
    val instantMs: Int,
    val quickMs: Int,
    val standardMs: Int,
    val expressiveMs: Int,
)

/** A cubic-bezier easing curve, expressed as the two interior control points. */
data class VanCubicEasing(val x1: Float, val y1: Float, val x2: Float, val y2: Float)

object VanMotionSpec {
    /** DNA §2: `instant` 80ms · `quick` 160ms · `standard` 240ms · `expressive` 360ms. */
    val DURATIONS = VanMotionDurations(instantMs = 80, quickMs = 160, standardMs = 240, expressiveMs = 360)

    /** Reduced motion: state changes still communicated by colour/shape, never by tween. */
    val REDUCED_MOTION_DURATIONS = VanMotionDurations(instantMs = 0, quickMs = 0, standardMs = 0, expressiveMs = 0)

    /** DNA §2 easings, by name. */
    val EASING_STANDARD = VanCubicEasing(0.2f, 0f, 0f, 1f)
    val EASING_ENTER = VanCubicEasing(0f, 0f, 0.2f, 1f)
    val EASING_EXIT = VanCubicEasing(0.4f, 0f, 1f, 1f)

    /** DNA §2: "Press scale 0.97 at `instant`." */
    const val PRESS_SCALE = 0.97f

    /** DNA §2: data updates (value + sparkline) animate at `quick`. */
    fun dataUpdateDurationMs(reducedMotion: Boolean): Int = resolve(reducedMotion).quickMs

    /** DNA §2: shared-element card→detail transitions animate at `standard`. */
    fun sharedElementDurationMs(reducedMotion: Boolean): Int = resolve(reducedMotion).standardMs

    /**
     * The durations a screen should actually animate with.
     *
     * Reduced motion is a designed zero, not a missing token: callers still run every
     * transition, they simply run it in 0ms, so the state-change side effects (colour swap,
     * shape change, a `LiveBadge` flipping) still fire in the same code path instead of a
     * parallel "skip the animation" branch that can drift from the animated one.
     */
    fun resolve(reducedMotion: Boolean): VanMotionDurations =
        if (reducedMotion) REDUCED_MOTION_DURATIONS else DURATIONS
}
