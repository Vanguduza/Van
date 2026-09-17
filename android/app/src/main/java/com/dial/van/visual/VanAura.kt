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
 * Three-zone living windy electrical atmosphere.
 *
 * Zone A is a very restrained identity haze, Zone B is activity-cyan, and Zone C independently
 * carries semantic truth. Main geometry and electrical events are produced by the shared
 * renderer-neutral geometry engine, so device and evidence topology cannot silently diverge.
 */
@Composable
fun VanAuraLayer(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    modifier: Modifier = Modifier,
    characterScale: Float = 1f,
    semanticSpec: VanAuraSpec = spec,
) {
    Canvas(modifier = modifier) {
        drawVanAura(
            spec = spec,
            phase = phase,
            budget = budget,
            characterScale = characterScale,
            semanticSpec = semanticSpec,
        )
    }
}

const val FACE_SAFE_RADIUS = 0.34f
private const val TAU = (2.0 * PI).toFloat()

fun DrawScope.drawVanAura(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    characterScale: Float = 1f,
    semanticSpec: VanAuraSpec = spec,
) {
    val minEdge = minOf(size.width, size.height)
    if (minEdge <= 0f || (spec.intensity <= 0.01f && semanticSpec.intensity <= 0.01f)) return

    val bodyEdge = minEdge * characterScale.coerceIn(0.40f, 1f)
    val center = Offset(size.width / 2f, size.height * 0.48f)
    val cyan = Color(VanGlassTokens.ACCENT_CYAN)
    val semantic = Color(semanticSpec.semanticColor ?: VanGlassTokens.ACCENT_CYAN)
    val motion = VanWindFieldMotion.sample(spec, phase, budget)

    drawZoneA(spec, motion, center, bodyEdge, cyan)

    val geometry = VanFieldGeometryEngine.build(
        spec = spec,
        phase = phase,
        budget = budget,
        bodyEdge = bodyEdge,
        centerX = center.x,
        centerY = center.y,
        semanticSpec = semanticSpec,
    )

    geometry.strokes.forEach { stroke ->
        val color = if (stroke.ink == VanFieldInk.IDENTITY) cyan else semantic
        val path = stroke.toPath()
        drawPath(
            path = path,
            color = color.copy(alpha = (stroke.alpha * 0.20f).coerceAtMost(0.18f)),
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

    geometry.electricalBranches.forEach { branch ->
        val color = if (branch.ink == VanFieldInk.IDENTITY) cyan else semantic
        drawElectricalPolyline(branch.trunk, color, branch.alpha, branch.width, branch.glowWidth)
        branch.children.forEach { child ->
            drawElectricalPolyline(
                child,
                color,
                branch.alpha * 0.82f,
                branch.width * 0.78f,
                branch.glowWidth * 0.72f,
            )
        }
    }

    geometry.dots.forEach { dot ->
        val color = if (dot.ink == VanFieldInk.IDENTITY) cyan else semantic
        // Ion fragments receive a small bloom so motion remains legible on bright apps.
        drawCircle(
            color = color.copy(alpha = dot.alpha * 0.16f),
            radius = dot.radius * 2.8f,
            center = Offset(dot.point.x, dot.point.y),
        )
        drawCircle(
            color = color.copy(alpha = dot.alpha),
            radius = dot.radius,
            center = Offset(dot.point.x, dot.point.y),
        )
    }

    if (spec.orbLink > 0.05f) {
        val pulse = 0.18f + 0.34f * motion.electricPulse
        val path = Path().apply {
            moveTo(center.x + bodyEdge * 0.18f, center.y - bodyEdge * 0.03f)
            quadraticBezierTo(
                center.x + bodyEdge * 0.30f,
                center.y - bodyEdge * 0.19f,
                center.x + bodyEdge * 0.39f,
                center.y - bodyEdge * 0.12f,
            )
        }
        drawPath(
            path = path,
            color = cyan.copy(alpha = pulse * spec.orbLink),
            style = Stroke(width = (bodyEdge * 0.009f).coerceAtLeast(1f), cap = StrokeCap.Round),
        )
    }
}

private fun VanFieldStroke.toPath(): Path = Path().apply {
    points.forEachIndexed { index, point ->
        if (index == 0) moveTo(point.x, point.y) else lineTo(point.x, point.y)
    }
}

private fun DrawScope.drawElectricalPolyline(
    points: List<VanFieldPoint>,
    color: Color,
    alpha: Float,
    width: Float,
    glowWidth: Float,
) {
    if (points.size < 2 || alpha <= 0.01f) return
    val path = Path().apply {
        points.forEachIndexed { index, point ->
            if (index == 0) moveTo(point.x, point.y) else lineTo(point.x, point.y)
        }
    }
    drawPath(
        path = path,
        color = color.copy(alpha = (alpha * 0.20f).coerceAtMost(0.22f)),
        style = Stroke(glowWidth, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
    drawPath(
        path = path,
        color = Color.White.copy(alpha = (alpha * 0.62f).coerceAtMost(0.82f)),
        style = Stroke((width * 0.48f).coerceAtLeast(0.55f), cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
    drawPath(
        path = path,
        color = color.copy(alpha = alpha.coerceAtMost(0.92f)),
        style = Stroke(width, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
}

/**
 * Identity haze only. It must not form a body outline; the visible atmosphere is carried by
 * detached Zone B/C streams. Two displaced low-alpha blobs keep VAN optically tied to his field.
 */
private fun DrawScope.drawZoneA(
    spec: VanAuraSpec,
    motion: VanWindFieldFrame,
    center: Offset,
    bodyEdge: Float,
    cyan: Color,
) {
    val alpha = (0.045f + 0.045f * spec.intensity).coerceIn(0.035f, 0.085f)
    val r = bodyEdge * 0.13f * motion.breathing
    val driftX = bodyEdge * 0.032f * sin(TAU * motion.phase)
    val driftY = bodyEdge * 0.022f * sin(TAU * 2f * motion.phase + 0.9f)

    val first = Offset(
        center.x - bodyEdge * 0.31f + driftX,
        center.y + bodyEdge * 0.05f + driftY,
    )
    val second = Offset(
        center.x + bodyEdge * 0.34f - driftX * 0.6f,
        center.y - bodyEdge * 0.09f - driftY,
    )

    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(cyan.copy(alpha = alpha), Color.Transparent),
            center = first,
            radius = r,
        ),
        radius = r,
        center = first,
    )
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(cyan.copy(alpha = alpha * 0.72f), Color.Transparent),
            center = second,
            radius = r * 0.78f,
        ),
        radius = r * 0.78f,
        center = second,
    )

    if (spec.groundGlow > 0.01f) {
        val gy = center.y + bodyEdge * 0.47f
        val gw = bodyEdge * 0.28f
        val crescent = Path().apply {
            moveTo(center.x - gw, gy)
            quadraticBezierTo(center.x, gy + bodyEdge * 0.045f, center.x + gw, gy)
            quadraticBezierTo(center.x, gy - bodyEdge * 0.012f, center.x - gw, gy)
            close()
        }
        drawPath(
            path = crescent,
            brush = Brush.radialGradient(
                colors = listOf(cyan.copy(alpha = 0.13f * spec.groundGlow), Color.Transparent),
                center = Offset(center.x, gy),
                radius = gw,
            ),
        )
    }
}

internal fun normalizedEllipseDistance(point: Offset, center: Offset, rx: Float, ry: Float): Float {
    if (rx <= 0f || ry <= 0f) return Float.POSITIVE_INFINITY
    val nx = (point.x - center.x) / rx
    val ny = (point.y - center.y) / ry
    return sqrt(nx * nx + ny * ny)
}
