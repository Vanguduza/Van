package com.dial.van.design.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens

/**
 * A destination or panel-group heading, with an optional supporting line and a trailing
 * slot (a `LiveBadge`, a count, an action). Distinct from `com.dial.van.command.SectionHeader`
 * and `com.dial.van.trading.ui.SectionPanel`'s inline header row — this is the tokenised
 * version those screens migrate onto.
 */
@Composable
fun SectionHeader(
    title: String,
    modifier: Modifier = Modifier,
    detail: String? = null,
    trailing: (@Composable () -> Unit)? = null,
) {
    val tokens = LocalVanTokens.current
    Row(
        modifier = modifier.padding(vertical = tokens.space.space2),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space1 / 2),
        ) {
            Text(title, style = tokens.type.title, color = tokens.color.textPrimary)
            if (detail != null) {
                Text(detail, style = tokens.type.body, color = tokens.color.textSecondary)
            }
        }
        if (trailing != null) {
            trailing()
        }
    }
}
