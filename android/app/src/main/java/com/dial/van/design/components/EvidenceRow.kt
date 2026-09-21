package com.dial.van.design.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dial.van.design.LocalVanTokens

/**
 * DNA §3: "EvidenceRow (source, trust tier, time, open)." Provenance for a fact, a finding or
 * a memory item — [trustTier] is shown as text (`StatusChip`), never colour alone, since a
 * trust tier is exactly the kind of fact an owner should be able to read without inferring it
 * from a hue.
 */
@Composable
fun EvidenceRow(
    source: String,
    trustTier: String,
    trustRole: String,
    timeLabel: String,
    modifier: Modifier = Modifier,
    onOpen: (() -> Unit)? = null,
) {
    val tokens = LocalVanTokens.current
    val row: @Composable () -> Unit = {
        Row(
            modifier = Modifier,
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
        ) {
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(tokens.space.space1 / 2)) {
                Text(source, style = tokens.type.body, color = tokens.color.textPrimary, maxLines = 1)
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2), verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(label = trustTier, role = trustRole)
                    Text(timeLabel, style = tokens.type.label, color = tokens.color.textTertiary)
                }
            }
            if (onOpen != null) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.OpenInNew,
                    contentDescription = "Open source",
                    tint = tokens.color.textTertiary,
                    modifier = Modifier,
                )
            }
        }
    }
    if (onOpen != null) {
        VanPressable(
            onClick = onOpen,
            modifier = modifier,
            contentDescription = "$source, $trustTier, $timeLabel. Open.",
        ) {
            Column { row() }
        }
    } else {
        Column(modifier = modifier) { row() }
    }
}
