package com.dial.van.design.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenAction

/**
 * DNA §3/§5: "EmptyState (VAN-voiced sentence, one action)." [sentence] is written the way
 * VAN would say it ("Nothing needs you right now." not "No items"), and there is at most one
 * [action] — DNA is explicit that empty states offer one action, not a menu.
 */
@Composable
fun EmptyState(
    sentence: String,
    modifier: Modifier = Modifier,
    action: ScreenAction? = null,
    onAction: (() -> Unit)? = null,
) {
    val tokens = LocalVanTokens.current
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(tokens.space.space5),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        Text(
            text = sentence,
            style = tokens.type.body,
            color = tokens.color.textSecondary,
            textAlign = TextAlign.Center,
        )
        if (action != null && onAction != null) {
            OutlinedButton(
                onClick = onAction,
                colors = ButtonDefaults.outlinedButtonColors(contentColor = tokens.color.accentCyan),
            ) {
                Text(action.label, style = tokens.type.label)
            }
        }
    }
}
