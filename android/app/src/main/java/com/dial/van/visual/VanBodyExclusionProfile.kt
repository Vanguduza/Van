package com.dial.van.visual

import kotlin.math.max
import kotlin.math.min

/** Renderer-neutral conservative silhouette used to keep living-field strands visibly detached. */
sealed interface VanExclusionPrimitive {
    fun contains(x: Float, y: Float): Boolean

    data class Ellipse(
        val cx: Float,
        val cy: Float,
        val rx: Float,
        val ry: Float,
    ) : VanExclusionPrimitive {
        override fun contains(x: Float, y: Float): Boolean {
            if (rx <= 0f || ry <= 0f) return false
            val nx = (x - cx) / rx
            val ny = (y - cy) / ry
            return nx * nx + ny * ny <= 1f
        }
    }

    data class Capsule(
        val ax: Float,
        val ay: Float,
        val bx: Float,
        val by: Float,
        val radius: Float,
    ) : VanExclusionPrimitive {
        override fun contains(x: Float, y: Float): Boolean {
            val abx = bx - ax
            val aby = by - ay
            val apx = x - ax
            val apy = y - ay
            val denominator = abx * abx + aby * aby
            val t = if (denominator <= 0.00001f) 0f else ((apx * abx + apy * aby) / denominator).coerceIn(0f, 1f)
            val qx = ax + abx * t
            val qy = ay + aby * t
            val dx = x - qx
            val dy = y - qy
            return dx * dx + dy * dy <= radius * radius
        }
    }
}

/**
 * Approximation of the shipping compact VAN silhouette plus an inflated air gap.
 * Coordinates are absolute pixels generated from [bodyEdge]. The profile is intentionally
 * conservative: a strand clipped slightly farther away is preferable to another body-hugging halo.
 */
data class VanBodyExclusionProfile(
    val primitives: List<VanExclusionPrimitive>,
) {
    fun contains(point: VanFieldPoint): Boolean = primitives.any { it.contains(point.x, point.y) }

    companion object {
        fun compact(
            bodyEdge: Float,
            centerX: Float,
            centerY: Float,
            extraGapScale: Float = 1f,
        ): VanBodyExclusionProfile {
            val gap = bodyEdge * 0.055f * extraGapScale.coerceIn(0.65f, 1.5f)
            val head = VanExclusionPrimitive.Ellipse(
                cx = centerX - bodyEdge * 0.025f,
                cy = centerY - bodyEdge * 0.055f,
                rx = bodyEdge * 0.255f + gap,
                ry = bodyEdge * 0.300f + gap,
            )
            val torso = VanExclusionPrimitive.Capsule(
                ax = centerX,
                ay = centerY + bodyEdge * 0.215f,
                bx = centerX,
                by = centerY + bodyEdge * 0.455f,
                radius = bodyEdge * 0.295f + gap,
            )
            // Shoulders flare wider than the central torso capsule.
            val shoulders = VanExclusionPrimitive.Ellipse(
                cx = centerX,
                cy = centerY + bodyEdge * 0.285f,
                rx = bodyEdge * 0.355f + gap,
                ry = bodyEdge * 0.155f + gap * 0.7f,
            )
            return VanBodyExclusionProfile(listOf(head, torso, shoulders))
        }
    }
}

internal fun clampSegmentToCanvas(value: Float, minValue: Float, maxValue: Float): Float =
    max(minValue, min(value, maxValue))
