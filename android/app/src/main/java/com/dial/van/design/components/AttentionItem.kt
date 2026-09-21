package com.dial.van.design.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Snooze
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dial.van.design.AttentionSeverity
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics

/**
 * DNA §3/§4: "AttentionItem (severity rail, swipe: ack / snooze / open)." The severity rail is
 * a coloured bar down the left edge (never colour alone — [severity] is also the [StatusChip]
 * text). Swipe start→end (typically right, in an LTR layout) acknowledges; swipe end→start
 * snoozes; a tap opens. `SwipeToDismissBox`/`rememberSwipeToDismissBoxState` are
 * `@ExperimentalMaterial3Api` in Compose BOM 2024.06.00's material3 (1.2.1) — opted in here,
 * at the one place this package uses them.
 *
 * `confirmValueChange` returns `false` for both swipe directions: the swipe *fires* [onAck]/
 * [onSnooze] and then the item settles back to its resting position rather than flying off —
 * the caller removes it from whatever list produced it (or does not, if ack/snooze should
 * leave it visible), so this component never assumes removal is the right visual outcome.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AttentionItem(
    title: String,
    severity: AttentionSeverity,
    modifier: Modifier = Modifier,
    detail: String? = null,
    timeLabel: String? = null,
    onAck: (() -> Unit)? = null,
    onSnooze: (() -> Unit)? = null,
    onOpen: (() -> Unit)? = null,
) {
    val tokens = LocalVanTokens.current
    val role = StatusSemantics.forAttentionSeverity(severity)
    val color = tokens.color.forStatusRole(role)

    var pendingAck by remember { mutableStateOf(false) }
    var pendingSnooze by remember { mutableStateOf(false) }

    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            when (value) {
                SwipeToDismissBoxValue.StartToEnd -> {
                    if (onAck != null) pendingAck = true
                    false
                }
                SwipeToDismissBoxValue.EndToStart -> {
                    if (onSnooze != null) pendingSnooze = true
                    false
                }
                SwipeToDismissBoxValue.Settled -> true
            }
        },
    )

    LaunchedEffect(pendingAck) {
        if (pendingAck) {
            onAck?.invoke()
            pendingAck = false
        }
    }
    LaunchedEffect(pendingSnooze) {
        if (pendingSnooze) {
            onSnooze?.invoke()
            pendingSnooze = false
        }
    }

    val rowContentDescription = buildString {
        append(severity.name.lowercase().replaceFirstChar { it.uppercase() })
        append(": ")
        append(title)
        if (timeLabel != null) append(", $timeLabel")
    }

    SwipeToDismissBox(
        state = dismissState,
        modifier = modifier.fillMaxWidth(),
        enableDismissFromStartToEnd = onAck != null,
        enableDismissFromEndToStart = onSnooze != null,
        backgroundContent = { AttentionSwipeBackground(dismissState.targetValue) },
    ) {
        // The `onClick` semantics action comes from `VanPressable`'s own `clickable` when
        // `onOpen` is set — adding a second one here would just duplicate it, so this modifier
        // only ever carries the description.
        val cardModifier = Modifier
            .fillMaxWidth()
            .semantics { contentDescription = rowContentDescription }
        val body: @Composable () -> Unit = {
            // `height(IntrinsicSize.Min)` so the rail's `fillMaxHeight()` resolves against the
            // row's own content height rather than an unconstrained/screen-height measurement.
            Row(modifier = Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
                Box(
                    modifier = Modifier
                        .width(3.dp)
                        .fillMaxHeight()
                        .background(color),
                )
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .padding(start = tokens.space.space3),
                    verticalArrangement = Arrangement.spacedBy(tokens.space.space1),
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2), verticalAlignment = Alignment.CenterVertically) {
                        StatusChip(label = severity.name.replace('_', ' '), role = role)
                        if (timeLabel != null) {
                            Text(timeLabel, style = tokens.type.label, color = tokens.color.textTertiary)
                        }
                    }
                    Text(title, style = tokens.type.body, color = tokens.color.textPrimary)
                    if (detail != null) {
                        Text(detail, style = tokens.type.label, color = tokens.color.textSecondary)
                    }
                }
            }
        }
        if (onOpen != null) {
            VanPressable(onClick = onOpen, modifier = cardModifier, role = Role.Button) {
                VanPanel(modifier = Modifier.fillMaxWidth(), dense = true) { body() }
            }
        } else {
            VanPanel(modifier = cardModifier, dense = true) { body() }
        }
    }
}

@Composable
private fun AttentionSwipeBackground(direction: SwipeToDismissBoxValue) {
    val tokens = LocalVanTokens.current
    val (color, icon, alignment) = when (direction) {
        SwipeToDismissBoxValue.StartToEnd -> Triple(
            tokens.color.forStatusRole(StatusSemantics.ROLE_FAVOURABLE),
            Icons.Filled.CheckCircle,
            Alignment.CenterStart,
        )
        SwipeToDismissBoxValue.EndToStart -> Triple(
            tokens.color.forStatusRole(StatusSemantics.ROLE_MONITOR),
            Icons.Filled.Snooze,
            Alignment.CenterEnd,
        )
        SwipeToDismissBoxValue.Settled -> Triple(tokens.color.surface1, null, Alignment.Center)
    }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(color.copy(alpha = 0.24f))
            .padding(horizontal = tokens.space.space4),
        contentAlignment = alignment,
    ) {
        if (icon != null) {
            Icon(imageVector = icon, contentDescription = null, tint = color)
        }
    }
}
