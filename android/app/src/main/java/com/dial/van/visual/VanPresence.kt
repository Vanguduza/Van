package com.dial.van.visual

import com.dial.van.degraded.DegradedMode
import com.dial.van.degraded.SubsystemStatus

/**
 * Resolves subsystem truth and the orthogonal live presence frame into UI chrome and embodiment.
 *
 * Health remains fail-closed, but DEGRADED is no longer allowed to erase a locally truthful
 * LISTENING/THINKING/SPEAKING pose. The character can therefore interact while Zone C and chrome
 * continue to show an unverified Google mesh. Uplink loss remains stronger and forces OFFLINE.
 */
object VanPresence {

    private const val HERMES = "hermes"
    private const val GATEWAY = "gateway"
    private const val GOOGLE = "google"

    data class Cue(
        val durableState: VanDurableState,
        val health: VanHealthState,
        val headline: String,
        val detail: String,
        val brokenLabels: List<String>,
        val urgency: Float,
    ) {
        val degraded: Boolean get() = health != VanHealthState.NOMINAL
    }

    fun cue(
        mode: DegradedMode,
        listening: Boolean = false,
        speaking: Boolean = false,
        awaitingOwner: Boolean = false,
        live: VanPresenceFrame = VanLiveVisualState.frame,
    ): Cue {
        val broken = mode.subsystems.filter { it.status == SubsystemStatus.BROKEN }
        val brokenLabels = broken.map { it.label }
        val uplinkDown = broken.any { it.id == HERMES || it.id == GATEWAY }
        val health = when {
            uplinkDown -> VanHealthState.OFFLINE
            broken.isNotEmpty() -> VanHealthState.DEGRADED
            else -> VanHealthState.NOMINAL
        }

        if (uplinkDown) {
            val lead = broken.first { it.id == HERMES || it.id == GATEWAY }
            return Cue(
                durableState = VanDurableState.OFFLINE,
                health = VanHealthState.OFFLINE,
                headline = VanStatusPalette.forState(VanDurableState.OFFLINE).label,
                detail = lead.detail,
                brokenLabels = brokenLabels,
                urgency = 0.25f,
            )
        }

        if (awaitingOwner || live.authority == VanAuthorityState.WAITING_FOR_OWNER) {
            return Cue(
                durableState = VanDurableState.WAITING_FOR_OWNER,
                health = health,
                headline = VanStatusPalette.forState(VanDurableState.WAITING_FOR_OWNER).label,
                detail = "Waiting on your decision",
                brokenLabels = brokenLabels,
                urgency = 0.45f,
            )
        }

        if (broken.isNotEmpty()) {
            val lead = broken.firstOrNull { it.id == GOOGLE } ?: broken.first()
            return Cue(
                durableState = VanDurableState.DEGRADED,
                health = VanHealthState.DEGRADED,
                headline = VanStatusPalette.forState(VanDurableState.DEGRADED).label,
                detail = "${lead.label}: ${lead.detail}",
                brokenLabels = brokenLabels,
                urgency = 0.30f,
            )
        }

        val state = when {
            listening -> VanDurableState.LISTENING
            speaking -> VanDurableState.SPEAKING
            live.semanticState != VanDurableState.IDLE -> live.semanticState
            else -> VanDurableState.IDLE
        }
        return nominal(state, if (state == VanDurableState.IDLE) mode.reason else VanCaptions.forState(state))
    }

    /** Legacy/overlay bridge while call sites migrate to [VanPresenceFrame]. */
    fun cue(mode: DegradedMode, live: VanVisualState): Cue = cue(
        mode = mode,
        live = frameFromVisual(live),
    )

    fun visualState(
        cue: Cue,
        base: VanPresenceFrame = VanLiveVisualState.frame,
    ): VanVisualState {
        var frame = base.copy(health = cue.health)

        frame = when (cue.durableState) {
            VanDurableState.WAITING_FOR_OWNER ->
                frame.copy(authority = VanAuthorityState.WAITING_FOR_OWNER, urgency = maxOf(frame.urgency, cue.urgency))
            VanDurableState.WARNING ->
                frame.copy(authority = VanAuthorityState.WARNING, urgency = maxOf(frame.urgency, cue.urgency))
            VanDurableState.ERROR ->
                frame.copy(authority = VanAuthorityState.ERROR, urgency = maxOf(frame.urgency, cue.urgency))
            VanDurableState.URGENT ->
                frame.copy(authority = VanAuthorityState.URGENT, urgency = maxOf(frame.urgency, cue.urgency))
            else -> frame.copy(urgency = maxOf(frame.urgency, cue.urgency))
        }

        if (cue.health == VanHealthState.OFFLINE) {
            frame = frame.copy(
                activity = VanDurableState.OFFLINE,
                speech = VanSpeechState.QUIET,
                turn = VanTurnPhase.IDLE,
                mouthOpen = 0f,
                viseme = 0,
            )
        }
        return frame.toVisualState()
    }

    fun visualState(cue: Cue, base: VanVisualState): VanVisualState =
        visualState(cue, frameFromVisual(base))

    fun meshCue(mode: DegradedMode): String {
        val google = mode.subsystems.firstOrNull { it.id == GOOGLE }
            ?: return "Google mesh: unknown"
        return when (google.status) {
            SubsystemStatus.WORKING -> "Google mesh verified"
            SubsystemStatus.BROKEN -> "Google mesh unverified"
            SubsystemStatus.WONT_DO -> "Google mesh disabled"
        }
    }

    private fun frameFromVisual(base: VanVisualState): VanPresenceFrame = VanPresenceFrame(
        activity = base.durableState,
        speech = when {
            base.speaking -> VanSpeechState.SPEAKING
            base.listening -> VanSpeechState.LISTENING
            else -> VanSpeechState.QUIET
        },
        attentionX = base.attentionX,
        attentionY = base.attentionY,
        mouthOpen = base.mouthOpen,
        viseme = base.viseme,
        urgency = base.urgency,
        actionCode = base.actionCode,
    )

    private fun nominal(state: VanDurableState, detail: String) = Cue(
        durableState = state,
        health = VanHealthState.NOMINAL,
        headline = VanStatusPalette.forState(state).label,
        detail = detail,
        brokenLabels = emptyList(),
        urgency = 0f,
    )
}
