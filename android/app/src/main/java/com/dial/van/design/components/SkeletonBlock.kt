package com.dial.van.design.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import com.dial.van.design.LocalVanTokens

/**
 * DNA §5: "LOADING (skeleton matching final geometry)." Callers size this to the shape of the
 * real content it stands in for — a `MetricTile`-sized block, a row-height block for a list —
 * rather than one generic spinner, so layout does not jump when data arrives.
 *
 * The shimmer is an animated gradient position, not alpha pulsing: at [reducedMotionOverride]
 * `true` (or the theme's own [com.dial.van.design.VanMotion.reducedMotion]) it freezes the
 * gradient at its centre position — still visibly "loading" from its shape and colour, DNA
 * §2's "state changes still communicated by colour/shape," just not moving.
 *
 * Built with `drawWithCache` rather than a fractional [Offset] on the gradient directly: a
 * gradient's start/end are measured in the draw scope's own pixels, so a shimmer position
 * computed as a bare `0f..1f` float has to be multiplied by the actual on-screen size at draw
 * time, not passed to [Brush.linearGradient] as though it already were one.
 */
@Composable
fun SkeletonBlock(
    modifier: Modifier = Modifier,
    cornerRadius: Dp? = null,
    reducedMotionOverride: Boolean? = null,
) {
    val tokens = LocalVanTokens.current
    val reducedMotion = reducedMotionOverride ?: tokens.motion.reducedMotion
    val base = tokens.color.surface2
    val highlight = tokens.color.surface1.copy(alpha = 0.85f)

    val travel: Float = if (reducedMotion) {
        0.5f
    } else {
        val transition = rememberInfiniteTransition(label = "VanSkeletonShimmer")
        val animated by transition.animateFloat(
            initialValue = -0.5f,
            targetValue = 1.5f,
            animationSpec = infiniteRepeatable(
                animation = tween(durationMillis = SHIMMER_PERIOD_MS, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
            label = "VanSkeletonShimmerPhase",
        )
        animated
    }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(cornerRadius ?: tokens.radius.m))
            .drawWithCache {
                val centerX = size.width * travel
                val bandWidth = (size.width * 0.5f).coerceAtLeast(1f)
                val brush = Brush.linearGradient(
                    colors = listOf(base, highlight, base),
                    start = Offset(centerX - bandWidth, 0f),
                    end = Offset(centerX + bandWidth, size.height),
                )
                onDrawBehind { drawRect(brush) }
            }
            .semantics { contentDescription = "Loading" },
    )
}

private const val SHIMMER_PERIOD_MS = 1400
