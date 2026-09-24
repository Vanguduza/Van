package com.dial.van.visual

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * VAN's aura: a flame envelope that wraps his silhouette and rises off it, in the manner of
 * Goku's and Naruto's auras (CF-D-06), rebuilt as Aura Rev 2 (CF-D-08).
 *
 * * **Envelope.** Three stacked tongue layers: a state-coloured outer flame, a lighter mid
 *   flame and a white-hot core that hugs the body.
 * * **Breakaway fragments.** Flame pieces detach from the tips, rise, shrink and fade, so
 *   energy visibly leaves VAN rather than sitting on him.
 * * **Front/back depth.** A few faint wisps cross in front of the legs and forearms; never
 *   the face. Everything else is behind the opaque body.
 * * **Rim light.** A thin glow along VAN's own edge, in the aura's colour, so the field reads as
 *   light that falls on him.
 * * **Embers** rise off the upper flanks.
 * * **Two clocks.** [phase] loops seamlessly; [slowPhase] runs on a long, unrelated period so
 *   the combined motion does not visibly repeat.
 * * **Pulse.** A brief white expansion (a closed trade, a success) scales height and whitens.
 *
 * All of it wraps a [VanSilhouette] taken from what is on screen: the Rive artboard's alpha
 * each few frames, the Candidate B art's alpha, or the measured layout. No strands, lightning
 * or specks (CF-D-06-REV1). Android-native; `van.riv` never contains any of it.
 *
 * Every tunable here is bounded by
 * `visual-authority/character-forge/aura/AURA_RUNTIME_CONTRACT.yaml`, and a contract test
 * reads these constants back and fails when one leaves its range.
 */
object VanFlameAura {

    const val SAMPLES = VanSilhouette.SAMPLES
    /** Air between the body edge and each layer's base, as a fraction of the body edge. */
    const val OUTER_PAD = 0.030f
    const val MID_PAD = 0.018f
    const val CORE_PAD = 0.008f
    /** Tongue height at full intensity, as a fraction of the body edge. */
    const val HEIGHT_BASE = 0.02f
    const val HEIGHT_PER_INTENSITY = 0.42f
    const val OUTER_ALPHA_BASE = 0.12f
    const val OUTER_ALPHA_PER_INTENSITY = 0.50f
    const val OUTER_ALPHA_MAX = 0.78f
    const val MID_WHITE_MIX = 0.30f
    const val CORE_WHITE_MIX = 0.85f
    /** Gradient stops shared by both executors: solid to 55% of the radius, fading out at the tips. */
    const val FLAME_SOLID_STOP_FRACTION = 0.55f
    const val FLAME_TIP_ALPHA_FRACTION = 0.0f
    const val MIN_TONGUES = 12
    const val MAX_TONGUES = 22
    const val MAX_FRAGMENTS = 12
    const val MAX_FRONT_WISPS = 6
    /** Front wisps stay translucent: VAN must read through them. */
    const val FRONT_ALPHA_MAX = 0.24f
    /** Front wisps never rise above this fraction of VAN's height (0 = crown): the face is clear. */
    const val FRONT_TOP_FRACTION = 0.45f
    const val RIM_ALPHA_MAX = 0.45f
    const val RIM_WIDTH = 0.010f
    const val EMBER_BLOOM_RADIUS_SCALE = 3.2f
    const val PULSE_HEIGHT_GAIN = 0.8f
    const val PULSE_WHITE_MIX = 0.5f

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
        silhouette: VanSilhouette? = null,
        slowPhase: Float = 0f,
        pulse: Float = 0f,
    ): List<VanAuraOp> {
        val intensity = max(spec.intensity, semanticSpec.intensity * 0.8f).coerceIn(0f, 1f)
        if (bodyEdge <= 4f || intensity <= 0.01f) return emptyList()
        val p = pulse.coerceIn(0f, 1f)
        val base = semanticSpec.semanticColor ?: identityColor
        val color = if (p > 0f) mix(base, WHITE, PULSE_WHITE_MIX * p) else base
        // Superlinear, so a sleeping VAN smoulders and a working one flares.
        val height = bodyEdge * (HEIGHT_BASE + HEIGHT_PER_INTENSITY * intensity.pow(1.2f)) * (1f + PULSE_HEIGHT_GAIN * p)
        val reach = bodyEdge * 0.5f * spec.envelopeRadiusScale.coerceIn(
            VanAuraSpec.MIN_ENVELOPE_SCALE,
            VanAuraSpec.MAX_ENVELOPE_SCALE,
        )
        val arc = max(spec.arcActivity, semanticSpec.arcActivity).coerceIn(0f, 1f)
        val deform = max(spec.deformation, semanticSpec.deformation).coerceIn(0f, 1f)
        val tongues = (MIN_TONGUES + (MAX_TONGUES - MIN_TONGUES) * arc).toInt()
        val motion = budget.allowMotion
        val flicker = if (motion) 0.10f + 0.30f * deform else 0f
        val lean = (spec.fieldAsymmetry - 0.2f) * 0.35f
        val outerAlpha = (OUTER_ALPHA_BASE + OUTER_ALPHA_PER_INTENSITY * intensity + 0.12f * p).coerceAtMost(OUTER_ALPHA_MAX)
        val shape = silhouette ?: VanSilhouette.fromLayout(framing)
        val frame = Frame(centerX, centerY, bodyEdge, reach, tongues, flicker, lean, phase, if (motion) slowPhase else 0f, shape)

        val ops = mutableListOf<VanAuraOp>()
        val full = budget != VanEffectBudget.LOW && budget != VanEffectBudget.STATIC
        // Behind VAN.
        if (full) {
            ops += frame.layer(OUTER_PAD * 1.6f, height * 1.18f, 3f, 0.61f, color, outerAlpha * 0.28f)
        }
        ops += frame.layer(OUTER_PAD, height, 5f, 0f, color, outerAlpha)
        if (full) {
            ops += frame.layer(MID_PAD, height * 0.55f, 6f, 0.37f, mix(color, WHITE, MID_WHITE_MIX), min(outerAlpha * 1.05f, 0.82f))
        }
        ops += frame.layer(CORE_PAD, height * 0.20f, 7f, 0.83f, mix(color, WHITE, CORE_WHITE_MIX), min(outerAlpha * 1.15f, 0.88f))
        if (full && motion) {
            val fragments = min(MAX_FRAGMENTS, (2 + 10 * arc * intensity + 6 * deform * intensity + 4 * p).toInt())
            ops += frame.fragments(fragments, height, mix(color, WHITE, 0.15f), outerAlpha)
        }
        ops += frame.embers(spec, budget, height, mix(color, WHITE, 0.35f), outerAlpha, p)
        // In front of VAN.
        if (full) {
            val wisps = min(MAX_FRONT_WISPS, (2 + 4 * intensity).toInt())
            ops += frame.frontWisps(wisps, height, mix(color, WHITE, MID_WHITE_MIX), min(FRONT_ALPHA_MAX, 0.08f + 0.18f * intensity))
        }
        frame.rim(mix(color, WHITE, 0.30f), min(RIM_ALPHA_MAX, 0.12f + 0.40f * intensity))?.let { ops += it }
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
        val slowPhase: Float,
        val shape: VanSilhouette,
    ) {
        val originX = px(shape.centerU)
        val originY = py(shape.centerV)

        fun px(u: Float) = cx + (u - 0.5f) * edge
        fun py(v: Float) = cy + (v - 0.5f) * edge
        fun insideBody(x: Float, y: Float): Boolean = shape.contains((x - cx) / edge + 0.5f, (y - cy) / edge + 0.5f)

        private fun clampToReach(x: Float, y: Float): Pair<Float, Float> {
            val dx = x - cx
            val dy = y - cy
            val d = sqrt(dx * dx + dy * dy)
            return if (d > reach) (cx + dx / d * reach) to (cy + dy / d * reach) else x to y
        }

        /** A closed ring of flame tongues around the silhouette. */
        fun layer(pad: Float, height: Float, sharpness: Float, seed: Float, color: Int, alpha: Float): VanAuraOp.Flame {
            val xs = FloatArray(SAMPLES)
            val ys = FloatArray(SAMPLES)
            var farthest = 0f
            for (i in 0 until SAMPLES) {
                val angle = VanSilhouette.angleAt(i)
                val dx = cos(angle)
                val dy = sin(angle)
                val base = shape.extent(i) * edge + pad * edge
                // Tongues grow with how much a point faces up, and die out under the feet.
                val up = (-dy).coerceAtLeast(0f)
                val side = 1f - abs(dy)
                val grow = (0.22f + 0.78f * up + 0.35f * side) * if (dy > 0.55f) 0.25f else 1f
                val lick = height * grow * tongueField(i, sharpness, seed)
                // Tips bend towards vertical, as flames do, with a slight lean.
                var tx = dx * 0.75f + lean
                var ty = dy * 0.75f - 0.85f * (1f - max(0f, dy))
                val norm = sqrt(tx * tx + ty * ty).coerceAtLeast(0.001f)
                tx /= norm; ty /= norm
                var x = originX + dx * base + tx * lick
                var y = originY + dy * base + ty * lick
                // A bent tip can curl back over an arm or the head; then it rises straight out,
                // which always clears the body because `base` is past the outermost edge.
                if (insideBody(x, y)) {
                    x = originX + dx * (base + lick)
                    y = originY + dy * (base + lick)
                }
                val (cxr, cyr) = clampToReach(x, y)
                xs[i] = cxr; ys[i] = cyr
                farthest = max(farthest, sqrt((cxr - originX) * (cxr - originX) + (cyr - originY) * (cyr - originY)))
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
         * Sum of narrow peaks, one per tongue. Heights and widths come from a hash so every
         * tongue differs; each flickers on its own clock, breathes on the slow clock, and a
         * ripple runs up both flanks so the fire appears to climb.
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
                val shapeK = (0.5f + 0.5f * cos(Math.PI.toFloat() * d / width)).pow(sharpness * 0.5f)
                // Whole-number speeds: the phase loops 0..1 and the fire must not jump at the wrap.
                val clock = sin(TAU * (phase * (1 + (h * 3f).toInt()) + h))
                val breath = 0.88f + 0.12f * sin(TAU * (slowPhase * (1 + k % 3) + h))
                val amp = (0.45f + 0.55f * h) * (1f + flicker * clock) * breath
                total = max(total, shapeK * amp)
            }
            val climb = 0.10f * sin(TAU * (t * 6f - phase * 2f + seed + slowPhase)) * (flicker / 0.4f).coerceAtMost(1f)
            return (total + climb).coerceAtLeast(0f)
        }

        /** Flame pieces that break off the upper tips, rise, shrink and fade. */
        fun fragments(count: Int, height: Float, color: Int, alpha: Float): List<VanAuraOp> {
            val out = ArrayList<VanAuraOp>(count)
            for (k in 0 until count) {
                val h = hash(k * 4.37f + 1.3f)
                // Upper arc only: 0..SAMPLES/4 either side of straight up.
                val offset = ((h - 0.5f) * SAMPLES * 0.55f).toInt()
                val index = (offset + SAMPLES) % SAMPLES
                val angle = VanSilhouette.angleAt(index)
                val life = frac(phase * (1 + (h * 3f).toInt()) + hash(k * 2.9f) + slowPhase * 0.5f)
                val start = shape.extent(index) * edge + OUTER_PAD * edge + height * 0.55f
                val sway = sin(TAU * (life + h)) * edge * 0.02f
                val x0 = originX + cos(angle) * start + sway
                val y0 = originY + sin(angle) * start - height * 1.4f * life
                val (x, y) = clampToReach(x0, y0)
                val r = edge * (0.014f + 0.016f * h) * (1f - 0.65f * life)
                val a = alpha * 0.85f * (1f - life)
                if (r <= 0.5f || a <= 0.01f) continue
                out += VanAuraOp.Flame(
                    path = teardrop(x, y, r, r * (2.2f + h)),
                    gradientX = x, gradientY = y + r * 0.4f, gradientRadius = r * (2.4f + h),
                    color = color, alpha = a,
                )
            }
            return out
        }

        /** Faint wisps crossing in front of the legs and forearms, never above the face line. */
        fun frontWisps(count: Int, height: Float, color: Int, alpha: Float): List<VanAuraOp> {
            val out = ArrayList<VanAuraOp>(count)
            val faceLine = py(shape.topV + FRONT_TOP_FRACTION * (shape.bottomV - shape.topV))
            for (k in 0 until count) {
                val h = hash(k * 6.11f + 2.1f)
                // Alternate flanks, lower half of the figure (angles 45°–120° from straight down).
                val side = if (k % 2 == 0) 1 else -1
                val index = (SAMPLES / 2 + side * (SAMPLES / 8 + (h * SAMPLES / 8).toInt()) + SAMPLES) % SAMPLES
                val angle = VanSilhouette.angleAt(index)
                // Rooted just inside the edge so the wisp crosses the silhouette.
                val root = shape.extent(index) * edge - edge * 0.012f
                val x = originX + cos(angle) * root
                val y = originY + sin(angle) * root
                val life = frac(phase * (1 + (h * 2f).toInt()) + h + slowPhase)
                // The tip sits 1.35 × tall above the root (base lifted 0.35, then the full length).
                val tall = min(height * (0.45f + 0.35f * h) * (0.6f + 0.4f * sin(TAU * life)), max(0f, y - faceLine) / 1.35f)
                if (tall < edge * 0.02f) continue
                out += VanAuraOp.Flame(
                    path = teardrop(x, y - tall * 0.35f, edge * (0.010f + 0.008f * h), tall),
                    gradientX = x, gradientY = y, gradientRadius = tall * 1.1f,
                    color = color, alpha = alpha * (0.7f + 0.3f * h), front = true,
                )
            }
            return out
        }

        /**
         * Light falling on VAN's own edge: runs of points along the silhouette, broken wherever
         * the chord between two samples would cross empty space (between the legs, under the
         * arm) so the rim never becomes a line drawn across the background.
         */
        fun rim(color: Int, alpha: Float): VanAuraOp.Rim? {
            val runs = ArrayList<List<VanFieldPoint>>()
            var run = ArrayList<VanFieldPoint>()
            fun flush() {
                if (run.size >= 3) runs += run
                run = ArrayList()
            }
            for (i in 0..SAMPLES) {
                val angle = VanSilhouette.angleAt(i)
                val dy = sin(angle)
                if (dy > 0.6f) { flush(); continue }  // not along the soles
                val r = shape.extent(i) * edge - edge * 0.004f
                val point = VanFieldPoint(originX + cos(angle) * r, originY + dy * r)
                val prev = run.lastOrNull()
                if (prev != null) {
                    val mx = (prev.x + point.x) / 2f
                    val my = (prev.y + point.y) / 2f
                    // Nudge the midpoint towards the centre; if that is still outside, the chord spans a gap.
                    val inX = mx + (originX - mx) * 0.03f
                    val inY = my + (originY - my) * 0.03f
                    if (!insideBody(inX, inY)) flush()
                }
                run += point
            }
            flush()
            if (runs.isEmpty() || alpha <= 0.01f) return null
            return VanAuraOp.Rim(runs = runs, color = color, alpha = alpha, width = max(edge * RIM_WIDTH, 1f))
        }

        /** Sparks lifting off the upper flanks and fading as they rise. */
        fun embers(spec: VanAuraSpec, budget: VanEffectBudget, height: Float, color: Int, alpha: Float, pulse: Float): List<VanAuraOp> {
            if (budget == VanEffectBudget.STATIC) return emptyList()
            val count = (3 + 15 * spec.sparkRate.coerceIn(0f, 1f) + 4 * spec.intensity + 10 * pulse).toInt()
            val out = ArrayList<VanAuraOp>(count)
            for (k in 0 until count) {
                val h = hash(k * 5.31f + 0.7f)
                val index = ((0.62f + 0.76f * h) * SAMPLES / 2f).toInt() % SAMPLES
                val angle = VanSilhouette.angleAt(index)
                val base = shape.extent(index) * edge + OUTER_PAD * edge
                val life = frac(phase * (1 + (h * 2f).toInt()) + hash(k * 2.17f) + slowPhase * 0.3f)
                val rise = height * (0.3f + 1.6f * life)
                val x = originX + cos(angle) * base + (hash(k * 9.1f) - 0.5f) * edge * 0.06f
                val y = originY + sin(angle) * base - rise
                if ((x - cx) * (x - cx) + (y - cy) * (y - cy) > reach * reach) continue
                out += VanAuraOp.Dot(
                    cx = x, cy = y,
                    radius = max(edge * (0.004f + 0.004f * h), 0.8f),
                    color = color,
                    alpha = (alpha * 1.1f * (1f - life)).coerceIn(0f, 0.9f),
                    bloomRadiusScale = EMBER_BLOOM_RADIUS_SCALE,
                    bloomAlphaScale = 0.22f,
                )
            }
            return out
        }
    }

    /** A flame droplet: round base at ([x], [y]), tapering to a point [length] above it. */
    private fun teardrop(x: Float, y: Float, r: Float, length: Float): List<VanPathSeg> = listOf(
        VanPathSeg.MoveTo(x, y - length),
        VanPathSeg.QuadTo(x + r * 1.1f, y - length * 0.45f, x + r, y),
        VanPathSeg.QuadTo(x, y + r * 1.3f, x - r, y),
        VanPathSeg.QuadTo(x - r * 1.1f, y - length * 0.45f, x, y - length),
        VanPathSeg.Close,
    )

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
