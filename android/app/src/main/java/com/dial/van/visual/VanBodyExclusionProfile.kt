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
        /**
         * P2-AURA-001 — the air gap is a dp contract, not a fraction of whatever size the
         * caller happened to render at.
         *
         * The gap used to be `bodyEdge * 0.055f`. At the shipping 96 dp floating avatar that
         * is 5.3 dp against a 10–14 dp requirement — the field visibly hugged the body —
         * and at the 400 dp evidence board the same fraction gives 22 dp, so the *same
         * code* was too tight in one place and too loose in the other. A gap is a physical
         * distance the eye reads; expressing it as a proportion of an arbitrary render size
         * cannot be right at two sizes at once.
         *
         * [bodyEdgeDp] is the body's size in density-independent pixels. When a caller does
         * not know it — the JVM evidence renderer works in raw pixels with no density — the
         * legacy fraction is used and [gapDp] returns null, so a test can tell the
         * difference between "the gap is out of band" and "nobody said what a dp is here".
         */
        const val MIN_BODY_GAP_DP = 10f
        const val MAX_BODY_GAP_DP = 14f
        const val TARGET_BODY_GAP_DP = 12f

        /** The legacy proportion, kept only for callers that cannot supply a density. */
        const val LEGACY_GAP_FRACTION = 0.055f

        /** The gap in dp that [compact] will use, or null when no density was supplied. */
        fun gapDp(bodyEdgeDp: Float?, extraGapScale: Float = 1f): Float? {
            if (bodyEdgeDp == null || bodyEdgeDp <= 0f) return null
            return (TARGET_BODY_GAP_DP * extraGapScale.coerceIn(0.65f, 1.5f))
                .coerceIn(MIN_BODY_GAP_DP, MAX_BODY_GAP_DP)
        }

        fun compact(
            bodyEdge: Float,
            centerX: Float,
            centerY: Float,
            extraGapScale: Float = 1f,
            bodyEdgeDp: Float? = null,
        ): VanBodyExclusionProfile {
            val scale = extraGapScale.coerceIn(0.65f, 1.5f)
            val dp = gapDp(bodyEdgeDp, extraGapScale)
            val gap = if (dp != null && bodyEdgeDp != null && bodyEdgeDp > 0f) {
                bodyEdge * (dp / bodyEdgeDp)
            } else {
                bodyEdge * LEGACY_GAP_FRACTION * scale
            }
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

        /**
         * P2-PERF-001 — the silhouette was rebuilt on every frame, and it never changes
         * between them.
         *
         * The profile depends only on the body's size and position, which are fixed for as
         * long as the overlay is the size it is. Rebuilding it per frame allocated three
         * objects and a list sixty times a second for a value that was identical each time.
         * The strand *coordinates* genuinely do change every frame — that is the animation
         * — so this caches what is stable and makes no claim about what is not.
         *
         * A one-entry memo rather than a map: the renderer draws one body at one size, and
         * a map would be an unbounded cache keyed on floats.
         */
        private var cachedKey: Long = Long.MIN_VALUE
        private var cached: VanBodyExclusionProfile? = null

        /** Rebuilds counted so a test can prove the caching is real rather than intended. */
        var rebuilds: Long = 0L
            private set

        fun compactCached(
            bodyEdge: Float,
            centerX: Float,
            centerY: Float,
            extraGapScale: Float = 1f,
            bodyEdgeDp: Float? = null,
        ): VanBodyExclusionProfile {
            val key = profileKey(bodyEdge, centerX, centerY, extraGapScale, bodyEdgeDp)
            val hit = cached
            if (hit != null && key == cachedKey) return hit
            val built = compact(bodyEdge, centerX, centerY, extraGapScale, bodyEdgeDp)
            cachedKey = key
            cached = built
            rebuilds += 1L
            return built
        }

        internal fun resetCache() {
            cachedKey = Long.MIN_VALUE
            cached = null
            rebuilds = 0L
        }

        /**
         * Quantised to 1/16 of a unit before hashing. Layout floats wobble in the last bits
         * between frames; an exact-equality key would miss on a body that has not moved.
         */
        private fun profileKey(
            bodyEdge: Float,
            centerX: Float,
            centerY: Float,
            extraGapScale: Float,
            bodyEdgeDp: Float?,
        ): Long {
            fun q(value: Float): Long = (value * 16f).toLong()
            var key = q(bodyEdge)
            key = key * 1_000_003L + q(centerX)
            key = key * 1_000_003L + q(centerY)
            key = key * 1_000_003L + q(extraGapScale)
            key = key * 1_000_003L + (bodyEdgeDp?.let { q(it) } ?: -1L)
            return key
        }
    }
}

internal fun clampSegmentToCanvas(value: Float, minValue: Float, maxValue: Float): Float =
    max(minValue, min(value, maxValue))
