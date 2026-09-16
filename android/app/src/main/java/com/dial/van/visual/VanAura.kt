package com.dial.van.visual

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import kotlin.math.PI
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Three-zone living refractive aura.
 *
 * Zone A is the quiet identity presence. Zone B and Zone C consume the renderer-neutral
 * [VanFieldGeometryEngine], which is also used by the JVM evidence painter. This prevents the
 * shipping Compose field and owner-facing boards from drifting into different topologies.
 */
@Composable
fun VanAuraLayer(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    modifier: Modifier = Modifier,
    characterScale: Float = 1f,
) {
    Canvas(modifier = modifier) { drawVanAura(spec, phase, budget, characterScale) }
}

const val FACE_SAFE_RADIUS = 0.34f
private const val TAU = (2.0 * PI).toFloat()

fun DrawScope.drawVanAura(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    characterScale: Float = 1f,
) {
    val minEdge = minOf(size.width, size.height)
    if (minEdge <= 0f || spec.intensity <= 0.01f) return

    val bodyEdge = minEdge * characterScale.coerceIn(0.40f, 1f)
    val center = Offset(size.width / 2f, size.height * 0.48f)
    val cyan = Color(VanGlassTokens.ACCENT_CYAN)
    val semantic = Color(spec.semanticColor ?: VanGlassTokens.ACCENT_CYAN)
    val motion = VanWindFieldMotion.sample(spec, phase, budget)

    drawZoneA(spec, motion, center, bodyEdge, cyan)

    val geometry = VanFieldGeometryEngine.build(
        spec = spec,
        phase = phase,
        budget = budget,
        bodyEdge = bodyEdge,
        centerX = center.x,
        centerY = center.y,
    )

    geometry.strokes.forEach { stroke ->
        val color = if (stroke.ink == VanFieldInk.IDENTITY) cyan else semantic
        val path = Path().apply {
            stroke.points.forEachIndexed { index, point ->
                if (index == 0) moveTo(point.x, point.y) else lineTo(point.x, point.y)
            }
        }
        drawPath(
            path = path,
            color = color.copy(alpha = stroke.alpha * 0.16f),
            style = Stroke(
                width = stroke.glowWidth,
                cap = StrokeCap.Round,
                join = StrokeJoin.Round,
            ),
        )
        drawPath(
            path = path,
            color = color.copy(alpha = stroke.alpha),
            style = Stroke(
                width = stroke.width,
                cap = StrokeCap.Round,
                join = StrokeJoin.Round,
            ),
        )
    }

    geometry.dots.forEach { dot ->
        val color = if (dot.ink == VanFieldInk.IDENTITY) cyan else semantic
        drawCircle(
            color = color.copy(alpha = dot.alpha),
            radius = dot.radius,
            center = Offset(dot.point.x, dot.point.y),
        )
    }

    // Orb link remains a local identity detail rather than part of semantic Zone C topology.
    if (spec.orbLink > 0.05f) {
        val pulse = 0.24f + 0.30f * motion.electricPulse
        val path = Path().apply {
            moveTo(center.x + bodyEdge * 0.11f, center.y - bodyEdge * 0.04f)
            quadraticBezierTo(
                center.x + bodyEdge * 0.25f,
                center.y - bodyEdge * 0.17f,
                center.x + bodyEdge * 0.35f,
                center.y - bodyEdge * 0.10f,
            )
        }
        drawPath(
            path = path,
            color = cyan.copy(alpha = pulse * spec.orbLink),
            style = Stroke(width = (bodyEdge * 0.011f).coerceAtLeast(1.1f), cap = StrokeCap.Round),
        )
    }
}

private fun DrawScope.drawZoneA(
    spec: VanAuraSpec,
    motion: VanWindFieldFrame,
    center: Offset,
    bodyEdge: Float,
    cyan: Color,
) {
    val alpha = (0.10f + 0.08f * spec.intensity).coerceIn(0.08f, 0.18f)
    val r = bodyEdge * 0.20f * VanAuraSpec.INNER_RADIUS_SCALE * motion.breathing
    val driftX = bodyEdge * 0.025f * sin(TAU * motion.phase)
    val driftY = bodyEdge * 0.018f * sin(TAU * 2f * motion.phase + 0.9f)

    val first = Offset(center.x - bodyEdge * 0.05f + driftX, center.y + bodyEdge * 0.02f + driftY)
    val second = Offset(center.x + bodyEdge * 0.07f - driftX * 0.6f, center.y - bodyEdge * 0.04f - driftY)

    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(cyan.copy(alpha = alpha * 0.82f), Color.Transparent),
            center = first,
            radius = r,
        ),
        radius = r,
        center = first,
    )
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(cyan.copy(alpha = alpha * 0.50f), Color.Transparent),
            center = second,
            radius = r * 0.70f,
        ),
        radius = r * 0.70f,
        center = second,
    )

    if (spec.groundGlow > 0.01f) {
        val gy = center.y + bodyEdge * 0.41f
        val gw = bodyEdge * 0.31f
        val crescent = Path().apply {
            moveTo(center.x - gw, gy)
            quadraticBezierTo(center.x, gy + bodyEdge * 0.060f, center.x + gw, gy)
            quadraticBezierTo(center.x, gy - bodyEdge * 0.018f, center.x - gw, gy)
            close()
        }
        drawPath(
            path = crescent,
            brush = Brush.radialGradient(
                colors = listOf(cyan.copy(alpha = 0.18f * spec.groundGlow), Color.Transparent),
                center = Offset(center.x, gy),
                radius = gw,
            ),
        )
    }
}

/** Retained for acceptance tests that verify body detachment mathematically. */
internal fun normalizedEllipseDistance(point: Offset, center: Offset, rx: Float, ry: Float): Float {
    if (rx <= 0f || ry <= 0f) return Float.POSITIVE_INFINITY
    val nx = (point.x - center.x) / rx
    val ny = (point.y - center.y) / ry
    return sqrt(nx * nx + ny * ny)
}
