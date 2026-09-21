package com.dial.van.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.dial.van.design.LiveBadgeFormat
import com.dial.van.design.StatusSemantics

/** DNA §3: "`LiveBadge` (LIVE / STALE hh:mm / OFFLINE / EXTERNAL)." */
sealed class LiveBadgeState {
    object Live : LiveBadgeState()
    data class Stale(val ageMs: Long) : LiveBadgeState()
    object Offline : LiveBadgeState()
    object External : LiveBadgeState()
}

/**
 * The one place `ScreenState.Stale`'s age becomes an "hh:mm" string, and the one place any
 * screen says LIVE/STALE/OFFLINE/EXTERNAL — so the format cannot drift between two panels
 * showing the same underlying staleness.
 */
@Composable
fun LiveBadge(state: LiveBadgeState, modifier: Modifier = Modifier) {
    val (label, role) = when (state) {
        LiveBadgeState.Live -> "LIVE" to StatusSemantics.ROLE_ENGAGED
        is LiveBadgeState.Stale -> "STALE ${LiveBadgeFormat.hhmm(state.ageMs)}" to StatusSemantics.ROLE_EVENT_RISK
        LiveBadgeState.Offline -> "OFFLINE" to StatusSemantics.ROLE_DISABLED
        LiveBadgeState.External -> "EXTERNAL" to StatusSemantics.ROLE_COGNITION
    }
    StatusChip(label = label, role = role, modifier = modifier, filled = state is LiveBadgeState.Live)
}
