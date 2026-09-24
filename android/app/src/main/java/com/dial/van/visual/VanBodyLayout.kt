package com.dial.van.visual

import kotlin.math.cos
import kotlin.math.sin

/**
 * Candidate B's front silhouette in the character's unit square (CF-D-05-REV2_1).
 *
 * Every number is a landmark measured on the native Candidate B image and mapped with the same
 * framing the Rive artboard `Van` uses (character 86% of the height, 7% top margin; see
 * `visual-authority/character-forge/00-source/reference-pack/PROPORTIONS.yaml`). The Canvas
 * fallback draws inside these shapes, and the flame aura wraps them. So the aura fits the Rive
 * character and the fallback alike without either renderer knowing about the other.
 *
 * `u` grows right, `v` grows down, both 0..1 across the square the character is drawn in.
 * "Left" is the viewer's left, matching the reference crops.
 */
object VanBodyLayout {
    /** Board px → unit square, exactly as `build_reference_pack.P` maps board px → artboard. */
    private const val K = 0.0016863f
    fun u(boardX: Float): Float = 0.5f + (boardX - 200f) * K
    fun v(boardY: Float): Float = 0.07f + (boardY - 8f) * K
    fun len(boardPx: Float): Float = boardPx * K

    val HAIR_CROWN_V = v(8f)
    val CHIN_V = v(170f)
    val SOLE_V = v(518f)

    /** Aura centre: the middle of the figure, where the flame gradient starts. */
    const val CENTER_U = 0.49f
    const val CENTER_V = 0.50f

    /** The orb companion is drawn separately and is not wrapped by the character's flames. */
    val ORB = VanExclusionPrimitive.Ellipse(u(67f), v(171f), len(50f), len(50f))

    /**
     * Head-and-hair, torso, arms, legs and boots as ellipses and capsules. The shapes are
     * deliberately coarse: they are an envelope to wrap, not a drawing.
     */
    val silhouette: List<VanExclusionPrimitive> = listOf(
        VanExclusionPrimitive.Ellipse(u(190f), v(88f), len(96f), len(84f)),
        VanExclusionPrimitive.Ellipse(u(205f), v(262f), len(107f), len(82f)),
        VanExclusionPrimitive.Capsule(u(130f), v(205f), u(50f), v(262f), len(24f)),
        VanExclusionPrimitive.Ellipse(u(45f), v(262f), len(32f), len(22f)),
        VanExclusionPrimitive.Capsule(u(285f), v(205f), u(302f), v(350f), len(22f)),
        VanExclusionPrimitive.Capsule(u(160f), v(330f), u(140f), v(470f), len(32f)),
        VanExclusionPrimitive.Capsule(u(240f), v(330f), u(268f), v(470f), len(32f)),
        VanExclusionPrimitive.Ellipse(u(136f), v(492f), len(56f), len(28f)),
        VanExclusionPrimitive.Ellipse(u(272f), v(492f), len(42f), len(28f)),
    )

    fun contains(u: Float, v: Float): Boolean = silhouette.any { it.contains(u, v) }

    /**
     * Distance from the aura centre to the silhouette's outer edge along [angleRad]
     * (0 = right, π/2 = down), in unit-square lengths. It is found by marching inwards from
     * well outside, so a concavity (the gap between the legs) is bridged, not followed.
     */
    fun radialExtent(angleRad: Float): Float {
        val dx = cos(angleRad)
        val dy = sin(angleRad)
        var r = 0.62f
        while (r > 0.02f) {
            if (contains(CENTER_U + dx * r, CENTER_V + dy * r)) return r
            r -= 0.003f
        }
        return 0.02f
    }

    /** [radialExtent] sampled at [count] evenly spaced angles, starting straight up. */
    fun extents(count: Int): FloatArray {
        cachedExtents[count]?.let { return it }
        val built = FloatArray(count) { i -> radialExtent(angleAt(i, count)) }
        cachedExtents[count] = built
        return built
    }

    fun angleAt(index: Int, count: Int): Float = (-Math.PI / 2 + 2 * Math.PI * index / count).toFloat()

    private val cachedExtents = HashMap<Int, FloatArray>()
}

/**
 * How much of Candidate B a surface shows. The full body is framed exactly like the Rive
 * artboard; the compact overlay zooms into head and shoulders so the face still reads at
 * 72–92 dp. The Canvas character and the flame aura take the same framing, so the flames stay
 * fitted to the body whatever the zoom.
 */
data class VanFraming(val zoom: Float, val focusU: Float, val focusV: Float) {
    fun x(u: Float): Float = 0.5f + (u - focusU) * zoom
    fun y(v: Float): Float = 0.5f + (v - focusV) * zoom
    fun unframeX(x: Float): Float = focusU + (x - 0.5f) / zoom
    fun unframeY(y: Float): Float = focusV + (y - 0.5f) / zoom

    companion object {
        val FULL_BODY = VanFraming(1f, 0.5f, 0.5f)
        val EXPANDED = VanFraming(1.40f, 0.47f, 0.40f)
        val COMPACT = VanFraming(1.80f, 0.47f, 0.33f)

        fun forPresentation(presentation: VanPresentation): VanFraming = when (presentation) {
            VanPresentation.COMPACT -> COMPACT
            VanPresentation.EXPANDED -> EXPANDED
            VanPresentation.COMMAND_CENTRE -> FULL_BODY
        }
    }
}

/**
 * The interim character art: a native-resolution cut-out of Candidate B's front view, in the
 * same unit-square framing as the Rive artboard (built by
 * `tools/character_forge/build_reference_pack.py`, bundled as `drawable-nodpi/van_candidate_b_front.png`).
 *
 * The owner chose real Candidate B art over the procedural drawing until `van.riv` exists.
 * It is a still: VAN bobs and the state desaturates him, but he has no expressions or gestures.
 */
object VanInterimArt {
    const val SIDE_PX = 593

    /** Source rectangle in bitmap pixels and destination rectangle in box pixels. */
    data class Blit(
        val srcLeft: Int, val srcTop: Int, val srcWidth: Int, val srcHeight: Int,
        val dstLeft: Float, val dstTop: Float, val dstWidth: Float, val dstHeight: Float,
    )

    /**
     * Where to copy the bitmap so that [framing] shows the same part of VAN as the Canvas
     * character and the flame aura. The unit square is the largest centred square of the box;
     * a framing that reaches past the bitmap is clamped, with the destination shrunk to match,
     * so nothing is stretched.
     */
    fun blit(framing: VanFraming, bitmapSide: Int, boxWidth: Float, boxHeight: Float): Blit? {
        val side = minOf(boxWidth, boxHeight)
        if (side <= 0f || bitmapSide <= 0) return null
        val originX = (boxWidth - side) / 2f
        val originY = (boxHeight - side) / 2f
        val l = framing.unframeX(0f) * bitmapSide
        val t = framing.unframeY(0f) * bitmapSide
        val r = framing.unframeX(1f) * bitmapSide
        val b = framing.unframeY(1f) * bitmapSide
        val scale = side / (r - l)
        val cl = l.coerceIn(0f, bitmapSide.toFloat())
        val ct = t.coerceIn(0f, bitmapSide.toFloat())
        val cr = r.coerceIn(0f, bitmapSide.toFloat())
        val cb = b.coerceIn(0f, bitmapSide.toFloat())
        if (cr - cl < 1f || cb - ct < 1f) return null
        val srcLeft = cl.toInt()
        val srcTop = ct.toInt()
        val srcWidth = (cr.toInt() - srcLeft).coerceAtLeast(1)
        val srcHeight = (cb.toInt() - srcTop).coerceAtLeast(1)
        return Blit(
            srcLeft, srcTop, srcWidth, srcHeight,
            dstLeft = originX + (srcLeft - l) * scale,
            dstTop = originY + (srcTop - t) * scale,
            dstWidth = srcWidth * scale,
            dstHeight = srcHeight * scale,
        )
    }
}
