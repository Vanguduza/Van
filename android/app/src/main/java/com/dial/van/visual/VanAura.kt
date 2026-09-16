package com.dial.van.visual

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * Living refractive aura.
 *
 * Rev 2.1: a deformable field around VAN — not a cyan circle, not a ring, not a plate.
 * Layers: core radiance, outer field, filaments, broken orbital arcs, caustics, ground crescent.
 */
@Composable
fun VanAuraLayer(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier) { drawVanAura(spec, phase, budget) }
}

/** Nothing decorative is drawn inside this fraction of the box — face/outfit protection. */
const val FACE_SAFE_RADIUS = 0.34f

fun DrawScope.drawVanAura(spec: VanAuraSpec, phase: Float, budget: VanEffectBudget) {
    if (spec.intensity <= 0.01f) return

    val w = size.width
    val h = size.height
    val minEdge = minOf(w, h)
    if (minEdge <= 0f) return

    val center = Offset(w / 2f, h * 0.48f)
    val cyan = Color(VanGlassTokens.ACCENT_CYAN)
    val accent = spec.alertAccent?.let { Color(it) }
    val field = accent?.copy(alpha = 1f)?.let { mix(cyan, it, 0.28f) } ?: cyan
    val tau = (2f * PI).toFloat()
    val breath = if (budget.allowMotion) 0.94f + 0.06f * sin(phase * tau) else 1f

    val rx = minEdge * (0.46f + 0.08f * spec.intensity) * spec.fieldAsymmetry.let { 1f + it } * budget.bloomScale * breath
    val ry = minEdge * (0.50f + 0.06f * spec.intensity) * budget.bloomScale * breath

    drawDeformableField(
        center = center,
        rx = rx,
        ry = ry,
        color = field.copy(alpha = 0.08f * spec.intensity),
        spec = spec,
        inner = false,
    )
    drawDeformableField(
        center = center,
        rx = rx * 0.62f,
        ry = ry * 0.58f,
        color = field.copy(alpha = 0.16f * spec.intensity),
        spec = spec,
        inner = true,
    )

    if (spec.groundGlow > 0.01f) {
        val crescent = Path()
        val gy = h * 0.90f
        val gw = minEdge * 0.48f
        crescent.moveTo(center.x - gw, gy)
        crescent.quadraticBezierTo(center.x, gy + minEdge * 0.10f, center.x + gw, gy)
        crescent.quadraticBezierTo(center.x, gy - minEdge * 0.04f, center.x - gw, gy)
        crescent.close()
        drawPath(
            path = crescent,
            brush = Brush.radialGradient(
                colors = listOf(field.copy(alpha = 0.28f * spec.groundGlow), Color.Transparent),
                center = Offset(center.x, gy),
                radius = gw,
            ),
        )
    }

    if (spec.filamentCount > 0 && spec.arcActivity > 0.01f) {
        val count = spec.filamentCount.coerceIn(1, 5)
        repeat(count) { index ->
            val seed = index * 1.17f + spec.intensity
            val life = (phase + seed * 0.13f) % 1f
            val visible = if (budget.allowMotion) life < 0.72f else true
            if (!visible) return@repeat
            val fade = if (budget.allowMotion) {
                sin((life / 0.72f) * PI.toFloat()).coerceAtLeast(0.25f)
            } else {
                0.72f
            }
            val start = (0.55f + index * 0.9f) % tau
            val inner = minEdge * FACE_SAFE_RADIUS * 1.05f
            val outer = minEdge * (0.48f + 0.08f * ((seed * 3f) % 1f))
            val path = Path()
            val x0 = center.x + cos(start) * inner
            val y0 = center.y + sin(start) * inner
            path.moveTo(x0, y0)
            val bend = start + 0.55f + 0.25f * sin(seed)
            path.quadraticBezierTo(
                center.x + cos(bend) * (inner + outer) * 0.48f,
                center.y + sin(bend) * (inner + outer) * 0.42f,
                center.x + cos(start + 0.35f) * outer,
                center.y + sin(start + 0.22f) * outer,
            )
            drawPath(
                path = path,
                color = field.copy(alpha = (0.42f + 0.40f * spec.arcActivity).coerceIn(0.42f, 0.88f) * fade),
                style = Stroke(
                    width = minEdge * 0.018f,
                    cap = StrokeCap.Round,
                    join = StrokeJoin.Round,
                ),
            )
        }
    }

    if (spec.arcActivity > 0.02f) {
        val arcs = (1 + (spec.arcActivity * 3f).toInt()).coerceAtMost(3)
        var remaining = VanAuraSpec.MAX_TOTAL_ARC_DEG
        val ovalRx = minEdge * 0.44f
        val ovalRy = minEdge * 0.50f
        repeat(arcs) { index ->
            if (remaining <= 18f) return@repeat
            val seed = index * 0.41f
            val life = (phase * 0.6f + seed) % 1f
            val visible = if (budget.allowMotion) life < 0.62f else index == 0 || !budget.allowMotion
            if (!visible && budget.allowMotion) return@repeat
            val fade = if (budget.allowMotion) sin((life / 0.62f) * PI.toFloat()).coerceAtLeast(0.3f) else 0.7f
            val sweep = (48f + 38f * spec.arcActivity - index * 12f)
                .coerceAtMost(VanAuraSpec.MAX_ARC_SWEEP_DEG)
                .coerceAtMost(remaining)
            remaining -= sweep
            val start = (index * 118f + 18f + if (budget.allowMotion) phase * 40f else 0f) % 360f
            val inset = index * minEdge * 0.018f
            drawArc(
                color = field.copy(alpha = (0.38f + 0.32f * spec.arcActivity).coerceIn(0.38f, 0.78f) * fade),
                startAngle = start,
                sweepAngle = sweep,
                useCenter = false,
                topLeft = Offset(center.x - ovalRx + inset, center.y - ovalRy - inset * 0.4f),
                size = Size((ovalRx - inset) * 2f, (ovalRy - inset) * 2f),
                style = Stroke(width = minEdge * 0.011f, cap = StrokeCap.Round),
            )
        }
    }

    if (spec.sparkRate > 0.02f && budget.allowMotion) {
        val sparks = (spec.sparkRate * 5f).toInt().coerceIn(1, 4)
        repeat(sparks) { index ->
            val seed = index * 0.611f
            val life = ((phase * 1.7f + seed) % 1f)
            if (life > 0.22f) return@repeat
            val angle = (seed * tau * 3.1f) % tau
            val distance = minEdge * (0.40f + 0.08f * ((seed * 7f) % 1f))
            drawCircle(
                color = field.copy(alpha = 0.70f * (1f - life / 0.22f)),
                radius = minEdge * 0.008f,
                center = Offset(
                    center.x + cos(angle) * distance,
                    center.y + sin(angle) * distance,
                ),
            )
        }
    }

    if (spec.orbLink > 0.05f) {
        val linkAlpha = if (budget.allowMotion) {
            0.28f + 0.22f * (0.5f + 0.5f * sin(phase * tau * 2f))
        } else {
            0.32f
        }
        val path = Path()
        path.moveTo(center.x + minEdge * 0.12f, center.y - minEdge * 0.04f)
        path.quadraticBezierTo(
            center.x + minEdge * 0.28f,
            center.y - minEdge * 0.18f,
            center.x + minEdge * 0.36f,
            center.y - minEdge * 0.10f,
        )
        drawPath(
            path = path,
            color = field.copy(alpha = linkAlpha * spec.orbLink),
            style = Stroke(width = minEdge * 0.014f, cap = StrokeCap.Round),
        )
    }
}

private fun DrawScope.drawDeformableField(
    center: Offset,
    rx: Float,
    ry: Float,
    color: Color,
    spec: VanAuraSpec,
    inner: Boolean,
) {
    val path = Path()
    val n = 14
    for (i in 0..n) {
        val t = i.toFloat() / n
        val ang = t * (2f * PI).toFloat()
        val wobble = 1f +
            spec.deformation * sin(ang * 3f + spec.intensity * 5f + if (inner) 0.8f else 0f) +
            spec.fieldAsymmetry * 0.35f * cos(ang * 2f + 0.6f) +
            0.06f * sin(ang * 5f + spec.arcActivity)
        val x = center.x + cos(ang) * rx * wobble
        val y = center.y + sin(ang) * ry * wobble
        if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
    }
    path.close()
    drawPath(
        path = path,
        brush = Brush.radialGradient(
            colors = listOf(color, color.copy(alpha = color.alpha * 0.35f), Color.Transparent),
            center = center,
            radius = maxOf(rx, ry),
        ),
    )
}

private fun mix(a: Color, b: Color, t: Float): Color = Color(
    red = a.red + (b.red - a.red) * t,
    green = a.green + (b.green - a.green) * t,
    blue = a.blue + (b.blue - a.blue) * t,
    alpha = 1f,
)
