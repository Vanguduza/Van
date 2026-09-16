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
 * Optical glass surface.
 *
 * Rev 2.1 layers: absorptive tint, shaping gradient, grain, inner highlight, structural edge,
 * selective specular, aura contamination. A uniform glowing outline is forbidden.
 *
 * Live backdrop blur is a window-level capability requested by `FloatingOverlayService`.
 * When unavailable this surface keeps shaping, grain and specular on a heavier pre-tint.
 */
@Composable
fun VanGlassSurface(
    style: VanGlassStyle,
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit,
) {
    val shape = RoundedCornerShape(style.cornerRadiusDp.dp)
    val tint = Color(VanGlassTokens.TINT_NAVY)
    val edge = Color(style.borderColor)

    Box(
        modifier = modifier
            .shadow(style.elevationDp.dp, shape, clip = false)
            .clip(shape)
            .drawBehind {
                val radius = CornerRadius(style.cornerRadiusDp.dp.toPx())
                drawRoundRect(color = tint.copy(alpha = style.backgroundAlpha), cornerRadius = radius)

                drawRoundRect(
                    brush = Brush.verticalGradient(
                        colors = listOf(
                            Color.White.copy(alpha = 0.06f * (style.innerHighlightAlpha / 0.11f).coerceIn(0.4f, 1.4f)),
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
                                Color.White.copy(alpha = style.innerHighlightAlpha),
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

                val structural = style.structuralEdgeAlpha
                if (structural > 0f) {
                    drawRoundRect(
                        color = edge.copy(alpha = structural),
                        cornerRadius = radius,
                        style = Stroke(width = style.borderWidthDp.dp.toPx()),
                    )
                }

                val specular = style.specularAlpha
                if (specular > 0f) {
                    val inset = min(size.minDimension * 0.04f, 8f)
                    drawArc(
                        color = Color.White.copy(alpha = specular),
                        startAngle = 200f,
                        sweepAngle = 78f,
                        useCenter = false,
                        topLeft = Offset(inset, inset),
                        size = Size(size.width - inset * 2f, size.height - inset * 2f),
                        style = Stroke(width = style.borderWidthDp.dp.toPx() * 1.6f, cap = StrokeCap.Round),
                    )
                    if (style.activeGlowAlpha > 0f) {
                        drawArc(
                            color = edge.copy(alpha = style.activeGlowAlpha),
                            startAngle = 208f,
                            sweepAngle = 52f,
                            useCenter = false,
                            topLeft = Offset(inset, inset),
                            size = Size(size.width - inset * 2f, size.height - inset * 2f),
                            style = Stroke(width = style.borderWidthDp.dp.toPx() * 2.2f, cap = StrokeCap.Round),
                        )
                    }
                }
            },
        content = content,
    )
}

/** Full-bleed glass used as a Command Centre backdrop. */
@Composable
fun VanGlassBackdrop(style: VanGlassStyle, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .drawBehind {
                drawRect(Color(VanGlassTokens.TINT_NAVY).copy(alpha = style.backgroundAlpha))
            },
    )
}
