package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenState
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPressable
import com.dial.van.trading.Loaded
import com.dial.van.trading.TradingFormat

/**
 * Small pieces every rebuilt trading screen shares: turning [Loaded] (the repository's own
 * "still fetching / here it is / could not reach it" state) into the design system's
 * [ScreenState] (DNA §5's seven-state contract), a refresh affordance and a chip-style tab
 * row built from tokens rather than the deleted `ui/TradingComponents.kt`'s raw-colour ones.
 */

/**
 * [Loaded] has no concept of "empty" (a repository does not know what an empty list means to
 * a screen), so the caller supplies [isEmpty]. [Loaded.Unavailable] always becomes
 * [ScreenState.Error] — DNA's ERROR state, with [TradingFormat.unavailableState] turning the
 * transport-layer reason into an owner-facing sentence — never a silent EMPTY, which is the
 * P3-AND-011 defect this package's other files were written to fix.
 */
fun <T> Loaded<T>.toScreenState(
    emptySentence: String = "Nothing here yet.",
    isEmpty: (T) -> Boolean = { false },
): ScreenState<T> = when (this) {
    is Loaded.Loading -> ScreenState.Loading
    is Loaded.Unavailable -> ScreenState.Error(TradingFormat.unavailableState(reason))
    is Loaded.Ready -> if (isEmpty(value)) ScreenState.Empty(emptySentence) else ScreenState.Content(value)
}

/** DNA §2 press affordance + `Refresh` icon, used in place of a bare `Icon(...clickable)`. */
@Composable
fun TradingRefreshAction(modifier: Modifier = Modifier, onClick: () -> Unit) {
    val tokens = LocalVanTokens.current
    IconButton(onClick = onClick, modifier = modifier) {
        Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = tokens.color.accentCyan)
    }
}

/**
 * A row of [StatusChip]s acting as single-select tabs, replacing `TabRowChips`. `modifier`
 * comes before [onSelect] (not after, DNA-codebase convention — see `VanPressable`) so every
 * call site can use trailing-lambda syntax for the selection callback.
 */
@Composable
fun TradingTabs(options: List<String>, selected: String, modifier: Modifier = Modifier, onSelect: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    Row(modifier = modifier, horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        options.forEach { option ->
            VanPressable(onClick = { onSelect(option) }, contentDescription = option) {
                StatusChip(
                    label = option,
                    role = if (option == selected) StatusSemantics.ROLE_ENGAGED else StatusSemantics.ROLE_DISABLED,
                    filled = option == selected,
                )
            }
        }
    }
}

/** A muted footer disclosure line — every trading screen's "this is a read model, nothing here can act" note. */
@Composable
fun TradingDisclosure(text: String, modifier: Modifier = Modifier) {
    val tokens = LocalVanTokens.current
    Text(text, style = tokens.type.label, color = tokens.color.textTertiary, modifier = modifier)
}

/** How old VAN's own read of the ledger is, from whatever timestamps a screen actually fetched. */
fun latestOf(vararg candidates: Long?): Long? = candidates.filterNotNull().filter { it > 0 }.maxOrNull()
