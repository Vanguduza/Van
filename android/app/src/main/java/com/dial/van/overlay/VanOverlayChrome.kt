package com.dial.van.overlay

import com.dial.van.visual.VanAuthorityState
import com.dial.van.visual.VanCaptions
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanHealthState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresenceFrame
import com.dial.van.visual.VanStatusPalette

/**
 * Pure presentation policy for overlay chrome.
 *
 * Local activity remains the primary owner-facing experience while non-uplink degradation is kept
 * visible as secondary truth. OFFLINE and critical authority are allowed to take over primary
 * presentation because they require immediate owner attention.
 */
data class VanOverlayChromeModel(
    val primaryState: VanDurableState,
    val headline: String,
    val caption: String,
    val healthLine: String?,
    val accent: Int,
)

object VanOverlayChrome {
    fun resolve(
        cue: VanPresence.Cue,
        live: VanPresenceFrame,
        healthLine: String?,
    ): VanOverlayChromeModel {
        val criticalAuthority = live.authority != VanAuthorityState.NONE
        val primaryState = when {
            cue.health == VanHealthState.OFFLINE -> VanDurableState.OFFLINE
            criticalAuthority -> cue.durableState
            else -> live.poseState
        }
        val palette = VanStatusPalette.forState(primaryState)
        return VanOverlayChromeModel(
            primaryState = primaryState,
            headline = palette.label,
            caption = VanCaptions.forState(primaryState),
            healthLine = healthLine?.takeIf { it.isNotBlank() && cue.health != VanHealthState.NOMINAL },
            accent = palette.accent,
        )
    }
}
