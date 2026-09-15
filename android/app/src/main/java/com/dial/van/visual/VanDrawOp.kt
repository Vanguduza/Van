package com.dial.van.visual

/**
 * Renderer-independent drawing primitives for the canonical Van character.
 *
 * Every op is expressed in a unit square (0f..1f, y down) so a renderer can fit the
 * scene into any box without distorting the locked proportions. Keeping this file free
 * of Android imports lets the Compose overlay and the JVM preview renderer share one
 * geometry source of truth.
 */
sealed interface VanPathSeg {
    data class MoveTo(val x: Float, val y: Float) : VanPathSeg

    data class LineTo(val x: Float, val y: Float) : VanPathSeg

    data class QuadTo(val cx: Float, val cy: Float, val x: Float, val y: Float) : VanPathSeg

    object Close : VanPathSeg
}

sealed interface VanDrawOp {
    /** Packed ARGB. */
    val color: Int

    /** Null means fill; a value means stroke of that width in unit-square units. */
    val strokeWidth: Float?

    data class Circle(
        val cx: Float,
        val cy: Float,
        val r: Float,
        override val color: Int,
        override val strokeWidth: Float? = null,
    ) : VanDrawOp

    data class Oval(
        val cx: Float,
        val cy: Float,
        val rx: Float,
        val ry: Float,
        override val color: Int,
        override val strokeWidth: Float? = null,
    ) : VanDrawOp

    data class RoundRect(
        val cx: Float,
        val cy: Float,
        val halfW: Float,
        val halfH: Float,
        val radius: Float,
        override val color: Int,
        override val strokeWidth: Float? = null,
    ) : VanDrawOp

    data class PathOp(
        val segments: List<VanPathSeg>,
        override val color: Int,
        override val strokeWidth: Float? = null,
    ) : VanDrawOp

    data class Arc(
        val cx: Float,
        val cy: Float,
        val r: Float,
        val startDegrees: Float,
        val sweepDegrees: Float,
        override val color: Int,
        override val strokeWidth: Float?,
    ) : VanDrawOp
}

/** Colour helpers. Hex literals are `0xAARRGGBB`. */
object VanColors {
    fun of(hex: Long, alpha: Float = 1f): Int {
        val base = hex.toInt()
        if (alpha >= 1f) return base
        val a = ((base ushr 24) and 0xFF) * alpha.coerceIn(0f, 1f)
        return (a.toInt() shl 24) or (base and 0x00FFFFFF)
    }

    fun alpha(color: Int): Int = (color ushr 24) and 0xFF

    fun scaleAlpha(color: Int, factor: Float): Int {
        val a = (alpha(color) * factor.coerceIn(0f, 1f)).toInt()
        return (a shl 24) or (color and 0x00FFFFFF)
    }

    /** Blends [color] toward [target] by [amount]; alpha is preserved. */
    fun mix(color: Int, target: Int, amount: Float): Int {
        val t = amount.coerceIn(0f, 1f)
        if (t <= 0f) return color
        val a = alpha(color)
        val r = channelMix(color, target, 16, t)
        val g = channelMix(color, target, 8, t)
        val b = channelMix(color, target, 0, t)
        return (a shl 24) or (r shl 16) or (g shl 8) or b
    }

    /**
     * Pulls a colour toward its own luminance, which is how offline and degraded modes stay
     * truthful: the silhouette survives but the DIAL cyan energy visibly drains away.
     */
    fun desaturate(color: Int, amount: Float): Int {
        val t = amount.coerceIn(0f, 1f)
        if (t <= 0f) return color
        val r = (color ushr 16) and 0xFF
        val g = (color ushr 8) and 0xFF
        val b = color and 0xFF
        val luma = (0.299f * r + 0.587f * g + 0.114f * b).toInt().coerceIn(0, 255)
        val grey = (0xFF shl 24) or (luma shl 16) or (luma shl 8) or luma
        return mix(color, grey, t)
    }

    private fun channelMix(color: Int, target: Int, shift: Int, t: Float): Int {
        val c = (color ushr shift) and 0xFF
        val d = (target ushr shift) and 0xFF
        return (c + (d - c) * t).toInt().coerceIn(0, 255)
    }
}

/** Translates a whole group of ops, used for idle bob and orb drift. */
fun List<VanDrawOp>.translated(dx: Float, dy: Float): List<VanDrawOp> {
    if (dx == 0f && dy == 0f) return this
    return map { op ->
        when (op) {
            is VanDrawOp.Circle -> op.copy(cx = op.cx + dx, cy = op.cy + dy)
            is VanDrawOp.Oval -> op.copy(cx = op.cx + dx, cy = op.cy + dy)
            is VanDrawOp.RoundRect -> op.copy(cx = op.cx + dx, cy = op.cy + dy)
            is VanDrawOp.Arc -> op.copy(cx = op.cx + dx, cy = op.cy + dy)
            is VanDrawOp.PathOp -> op.copy(
                segments = op.segments.map { seg ->
                    when (seg) {
                        is VanPathSeg.MoveTo -> seg.copy(x = seg.x + dx, y = seg.y + dy)
                        is VanPathSeg.LineTo -> seg.copy(x = seg.x + dx, y = seg.y + dy)
                        is VanPathSeg.QuadTo -> seg.copy(
                            cx = seg.cx + dx,
                            cy = seg.cy + dy,
                            x = seg.x + dx,
                            y = seg.y + dy,
                        )
                        VanPathSeg.Close -> seg
                    }
                },
            )
        }
    }
}

/** Applies the status desaturation/dimming pass to a group of character ops. */
fun List<VanDrawOp>.muted(desaturation: Float, dim: Float): List<VanDrawOp> {
    if (desaturation <= 0f && dim >= 1f) return this
    return map { op ->
        val next = VanColors.scaleAlpha(VanColors.desaturate(op.color, desaturation), dim)
        when (op) {
            is VanDrawOp.Circle -> op.copy(color = next)
            is VanDrawOp.Oval -> op.copy(color = next)
            is VanDrawOp.RoundRect -> op.copy(color = next)
            is VanDrawOp.PathOp -> op.copy(color = next)
            is VanDrawOp.Arc -> op.copy(color = next)
        }
    }
}

class VanPathBuilder {
    private val segments = mutableListOf<VanPathSeg>()

    fun moveTo(x: Float, y: Float) = apply { segments += VanPathSeg.MoveTo(x, y) }

    fun lineTo(x: Float, y: Float) = apply { segments += VanPathSeg.LineTo(x, y) }

    fun quadTo(cx: Float, cy: Float, x: Float, y: Float) = apply {
        segments += VanPathSeg.QuadTo(cx, cy, x, y)
    }

    fun close() = apply { segments += VanPathSeg.Close }

    fun build(): List<VanPathSeg> = segments.toList()
}

fun vanPath(block: VanPathBuilder.() -> Unit): List<VanPathSeg> =
    VanPathBuilder().apply(block).build()
