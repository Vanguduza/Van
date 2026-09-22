package com.dial.van.design.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics

/**
 * A short status label with a coloured dot, coloured by [StatusSemantics] role name — never a
 * raw `Color`, so a chip's colour and the aura's colour for the same domain state are
 * guaranteed to come from the same mapping.
 *
 * "Never colour alone" (repo-wide convention — see `CommandCentreComponents.statusColor`'s own
 * doc comment): the dot is decorative, [label] is the word itself and is what a screen reader
 * announces.
 */
@Composable
fun StatusChip(
    label: String,
    role: String,
    modifier: Modifier = Modifier,
    filled: Boolean = false,
) {
    val tokens = LocalVanTokens.current
    val color = tokens.color.forStatusRole(role)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier
            .clip(RoundedCornerShape(tokens.radius.s))
            .background(if (filled) color else color.copy(alpha = 0.16f))
            .padding(horizontal = tokens.space.space3, vertical = tokens.space.space1)
            .semantics { contentDescription = label },
    ) {
        Box(
            modifier = Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(if (filled) tokens.color.textInverse else color),
        )
        Text(
            text = label,
            style = tokens.type.label,
            color = if (filled) tokens.color.textInverse else color,
            modifier = Modifier.padding(start = tokens.space.space1),
        )
    }
}
