package com.dial.van.design.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.ThesisState

/**
 * DNA §3: "ThesisCard (state, invalidation, confirmation)." Takes [ThesisState] rather than a
 * trading-package type — the trading screens this migrates onto own their own thesis model and
 * pass `ThesisState.CONFIRMED`/etc. (or map their richer state onto it) rather than this
 * package depending on `trading/`.
 */
@Composable
fun ThesisCard(
    title: String,
    state: ThesisState,
    modifier: Modifier = Modifier,
    thesisSummary: String? = null,
    invalidation: String? = null,
    confirmation: String? = null,
) {
    val tokens = LocalVanTokens.current
    val role = StatusSemantics.forThesisState(state)
    VanPanel(modifier = modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Text(
                    title,
                    style = tokens.type.headline,
                    color = tokens.color.textPrimary,
                    modifier = Modifier.weight(1f),
                )
                StatusChip(label = stateLabel(state), role = role)
            }
            if (thesisSummary != null) {
                Text(thesisSummary, style = tokens.type.body, color = tokens.color.textSecondary)
            }
            if (confirmation != null) {
                LabeledLine(caption = "Confirms if", value = confirmation, role = StatusSemantics.ROLE_FAVOURABLE)
            }
            if (invalidation != null) {
                LabeledLine(caption = "Invalidates if", value = invalidation, role = StatusSemantics.ROLE_CRITICAL)
            }
        }
    }
}

@Composable
private fun LabeledLine(caption: String, value: String, role: String) {
    val tokens = LocalVanTokens.current
    Column {
        Text(caption, style = tokens.type.label, color = tokens.color.textTertiary)
        Text(value, style = tokens.type.body, color = tokens.color.forStatusRole(role))
    }
}

private fun stateLabel(state: ThesisState): String = when (state) {
    ThesisState.HYPOTHESIS -> "Hypothesis"
    ThesisState.MONITORING -> "Monitoring"
    ThesisState.CONFIRMED -> "Confirmed"
    ThesisState.WEAKENING -> "Weakening"
    ThesisState.INVALIDATED -> "Invalidated"
}
