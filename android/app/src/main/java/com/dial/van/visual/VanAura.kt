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
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Three-zone living refractive aura (Rev 2.3 living-field implementation).
 *
 * Zone A — inner identity presence, always identity cyan and deliberately quiet.
 * Zone B — detached windy interaction field: travelling ribbons, ion fragments and pulses.
 * Zone C — sparse outer semantic field. State colour lives here, never on VAN's body.
 *
 * The field is not an orbit and never paints a circular halo. Every visible strand follows a
 * directional flow line and is cut away inside the body-safe ellipse. The same deterministic
 * phase can therefore animate owner art, Canvas Van and the future Rive artboard consistently.
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
    val motion = VanWindFieldMotion.sample(spec, phase, budget)
    val midRadius = bodyEdge * 0.42f * VanAuraSpec.MID_RADIUS_SCALE * motion.fieldScale

    drawZoneA(spec, motion, center, bodyEdge, cyan)
    drawZoneB(spec, motion, budget, center, bodyEdge, midRadius, cyan)
    drawZoneC(spec, motion, budget, center, bodyEdge, midRadius)
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

    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(cyan.copy(alpha = alpha * 0.82f), Color.Transparent),
            center = Offset(center.x - bodyEdge * 0.05f + driftX, center.y + bodyEdge * 0.02f + driftY),
            radius = r,
        ),
        radius = r,
        center = Offset(center.x - bodyEdge * 0.05f + driftX, center.y + bodyEdge * 0.02f + driftY),
    )
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(cyan.copy(alpha = alpha * 0.50f), Color.Transparent),
            center = Offset(center.x + bodyEdge * 0.07f - driftX * 0.6f, center.y - bodyEdge * 0.04f - driftY),
            radius = r * 0.70f,
        ),
        radius = r * 0.70f,
        center = Offset(center.x + bodyEdge * 0.07f - driftX * 0.6f, center.y - bodyEdge * 0.04f - driftY),
    )

    // A small refractive ground crescent anchors VAN without becoming a circular plate.
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

private fun DrawScope.drawZoneB(
    spec: VanAuraSpec,
    motion: VanWindFieldFrame,
    budget: VanEffectBudget,
    center: Offset,
    bodyEdge: Float,
    midRadius: Float,
    cyan: Color,
) {
    val wind = Offset(cos(motion.windAngleRad), sin(motion.windAngleRad))
    val normal = Offset(-wind.y, wind.x)
    val safeRx = bodyEdge * FACE_SAFE_RADIUS * 1.08f
    val safeRy = bodyEdge * 0.43f

    if (spec.filamentCount > 0 && spec.arcActivity > 0.01f) {
        val count = spec.filamentCount.coerceIn(1, 5)
        repeat(count) { index ->
            val seed = seed01(index, spec.intensity + spec.deformation)
            val side = if (index % 2 == 0) -1f else 1f
            val tier = 0.34f + (index / 2) * 0.19f
            val lateral = side * midRadius * tier
            val longitudinal = (seed - 0.5f) * midRadius * 0.32f
            val length = midRadius * (1.75f + 0.48f * motion.windStrength + seed * 0.18f)
            val amplitude = midRadius * (0.10f + 0.17f * motion.waveAmplitude) * (0.82f + seed * 0.28f)
            val alpha = (0.25f + spec.arcActivity * 0.34f).coerceIn(0.24f, 0.66f)

            drawFlowRibbon(
                center = center,
                wind = wind,
                normal = normal,
                length = length,
                lateralOffset = lateral,
                longitudinalOffset = longitudinal,
                amplitude = amplitude,
                phase = motion.phase,
                seed = seed,
                turbulence = motion.turbulence,
                safeRx = safeRx,
                safeRy = safeRy,
                color = cyan,
                alpha = alpha,
                coreWidth = (bodyEdge * 0.0105f).coerceAtLeast(1.1f),
                glowWidth = (bodyEdge * 0.032f).coerceAtLeast(2.4f),
                allowMotion = budget.allowMotion,
            )
        }
    }

    drawAdvectedParticles(
        spec = spec,
        motion = motion,
        budget = budget,
        center = center,
        wind = wind,
        normal = normal,
        radius = midRadius,
        safeRx = safeRx,
        safeRy = safeRy,
        color = cyan,
        bodyEdge = bodyEdge,
    )

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

private fun DrawScope.drawZoneC(
    spec: VanAuraSpec,
    motion: VanWindFieldFrame,
    budget: VanEffectBudget,
    center: Offset,
    bodyEdge: Float,
    midRadius: Float,
) {
    val segments = spec.segmentsForBudget(budget)
    if (segments.isEmpty()) return

    val scale = spec.envelopeRadiusScale.coerceIn(
        VanAuraSpec.MIN_ENVELOPE_SCALE,
        VanAuraSpec.MAX_ENVELOPE_SCALE,
    )
    val outerRadius = midRadius * scale
    val ink = Color(spec.semanticColor ?: VanGlassTokens.ACCENT_CYAN)
    val baseAlpha = spec.envelopeAlpha.coerceIn(0.05f, 0.22f)
    val wind = Offset(cos(motion.windAngleRad), sin(motion.windAngleRad))
    val normal = Offset(-wind.y, wind.x)
    val safeRx = bodyEdge * 0.52f
    val safeRy = bodyEdge * 0.56f

    segments.forEachIndexed { index, segment ->
        val angle = Math.toRadians(segment.startDeg.toDouble()).toFloat()
        val seed = seed01(index + 11, segment.startDeg * 0.017f + segment.sweepDeg * 0.011f)
        val side = if (sin(angle) >= 0f) 1f else -1f
        val lateral = side * outerRadius * (0.54f + 0.16f * abs(sin(angle)))
        val longitudinal = cos(angle) * outerRadius * 0.24f
        val length = outerRadius * (1.00f + segment.sweepDeg.coerceIn(20f, 110f) / 220f)
        val amplitude = outerRadius * (0.075f + 0.12f * motion.waveAmplitude)
        val semanticBoost = if (spec.semanticColor != null) 1.0f else 0.68f

        drawFlowRibbon(
            center = center,
            wind = wind,
            normal = normal,
            length = length,
            lateralOffset = lateral,
            longitudinalOffset = longitudinal,
            amplitude = amplitude,
            phase = motion.phase,
            seed = seed,
            turbulence = motion.turbulence * 0.85f,
            safeRx = safeRx,
            safeRy = safeRy,
            color = ink,
            alpha = baseAlpha * semanticBoost,
            coreWidth = (bodyEdge * 0.008f).coerceAtLeast(1f),
            glowWidth = (bodyEdge * 0.026f).coerceAtLeast(2.0f),
            allowMotion = budget.allowMotion,
        )

        if (segment.node || segments.size == 1) {
            val nodeProgress = (0.20f + seed * 0.62f + motion.particleAdvection * 0.18f) % 1f
            val node = flowPoint(
                center = center,
                wind = wind,
                normal = normal,
                length = length,
                lateralOffset = lateral,
                longitudinalOffset = longitudinal,
                amplitude = amplitude,
                progress = nodeProgress,
                phase = motion.phase,
                seed = seed,
                turbulence = motion.turbulence,
            )
            if (!insideEllipse(node, center, safeRx, safeRy)) {
                val r = (bodyEdge * (0.010f + 0.006f * motion.electricPulse)).coerceAtLeast(1.2f)
                drawCircle(
                    color = ink.copy(alpha = (baseAlpha + 0.12f).coerceAtMost(0.34f)),
                    radius = r,
                    center = node,
                )
            }
        }
    }

    // Semantic states gain a sparse electrical branch; cyan identity states remain softer.
    if (spec.semanticColor != null && spec.sparkRate > 0.02f) {
        val seed = spec.envelopeSegments.first().startDeg * 0.013f
        val branchCenter = point(
            center,
            wind,
            normal,
            along = outerRadius * (0.08f + 0.16f * sin(TAU * motion.phase)),
            across = outerRadius * if (seed >= 0f) 0.72f else -0.72f,
        )
        drawElectricBranch(
            origin = branchCenter,
            wind = wind,
            normal = normal,
            length = outerRadius * 0.34f,
            phase = motion.phase,
            color = ink,
            alpha = (baseAlpha + 0.10f * motion.electricPulse).coerceAtMost(0.34f),
            width = (bodyEdge * 0.007f).coerceAtLeast(1f),
        )
    }
}

private fun DrawScope.drawFlowRibbon(
    center: Offset,
    wind: Offset,
    normal: Offset,
    length: Float,
    lateralOffset: Float,
    longitudinalOffset: Float,
    amplitude: Float,
    phase: Float,
    seed: Float,
    turbulence: Float,
    safeRx: Float,
    safeRy: Float,
    color: Color,
    alpha: Float,
    coreWidth: Float,
    glowWidth: Float,
    allowMotion: Boolean,
) {
    val path = Path()
    var openSubPath = false
    val steps = 28
    repeat(steps + 1) { i ->
        val u = i / steps.toFloat()
        val p = flowPoint(
            center = center,
            wind = wind,
            normal = normal,
            length = length,
            lateralOffset = lateralOffset,
            longitudinalOffset = longitudinalOffset,
            amplitude = amplitude,
            progress = u,
            phase = phase,
            seed = seed,
            turbulence = turbulence,
            allowMotion = allowMotion,
        )
        if (insideEllipse(p, center, safeRx, safeRy)) {
            openSubPath = false
        } else if (!openSubPath) {
            path.moveTo(p.x, p.y)
            openSubPath = true
        } else {
            path.lineTo(p.x, p.y)
        }
    }

    drawPath(
        path = path,
        color = color.copy(alpha = alpha * 0.16f),
        style = Stroke(width = glowWidth, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
    drawPath(
        path = path,
        color = color.copy(alpha = alpha),
        style = Stroke(width = coreWidth, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
}

private fun flowPoint(
    center: Offset,
    wind: Offset,
    normal: Offset,
    length: Float,
    lateralOffset: Float,
    longitudinalOffset: Float,
    amplitude: Float,
    progress: Float,
    phase: Float,
    seed: Float,
    turbulence: Float,
    allowMotion: Boolean = true,
): Offset {
    val u = progress.coerceIn(0f, 1f)
    val moving = if (allowMotion) 1f else 0f
    val envelope = sin(PI.toFloat() * u).coerceAtLeast(0f)
    val wave1 = sin(TAU * (2f * u - 2f * phase * moving + seed))
    val wave2 = sin(TAU * (3f * u + 3f * phase * moving + seed * 1.71f))
    val wave3 = sin(TAU * (5f * u - phase * moving + seed * 0.47f))
    val wave = (wave1 + wave2 * 0.38f + wave3 * 0.14f) * amplitude * (0.58f + 0.42f * envelope)
    val curl = sin(TAU * (u + phase * moving + seed * 0.31f)) * amplitude * turbulence * 0.34f
    val along = (u - 0.5f) * length + longitudinalOffset + curl
    val across = lateralOffset + wave
    return point(center, wind, normal, along, across)
}

private fun DrawScope.drawAdvectedParticles(
    spec: VanAuraSpec,
    motion: VanWindFieldFrame,
    budget: VanEffectBudget,
    center: Offset,
    wind: Offset,
    normal: Offset,
    radius: Float,
    safeRx: Float,
    safeRy: Float,
    color: Color,
    bodyEdge: Float,
) {
    if (spec.sparkRate <= 0.015f) return
    val count = (2 + spec.sparkRate * 8f * budget.filamentScale).toInt().coerceIn(2, 8)
    repeat(count) { index ->
        val seed = seed01(index + 31, spec.sparkRate + spec.intensity)
        val progress = if (budget.allowMotion) {
            (motion.particleAdvection * (0.65f + seed * 0.70f) + seed) % 1f
        } else {
            seed
        }
        val side = if (index % 2 == 0) -1f else 1f
        val lateral = side * radius * (0.30f + 0.46f * seed)
        val p = flowPoint(
            center = center,
            wind = wind,
            normal = normal,
            length = radius * (1.55f + motion.windStrength * 0.35f),
            lateralOffset = lateral,
            longitudinalOffset = 0f,
            amplitude = radius * (0.06f + motion.waveAmplitude * 0.08f),
            progress = progress,
            phase = motion.phase,
            seed = seed,
            turbulence = motion.turbulence,
            allowMotion = budget.allowMotion,
        )
        if (insideEllipse(p, center, safeRx, safeRy)) return@repeat

        val alpha = (0.28f + 0.52f * motion.electricPulse) * (0.45f + 0.55f * spec.sparkRate)
        val streak = bodyEdge * (0.018f + 0.020f * motion.windStrength)
        drawLine(
            color = color.copy(alpha = alpha.coerceIn(0.12f, 0.78f)),
            start = Offset(p.x - wind.x * streak, p.y - wind.y * streak),
            end = Offset(p.x + wind.x * streak * 0.22f, p.y + wind.y * streak * 0.22f),
            strokeWidth = (bodyEdge * 0.006f).coerceAtLeast(1f),
            cap = StrokeCap.Round,
        )
        drawCircle(
            color = color.copy(alpha = (alpha * 0.70f).coerceAtMost(0.62f)),
            radius = (bodyEdge * 0.006f).coerceAtLeast(0.8f),
            center = p,
        )
    }
}

private fun DrawScope.drawElectricBranch(
    origin: Offset,
    wind: Offset,
    normal: Offset,
    length: Float,
    phase: Float,
    color: Color,
    alpha: Float,
    width: Float,
) {
    val path = Path().apply {
        moveTo(origin.x, origin.y)
        repeat(4) { index ->
            val u = (index + 1) / 4f
            val jitter = sin(TAU * (phase * 3f + index * 0.37f)) * length * 0.08f
            val p = point(
                origin,
                wind,
                normal,
                along = length * u,
                across = jitter,
            )
            lineTo(p.x, p.y)
        }
    }
    drawPath(
        path = path,
        color = color.copy(alpha = alpha),
        style = Stroke(width = width, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
}

private fun point(
    center: Offset,
    wind: Offset,
    normal: Offset,
    along: Float,
    across: Float,
): Offset = Offset(
    x = center.x + wind.x * along + normal.x * across,
    y = center.y + wind.y * along + normal.y * across,
)

private fun insideEllipse(point: Offset, center: Offset, rx: Float, ry: Float): Boolean {
    if (rx <= 0f || ry <= 0f) return false
    val nx = (point.x - center.x) / rx
    val ny = (point.y - center.y) / ry
    return nx * nx + ny * ny < 1f
}

/** Cheap deterministic hash in 0..1; avoids Random so previews remain bit-for-bit stable. */
private fun seed01(index: Int, salt: Float): Float {
    val x = sin(index * 12.9898f + salt * 78.233f) * 43758.5453f
    return abs(x - kotlin.math.floor(x)).coerceIn(0f, 1f)
}

/** Kept internal for JVM tests that guard body detachment without depending on Compose pixels. */
internal fun normalizedEllipseDistance(point: Offset, center: Offset, rx: Float, ry: Float): Float {
    if (rx <= 0f || ry <= 0f) return Float.POSITIVE_INFINITY
    val nx = (point.x - center.x) / rx
    val ny = (point.y - center.y) / ry
    return sqrt(nx * nx + ny * ny)
}
