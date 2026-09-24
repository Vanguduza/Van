package com.dial.van.visual

import kotlin.math.cos
import kotlin.math.sin

/**
 * Where VAN is, in the character box's unit square (0..1 across the largest centred square),
 * as the aura sees it.
 *
 * Aura Rev 2 (CF-D-08): the flame envelope, breakaway fragments, front wisps and rim light
 * all wrap *this*. It is taken from what is actually on screen:
 *
 * * **Rive** — the rendered artboard's alpha, sampled every few frames
 *   ([fromAlphaMask], fed by `VanRiveSilhouetteSampler`), so the field follows every pose,
 *   gesture and head turn the rig makes;
 * * **Candidate B art** — the cut-out's alpha, built once per framing;
 * * **Canvas fallback** — the measured layout ([fromLayout]).
 *
 * Pure Kotlin: the same silhouette object drives the Compose painter, the JVM evidence
 * renderer and the tests.
 */
class VanSilhouette private constructor(
    /** Horizontal centre of the figure, the flame gradient's origin. */
    val centerU: Float,
    /** Vertical centre of the figure. */
    val centerV: Float,
    /** Distance from the centre to the outer edge at each of [SAMPLES] angles (0 = up, clockwise). */
    private val extents: FloatArray,
    /** Crown (top) and sole (bottom) of the figure, box units. */
    val topV: Float,
    val bottomV: Float,
    private val inside: (Float, Float) -> Boolean,
) {
    fun extent(index: Int): Float = extents[((index % SAMPLES) + SAMPLES) % SAMPLES]

    fun contains(u: Float, v: Float): Boolean = inside(u, v)

    /** 0 at the crown, 1 at the sole: used to keep front wisps away from the face. */
    fun heightFraction(v: Float): Float = ((v - topV) / (bottomV - topV).coerceAtLeast(1e-4f)).coerceIn(0f, 1f)

    companion object {
        const val SAMPLES = 144

        fun angleAt(index: Int): Float = VanBodyLayout.angleAt(index, SAMPLES)

        private val layoutCache = HashMap<VanFraming, VanSilhouette>()

        /** Candidate B's measured layout, framed. Used by the Canvas fallback and as the default. */
        fun fromLayout(framing: VanFraming = VanFraming.FULL_BODY): VanSilhouette = layoutCache.getOrPut(framing) {
            val raw = VanBodyLayout.extents(SAMPLES)
            VanSilhouette(
                centerU = framing.x(VanBodyLayout.CENTER_U),
                centerV = framing.y(VanBodyLayout.CENTER_V),
                extents = FloatArray(SAMPLES) { raw[it] * framing.zoom },
                topV = framing.y(VanBodyLayout.HAIR_CROWN_V),
                bottomV = framing.y(VanBodyLayout.SOLE_V),
                inside = { u, v -> VanBodyLayout.contains(framing.unframeX(u), framing.unframeY(v)) },
            )
        }

        /**
         * From an alpha grid sampled over a whole view of [viewWidth] × [viewHeight] (the Rive
         * `TextureView`): the character box is the view's largest centred square, so the grid
         * is remapped onto that square before the silhouette is built.
         */
        fun fromViewAlpha(
            gridWidth: Int, gridHeight: Int, alpha: ByteArray,
            viewWidth: Float, viewHeight: Float, out: ByteArray = ByteArray(SQUARE * SQUARE),
        ): VanSilhouette? {
            val side = minOf(viewWidth, viewHeight)
            if (side <= 0f || gridWidth <= 0 || gridHeight <= 0) return null
            val ox = (viewWidth - side) / 2f
            val oy = (viewHeight - side) / 2f
            for (y in 0 until SQUARE) {
                val vy = oy + (y + 0.5f) / SQUARE * side
                val gy = (vy / viewHeight * gridHeight).toInt().coerceIn(0, gridHeight - 1)
                for (x in 0 until SQUARE) {
                    val vx = ox + (x + 0.5f) / SQUARE * side
                    val gx = (vx / viewWidth * gridWidth).toInt().coerceIn(0, gridWidth - 1)
                    out[y * SQUARE + x] = alpha[gy * gridWidth + gx]
                }
            }
            return fromAlphaMask(SQUARE, SQUARE, out)
        }

        /**
         * From an alpha grid of the full-body unit square (the Candidate B cut-out), seen
         * through [framing]: each cell of the framed square is looked up in the full-body grid.
         */
        fun framedFromUnitAlpha(width: Int, height: Int, alpha: ByteArray, framing: VanFraming): VanSilhouette? {
            if (framing == VanFraming.FULL_BODY) return fromAlphaMask(width, height, alpha)
            val out = ByteArray(SQUARE * SQUARE)
            for (y in 0 until SQUARE) {
                val v = framing.unframeY((y + 0.5f) / SQUARE)
                val gy = (v * height).toInt()
                for (x in 0 until SQUARE) {
                    val u = framing.unframeX((x + 0.5f) / SQUARE)
                    val gx = (u * width).toInt()
                    out[y * SQUARE + x] = if (gx in 0 until width && gy in 0 until height) alpha[gy * width + gx] else 0
                }
            }
            return fromAlphaMask(SQUARE, SQUARE, out)
        }

        /** Resolution of the square masks built above: enough for flame placement, cheap per frame. */
        const val SQUARE = 72

        /**
         * From an alpha mask covering the unit square: [alpha] is row-major, [width] × [height],
         * and a pixel counts as VAN when its alpha is at least [threshold] (0..255).
         *
         * The centre is the mask's centroid, so a rig that leans or reaches moves the field's
         * origin with it. Extents are found by marching inwards from outside the figure, so a
         * concavity (between the legs, under an outstretched arm) is bridged, not followed.
         * Returns null for an empty mask; the caller keeps its previous silhouette.
         */
        fun fromAlphaMask(width: Int, height: Int, alpha: ByteArray, threshold: Int = 96): VanSilhouette? {
            if (width <= 1 || height <= 1 || alpha.size < width * height) return null
            val solid = BooleanArray(width * height) { (alpha[it].toInt() and 0xFF) >= threshold }
            var count = 0
            var sumX = 0.0
            var sumY = 0.0
            var top = height
            var bottom = -1
            for (y in 0 until height) {
                for (x in 0 until width) {
                    if (solid[y * width + x]) {
                        count++; sumX += x; sumY += y
                        if (y < top) top = y
                        if (y > bottom) bottom = y
                    }
                }
            }
            if (count < 8) return null
            val cu = ((sumX / count + 0.5) / width).toFloat()
            val cv = ((sumY / count + 0.5) / height).toFloat()
            fun at(u: Float, v: Float): Boolean {
                val x = (u * width).toInt()
                val y = (v * height).toInt()
                return x in 0 until width && y in 0 until height && solid[y * width + x]
            }
            val step = 0.5f / maxOf(width, height)
            val extents = FloatArray(SAMPLES) { i ->
                val a = angleAt(i)
                val dx = cos(a)
                val dy = sin(a)
                var r = 0.75f
                var found = step
                while (r > step) {
                    if (at(cu + dx * r, cv + dy * r)) { found = r; break }
                    r -= step
                }
                found
            }
            return VanSilhouette(
                centerU = cu,
                centerV = cv,
                extents = extents,
                topV = top.toFloat() / height,
                bottomV = (bottom + 1).toFloat() / height,
                inside = ::at,
            )
        }
    }
}
