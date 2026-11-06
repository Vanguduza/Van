package com.dial.van.overlay

import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanPresenceFrame
import com.dial.van.visual.VanVisualState

/** UI chrome must not subscribe to every lip, pupil or pointer sample. */
object OverlayPresentationFrame {
    fun chrome(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        attentionX = 0f, attentionY = 0f, mouthOpen = 0f, viseme = 0,
    )

    /** Preserve the caller's authoritative pose/health/approval decisions. */
    fun character(semantic: VanVisualState, live: VanPresenceFrame): VanVisualState {
        fun finite(value: Float, minimum: Float, maximum: Float): Float =
            if (value.isFinite()) value.coerceIn(minimum, maximum) else 0f
        val offline = semantic.durableState == VanDurableState.OFFLINE || semantic.resolvedSemanticState == VanDurableState.OFFLINE
        return semantic.copy(
            attentionX = finite(live.attentionX, -1f, 1f),
            attentionY = finite(live.attentionY, -1f, 1f),
            mouthOpen = if (offline) 0f else finite(live.mouthOpen, 0f, 1f),
            viseme = if (offline) 0 else when { live.viseme < 0 -> 0; live.viseme > 4 -> 1; else -> live.viseme },
        )
    }
}
