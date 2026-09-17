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
) {
    val transition = rememberInfiniteTransition(label = "van-minimized-life")
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(5_200, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "van-minimized-phase",
    )
    val palette = VanStatusPalette.forState(state.resolvedSemanticState)
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
            color = Color(0xFFA9764E),
            topLeft = Offset(faceCenter.x - faceRx * 1.11f, faceCenter.y - faceRy * 0.18f),
            size = Size(faceRx * 2.22f, faceRy * 0.45f),
        )
        drawOval(
            color = Color(0xFFA9764E),
            topLeft = Offset(faceCenter.x - faceRx, faceCenter.y - faceRy),
            size = Size(faceRx * 2f, faceRy * 2f),
        )
        drawOval(
            color = Color(0xFF8A5C3A).copy(alpha = 0.30f),
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
        drawPath(hair, Color(0xFFE9EAF0))
        val hairShadow = Path().apply {
            moveTo(center.x - d * 0.25f, center.y - d * 0.15f)
            quadraticBezierTo(center.x, center.y - d * 0.31f, center.x + d * 0.27f, center.y - d * 0.16f)
            quadraticBezierTo(center.x + d * 0.14f, center.y - d * 0.17f, center.x - d * 0.25f, center.y - d * 0.15f)
            close()
        }
        drawPath(hairShadow, Color(0xFFC2C7D3))

        // Eyes remain blue and readable under the transparent cyan visor.
        val eyeY = center.y + d * 0.015f
        val eyeOpen = (1f - blink).coerceIn(0.08f, 1f)
        val gaze = state.attentionX.coerceIn(-1f, 1f) * d * 0.012f
        listOf(-1f, 1f).forEach { side ->
            val eyeX = center.x + side * d * 0.105f
            drawOval(
                color = Color(0xFFF2F6FA),
                topLeft = Offset(eyeX - d * 0.040f, eyeY - d * 0.026f * eyeOpen),
                size = Size(d * 0.080f, d * 0.052f * eyeOpen),
            )
            drawCircle(
                color = Color(0xFF1E88E5),
                radius = d * 0.021f * eyeOpen,
                center = Offset(eyeX + gaze, eyeY),
            )
            drawCircle(
                color = Color(0xFF10233A),
                radius = d * 0.010f * eyeOpen,
                center = Offset(eyeX + gaze, eyeY),
            )
        }

        // Cyan transparent visor; the face itself remains opaque.
        drawRoundRect(
            color = Color(0xFF00E5FF).copy(alpha = 0.22f),
            topLeft = Offset(center.x - d * 0.245f, center.y - d * 0.055f),
            size = Size(d * 0.49f, d * 0.16f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(d * 0.045f),
        )
        drawRoundRect(
            color = Color(0xFF62EAF7).copy(alpha = 0.74f),
            topLeft = Offset(center.x - d * 0.245f, center.y - d * 0.055f),
            size = Size(d * 0.49f, d * 0.16f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(d * 0.045f),
            style = Stroke(width = (d * 0.013f).coerceAtLeast(1f)),
        )

        // Small dark headband/temple anchors keep the portrait recognisably VAN.
        drawCircle(Color(0xFF101720), d * 0.035f, Offset(center.x - d * 0.275f, center.y + d * 0.005f))
        drawCircle(Color(0xFF101720), d * 0.035f, Offset(center.x + d * 0.275f, center.y + d * 0.005f))
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
