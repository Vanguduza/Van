package com.dial.van.visual

import com.dial.van.degraded.DegradedMode
import com.dial.van.degraded.SubsystemStatus

/**
 * Translates subsystem truth and live interaction state into how Van *appears*.
 *
 * The overlay must never look healthy while a subsystem is broken, so this mapping fails
 * closed: any uplink loss presents OFFLINE, any other broken subsystem presents DEGRADED.
 * When subsystem truth is nominal, the live visual controller is allowed to surface listening,
 * speaking, thinking, working and other activity states continuously.
 */
object VanPresence {

    private const val HERMES = "hermes"
    private const val GATEWAY = "gateway"
    private const val GOOGLE = "google"

    data class Cue(
        val durableState: VanDurableState,
        val headline: String,
        val detail: String,
        val brokenLabels: List<String>,
        val urgency: Float,
    ) {
        val degraded: Boolean
            get() = durableState == VanDurableState.OFFLINE || durableState == VanDurableState.DEGRADED
    }

    fun cue(
        mode: DegradedMode,
        listening: Boolean = false,
        speaking: Boolean = false,
        awaitingOwner: Boolean = false,
        live: VanVisualState = VanLiveVisualState.current,
    ): Cue {
        val broken = mode.subsystems.filter { it.status == SubsystemStatus.BROKEN }
        val brokenLabels = broken.map { it.label }
        val uplinkDown = broken.any { it.id == HERMES || it.id == GATEWAY }

        return when {
            uplinkDown -> Cue(
                durableState = VanDurableState.OFFLINE,
                headline = VanStatusPalette.forState(VanDurableState.OFFLINE).label,
                detail = broken.first { it.id == HERMES || it.id == GATEWAY }.detail,
                brokenLabels = brokenLabels,
                urgency = 0.25f,
            )

            broken.isNotEmpty() -> {
                val lead = broken.firstOrNull { it.id == GOOGLE } ?: broken.first()
                Cue(
                    durableState = VanDurableState.DEGRADED,
                    headline = VanStatusPalette.forState(VanDurableState.DEGRADED).label,
                    detail = "${lead.label}: ${lead.detail}",
                    brokenLabels = brokenLabels,
                    urgency = 0.30f,
                )
            }

            awaitingOwner -> Cue(
                durableState = VanDurableState.WAITING_FOR_OWNER,
                headline = VanStatusPalette.forState(VanDurableState.WAITING_FOR_OWNER).label,
                detail = "Waiting on your decision",
                brokenLabels = emptyList(),
                urgency = 0.45f,
            )

            listening -> nominal(VanDurableState.LISTENING, "Listening for you")
            speaking -> nominal(VanDurableState.SPEAKING, "Speaking")
            live.durableState != VanDurableState.IDLE -> nominal(
                live.durableState,
                VanCaptions.forState(live.durableState),
            )
            else -> nominal(VanDurableState.IDLE, mode.reason)
        }
    }

    /**
     * Merges truth with the continuously changing live presence state.
     *
     * Precedence is deliberately asymmetric: OFFLINE/DEGRADED and explicit owner-decision cues
     * always override the live controller. A nominal IDLE cue is merely permission for the live
     * state (LISTENING, THINKING, WORKING, SPEAKING, etc.) to show through.
     *
     * The default [base] is Compose snapshot state, so callers such as the floating overlay and
     * Command Centre automatically recompose when voice/task state changes, without polling.
     */
    fun visualState(
        cue: Cue,
        base: VanVisualState = VanLiveVisualState.current,
    ): VanVisualState {
        val resolved = when {
            cue.degraded -> cue.durableState
            cue.durableState != VanDurableState.IDLE -> cue.durableState
            else -> base.durableState
        }
        return base.copy(
            durableState = resolved,
            listening = resolved == VanDurableState.LISTENING ||
                (base.listening && resolved != VanDurableState.SPEAKING),
            speaking = resolved == VanDurableState.SPEAKING || base.speaking,
            urgency = maxOf(base.urgency, cue.urgency),
        )
    }

    /** One-line mesh cue for the overlay chrome; kept short enough to read at overlay width. */
    fun meshCue(mode: DegradedMode): String {
        val google = mode.subsystems.firstOrNull { it.id == GOOGLE }
            ?: return "Google mesh: unknown"
        return when (google.status) {
            SubsystemStatus.WORKING -> "Google mesh verified"
            SubsystemStatus.BROKEN -> "Google mesh unverified"
            SubsystemStatus.WONT_DO -> "Google mesh disabled"
        }
    }

    private fun nominal(state: VanDurableState, detail: String) = Cue(
        durableState = state,
        headline = VanStatusPalette.forState(state).label,
        detail = detail,
        brokenLabels = emptyList(),
        urgency = 0f,
    )
}
