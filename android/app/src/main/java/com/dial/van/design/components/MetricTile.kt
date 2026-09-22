package com.dial.van.design.components

import androidx.compose.animation.core.tween
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics

/**
 * DNA §3: "MetricTile (value, delta, sparkline, tap → detail)." [deltaRole] is a
 * [StatusSemantics] role name, not a raw green/red — a positive delta on a *deteriorating*
 * thesis still reads as the DNA-mandated colour for that state, not as "up is good."
 *
 * Wrapping in [VanPressable] is the caller's choice ([onClick] is optional): a tile inside a
 * read-only summary row has nothing to navigate to.
 */
@Composable
fun MetricTile(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    delta: String? = null,
    deltaRole: String? = null,
    sparkline: List<Float>? = null,
    onClick: (() -> Unit)? = null,
) {
    val tokens = LocalVanTokens.current
    val body: @Composable () -> Unit = {
        Column(
            modifier = Modifier.animateContentSize(
                animationSpec = tween(tokens.motion.durations.quickMs, easing = tokens.motion.standardEasing),
            ),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space1),
        ) {
            Text(label, style = tokens.type.label, color = tokens.color.textTertiary, maxLines = 1)
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                Text(value, style = tokens.type.dataLarge, color = tokens.color.textPrimary, maxLines = 1)
                if (delta != null) {
                    Text(
                        delta,
                        style = tokens.type.data,
                        color = deltaRole?.let { tokens.color.forStatusRole(it) } ?: tokens.color.textSecondary,
                        maxLines = 1,
                    )
                }
            }
            if (sparkline != null && sparkline.size > 1) {
                Sparkline(
                    values = sparkline,
                    lineColor = deltaRole?.let { tokens.color.forStatusRole(it) },
                )
            }
        }
    }
    val semanticLabel = if (delta != null) "$label, $value, $delta" else "$label, $value"
    if (onClick != null) {
        VanPressable(
            onClick = onClick,
            modifier = modifier,
            contentDescription = "$semanticLabel. Open detail.",
        ) {
            Column { body() }
        }
    } else {
        Column(modifier = modifier.semantics { contentDescription = semanticLabel }) { body() }
    }
}
