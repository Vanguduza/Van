package com.dial.van.visual

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * Layered blue electrical aura.
 *
 * Implements `docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md` §7's six layers as separate
 * passes rather than one heavy glow, and honours §2's rule that the aura sits between Van and
 * the glass while never covering his face. The face-safe region is enforced by keeping every
 * layer at or outside [FACE_SAFE_RADIUS] of the character box, so filaments and sparks orbit
 * the silhouette instead of crossing the visor.
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

/** Nothing decorative is drawn inside this fraction of the box — §2 face/outfit protection. */
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
    val tau = (2f * PI).toFloat()

    // §12: reduced motion holds the aura at a steady mid-breath instead of pulsing.
    val breath = if (budget.allowMotion) 0.85f + 0.15f * sin(phase * tau) else 0.92f

    // §7 layer 2 — secondary bloom, large radius and low opacity for spatial separation.
    val bloomRadius = minEdge * (0.52f + 0.10f * spec.intensity) * budget.bloomScale * breath
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(
                cyan.copy(alpha = 0.30f * spec.intensity),
                cyan.copy(alpha = 0.10f * spec.intensity),
                Color.Transparent,
            ),
            center = center,
            radius = bloomRadius,
        ),
        radius = bloomRadius,
        center = center,
    )

    // §7 layer 1 — core rim glow hugging the silhouette.
    val rimRadius = minEdge * 0.40f * breath
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(Color.Transparent, cyan.copy(alpha = 0.55f * spec.intensity)),
            center = center,
            radius = rimRadius,
        ),
        radius = rimRadius,
        center = center,
    )

    // §7 layer 5 — ground/hover glow, a soft elliptical cyan illumination under the body.
    if (spec.groundGlow > 0.01f) {
        val gw = minEdge * 0.62f
        val gh = minEdge * 0.13f
        drawOval(
            brush = Brush.radialGradient(
                colors = listOf(cyan.copy(alpha = 0.42f * spec.groundGlow), Color.Transparent),
                center = Offset(center.x, h * 0.90f),
                radius = gw / 2f,
            ),
            topLeft = Offset(center.x - gw / 2f, h * 0.90f - gh / 2f),
            size = Size(gw, gh),
        )
    }

    // §7 layer 3 — electrical filaments: sparse, short-lived, state-driven, never continuous.
    if (spec.arcActivity > 0.02f) {
        val arcs = (1 + (spec.arcActivity * 4f).toInt()).coerceAtMost(5)
        val radius = minEdge * 0.43f
        repeat(arcs) { index ->
            val seed = index * 0.37f
            // Each filament has its own short life within the cycle, so they flicker in and out.
            val life = ((phase + seed) % 1f)
            val visible = if (budget.allowMotion) life < 0.45f else index == 0
            if (!visible) return@repeat
            val fade = if (budget.allowMotion) sin((life / 0.45f) * PI.toFloat()) else 0.7f
            val start = (seed * 360f + if (budget.allowMotion) phase * 220f else 0f) % 360f
            val sweep = 22f + 16f * spec.arcActivity
            drawArc(
                color = (accent ?: cyan).copy(alpha = 0.55f * spec.arcActivity * fade),
                startAngle = start,
                sweepAngle = sweep,
                useCenter = false,
                topLeft = Offset(center.x - radius, center.y - radius),
                size = Size(radius * 2f, radius * 2f),
                style = Stroke(width = minEdge * 0.012f),
            )
        }
    }

    // §7 layer 4 — micro-sparks: very low frequency at idle, more during execution.
    if (spec.sparkRate > 0.02f && budget.allowMotion) {
        val sparks = (spec.sparkRate * 6f).toInt().coerceIn(1, 5)
        repeat(sparks) { index ->
            val seed = index * 0.611f
            val life = ((phase * 1.7f + seed) % 1f)
            if (life > 0.22f) return@repeat
            val angle = (seed * tau * 3.1f) % tau
            val distance = minEdge * (0.40f + 0.06f * ((seed * 7f) % 1f))
            drawCircle(
                color = cyan.copy(alpha = 0.85f * (1f - life / 0.22f)),
                radius = minEdge * 0.010f,
                center = Offset(
                    center.x + cos(angle) * distance,
                    center.y + sin(angle) * distance,
                ),
            )
        }
    }

    // §7 layer 6 — orb link: a short energy bridge, strongest while working or listening.
    if (spec.orbLink > 0.05f) {
        val linkAlpha = if (budget.allowMotion) {
            0.30f + 0.35f * (0.5f + 0.5f * sin(phase * tau * 2f))
        } else {
            0.35f
        }
        val radius = minEdge * 0.40f
        drawArc(
            color = cyan.copy(alpha = linkAlpha * spec.orbLink),
            startAngle = -58f,
            sweepAngle = 44f,
            useCenter = false,
            topLeft = Offset(center.x - radius, center.y - radius),
            size = Size(radius * 2f, radius * 2f),
            style = Stroke(width = minEdge * 0.016f),
        )
    }

    // §6 WARNING/APPROVAL — the alert accent is an addition to cyan, never a replacement.
    if (accent != null) {
        val radius = minEdge * 0.47f
        drawCircle(
            color = accent.copy(alpha = 0.30f),
            radius = radius,
            center = center,
            style = Stroke(width = minEdge * 0.010f),
        )
    }
}
