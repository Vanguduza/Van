package com.dial.van.visual

import kotlin.math.PI
import kotlin.math.sin

/**
 * Pure, renderer-independent motion model for VAN's living aura.
 *
 * The important property is continuity: callers may drive [phase] with any repeating 0..1 clock
 * and the sampled field is identical at phase 0 and phase 1. That means no visible jump when the
 * Compose animation restarts. Multiple harmonics are then layered by the painter so the motion
 * does not read like one simple rotating loop.
 *
 * This is intentionally deterministic. A given state/spec, budget and phase always produce the
 * same frame, which keeps JVM visual previews and acceptance tests reproducible.
 */
data class VanWindFieldFrame(
    /** Wrapped 0..1 motion phase. */
    val phase: Float,
    /** Slow radial breathing multiplier around 1.0. */
    val breathing: Float,
    /** Direction of the prevailing field flow in radians. */
    val windAngleRad: Float,
    /** 0..1 longitudinal flow strength. */
    val windStrength: Float,
    /** 0..1 cross-flow/curl energy. */
    val turbulence: Float,
    /** 0..1 amplitude of the visible ribbon waves. */
    val waveAmplitude: Float,
    /** 0..1 electrical pulse intensity. */
    val electricPulse: Float,
    /** 0..1 advection coordinate for sparks and ion fragments. */
    val particleAdvection: Float,
    /** Final field size multiplier after battery/thermal budget. */
    val fieldScale: Float,
)

object VanWindFieldMotion {
    private const val TAU = (2.0 * PI).toFloat()

    fun sample(
        spec: VanAuraSpec,
        phase: Float,
        budget: VanEffectBudget,
    ): VanWindFieldFrame {
        val p = wrap01(phase)
        val moving = if (budget.allowMotion) 1f else 0f
        val activity = spec.arcActivity.coerceIn(0f, 1f)
        val energy = (spec.intensity * 0.62f + activity * 0.38f).coerceIn(0f, 1f)

        // Breathing stays deliberately small. VAN should feel alive, not inflate/deflate.
        val breathing = 1f +
            sin(TAU * p) * (0.018f + 0.035f * energy) * moving +
            sin(TAU * 2f * p + 0.7f) * 0.010f * moving

        // Bias left-to-right/upward like wind, then let the field slowly meander by state energy.
        val baseDegrees = -18f + spec.fieldAsymmetry.coerceIn(0f, 0.4f) * 32f
        val meanderDegrees = (
            sin(TAU * p) * 8f +
                sin(TAU * 2f * p + 1.3f) * 4f
            ) * moving
        val windAngleRad = Math.toRadians((baseDegrees + meanderDegrees).toDouble()).toFloat()

        val windStrength = (0.24f + activity * 0.58f + spec.sparkRate * 0.16f)
            .coerceIn(0.18f, 1f)
        val turbulence = (0.14f + spec.deformation * 1.65f + activity * 0.30f)
            .coerceIn(0.12f, 0.92f)
        val waveAmplitude = (0.22f + spec.deformation * 1.35f + activity * 0.20f)
            .coerceIn(0.18f, 0.82f)

        val pulse = if (budget.allowMotion) {
            (
                0.46f +
                    0.30f * sin(TAU * 3f * p + 0.4f) +
                    0.18f * sin(TAU * 5f * p + 1.1f)
                ).coerceIn(0f, 1f)
        } else {
            0.32f
        }

        return VanWindFieldFrame(
            phase = p,
            breathing = breathing,
            windAngleRad = windAngleRad,
            windStrength = windStrength,
            turbulence = turbulence,
            waveAmplitude = waveAmplitude,
            electricPulse = pulse,
            particleAdvection = if (budget.allowMotion) p else 0.37f,
            fieldScale = (budget.bloomScale * breathing).coerceIn(0.50f, 1.08f),
        )
    }

    internal fun wrap01(value: Float): Float {
        val mod = value % 1f
        return if (mod < 0f) mod + 1f else mod
    }
}
