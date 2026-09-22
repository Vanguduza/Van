package com.dial.van.visual

/**
 * State transition -> motion, as data.
 *
 * DNA §2 names a `com.dial.van.design.VanMotion` token set (`instant` 80ms, `quick` 160ms,
 * `standard` 240ms, `expressive` 360ms, named easing curves) and a reduced-motion rule (all
 * durations 0, state still communicated by colour/shape). No `com.dial.van.design` package
 * exists in this tree yet, so the tokens live here, pure and dependency-free, until that
 * package does — the manager unifies them at that point rather than this file inventing a
 * second, disagreeing set of numbers.
 *
 * [VanEffectBudget]/[VanTransitionBlend] already own the aura's own blend timing (P1-AURA-002:
 * a monotonic clock, 120-420ms retargetable blends). This file is the *other* half DNA §3/§6
 * ask for: overlay chrome transitions (compact<->expanded, dock/snap, panel reveal) and how
 * long a finite action's gesture holds the embodiment before [VanLiveVisualState.clearAction]
 * fires automatically. Both are pure arithmetic over an enum, so both are exercised in
 * `android/verification` rather than only reasoned about on a device.
 */
enum class MotionEasing { STANDARD, ENTER, EXIT, LINEAR }

data class MotionSpec(
    val durationMs: Int,
    val easing: MotionEasing = MotionEasing.STANDARD,
) {
    /** DNA §2's reduced-motion rule: duration collapses to zero, the easing is irrelevant. */
    fun reduced(reducedMotion: Boolean): MotionSpec =
        if (reducedMotion) copy(durationMs = 0) else this
}

object VanMotionTokens {
    const val INSTANT_MS = 80
    const val QUICK_MS = 160
    const val STANDARD_MS = 240
    const val EXPRESSIVE_MS = 360

    /** DNA §2 — press scale at `instant`. */
    const val PRESS_SCALE = 0.97f

    /** cubic-bezier(0.2, 0, 0, 1). */
    val STANDARD_CURVE = floatArrayOf(0.2f, 0f, 0f, 1f)

    /** cubic-bezier(0, 0, 0.2, 1). */
    val ENTER_CURVE = floatArrayOf(0f, 0f, 0.2f, 1f)

    /** cubic-bezier(0.4, 0, 1, 1). */
    val EXIT_CURVE = floatArrayOf(0.4f, 0f, 1f, 1f)
}

object VanMotionMap {

    /**
     * How long a finite action's gesture plays before it auto-clears (DNA §6: "Every action
     * must auto-clear after its duration"). Chosen from the gesture's own shape rather than
     * one constant: a wave reads as a wave only if it has time to complete, a nod is quick
     * because it repeats often, and a highlight point holds long enough for the owner to
     * follow it to the card.
     */
    fun actionDurationMs(action: VanFiniteAction): Long = when (action) {
        VanFiniteAction.HELLO_WAVE -> 1_400L
        VanFiniteAction.ACK_NOD -> 650L
        VanFiniteAction.POINT_LEFT,
        VanFiniteAction.POINT_RIGHT,
        VanFiniteAction.POINT_UP,
        VanFiniteAction.POINT_DOWN,
        VanFiniteAction.POINT_TARGET,
        -> 1_200L
        VanFiniteAction.CELEBRATE -> 1_800L
        VanFiniteAction.CAUTION -> 1_000L
        VanFiniteAction.CONFIRM -> 900L
        VanFiniteAction.SHRUG -> 1_100L
        VanFiniteAction.PRESENT_CARD -> 1_500L
        VanFiniteAction.OPEN_PANEL, VanFiniteAction.CLOSE_PANEL -> VanMotionTokens.STANDARD_MS.toLong()
    }

    /** Compact <-> expanded overlay resize (`animateContentSize`/`AnimatedContent`). */
    fun presentationChange(reducedMotion: Boolean = false): MotionSpec =
        MotionSpec(VanMotionTokens.STANDARD_MS, MotionEasing.STANDARD).reduced(reducedMotion)

    /** A card/quick-controls panel revealing inside the expanded overlay. */
    fun panelReveal(reducedMotion: Boolean = false): MotionSpec =
        MotionSpec(VanMotionTokens.EXPRESSIVE_MS, MotionEasing.ENTER).reduced(reducedMotion)

    /** The settle at the end of a drag: fling toward the edge and dock, haptic tick on arrival. */
    fun dockSnap(reducedMotion: Boolean = false): MotionSpec =
        MotionSpec(VanMotionTokens.QUICK_MS, MotionEasing.EXIT).reduced(reducedMotion)

    /** Press feedback — DNA §2's `press scale 0.97 at instant`. */
    fun pressFeedback(reducedMotion: Boolean = false): MotionSpec =
        MotionSpec(VanMotionTokens.INSTANT_MS, MotionEasing.STANDARD).reduced(reducedMotion)

    /**
     * A velocity-biased fling duration for [OverlayDragController]'s release.
     *
     * A slow release settles at the standard dock speed; a fast flick — released while still
     * carrying real speed toward an edge — docks quicker, because a slow tween after a fast
     * flick reads as the overlay fighting the gesture rather than continuing it. `speedPxPerMs`
     * is the release velocity magnitude; the floor and ceiling keep the result inside DNA §2's
     * quick/instant band regardless of how large a measured velocity spike is.
     */
    fun flingDockDurationMs(speedPxPerMs: Float, reducedMotion: Boolean = false): Int {
        if (reducedMotion) return 0
        val fast = speedPxPerMs.coerceAtLeast(0f) >= FLING_VELOCITY_THRESHOLD_PX_PER_MS
        return if (fast) VanMotionTokens.INSTANT_MS else VanMotionTokens.QUICK_MS
    }

    /** Roughly a screen-inch (~160px) crossed in 120ms — fast enough to call a flick. */
    const val FLING_VELOCITY_THRESHOLD_PX_PER_MS = 1.3f
}
