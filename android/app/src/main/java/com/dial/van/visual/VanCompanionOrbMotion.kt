package com.dial.van.visual

import kotlin.math.PI
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Independent companion movement, never coupled to a VAN activity state.
 *
 * Driven by the already-existing long active-time phase: no new frame loop and
 * no hidden, screen-off or reduced-motion animation. Centre-to-centre transfer
 * crosses BEHIND VAN so the orb does not fly through his face.
 */
data class VanCompanionOrbFrame(
    val centerX: Float,
    val centerY: Float,
    /** Optical rim rotation; the full 3D turn belongs to the future Rive rig. */
    val spinDegrees: Float,
    val behindVan: Boolean,
    val onRight: Boolean,
)

object VanCompanionOrbMotion {
    private const val LR_START = 0.20f
    private const val LR_END = 0.41f
    private const val RL_START = 0.69f
    private const val RL_END = 0.90f

    /**
     * The base position comes from the accepted Candidate B board, viewer-left.
     * Autonomous transfer does not require touch, task, speech or action input.
     */
    fun sample(
        phase: Float,
        homeX: Float,
        homeY: Float,
        radius: Float,
        reducedMotion: Boolean = false,
    ): VanCompanionOrbFrame {
        val home = if (homeX.isFinite()) homeX else 0.25f
        val y0 = if (homeY.isFinite()) homeY else 0.50f
        val r = if (radius.isFinite()) radius.coerceIn(0.015f, 0.25f) else 0.08f
        val margin = r * 1.07f
        val left = max(home, margin).coerceAtMost(0.47f)
        val right = min(1f - margin, 1f - home).coerceAtLeast(0.53f)
        if (reducedMotion) return VanCompanionOrbFrame(left, y0, 0f, false, false)

        val p = if (phase.isFinite()) ((phase % 1f + 1f) % 1f) else 0f
        val goingRight = p >= LR_START && p < LR_END
        val goingLeft = p >= RL_START && p < RL_END
        val t = when {
            goingRight -> smoothstep((p - LR_START) / (LR_END - LR_START))
            goingLeft -> smoothstep((p - RL_START) / (RL_END - RL_START))
            p in LR_END..RL_START -> 1f
            else -> 0f
        }
        val x = if (goingLeft) right + (left - right) * t else left + (right - left) * t
        // The orb arcs behind VAN's head/shoulders and settles without a snap.
        val rise = if (goingRight || goingLeft) sin(PI.toFloat() * t) * 0.22f else 0f
        val leftHover = when {
            p < LR_START -> hover(p / LR_START)
            p >= RL_END -> hover((p - RL_END) / (1f - RL_END))
            else -> 0f
        }
        val rightHover = if (p >= LR_END && p < RL_START) {
            hover((p - LR_END) / (RL_START - LR_END))
        } else 0f
        return VanCompanionOrbFrame(
            centerX = x.coerceIn(margin, 1f - margin),
            centerY = (y0 - rise + (leftHover + rightHover) * 0.012f).coerceIn(margin, 1f - margin),
            spinDegrees = (p * 720f) % 360f,
            behindVan = goingRight || goingLeft,
            onRight = x > (left + right) * 0.5f,
        )
    }

    private fun smoothstep(t: Float): Float {
        val u = t.coerceIn(0f, 1f)
        return u * u * (3f - 2f * u)
    }

    private fun hover(t: Float): Float {
        val u = t.coerceIn(0f, 1f)
        val s = sin(PI.toFloat() * u)
        return s * s * sin((2.0 * PI).toFloat() * u)
    }
}
