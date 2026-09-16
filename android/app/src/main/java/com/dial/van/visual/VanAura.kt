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
 * Three-zone living refractive aura (Rev 2.2).
 *
 * Zone A — inner presence, identity cyan, body-adjacent.
 * Zone B — mid interaction, filaments and working arcs.
 * Zone C — outer semantic envelope, sparse broken orbit, semantic colour only.
 */
@Composable
fun VanAuraLayer(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    modifier: Modifier = Modifier,
    /** Fraction of the canvas occupied by VAN's body. <1 leaves air for Zone C. */
    characterScale: Float = 1f,
) {
    Canvas(modifier = modifier) { drawVanAura(spec, phase, budget, characterScale) }
}

/** Nothing decorative is drawn inside this fraction of the body box — face/outfit protection. */
const val FACE_SAFE_RADIUS = 0.34f

fun DrawScope.drawVanAura(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    characterScale: Float = 1f,
) {
    val w = size.width
    val h = size.height
    val minEdge = minOf(w, h)
    if (minEdge <= 0f) return

    val bodyEdge = minEdge * characterScale.coerceIn(0.40f, 1f)
    val center = Offset(w / 2f, h * 0.48f)
    val cyan = Color(VanGlassTokens.ACCENT_CYAN)
    val tau = (2f * PI).toFloat()
    val midRadius = bodyEdge * 0.44f * VanAuraSpec.MID_RADIUS_SCALE

    drawZoneA(spec, center, bodyEdge, cyan)
    drawZoneB(spec, phase, budget, center, bodyEdge, midRadius, cyan, tau)
    drawZoneC(spec, budget, center, midRadius)
}

private fun DrawScope.drawZoneA(spec: VanAuraSpec, center: Offset, minEdge: Float, cyan: Color) {
    val alpha = (0.12f + 0.08f * spec.intensity).coerceIn(0.08f, 0.20f)
    val r = minEdge * 0.22f * VanAuraSpec.INNER_RADIUS_SCALE
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(cyan.copy(alpha = alpha * 0.85f), Color.Transparent),
            center = Offset(center.x - minEdge * 0.06f, center.y + minEdge * 0.02f),
            radius = r,
        ),
        radius = r,
        center = Offset(center.x - minEdge * 0.06f, center.y + minEdge * 0.02f),
    )
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(cyan.copy(alpha = alpha * 0.55f), Color.Transparent),
            center = Offset(center.x + minEdge * 0.08f, center.y - minEdge * 0.04f),
            radius = r * 0.72f,
        ),
        radius = r * 0.72f,
        center = Offset(center.x + minEdge * 0.08f, center.y - minEdge * 0.04f),
    )
    if (spec.groundGlow > 0.01f) {
        val crescent = Path()
        val gy = center.y + minEdge * 0.42f
        val gw = minEdge * 0.36f
        crescent.moveTo(center.x - gw, gy)
        crescent.quadraticBezierTo(center.x, gy + minEdge * 0.08f, center.x + gw, gy)
        crescent.quadraticBezierTo(center.x, gy - minEdge * 0.03f, center.x - gw, gy)
        crescent.close()
        drawPath(
            path = crescent,
            brush = Brush.radialGradient(
                colors = listOf(cyan.copy(alpha = 0.22f * spec.groundGlow), Color.Transparent),
                center = Offset(center.x, gy),
                radius = gw,
            ),
        )
    }
}

private fun DrawScope.drawZoneB(
    spec: VanAuraSpec,
    phase: Float,
    budget: VanEffectBudget,
    center: Offset,
    minEdge: Float,
    midRadius: Float,
    cyan: Color,
    tau: Float,
) {
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
            val outer = midRadius * (0.92f + 0.08f * ((seed * 3f) % 1f))
            val path = Path()
            path.moveTo(center.x + cos(start) * inner, center.y + sin(start) * inner)
            val bend = start + 0.55f + 0.25f * sin(seed)
            path.quadraticBezierTo(
                center.x + cos(bend) * (inner + outer) * 0.48f,
                center.y + sin(bend) * (inner + outer) * 0.42f,
                center.x + cos(start + 0.35f) * outer,
                center.y + sin(start + 0.22f) * outer,
            )
            drawPath(
                path = path,
                color = cyan.copy(alpha = (0.42f + 0.40f * spec.arcActivity).coerceIn(0.42f, 0.88f) * fade),
                style = Stroke(
                    width = minEdge * 0.016f,
                    cap = StrokeCap.Round,
                    join = StrokeJoin.Round,
                ),
            )
        }
    }

    if (spec.arcActivity > 0.02f) {
        val arcs = (1 + (spec.arcActivity * 3f).toInt()).coerceAtMost(3)
        var remaining = VanAuraSpec.MAX_TOTAL_ARC_DEG
        val ovalRx = midRadius
        val ovalRy = midRadius * (0.82f + spec.fieldAsymmetry)
        repeat(arcs) { index ->
            if (remaining <= 18f) return@repeat
            val seed = index * 0.41f
            val life = (phase * 0.6f + seed) % 1f
            val visible = if (budget.allowMotion) life < 0.62f else true
            if (!visible && budget.allowMotion) return@repeat
            val fade = if (budget.allowMotion) sin((life / 0.62f) * PI.toFloat()).coerceAtLeast(0.3f) else 0.7f
            val sweep = (48f + 38f * spec.arcActivity - index * 12f)
                .coerceAtMost(VanAuraSpec.MAX_ARC_SWEEP_DEG)
                .coerceAtMost(remaining)
            remaining -= sweep
            val start = (index * 118f + 18f + if (budget.allowMotion) phase * 40f else 0f) % 360f
            val inset = index * minEdge * 0.014f
            drawArc(
                color = cyan.copy(alpha = (0.34f + 0.28f * spec.arcActivity).coerceIn(0.34f, 0.70f) * fade),
                startAngle = start,
                sweepAngle = sweep,
                useCenter = false,
                topLeft = Offset(center.x - ovalRx + inset, center.y - ovalRy - inset * 0.4f),
                size = Size((ovalRx - inset) * 2f, (ovalRy - inset) * 2f),
                style = Stroke(width = minEdge * 0.010f, cap = StrokeCap.Round),
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
            val distance = midRadius * (0.78f + 0.08f * ((seed * 7f) % 1f))
            drawCircle(
                color = cyan.copy(alpha = 0.70f * (1f - life / 0.22f)),
                radius = minEdge * 0.008f,
                center = Offset(center.x + cos(angle) * distance, center.y + sin(angle) * distance),
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
            color = cyan.copy(alpha = linkAlpha * spec.orbLink),
            style = Stroke(width = minEdge * 0.014f, cap = StrokeCap.Round),
        )
    }
}

private fun DrawScope.drawZoneC(spec: VanAuraSpec, budget: VanEffectBudget, center: Offset, midRadius: Float) {
    val segments = spec.segmentsForBudget(budget)
    if (segments.isEmpty()) return
    val scale = spec.envelopeRadiusScale.coerceIn(VanAuraSpec.MIN_ENVELOPE_SCALE, VanAuraSpec.MAX_ENVELOPE_SCALE)
    val rx = midRadius * scale * (1.05f + spec.fieldAsymmetry * 0.35f)
    val ry = midRadius * scale * 0.86f
    val ink = Color(spec.semanticColor ?: VanGlassTokens.ACCENT_CYAN)
    val alpha = spec.envelopeAlpha.coerceIn(0.05f, 0.22f)
    val stroke = (midRadius * 0.055f).coerceAtLeast(1.6f)
    segments.forEach { segment ->
        drawArc(
            color = ink.copy(alpha = alpha),
            startAngle = segment.startDeg,
            sweepAngle = segment.sweepDeg.coerceAtMost(VanAuraSpec.MAX_ARC_SWEEP_DEG),
            useCenter = false,
            topLeft = Offset(center.x - rx, center.y - ry),
            size = Size(rx * 2f, ry * 2f),
            style = Stroke(width = stroke, cap = StrokeCap.Round),
        )
        if (segment.node || spec.envelopeSegments.size == 1) {
            val rad = Math.toRadians(segment.startDeg.toDouble())
            drawCircle(
                color = ink.copy(alpha = (alpha + 0.12f).coerceAtMost(0.32f)),
                radius = stroke * 0.85f,
                center = Offset(
                    center.x + cos(rad).toFloat() * rx,
                    center.y + sin(rad).toFloat() * ry,
                ),
            )
        }
    }
}
