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
    framing: VanFraming = VanFraming.FULL_BODY,
) {
    Canvas(modifier = modifier) {
        drawVanAura(
            spec = spec,
            phase = phase,
            budget = budget,
            characterScale = characterScale,
            semanticSpec = semanticSpec,
            framing = framing,
        )
    }
}

const val FACE_SAFE_RADIUS = 0.34f

/**
 * P1-VIS-001 — the aura is described once and executed twice.
 *
 * This function used to hold the shipping aura's numbers, and `GlassPainter.drawAura` in the
 * JVM evidence renderer held a hand-written second copy of them. They drifted: the evidence
 * renderer never drew electrical branches at all, used roughly double the Zone A alpha and
 * 1.5x the radius, placed the haze blobs differently, and gave ion fragments no bloom. Every
 * piece of committed visual evidence was therefore a picture of something VAN does not look
 * like.
 *
 * So neither painter owns those numbers now. [VanAuraPlanner.plan] produces the ops and this
 * is the Compose executor for them; `GlassPainter` is the Java2D executor for the same ops.
 * A painter cannot diverge on a value it does not have.
 */
fun DrawScope.drawVanAura(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    characterScale: Float = 1f,
    semanticSpec: VanAuraSpec = spec,
    bodyEdgeDp: Float? = null,
    framing: VanFraming = VanFraming.FULL_BODY,
) {
    val minEdge = minOf(size.width, size.height)
    if (minEdge <= 0f) return
    val bodyEdge = minEdge * characterScale.coerceIn(0.40f, 1f)
    val center = Offset(size.width / 2f, size.height * 0.48f)
    drawAuraOps(
        VanAuraPlanner.plan(
            spec = spec,
            semanticSpec = semanticSpec,
            centerX = center.x,
            centerY = center.y,
            radius = bodyEdge / 2f,
            budget = budget,
            phase = phase,
            bodyEdgeDp = bodyEdgeDp,
            framing = framing,
            // The avatar is centred in the box; the field sits 2% higher by design.
            characterCenterY = size.height / 2f,
        ),
    )
}

/** The Compose executor for [VanAuraOp]. Knows how to draw; decides nothing. */
fun DrawScope.drawAuraOps(ops: List<VanAuraOp>) {
    for (op in ops) {
        when (op) {
            is VanAuraOp.Radial -> drawRadialOp(op)
            is VanAuraOp.Polyline -> drawPolylineOp(op)
            is VanAuraOp.Dot -> drawDotOp(op)
            is VanAuraOp.Quad -> drawQuadOp(op)
            is VanAuraOp.Flame -> drawFlameOp(op)
        }
    }
}

private fun DrawScope.drawRadialOp(op: VanAuraOp.Radial) {
    if (op.radius <= 0f || op.alpha <= 0.001f) return
    val color = Color(op.color).copy(alpha = op.alpha)
    val brush = Brush.radialGradient(
        colors = listOf(color, Color.Transparent),
        center = Offset(op.cx, op.cy),
        radius = op.radius,
    )
    if (op.clip.isEmpty()) {
        drawCircle(brush = brush, radius = op.radius, center = Offset(op.cx, op.cy))
    } else {
        drawPath(path = op.clip.toComposePath(), brush = brush)
    }
}

private fun DrawScope.drawPolylineOp(op: VanAuraOp.Polyline) {
    if (op.points.size < 2 || op.alpha <= 0.001f) return
    val path = Path().apply {
        op.points.forEachIndexed { index, point ->
            if (index == 0) moveTo(point.x, point.y) else lineTo(point.x, point.y)
        }
    }
    val color = Color(op.color)
    drawPath(
        path = path,
        color = color.copy(alpha = minOf(op.alpha * op.glowAlphaScale, op.glowAlphaCeiling)),
        style = Stroke(op.glowWidth, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
    val core = op.whiteCoreWidth
    if (core != null) {
        drawPath(
            path = path,
            color = Color.White.copy(alpha = op.whiteCoreAlpha),
            style = Stroke(core, cap = StrokeCap.Round, join = StrokeJoin.Round),
        )
    }
    drawPath(
        path = path,
        color = color.copy(alpha = op.alpha),
        style = Stroke(op.width, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
}

private fun DrawScope.drawDotOp(op: VanAuraOp.Dot) {
    if (op.radius <= 0f || op.alpha <= 0.001f) return
    val color = Color(op.color)
    drawCircle(
        color = color.copy(alpha = op.alpha * op.bloomAlphaScale),
        radius = op.radius * op.bloomRadiusScale,
        center = Offset(op.cx, op.cy),
    )
    drawCircle(color = color.copy(alpha = op.alpha), radius = op.radius, center = Offset(op.cx, op.cy))
}

private fun DrawScope.drawFlameOp(op: VanAuraOp.Flame) {
    if (op.path.isEmpty() || op.gradientRadius <= 0f || op.alpha <= 0.001f) return
    val color = Color(op.color)
    val brush = Brush.radialGradient(
        0f to color.copy(alpha = op.alpha),
        VanFlameAura.FLAME_SOLID_STOP_FRACTION to color.copy(alpha = op.alpha),
        1f to color.copy(alpha = op.alpha * VanFlameAura.FLAME_TIP_ALPHA_FRACTION),
        center = Offset(op.gradientX, op.gradientY),
        radius = op.gradientRadius,
    )
    drawPath(path = op.path.toComposePath(), brush = brush)
}

private fun DrawScope.drawQuadOp(op: VanAuraOp.Quad) {
    if (op.alpha <= 0.001f) return
    val path = Path().apply {
        moveTo(op.startX, op.startY)
        quadraticBezierTo(op.controlX, op.controlY, op.endX, op.endY)
    }
    drawPath(
        path = path,
        color = Color(op.color).copy(alpha = op.alpha),
        style = Stroke(width = op.width, cap = StrokeCap.Round),
    )
}

private fun List<VanPathSeg>.toComposePath(): Path = Path().apply {
    for (segment in this@toComposePath) {
        when (segment) {
            is VanPathSeg.MoveTo -> moveTo(segment.x, segment.y)
            is VanPathSeg.LineTo -> lineTo(segment.x, segment.y)
            is VanPathSeg.QuadTo -> quadraticBezierTo(segment.cx, segment.cy, segment.x, segment.y)
            VanPathSeg.Close -> close()
        }
    }
}

internal fun normalizedEllipseDistance(point: Offset, center: Offset, rx: Float, ry: Float): Float {
    if (rx <= 0f || ry <= 0f) return Float.POSITIVE_INFINITY
    val nx = (point.x - center.x) / rx
    val ny = (point.y - center.y) / ry
    return sqrt(nx * nx + ny * ny)
}
