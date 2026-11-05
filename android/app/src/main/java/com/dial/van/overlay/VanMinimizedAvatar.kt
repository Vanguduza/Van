package com.dial.van.overlay

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanMinimizedExpressionMap
import com.dial.van.visual.VanSmallMouth
import com.dial.van.visual.VanScene
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.rememberReducedMotion
import com.dial.van.visual.vanMotionEnabled
import com.dial.van.visual.VanStatusPalette
import com.dial.van.visual.VanVisualState
import kotlin.math.PI
import kotlin.math.sin

/**
 * Quiet live portrait used only when the owner minimizes floating VAN.
 * The face deliberately occupies most of the circle; this is not a generic status bubble.
 */
@Composable
fun VanMinimizedAvatar(
    state: VanVisualState,
    modifier: Modifier = Modifier.size(64.dp),
    animate: Boolean = true,
    budget: VanEffectBudget = VanEffectBudget.FULL,
    reducedMotion: Boolean = rememberReducedMotion(),
) {
    val enabled = vanMotionEnabled(budget, animate = animate, reducedMotion = reducedMotion)
    val phase = if (enabled) {
        val transition = rememberInfiniteTransition(label = "van-minimized-life")
        val animatedPhase by transition.animateFloat(
            initialValue = 0f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(
                animation = tween(5_200, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
            label = "van-minimized-phase",
        )
        animatedPhase
    } else {
        0f
    }
    val palette = VanStatusPalette.forState(state.resolvedSemanticState)
    val expression = VanMinimizedExpressionMap.from(state)
    val blink = blinkAmount(phase)
    val rimPulse = 0.38f + 0.14f * sin(phase * (2f * PI).toFloat())

    Canvas(modifier = modifier) {
        val d = size.minDimension
        val center = Offset(size.width / 2f, size.height / 2f)
        val radius = d * 0.48f

        // Optical shell, separate from the solid portrait.
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color(VanGlassTokens.TINT_NAVY).copy(alpha = 0.96f),
                    Color(VanGlassTokens.TINT_DEEP).copy(alpha = 0.99f),
                ),
                center = center,
                radius = radius,
            ),
            radius = radius,
            center = center,
        )
        drawCircle(
            color = Color(palette.accent).copy(alpha = rimPulse.coerceIn(0.24f, 0.62f)),
            radius = radius - d * 0.018f,
            center = center,
            style = Stroke(width = (d * 0.028f).coerceAtLeast(1.5f)),
        )

        val faceCenter = Offset(center.x, center.y + d * 0.045f)
        val faceRx = d * 0.255f
        val faceRy = d * 0.285f

        // Ears + solid medium-brown face.
        drawOval(
            color = Color(VanScene.SKIN.toInt()),
            topLeft = Offset(faceCenter.x - faceRx * 1.11f, faceCenter.y - faceRy * 0.18f),
            size = Size(faceRx * 2.22f, faceRy * 0.45f),
        )
        drawOval(
            color = Color(VanScene.SKIN.toInt()),
            topLeft = Offset(faceCenter.x - faceRx, faceCenter.y - faceRy),
            size = Size(faceRx * 2f, faceRy * 2f),
        )
        drawOval(
            color = Color(VanScene.SKIN_SHADOW.toInt()).copy(alpha = 0.30f),
            topLeft = Offset(faceCenter.x - faceRx * 0.88f, faceCenter.y + faceRy * 0.18f),
            size = Size(faceRx * 1.76f, faceRy * 0.76f),
        )

        // Swept silver-white hair: large enough to remain the first identity cue at launcher scale.
        val hair = Path().apply {
            moveTo(center.x - d * 0.30f, center.y - d * 0.14f)
            quadraticBezierTo(center.x - d * 0.18f, center.y - d * 0.40f, center.x + d * 0.22f, center.y - d * 0.31f)
            quadraticBezierTo(center.x + d * 0.36f, center.y - d * 0.25f, center.x + d * 0.25f, center.y - d * 0.04f)
            quadraticBezierTo(center.x + d * 0.10f, center.y - d * 0.18f, center.x - d * 0.30f, center.y - d * 0.14f)
            close()
        }
        drawPath(hair, Color(VanScene.HAIR.toInt()))
        val hairShadow = Path().apply {
            moveTo(center.x - d * 0.25f, center.y - d * 0.15f)
            quadraticBezierTo(center.x, center.y - d * 0.31f, center.x + d * 0.27f, center.y - d * 0.16f)
            quadraticBezierTo(center.x + d * 0.14f, center.y - d * 0.17f, center.x - d * 0.25f, center.y - d * 0.15f)
            close()
        }
        drawPath(hairShadow, Color(VanScene.HAIR_SHADOW.toInt()))

        // Independent brow expression shows real owner/task urgency without
        // changing Candidate B's approved face, hair or visor geometry.
        val browY = center.y - d * 0.065f
        listOf(-1f, 1f).forEach { side ->
            val eyeX = center.x + side * d * 0.105f
            drawLine(
                color = Color(VanScene.BROW.toInt()),
                start = Offset(eyeX + side * d * 0.038f, browY),
                end = Offset(eyeX - side * d * 0.038f, browY - expression.browLift * d * 0.022f),
                strokeWidth = (d * 0.017f).coerceAtLeast(1f),
            )
        }

        // Eyes remain blue and readable under the transparent cyan visor.
        val eyeY = center.y + d * 0.015f
        val eyeOpen = ((1f - blink) * (1f - 0.55f * expression.eyeNarrow)).coerceIn(0.08f, 1f)
        val gaze = state.attentionX.coerceIn(-1f, 1f) * d * 0.012f
        val gazeVertical = state.attentionY.coerceIn(-1f, 1f) * d * 0.012f
        listOf(-1f, 1f).forEach { side ->
            val eyeX = center.x + side * d * 0.105f
            drawOval(
                color = Color(VanScene.EYE_SCLERA.toInt()),
                topLeft = Offset(eyeX - d * 0.040f, eyeY - d * 0.026f * eyeOpen),
                size = Size(d * 0.080f, d * 0.052f * eyeOpen),
            )
            drawCircle(
                color = Color(VanScene.EYE_IRIS.toInt()),
                radius = d * 0.021f * eyeOpen,
                center = Offset(eyeX + gaze, eyeY + gazeVertical),
            )
            drawCircle(
                color = Color(0xFF10233A),
                radius = d * 0.010f * eyeOpen,
                center = Offset(eyeX + gaze, eyeY + gazeVertical),
            )
        }

        // Cyan transparent visor; the face itself remains opaque.
        drawRoundRect(
            color = Color(VanScene.VISOR.toInt()).copy(alpha = 0.22f),
            topLeft = Offset(center.x - d * 0.245f, center.y - d * 0.055f),
            size = Size(d * 0.49f, d * 0.16f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(d * 0.045f),
        )
        drawRoundRect(
            color = Color(VanScene.VISOR_FRAME.toInt()).copy(alpha = 0.74f),
            topLeft = Offset(center.x - d * 0.245f, center.y - d * 0.055f),
            size = Size(d * 0.49f, d * 0.16f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(d * 0.045f),
            style = Stroke(width = (d * 0.013f).coerceAtLeast(1f)),
        )

        // Small-scale face-only articulation while the production M2 rig is pending.
        // Drawn below the visor; no borrowed expressive character or new identity layer.
        val mouthColor = Color(VanScene.MOUTH.toInt())
        val mouthY = center.y + d * 0.175f
        val mouthStroke = Stroke(width = (d * 0.018f).coerceAtLeast(1f))
        when (expression.mouth) {
            VanSmallMouth.NEUTRAL -> drawLine(
                color = mouthColor,
                start = Offset(center.x - d * 0.030f, mouthY),
                end = Offset(center.x + d * 0.030f, mouthY),
                strokeWidth = mouthStroke.width,
            )
            VanSmallMouth.SMILE, VanSmallMouth.CONCERN -> drawArc(
                color = mouthColor,
                startAngle = if (expression.mouth == VanSmallMouth.SMILE) 0f else 180f,
                sweepAngle = 180f,
                useCenter = false,
                topLeft = Offset(center.x - d * 0.048f, mouthY - d * 0.027f),
                size = Size(d * 0.096f, d * 0.060f),
                style = mouthStroke,
            )
            VanSmallMouth.SPEECH -> {
                val widthScale = when (expression.viseme) {
                    2 -> 0.060f
                    3 -> 0.050f
                    4 -> 0.038f
                    else -> 0.032f
                }
                val w = d * widthScale
                val h = d * (0.012f + 0.075f * expression.speechOpening)
                drawOval(
                    color = mouthColor,
                    topLeft = Offset(center.x - w * 0.5f, mouthY - h * 0.5f),
                    size = Size(w, h),
                )
            }
        }
    }
}

private fun blinkAmount(phase: Float): Float {
    // Two short deterministic blink windows per long cycle; otherwise the portrait is calm.
    fun window(center: Float, halfWidth: Float): Float {
        val distance = kotlin.math.abs(phase - center)
        if (distance >= halfWidth) return 0f
        return sin(((halfWidth - distance) / halfWidth) * (PI / 2.0)).toFloat()
    }
    return maxOf(window(0.41f, 0.018f), window(0.79f, 0.016f)).coerceIn(0f, 1f)
}
