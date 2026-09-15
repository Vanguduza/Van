package com.dial.van.visual

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
 * silver hair, blue eyes, cyan visor, cyan orb companion.
 * Rive asset/runtime failures always fall back here (fail closed on visual).
 */
@Composable
fun VanAvatar(state: VanVisualState, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    var useRive by remember {
        mutableStateOf(
            try {
                context.assets.open(RiveBindingContract.ASSET_FILE).close()
                true
            } catch (_: IOException) {
                false
            },
        )
    }
    if (useRive) {
        VanRiveAvatar(
            state = state,
            modifier = modifier,
            onLoadFailed = { useRive = false },
        )
    } else {
        VanCanvasAvatar(state = state, modifier = modifier)
    }
}

@Composable
fun VanCanvasAvatar(state: VanVisualState, modifier: Modifier = Modifier) {
    val hairColor = Color(0xFFE8E8F0)
    val skinColor = Color(0xFF8D5524)
    val eyeColor = Color(0xFF1E88E5)
    val visorColor = Color(0x9900E5FF)
    val visorStroke = Color(0xFF00E5FF)
    val jacketColor = Color(0xFF1A1A1A)
    val orbColor = Color(0xFF00E5FF)
    val urgencyTint = Color(0xFFFF5252).copy(alpha = state.urgency.coerceIn(0f, 1f) * 0.4f)
    val offlineDim = if (state.durableState == VanDurableState.OFFLINE) 0.45f else 1f

    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        val cx = w / 2f
        val headR = w * 0.22f

        // Jacket shoulders
        drawRoundRect(
            color = jacketColor.copy(alpha = offlineDim),
            topLeft = Offset(w * 0.2f, h * 0.55f),
            size = Size(w * 0.6f, h * 0.35f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(12f, 12f),
        )

        // Neck
        drawRect(
            color = skinColor.copy(alpha = offlineDim),
            topLeft = Offset(cx - headR * 0.35f, h * 0.48f),
            size = Size(headR * 0.7f, h * 0.1f),
        )

        // Face
        drawCircle(color = skinColor.copy(alpha = offlineDim), radius = headR, center = Offset(cx, h * 0.38f))

        // Silver swept hair
        val hairPath = Path().apply {
            moveTo(cx - headR * 1.1f, h * 0.28f)
            quadraticBezierTo(cx - headR * 0.2f, h * 0.05f, cx + headR * 1.2f, h * 0.22f)
            lineTo(cx + headR * 0.9f, h * 0.42f)
            quadraticBezierTo(cx, h * 0.18f, cx - headR * 1.0f, h * 0.42f)
            close()
        }
        drawPath(hairPath, hairColor.copy(alpha = offlineDim))

        // Blue eyes (under visor cues)
        val eyeY = h * 0.36f
        val eyeR = headR * 0.08f
        drawCircle(color = eyeColor.copy(alpha = offlineDim), radius = eyeR, center = Offset(cx - headR * 0.35f, eyeY))
        drawCircle(color = eyeColor.copy(alpha = offlineDim), radius = eyeR, center = Offset(cx + headR * 0.35f, eyeY))
        drawCircle(color = Color.White.copy(alpha = 0.7f * offlineDim), radius = eyeR * 0.35f, center = Offset(cx - headR * 0.38f, eyeY - eyeR * 0.25f))
        drawCircle(color = Color.White.copy(alpha = 0.7f * offlineDim), radius = eyeR * 0.35f, center = Offset(cx + headR * 0.32f, eyeY - eyeR * 0.25f))

        // Cyan visor band
        drawRoundRect(
            color = visorColor.copy(alpha = offlineDim),
            topLeft = Offset(cx - headR * 0.85f, h * 0.32f),
            size = Size(headR * 1.7f, headR * 0.45f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(headR * 0.2f, headR * 0.2f),
        )
        drawRoundRect(
            color = visorStroke.copy(alpha = offlineDim),
            topLeft = Offset(cx - headR * 0.85f, h * 0.32f),
            size = Size(headR * 1.7f, headR * 0.45f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(headR * 0.2f, headR * 0.2f),
            style = Stroke(width = 2f),
        )

        // Mouth cue from speech sync
        if (state.speaking || state.mouthOpen > 0.05f) {
            val openH = headR * 0.15f * state.mouthOpen.coerceIn(0f, 1f)
            drawOval(
                color = Color(0xFF442211).copy(alpha = offlineDim),
                topLeft = Offset(cx - headR * 0.15f, h * 0.42f),
                size = Size(headR * 0.3f, openH.coerceAtLeast(2f)),
            )
        }

        // Cyan holographic orb companion
        val orbR = w * 0.08f
        val orbX = cx + headR * 1.3f + state.attentionX * orbR
        val orbY = h * 0.35f + state.attentionY * orbR
        val orbAlpha = if (state.durableState == VanDurableState.OFFLINE) 0.2f else 1f
        drawCircle(color = orbColor.copy(alpha = 0.35f * orbAlpha), radius = orbR * 1.4f, center = Offset(orbX, orbY))
        drawCircle(color = orbColor.copy(alpha = orbAlpha), radius = orbR, center = Offset(orbX, orbY))
        drawCircle(color = Color.White.copy(alpha = 0.6f * orbAlpha), radius = orbR * 0.25f, center = Offset(orbX - orbR * 0.3f, orbY - orbR * 0.3f))

        when (state.durableState) {
            VanDurableState.DEGRADED, VanDurableState.WARNING, VanDurableState.URGENT -> {
                drawCircle(color = urgencyTint, radius = w * 0.48f, center = Offset(cx, h * 0.45f))
            }
            VanDurableState.OFFLINE -> {
                drawCircle(color = Color(0xFF607D8B).copy(alpha = 0.25f), radius = w * 0.48f, center = Offset(cx, h * 0.45f))
            }
            else -> Unit
        }
    }
}
