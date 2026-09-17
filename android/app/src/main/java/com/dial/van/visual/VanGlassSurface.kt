package com.dial.van.visual

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import kotlin.math.min

/**
 * Optical glass used only for VAN's interface surfaces.
 *
 * Rev 3 keeps a deep absorber for readability, then introduces a baby-cyan optical body,
 * local specular/refraction and fine grain. The character renderer is deliberately not nested
 * inside this material by the floating surface composition.
 */
@Composable
fun VanGlassSurface(
    style: VanGlassStyle,
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit,
) {
    val shape = RoundedCornerShape(style.cornerRadiusDp.dp)
    val absorber = Color(VanGlassTokens.TINT_NAVY)
    val babyCyan = Color(VanGlassTokens.BABY_CYAN)
    val iceCyan = Color(VanGlassTokens.ICE_CYAN)
    val edge = Color(style.borderColor)

    Box(
        modifier = modifier
            .shadow(style.elevationDp.dp, shape, clip = false)
            .clip(shape)
            .drawBehind {
                val radius = CornerRadius(style.cornerRadiusDp.dp.toPx())

                // Readability absorber. This belongs to the board, never to VAN's body.
                drawRoundRect(
                    color = absorber.copy(alpha = style.backgroundAlpha),
                    cornerRadius = radius,
                )

                // Baby-cyan optical body. Concentrated on the character-facing/top-left side.
                drawRoundRect(
                    brush = Brush.linearGradient(
                        colors = listOf(
                            babyCyan.copy(alpha = style.cyanTintAlpha),
                            Color(VanGlassTokens.STRUCTURAL_CYAN).copy(alpha = style.cyanTintAlpha * 0.52f),
                            Color.Transparent,
                        ),
                        start = Offset.Zero,
                        end = Offset(size.width * 0.92f, size.height * 0.82f),
                    ),
                    cornerRadius = radius,
                )

                // Optical shaping rather than a uniform glowing border.
                drawRoundRect(
                    brush = Brush.verticalGradient(
                        colors = listOf(
                            iceCyan.copy(alpha = 0.055f + style.innerHighlightAlpha * 0.32f),
                            Color.Transparent,
                            Color.Black.copy(alpha = 0.12f),
                        ),
                    ),
                    cornerRadius = radius,
                )

                if (style.grainAlpha > 0f) {
                    val step = (size.minDimension / 28f).coerceAtLeast(3f)
                    var gy = step
                    var row = 0
                    while (gy < size.height) {
                        var gx = step * (0.4f + (row % 3) * 0.2f)
                        while (gx < size.width) {
                            val jitter = ((gx.toInt() * 13 + gy.toInt() * 7) % 5) - 2f
                            drawCircle(
                                color = Color.White.copy(alpha = style.grainAlpha),
                                radius = 0.6f,
                                center = Offset(gx + jitter, gy),
                            )
                            gx += step
                        }
                        gy += step
                        row++
                    }
                }

                if (style.innerHighlightAlpha > 0f) {
                    drawRoundRect(
                        brush = Brush.linearGradient(
                            colors = listOf(
                                iceCyan.copy(alpha = style.innerHighlightAlpha),
                                Color.Transparent,
                            ),
                            start = Offset.Zero,
                            end = Offset(size.width * 0.55f, size.height * 0.42f),
                        ),
                        cornerRadius = radius,
                    )
                }

                if (style.contaminationAlpha > 0f) {
                    drawRoundRect(
                        brush = Brush.radialGradient(
                            colors = listOf(
                                edge.copy(alpha = style.contaminationAlpha),
                                Color.Transparent,
                            ),
                            center = Offset(size.width * 0.12f, size.height * 0.45f),
                            radius = size.maxDimension * 0.55f,
                        ),
                        cornerRadius = radius,
                    )
                }

                if (style.structuralEdgeAlpha > 0f) {
                    drawRoundRect(
                        color = edge.copy(alpha = style.structuralEdgeAlpha),
                        cornerRadius = radius,
                        style = Stroke(width = style.borderWidthDp.dp.toPx()),
                    )
                }

                if (style.specularAlpha > 0f) {
                    val inset = min(size.minDimension * 0.04f, 8f)
                    val arcSize = Size(
                        (size.width - inset * 2f).coerceAtLeast(1f),
                        (size.height - inset * 2f).coerceAtLeast(1f),
                    )
                    drawArc(
                        color = iceCyan.copy(alpha = style.specularAlpha),
                        startAngle = 200f,
                        sweepAngle = 78f,
                        useCenter = false,
                        topLeft = Offset(inset, inset),
                        size = arcSize,
                        style = Stroke(
                            width = style.borderWidthDp.dp.toPx() * 1.6f,
                            cap = StrokeCap.Round,
                        ),
                    )
                    if (style.activeGlowAlpha > 0f) {
                        drawArc(
                            color = edge.copy(alpha = style.activeGlowAlpha),
                            startAngle = 208f,
                            sweepAngle = 52f,
                            useCenter = false,
                            topLeft = Offset(inset, inset),
                            size = arcSize,
                            style = Stroke(
                                width = style.borderWidthDp.dp.toPx() * 2.2f,
                                cap = StrokeCap.Round,
                            ),
                        )
                    }
                }
            },
        content = content,
    )
}

/** Full-bleed Command Centre optical backing. */
@Composable
fun VanGlassBackdrop(style: VanGlassStyle, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .drawBehind {
                drawRect(Color(VanGlassTokens.TINT_DEEP).copy(alpha = style.backgroundAlpha))
                drawRect(Color(VanGlassTokens.BABY_CYAN).copy(alpha = style.cyanTintAlpha * 0.35f))
            },
    )
}
