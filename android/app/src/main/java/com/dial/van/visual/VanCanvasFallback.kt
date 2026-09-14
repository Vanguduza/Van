package com.dial.van.visual

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import java.io.IOException

/**
 * Canvas fallback painter drawing canonical Van silhouette cues:
 * silver hair, cyan visor, cyan orb companion.
 */
@Composable
fun VanAvatar(state: VanVisualState, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val riveAvailable = rememberRiveAvailable(context)
    if (riveAvailable) {
        VanRiveAvatar(state = state, modifier = modifier)
    } else {
        VanCanvasAvatar(state = state, modifier = modifier)
    }
}

@Composable
private fun rememberRiveAvailable(context: android.content.Context): Boolean {
    return try {
        context.assets.open(RiveBindingContract.ASSET_FILE).close()
        true
    } catch (_: IOException) {
        false
    }
}

@Composable
fun VanCanvasAvatar(state: VanVisualState, modifier: Modifier = Modifier) {
    val hairColor = Color(0xFFE8E8F0)
    val skinColor = Color(0xFF8D5524)
    val visorColor = Color(0x9900E5FF)
    val visorStroke = Color(0xFF00E5FF)
    val jacketColor = Color(0xFF1A1A1A)
    val orbColor = Color(0xFF00E5FF)
    val urgencyTint = Color(0xFFFF5252).copy(alpha = state.urgency.coerceIn(0f, 1f) * 0.4f)

    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        val cx = w / 2f
        val headR = w * 0.22f

        // Jacket shoulders
        drawRoundRect(
            color = jacketColor,
            topLeft = Offset(w * 0.2f, h * 0.55f),
            size = Size(w * 0.6f, h * 0.35f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(12f, 12f),
        )

        // Neck
        drawRect(color = skinColor, topLeft = Offset(cx - headR * 0.35f, h * 0.48f), size = Size(headR * 0.7f, h * 0.1f))

        // Face
        drawCircle(color = skinColor, radius = headR, center = Offset(cx, h * 0.38f))

        // Silver swept hair
        val hairPath = Path().apply {
            moveTo(cx - headR * 1.1f, h * 0.28f)
            quadraticBezierTo(cx - headR * 0.2f, h * 0.05f, cx + headR * 1.2f, h * 0.22f)
            lineTo(cx + headR * 0.9f, h * 0.42f)
            quadraticBezierTo(cx, h * 0.18f, cx - headR * 1.0f, h * 0.42f)
            close()
        }
        drawPath(hairPath, hairColor)

        // Cyan visor band
        drawRoundRect(
            color = visorColor,
            topLeft = Offset(cx - headR * 0.85f, h * 0.32f),
            size = Size(headR * 1.7f, headR * 0.45f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(headR * 0.2f, headR * 0.2f),
        )
        drawRoundRect(
            color = visorStroke,
            topLeft = Offset(cx - headR * 0.85f, h * 0.32f),
            size = Size(headR * 1.7f, headR * 0.45f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(headR * 0.2f, headR * 0.2f),
            style = Stroke(width = 2f),
        )

        // Mouth cue from speech sync
        if (state.speaking || state.mouthOpen > 0.05f) {
            val openH = headR * 0.15f * state.mouthOpen.coerceIn(0f, 1f)
            drawOval(
                color = Color(0xFF442211),
                topLeft = Offset(cx - headR * 0.15f, h * 0.42f),
                size = Size(headR * 0.3f, openH.coerceAtLeast(2f)),
            )
        }

        // Cyan holographic orb companion
        val orbR = w * 0.08f
        val orbX = cx + headR * 1.3f + state.attentionX * orbR
        val orbY = h * 0.35f + state.attentionY * orbR
        drawCircle(color = orbColor.copy(alpha = 0.35f), radius = orbR * 1.4f, center = Offset(orbX, orbY))
        drawCircle(color = orbColor, radius = orbR, center = Offset(orbX, orbY))
        drawCircle(color = Color.White.copy(alpha = 0.6f), radius = orbR * 0.25f, center = Offset(orbX - orbR * 0.3f, orbY - orbR * 0.3f))

        if (state.durableState == VanDurableState.DEGRADED || state.durableState == VanDurableState.WARNING) {
            drawCircle(color = urgencyTint, radius = w * 0.48f, center = Offset(cx, h * 0.45f))
        }
    }
}
