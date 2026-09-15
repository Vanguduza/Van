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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

/**
 * DIAL glass surface.
 *
 * Implements the Compose contract sketched in
 * `docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md` §9, styled by [VanGlassTokens].
 *
 * Live *backdrop* blur is a window-level capability, not a composable one: for the floating
 * overlay it is requested via `WindowManager.LayoutParams.blurBehindRadius` in
 * `FloatingOverlayService`. When that is unavailable this surface applies §10's fallback —
 * a more heavily pre-tinted navy fill that preserves border, radius, depth and glow.
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
                // 3. Tinted glass surface.
                drawRect(color = tint.copy(alpha = style.backgroundAlpha))

                // 4. Glass border and inner highlight — restrained top-left sheen (§3).
                if (style.innerHighlightAlpha > 0f) {
                    drawRect(
                        brush = Brush.linearGradient(
                            colors = listOf(
                                Color.White.copy(alpha = style.innerHighlightAlpha),
                                Color.Transparent,
                            ),
                            start = Offset.Zero,
                            end = Offset(size.width * 0.75f, size.height * 0.75f),
                        ),
                    )
                }

                // Active glow: cyan only, and only around the interactive edge (§3).
                if (style.activeGlowAlpha > 0f) {
                    val inset = size.minDimension * 0.012f
                    drawRoundRect(
                        color = edge.copy(alpha = style.activeGlowAlpha),
                        topLeft = Offset(inset, inset),
                        size = androidx.compose.ui.geometry.Size(
                            size.width - inset * 2f,
                            size.height - inset * 2f,
                        ),
                        cornerRadius = androidx.compose.ui.geometry.CornerRadius(
                            style.cornerRadiusDp.dp.toPx(),
                        ),
                        style = Stroke(width = style.borderWidthDp.dp.toPx() * 2.5f),
                    )
                }

                drawRoundRect(
                    color = edge.copy(alpha = style.borderAlpha),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(
                        style.cornerRadiusDp.dp.toPx(),
                    ),
                    style = Stroke(width = style.borderWidthDp.dp.toPx()),
                )
            },
        content = content,
    )
}

/** Full-bleed glass used as a Command Centre backdrop (§14 top-level material language). */
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
