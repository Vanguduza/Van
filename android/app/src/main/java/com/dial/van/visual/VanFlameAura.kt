package com.dial.van.visual

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * CF-D-06 — VAN's aura is a flame envelope that wraps his silhouette and rises off it, in the
 * manner of Goku's and Naruto's auras (owner decision, 2026-09-24).
 *
 * It replaces the detached wind field entirely. There are three stacked tongue layers: an
 * outer one in the state colour, a lighter mid one, and a near-white core rim that hugs the
 * body. Embers rise off the tips. No lines, lightning or specks: on a phone they were noise.
 *
 * Everything is still Android-native and drawn *behind* the character. The body is opaque, so
 * the flames never cover the face; `van.riv` stays transparent and carries no aura geometry.
 *
 * Pure Kotlin like [VanAuraPlanner], so the app, the JVM preview and the verification harness
 * all execute the same numbers.
 */
object VanFlameAura {

    const val SAMPLES = 144
    /** Air between the body edge and each layer's base, as a fraction of the body edge. */
    const val OUTER_PAD = 0.030f
    const val MID_PAD = 0.018f
    const val CORE_PAD = 0.008f
    /** Tongue height at full intensity, as a fraction of the body edge. */
    const val HEIGHT_BASE = 0.02f
    const val HEIGHT_PER_INTENSITY = 0.42f
    const val OUTER_ALPHA_BASE = 0.12f
    const val OUTER_ALPHA_PER_INTENSITY = 0.50f
    const val MID_WHITE_MIX = 0.30f
    const val CORE_WHITE_MIX = 0.85f
    /** Gradient stops shared by both executors: solid to 55% of the radius, fading out at the tips. */
    const val FLAME_SOLID_STOP_FRACTION = 0.55f
    const val FLAME_TIP_ALPHA_FRACTION = 0.0f
    const val MIN_TONGUES = 12
    const val MAX_TONGUES = 22

    private const val TAU = 6.2831855f

    fun plan(
        spec: VanAuraSpec,
        semanticSpec: VanAuraSpec,
        centerX: Float,
        centerY: Float,
        bodyEdge: Float,
        budget: VanEffectBudget,
        phase: Float,
        identityColor: Int,
        framing: VanFraming = VanFraming.FULL_BODY,
    ): List<VanAuraOp> {
        val intensity = max(spec.intensity, semanticSpec.intensity * 0.8f).coerceIn(0f, 1f)
        if (bodyEdge <= 4f || intensity <= 0.01f) return emptyList()
        val color = semanticSpec.semanticColor ?: identityColor
        // Superlinear, so a sleeping VAN smoulders and a working one flares.
        val height = bodyEdge * (HEIGHT_BASE + HEIGHT_PER_INTENSITY * intensity.pow(1.2f))
        val reach = bodyEdge * 0.5f * spec.envelopeRadiusScale.coerceIn(
            VanAuraSpec.MIN_ENVELOPE_SCALE,
            VanAuraSpec.MAX_ENVELOPE_SCALE,
        )
        val tongues = (MIN_TONGUES + (MAX_TONGUES - MIN_TONGUES) * spec.arcActivity.coerceIn(0f, 1f))
            .toInt()
        val flicker = if (budget.allowMotion) 0.10f + 0.30f * spec.deformation.coerceIn(0f, 1f) else 0f
        val lean = (spec.fieldAsymmetry - 0.2f) * 0.35f
        val outerAlpha = (OUTER_ALPHA_BASE + OUTER_ALPHA_PER_INTENSITY * intensity).coerceAtMost(0.78f)
        val frame = Frame(centerX, centerY, bodyEdge, reach, tongues, flicker, lean, phase, framing)

        val ops = mutableListOf<VanAuraOp>()
        val full = budget != VanEffectBudget.LOW && budget != VanEffectBudget.STATIC
        if (full) {
            ops += frame.layer(
                pad = OUTER_PAD * 1.6f, height = height * 1.18f, sharpness = 3f, seed = 0.61f,
                color = color, alpha = outerAlpha * 0.28f,
            )
        }
        ops += frame.layer(
            pad = OUTER_PAD, height = height, sharpness = 5f, seed = 0f,
            color = color, alpha = outerAlpha,
        )
        if (full) {
            ops += frame.layer(
                pad = MID_PAD, height = height * 0.55f, sharpness = 6f, seed = 0.37f,
                color = mix(color, WHITE, MID_WHITE_MIX), alpha = min(outerAlpha * 1.05f, 0.82f),
            )
        }
        ops += frame.layer(
            pad = CORE_PAD, height = height * 0.20f, sharpness = 7f, seed = 0.83f,
            color = mix(color, WHITE, CORE_WHITE_MIX), alpha = min(outerAlpha * 1.15f, 0.88f),
        )
        ops += frame.embers(spec, budget, height, mix(color, WHITE, 0.35f), outerAlpha)
        return ops
    }

    private class Frame(
        val cx: Float,
        val cy: Float,
        val edge: Float,
        val reach: Float,
        val tongues: Int,
        val flicker: Float,
        val lean: Float,
        val phase: Float,
        val framing: VanFraming,
    ) {
        private val extents = VanBodyLayout.extents(SAMPLES)
        /** The silhouette is measured unzoomed; the zoom scales it into the framed square. */
        private val zoom = framing.zoom
        private val originX = cx + (framing.x(VanBodyLayout.CENTER_U) - 0.5f) * edge
        private val originY = cy + (framing.y(VanBodyLayout.CENTER_V) - 0.5f) * edge

        fun insideBody(px: Float, py: Float): Boolean = VanBodyLayout.contains(
            framing.unframeX((px - cx) / edge + 0.5f),
            framing.unframeY((py - cy) / edge + 0.5f),
        )

        /** A closed ring of flame tongues around the silhouette, as a [VanAuraOp.Flame]. */
        fun layer(pad: Float, height: Float, sharpness: Float, seed: Float, color: Int, alpha: Float): VanAuraOp.Flame {
            val xs = FloatArray(SAMPLES)
            val ys = FloatArray(SAMPLES)
            var farthest = 0f
            for (i in 0 until SAMPLES) {
                val angle = VanBodyLayout.angleAt(i, SAMPLES)
                val dx = cos(angle)
                val dy = sin(angle)
                val base = (extents[i] * edge * zoom) + pad * edge
                // Tongues grow with how much a point faces up, and die out under the feet.
                val up = (-dy).coerceAtLeast(0f)
                val side = 1f - abs(dy)
                val grow = (0.22f + 0.78f * up + 0.35f * side) * if (dy > 0.55f) 0.25f else 1f
                val tongue = tongueField(i, sharpness, seed)
                val lick = height * grow * tongue
                // Tips bend towards vertical, as flames do, with a slight lean.
                var tx = dx * 0.75f + lean
                var ty = dy * 0.75f - 0.85f * (1f - max(0f, dy))
                val norm = sqrt(tx * tx + ty * ty).coerceAtLeast(0.001f)
                tx /= norm; ty /= norm
                var px = originX + dx * base + tx * lick
                var py = originY + dy * base + ty * lick
                // A bent tip can curl back over an arm or the head; then it rises straight out.
                // Straight out along the ray always clears the body, because `base` is already
                // past the silhouette's outermost edge on that ray.
                if (insideBody(px, py)) {
                    px = originX + dx * (base + lick)
                    py = originY + dy * (base + lick)
                }
                val ddx = px - cx
                val ddy = py - cy
                val dist = sqrt(ddx * ddx + ddy * ddy)
                if (dist > reach) {
                    px = cx + ddx / dist * reach
                    py = cy + ddy / dist * reach
                }
                xs[i] = px; ys[i] = py
                farthest = max(farthest, sqrt((px - originX) * (px - originX) + (py - originY) * (py - originY)))
            }
            return VanAuraOp.Flame(
                path = smoothClosed(xs, ys),
                gradientX = originX,
                gradientY = originY,
                gradientRadius = farthest * 1.02f,
                color = color,
                alpha = alpha.coerceIn(0f, 1f),
            )
        }

        /**
         * Sum of narrow peaks, one per tongue. Heights and widths come from a hash so
         * every tongue differs. Each flickers on its own clock, and a slow ripple runs
         * upwards along both flanks so the fire appears to climb.
         */
        private fun tongueField(i: Int, sharpness: Float, seed: Float): Float {
            val t = i.toFloat() / SAMPLES
            var total = 0f
            for (k in 0 until tongues) {
                val h = hash(k * 7.13f + seed * 31f)
                val centre = (k + 0.5f * hash(k * 3.7f + seed)) / tongues
                var d = abs(t - centre)
                if (d > 0.5f) d = 1f - d
                val width = (0.38f + 0.42f * hash(k * 1.91f + seed * 5f)) / tongues
                if (d > width) continue
                val shape = (0.5f + 0.5f * cos(Math.PI.toFloat() * d / width)).pow(sharpness * 0.5f)
                // Whole-number speeds: the phase loops 0..1 and the fire must not jump at the wrap.
                val clock = sin(TAU * (phase * (1 + (h * 3f).toInt()) + h))
                val amp = (0.45f + 0.55f * h) * (1f + flicker * clock)
                total = max(total, shape * amp)
            }
            val climb = 0.10f * sin(TAU * (t * 6f - phase * 2f + seed)) * (flicker / 0.4f).coerceAtMost(1f)
            return (total + climb).coerceAtLeast(0f)
        }

        /** Sparks lifting off the upper flanks and fading as they rise. */
        fun embers(spec: VanAuraSpec, budget: VanEffectBudget, height: Float, color: Int, alpha: Float): List<VanAuraOp> {
            if (budget == VanEffectBudget.STATIC) return emptyList()
            val count = (3 + 15 * spec.sparkRate.coerceIn(0f, 1f) + 4 * spec.intensity).toInt()
            val out = ArrayList<VanAuraOp>(count)
            for (k in 0 until count) {
                val h = hash(k * 5.31f + 0.7f)
                val index = ((0.62f + 0.76f * h) * SAMPLES / 2f).toInt() % SAMPLES
                val angle = VanBodyLayout.angleAt(index, SAMPLES)
                val base = extents[index] * edge * zoom + OUTER_PAD * edge
                val life = frac(phase * (1 + (h * 2f).toInt()) + hash(k * 2.17f))
                val rise = height * (0.3f + 1.6f * life)
                val px = originX + cos(angle) * base + (hash(k * 9.1f) - 0.5f) * edge * 0.06f
                val py = originY + sin(angle) * base - rise
                if ((px - cx) * (px - cx) + (py - cy) * (py - cy) > reach * reach) continue
                out += VanAuraOp.Dot(
                    cx = px, cy = py,
                    radius = max(edge * (0.004f + 0.004f * h), 0.8f),
                    color = color,
                    alpha = (alpha * 1.1f * (1f - life)).coerceIn(0f, 0.9f),
                    bloomRadiusScale = 3.2f,
                    bloomAlphaScale = 0.22f,
                )
            }
            return out
        }
    }

    /** Midpoint quadratic smoothing: the curve passes between samples, so tips stay pointed. */
    private fun smoothClosed(xs: FloatArray, ys: FloatArray): List<VanPathSeg> {
        val n = xs.size
        val out = ArrayList<VanPathSeg>(n + 2)
        out += VanPathSeg.MoveTo((xs[n - 1] + xs[0]) / 2f, (ys[n - 1] + ys[0]) / 2f)
        for (i in 0 until n) {
            val j = (i + 1) % n
            out += VanPathSeg.QuadTo(xs[i], ys[i], (xs[i] + xs[j]) / 2f, (ys[i] + ys[j]) / 2f)
        }
        out += VanPathSeg.Close
        return out
    }

    private const val WHITE = 0xFFFFFF

    fun mix(a: Int, b: Int, t: Float): Int {
        fun ch(c: Int, s: Int) = (c shr s) and 0xFF
        fun m(s: Int) = (ch(a, s) + (ch(b, s) - ch(a, s)) * t).toInt().coerceIn(0, 255)
        return (0xFF shl 24) or (m(16) shl 16) or (m(8) shl 8) or m(0)
    }

    private fun hash(x: Float): Float = frac(sin(x * 12.9898f + 78.233f) * 43758.547f)

    private fun frac(x: Float): Float = x - kotlin.math.floor(x)
}
