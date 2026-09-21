package com.dial.van.design.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.ThesisState

/** A position's direction — kept local to this package rather than importing `trading/`. */
enum class PositionDirection { LONG, SHORT }

/**
 * DNA §3: "PositionCard (direction, exposure, R, protection, thesis state)." [rMultipleLabel]
 * is formatted by the caller (trading owns `TradingFormat`); this only lays it out and colours
 * it by [thesisState] — DNA §2: "P&L uses `text.primary` with a directional glyph and
 * `favourable`/`deteriorating` only when the thesis state says so," which is why the R's
 * colour here is [role], derived from [thesisState], never from the sign of the R itself.
 */
@Composable
fun PositionCard(
    symbol: String,
    direction: PositionDirection,
    exposureLabel: String,
    rMultipleLabel: String,
    thesisState: ThesisState,
    modifier: Modifier = Modifier,
    protectionLabel: String? = null,
    onClick: (() -> Unit)? = null,
) {
    val tokens = LocalVanTokens.current
    val role = StatusSemantics.forThesisState(thesisState)
    val glyph = if (direction == PositionDirection.LONG) "▲" else "▼"
    val body: @Composable () -> Unit = {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Text(
                    "$glyph $symbol",
                    style = tokens.type.headline,
                    color = tokens.color.textPrimary,
                    modifier = Modifier.weight(1f),
                )
                Text(rMultipleLabel, style = tokens.type.data, color = tokens.color.forStatusRole(role))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space4)) {
                LabeledData(caption = "Exposure", value = exposureLabel)
                if (protectionLabel != null) {
                    LabeledData(caption = "Protection", value = protectionLabel)
                }
            }
            StatusChip(label = thesisState.name.lowercase().replaceFirstChar { it.uppercase() }, role = role)
        }
    }
    if (onClick != null) {
        VanPressable(
            onClick = onClick,
            modifier = modifier,
            contentDescription = "$symbol, ${direction.name.lowercase()}, $exposureLabel, $rMultipleLabel. Open position.",
        ) {
            VanPanel(modifier = Modifier.fillMaxWidth()) { body() }
        }
    } else {
        VanPanel(modifier = modifier) { body() }
    }
}

@Composable
private fun LabeledData(caption: String, value: String) {
    val tokens = LocalVanTokens.current
    Column {
        Text(caption, style = tokens.type.label, color = tokens.color.textTertiary)
        Text(value, style = tokens.type.data, color = tokens.color.textPrimary)
    }
}
