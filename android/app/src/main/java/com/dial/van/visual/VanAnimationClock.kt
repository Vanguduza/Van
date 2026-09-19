package com.dial.van.visual

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * One monotonic clock, never restarted, and blended transitions on top of it.
 *
 * P1-AURA-002. Rev 3.0 §22 asks for a single monotonic clock that is never restarted, and
 * §25 asks for transitions blended over 120–420 ms. The shipping runtime had neither. The
 * only animation driver was `rememberInfiniteTransition` with a `durationMillis` chosen per
 * state, which has a specific and visible consequence: changing state changes the tween's
 * duration, which **restarts the ramp from zero**. Every aura change was therefore a
 * one-frame snap — the field jumped back to phase 0 at the exact moment VAN was supposed to
 * be showing the owner a change.
 *
 * The fix is to integrate phase rather than to derive it:
 *
 *     phase += dt / period
 *
 * A period change then alters how fast the phase advances and leaves where it *is* alone,
 * which is the continuity property the snap was violating. [VanAnimationClock] holds that
 * accumulator; it is deliberately not a Compose type, so the behaviour that matters is
 * testable on the JVM rather than only observable on a device.
 *
 * Everything here is pure Kotlin: no Android imports, no Compose. `withFrameNanos` supplies
 * the timestamps in `VanCanvasFallback`; this file decides what they mean.
 */
class VanAnimationClock(
    /** Where the phase starts. Only useful in tests; production always starts at zero. */
    initialPhase: Float = 0f,
) {
    /** Monotonically accumulated, wrapped to 0..1. */
    var phase: Float = VanWindFieldMotion.wrap01(initialPhase)
        private set

    /** Nanosecond timestamp of the last frame, or `null` before the first one. */
    var lastFrameNanos: Long? = null
        private set

    /** Total nanoseconds this clock has been running. Never reset. */
    var elapsedNanos: Long = 0L
        private set

    /** Frames seen. Used by the frame-budget sampler, and to know the clock is live. */
    var frames: Long = 0L
        private set

    /**
     * Advance to [frameNanos] with the given period, and return the new phase.
     *
     * Two guards, both for things that actually happen on a device:
     *
     * * The first frame has no predecessor, so it advances nothing. Treating `now - 0` as
     *   the delta would jump the phase by however long the process had been alive.
     * * A delta longer than [MAX_FRAME_DELTA_NANOS] means the composition was paused — the
     *   screen went off, the app was backgrounded, the device slept. Integrating it would
     *   spin the phase through hundreds of cycles in one frame, which looks exactly like
     *   the snap this class exists to remove. It is clamped, not dropped: time did pass.
     */
    fun advance(frameNanos: Long, periodMillis: Int): Float {
        val previous = lastFrameNanos
        lastFrameNanos = frameNanos
        frames += 1L
        if (previous == null) return phase
        val delta = frameNanos - previous
        if (delta <= 0L) return phase  // a non-monotonic source; ignore rather than rewind
        val clamped = min(delta, MAX_FRAME_DELTA_NANOS)
        elapsedNanos += clamped
        val period = max(periodMillis, MIN_PERIOD_MS).toFloat() * 1_000_000f
        phase = VanWindFieldMotion.wrap01(phase + clamped.toFloat() / period)
        return phase
    }

    companion object {
        const val MIN_PERIOD_MS = 250

        /** 250 ms. Longer than four frames at 60fps, shorter than any real animation cycle. */
        const val MAX_FRAME_DELTA_NANOS = 250L * 1_000_000L
    }
}

/** How long one full motion cycle takes, per state. Periods, not tween durations. */
object VanMotionPeriods {
    fun periodMillisFor(state: VanDurableState): Int = when (state) {
        VanDurableState.LISTENING,
        VanDurableState.WORKING,
        VanDurableState.SEARCHING,
        VanDurableState.CONNECTING,
        -> 2000

        VanDurableState.URGENT,
        VanDurableState.WARNING,
        VanDurableState.ERROR,
        VanDurableState.WAITING_FOR_OWNER,
        -> 2800

        VanDurableState.SLEEPING,
        VanDurableState.OFFLINE,
        -> 6000

        else -> 4200
    }
}

/**
 * Rev 3.0 §25 — a state change is blended, not switched.
 *
 * The duration is chosen from how far apart the two states are rather than being one
 * constant, because a slow fade on an error is as wrong as a snap on an idle drift: an
 * urgent change should arrive quickly and a settling change should not startle. Both ends
 * are clamped into the §25 band, so nothing reachable from here can produce an unblended
 * change or a sluggish one.
 */
object VanTransitionBlend {
    const val MIN_BLEND_MS = 120
    const val MAX_BLEND_MS = 420

    fun durationMillisFor(from: VanDurableState, to: VanDurableState): Int {
        if (from == to) return MIN_BLEND_MS
        // Arriving at something the owner must react to is fast; settling down is slow.
        val urgent = to in URGENT_STATES
        val settling = to == VanDurableState.IDLE || to == VanDurableState.SLEEPING
        return when {
            urgent -> MIN_BLEND_MS
            settling -> MAX_BLEND_MS
            else -> 260
        }
    }

    /** Smoothstep. Zero velocity at both ends, so neither the start nor the end reads as a step. */
    fun progress(elapsedMs: Long, durationMs: Int): Float {
        if (durationMs <= 0) return 1f
        val t = (elapsedMs.toFloat() / durationMs.toFloat()).coerceIn(0f, 1f)
        return t * t * (3f - 2f * t)
    }

    private val URGENT_STATES = setOf(
        VanDurableState.ERROR,
        VanDurableState.URGENT,
        VanDurableState.WARNING,
        VanDurableState.WAITING_FOR_OWNER,
        VanDurableState.OFFLINE,
    )
}

/** Linear interpolation of the continuous fields of an aura spec. */
fun VanAuraSpec.blendTo(target: VanAuraSpec, t: Float): VanAuraSpec {
    val k = t.coerceIn(0f, 1f)
    if (k <= 0f) return this
    if (k >= 1f) return target
    fun mix(a: Float, b: Float) = a + (b - a) * k
    return target.copy(
        intensity = mix(intensity, target.intensity),
        arcActivity = mix(arcActivity, target.arcActivity),
        sparkRate = mix(sparkRate, target.sparkRate),
        groundGlow = mix(groundGlow, target.groundGlow),
        orbLink = mix(orbLink, target.orbLink),
        fieldAsymmetry = mix(fieldAsymmetry, target.fieldAsymmetry),
        deformation = mix(deformation, target.deformation),
        envelopeRadiusScale = mix(envelopeRadiusScale, target.envelopeRadiusScale),
        // Zone C alpha carries the semantic envelope in. Fading it is what makes a state
        // change read as VAN turning toward something rather than as a cut.
        envelopeAlpha = mix(envelopeAlpha, target.envelopeAlpha),
        // Discrete fields take the target's value at the halfway point rather than being
        // interpolated: there is no meaningful colour between "no semantic" and "error red",
        // and filament count is an integer the geometry engine keys its topology on.
        semanticColor = if (k >= 0.5f) target.semanticColor else semanticColor,
        filamentCount = if (k >= 0.5f) target.filamentCount else filamentCount,
        envelopeSegments = if (k >= 0.5f) target.envelopeSegments else envelopeSegments,
        alertAccent = if (k >= 0.5f) target.alertAccent else alertAccent,
    )
}

/**
 * The blend in progress, as a value a renderer can hold across frames.
 *
 * Kept as immutable state rather than a mutable animator so the same transition can be
 * replayed deterministically in a test and in the JVM evidence renderer.
 */
data class VanAuraTransition(
    val from: VanAuraSpec,
    val to: VanAuraSpec,
    val startedAtNanos: Long,
    val durationMillis: Int,
) {
    fun specAt(nowNanos: Long): VanAuraSpec {
        val elapsedMs = (nowNanos - startedAtNanos) / 1_000_000L
        return from.blendTo(to, VanTransitionBlend.progress(elapsedMs, durationMillis))
    }

    fun isComplete(nowNanos: Long): Boolean =
        (nowNanos - startedAtNanos) / 1_000_000L >= durationMillis

    companion object {
        /**
         * Start a blend from wherever the current one had got to, not from the old target.
         *
         * Retargeting mid-blend is the common case — LISTENING to THINKING to WORKING inside
         * half a second — and restarting from `to` would produce the snap on the second
         * change that this whole file exists to remove.
         */
        fun retarget(
            existing: VanAuraTransition?,
            current: VanAuraSpec,
            to: VanAuraSpec,
            fromState: VanDurableState,
            toState: VanDurableState,
            nowNanos: Long,
        ): VanAuraTransition = VanAuraTransition(
            // Where the field actually is right now: mid-blend that is the interpolated
            // spec, otherwise whatever is on screen. Never `to`, which would make the
            // first frame of the blend the destination and reinstate the snap.
            from = existing?.specAt(nowNanos) ?: current,
            to = to,
            startedAtNanos = nowNanos,
            durationMillis = VanTransitionBlend.durationMillisFor(fromState, toState),
        )
    }
}

/** True when two specs differ enough to be worth blending rather than assigning. */
fun VanAuraSpec.differsFrom(other: VanAuraSpec, epsilon: Float = 0.001f): Boolean =
    abs(intensity - other.intensity) > epsilon ||
        abs(arcActivity - other.arcActivity) > epsilon ||
        abs(sparkRate - other.sparkRate) > epsilon ||
        abs(groundGlow - other.groundGlow) > epsilon ||
        abs(orbLink - other.orbLink) > epsilon ||
        abs(envelopeAlpha - other.envelopeAlpha) > epsilon ||
        abs(envelopeRadiusScale - other.envelopeRadiusScale) > epsilon ||
        semanticColor != other.semanticColor ||
        filamentCount != other.filamentCount ||
        envelopeSegments != other.envelopeSegments
