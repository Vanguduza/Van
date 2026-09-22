package com.dial.van.design.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.dial.van.design.DegradedRow
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenState
import com.dial.van.design.StatusSemantics

/**
 * Turns a [ScreenState] into pixels. DNA §5: every destination implements all seven states;
 * this is the one place that switch is written, so a screen that forgets one of them is a
 * screen that does not compile — [ScreenState] is `sealed`, so the `when` below is exhaustive
 * and a new case added there breaks this file until it is handled here too.
 *
 * [content] only ever receives live or last-known-good data (`T`), never a nullable "maybe
 * this is here" — [ScreenState.Degraded] with no surviving data renders its banner alone
 * rather than calling [content] with a placeholder.
 */
@Composable
fun <T> VanScreen(
    state: ScreenState<T>,
    modifier: Modifier = Modifier,
    onRetry: (() -> Unit)? = null,
    onEmptyAction: (() -> Unit)? = null,
    skeleton: @Composable () -> Unit = { VanScreenSkeleton() },
    content: @Composable (T) -> Unit,
) {
    val tokens = LocalVanTokens.current
    // Bound to a `val` rather than left as a bare statement: Kotlin only enforces exhaustive
    // coverage of a sealed class on a `when` used as an *expression*. As a statement, a new
    // `ScreenState` subclass with no branch here would silently fall through to nothing —
    // this binding is what turns that into the compile error the doc comment above promises.
    @Suppress("UNUSED_VARIABLE")
    val exhaustive: Unit = when (state) {
        is ScreenState.Loading -> skeleton()

        is ScreenState.Content -> content(state.data)

        is ScreenState.Empty -> EmptyState(
            sentence = state.sentence,
            modifier = modifier,
            action = state.action,
            onAction = onEmptyAction,
        )

        is ScreenState.Error -> VanErrorState(
            message = state.message,
            canRetry = state.canRetry,
            onRetry = onRetry,
            modifier = modifier,
        )

        is ScreenState.Offline -> VanOfflineState(queuedCount = state.queuedCount, modifier = modifier)

        is ScreenState.Degraded -> Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
            VanDegradedBanner(rows = state.rows)
            state.data?.let { content(it) }
        }

        is ScreenState.Stale -> Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            LiveBadge(state = LiveBadgeState.Stale(state.ageMs))
            content(state.content)
        }
    }
}

/** The default LOADING skeleton: three rows, the common shape of a list-first screen. */
@Composable
fun VanScreenSkeleton(modifier: Modifier = Modifier, rows: Int = 3) {
    val tokens = LocalVanTokens.current
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        repeat(rows) {
            SkeletonBlock(modifier = Modifier.fillMaxWidth().height(72.dp))
        }
    }
}

@Composable
fun VanErrorState(
    message: String,
    modifier: Modifier = Modifier,
    canRetry: Boolean = true,
    onRetry: (() -> Unit)? = null,
) {
    val tokens = LocalVanTokens.current
    Column(
        modifier = modifier.fillMaxWidth().padding(tokens.space.space5),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        Text(
            text = message,
            style = tokens.type.body,
            color = tokens.color.forStatusRole(StatusSemantics.ROLE_CRITICAL),
            textAlign = TextAlign.Center,
        )
        if (canRetry && onRetry != null) {
            OutlinedButton(
                onClick = onRetry,
                colors = ButtonDefaults.outlinedButtonColors(contentColor = tokens.color.accentCyan),
            ) {
                Text("Retry", style = tokens.type.label)
            }
        }
    }
}

@Composable
fun VanOfflineState(queuedCount: Int, modifier: Modifier = Modifier) {
    val tokens = LocalVanTokens.current
    Column(
        modifier = modifier.fillMaxWidth().padding(tokens.space.space5),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(tokens.space.space2),
    ) {
        LiveBadge(state = LiveBadgeState.Offline)
        Text(
            text = if (queuedCount > 0) {
                "Offline — $queuedCount ${if (queuedCount == 1) "action is" else "actions are"} queued and will send when you're back."
            } else {
                "Offline — I'll catch up."
            },
            style = tokens.type.body,
            color = tokens.color.textSecondary,
            textAlign = TextAlign.Center,
        )
    }
}

/** DNA §5: "DEGRADED (which subsystem, what still works — from `/health.degraded[]`)." */
@Composable
fun VanDegradedBanner(rows: List<DegradedRow>, modifier: Modifier = Modifier) {
    if (rows.isEmpty()) return
    val tokens = LocalVanTokens.current
    VanPanel(modifier = modifier, dense = true) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
            StatusChip(label = "DEGRADED", role = StatusSemantics.ROLE_EVENT_RISK)
            for (row in rows) {
                Text(
                    text = row.sentence,
                    style = tokens.type.body,
                    color = tokens.color.textSecondary,
                    modifier = Modifier.padding(top = tokens.space.space1),
                )
            }
        }
    }
}
