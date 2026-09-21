package com.dial.van.design.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics

/**
 * DNA §3: "HeatBar (portfolio heat / budget)." A single filled track from 0..1, coloured by
 * how close [fraction] is to its budget — under 60% reads `favourable`, 60-85% `eventRisk`,
 * above 85% `critical`. [fraction] is not clamped silently past 1.0: heat over budget still
 * fills the full track (DNA never asks HeatBar to lie about being over), it simply cannot
 * draw further right than the track itself.
 */
@Composable
fun HeatBar(
    label: String,
    fraction: Float,
    modifier: Modifier = Modifier,
    detail: String? = null,
) {
    val tokens = LocalVanTokens.current
    val clamped = fraction.coerceIn(0f, 1f)
    val role = when {
        fraction >= 0.85f -> StatusSemantics.ROLE_CRITICAL
        fraction >= 0.60f -> StatusSemantics.ROLE_EVENT_RISK
        else -> StatusSemantics.ROLE_FAVOURABLE
    }
    val color = tokens.color.forStatusRole(role)
    val animatedFraction by animateFloatAsState(
        targetValue = clamped,
        animationSpec = tween(tokens.motion.durations.quickMs, easing = tokens.motion.standardEasing),
        label = "VanHeatBar",
    )

    Column(
        modifier = modifier
            .fillMaxWidth()
            .semantics { contentDescription = "$label, ${(fraction * 100).toInt()} percent${detail?.let { ", $it" } ?: ""}" },
        verticalArrangement = Arrangement.spacedBy(tokens.space.space1),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(label, style = tokens.type.label, color = tokens.color.textTertiary)
            if (detail != null) {
                Text(detail, style = tokens.type.label, color = tokens.color.textTertiary)
            }
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(6.dp)
                .clip(RoundedCornerShape(tokens.radius.s))
                .background(tokens.color.surface2),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(animatedFraction.coerceIn(0f, 1f))
                    .clip(RoundedCornerShape(tokens.radius.s))
                    .background(color)
                    .align(Alignment.CenterStart),
            )
        }
    }
}
