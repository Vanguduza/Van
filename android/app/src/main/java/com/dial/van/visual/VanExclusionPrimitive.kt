package com.dial.van.visual

/** Renderer-neutral ellipse and capsule shapes that make up [VanBodyLayout.silhouette]. */
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
