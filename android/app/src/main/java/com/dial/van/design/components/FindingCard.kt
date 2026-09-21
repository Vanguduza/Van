package com.dial.van.design.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens

/** One action a [FindingCard] can offer, e.g. "Open", "Dismiss", "Snooze". */
data class FindingAction(val label: String, val onClick: () -> Unit, val emphasized: Boolean = false)

/**
 * DNA §3: "FindingCard (severity, actions)." A single research/monitoring finding — the
 * Attention screen's non-swipeable cousin of [AttentionItem], for surfaces (Work, Memory) that
 * list findings inline rather than in a triage queue.
 */
@Composable
fun FindingCard(
    title: String,
    severityRole: String,
    modifier: Modifier = Modifier,
    detail: String? = null,
    actions: List<FindingAction> = emptyList(),
) {
    val tokens = LocalVanTokens.current
    VanPanel(modifier = modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                StatusChip(label = severityRole.replaceFirstChar { it.uppercase() }, role = severityRole)
            }
            Text(title, style = tokens.type.headline, color = tokens.color.textPrimary)
            if (detail != null) {
                Text(detail, style = tokens.type.body, color = tokens.color.textSecondary)
            }
            if (actions.isNotEmpty()) {
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    for (action in actions) {
                        TextButton(
                            onClick = action.onClick,
                            colors = ButtonDefaults.textButtonColors(
                                contentColor = if (action.emphasized) tokens.color.accentCyan else tokens.color.textSecondary,
                            ),
                        ) {
                            Text(action.label, style = tokens.type.label)
                        }
                    }
                }
            }
        }
    }
}
