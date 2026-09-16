package com.dial.van.visual

/**
 * Orthogonal runtime truth for VAN.
 *
 * A single enum cannot faithfully represent "I am listening" and "Google is not verified" at
 * the same time. This frame keeps activity, health, authority, speech and attention independent,
 * then derives the pose and semantic state consumed by renderers.
 */
enum class VanHealthState { NOMINAL, DEGRADED, OFFLINE }

enum class VanAuthorityState { NONE, WAITING_FOR_OWNER, WARNING, ERROR, URGENT }

enum class VanSpeechState { QUIET, LISTENING, SPEAKING }

enum class VanTurnPhase { IDLE, CAPTURING, THINKING, DISPATCHING }

data class VanPresenceFrame(
    val activity: VanDurableState = VanDurableState.IDLE,
    val health: VanHealthState = VanHealthState.NOMINAL,
    val authority: VanAuthorityState = VanAuthorityState.NONE,
    val speech: VanSpeechState = VanSpeechState.QUIET,
    val turn: VanTurnPhase = VanTurnPhase.IDLE,
    val attentionX: Float = 0f,
    val attentionY: Float = 0f,
    val mouthOpen: Float = 0f,
    val viseme: Int = 0,
    val urgency: Float = 0f,
    val actionCode: Int = 0,
) {
    /** Character pose/activity. Health DEGRADED does not suppress local interaction. */
    val poseState: VanDurableState
        get() = when (authority) {
            VanAuthorityState.WAITING_FOR_OWNER -> VanDurableState.WAITING_FOR_OWNER
            VanAuthorityState.WARNING -> VanDurableState.WARNING
            VanAuthorityState.ERROR -> VanDurableState.ERROR
            VanAuthorityState.URGENT -> VanDurableState.URGENT
            VanAuthorityState.NONE -> when {
                health == VanHealthState.OFFLINE -> VanDurableState.OFFLINE
                speech == VanSpeechState.SPEAKING -> VanDurableState.SPEAKING
                speech == VanSpeechState.LISTENING -> VanDurableState.LISTENING
                else -> activity
            }
        }

    /** Outer semantic field/chrome truth. Degraded truth remains visible while pose stays active. */
    val semanticState: VanDurableState
        get() = when (authority) {
            VanAuthorityState.WAITING_FOR_OWNER -> VanDurableState.WAITING_FOR_OWNER
            VanAuthorityState.WARNING -> VanDurableState.WARNING
            VanAuthorityState.ERROR -> VanDurableState.ERROR
            VanAuthorityState.URGENT -> VanDurableState.URGENT
            VanAuthorityState.NONE -> when (health) {
                VanHealthState.OFFLINE -> VanDurableState.OFFLINE
                VanHealthState.DEGRADED -> VanDurableState.DEGRADED
                VanHealthState.NOMINAL -> poseState
            }
        }

    fun toVisualState(): VanVisualState = VanVisualState(
        durableState = poseState,
        semanticState = semanticState,
        speaking = speech == VanSpeechState.SPEAKING,
        listening = speech == VanSpeechState.LISTENING,
        attentionX = attentionX.coerceIn(-1f, 1f),
        attentionY = attentionY.coerceIn(-1f, 1f),
        mouthOpen = mouthOpen.coerceIn(0f, 1f),
        urgency = urgency.coerceIn(0f, 1f),
        viseme = viseme.coerceAtLeast(0),
        actionCode = actionCode,
    )
}

/** Pure reducer used by the Android runtime and JVM tests. */
object VanPresenceReducer {
    fun listeningStarted(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        activity = VanDurableState.LISTENING,
        speech = VanSpeechState.LISTENING,
        turn = VanTurnPhase.CAPTURING,
        urgency = 0f,
    )

    /** Microphone capture ending is not the end of the owner turn. */
    fun listeningEnded(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        speech = VanSpeechState.QUIET,
        activity = if (frame.turn == VanTurnPhase.CAPTURING) VanDurableState.ATTENTIVE else frame.activity,
    )

    fun finalTranscript(frame: VanPresenceFrame, hasText: Boolean): VanPresenceFrame = if (hasText) {
        frame.copy(
            activity = VanDurableState.THINKING,
            speech = VanSpeechState.QUIET,
            turn = VanTurnPhase.THINKING,
            urgency = 0f,
        )
    } else {
        idle(frame)
    }

    fun dispatchStarted(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        activity = VanDurableState.DELEGATING,
        turn = VanTurnPhase.DISPATCHING,
        speech = VanSpeechState.QUIET,
        urgency = 0f,
    )

    fun authority(frame: VanPresenceFrame, state: VanAuthorityState): VanPresenceFrame = frame.copy(
        authority = state,
        turn = if (state == VanAuthorityState.NONE) frame.turn else VanTurnPhase.IDLE,
        urgency = when (state) {
            VanAuthorityState.NONE -> 0f
            VanAuthorityState.WAITING_FOR_OWNER -> 0.45f
            VanAuthorityState.WARNING -> 0.35f
            VanAuthorityState.ERROR -> 0.75f
            VanAuthorityState.URGENT -> 1f
        },
    )

    /** Speech changes articulation, never authority/health truth. */
    fun speechStarted(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        speech = VanSpeechState.SPEAKING,
        activity = if (frame.authority == VanAuthorityState.NONE) VanDurableState.SPEAKING else frame.activity,
    )

    fun speechFrame(frame: VanPresenceFrame, mouthOpen: Float, viseme: Int): VanPresenceFrame = frame.copy(
        speech = VanSpeechState.SPEAKING,
        activity = if (frame.authority == VanAuthorityState.NONE) VanDurableState.SPEAKING else frame.activity,
        mouthOpen = mouthOpen.coerceIn(0f, 1f),
        viseme = viseme.coerceAtLeast(0),
    )

    fun speechEnded(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        speech = VanSpeechState.QUIET,
        mouthOpen = 0f,
        viseme = 0,
        activity = if (frame.authority == VanAuthorityState.NONE && frame.turn == VanTurnPhase.IDLE) {
            VanDurableState.IDLE
        } else {
            frame.activity
        },
    )

    fun idle(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        activity = VanDurableState.IDLE,
        speech = VanSpeechState.QUIET,
        turn = VanTurnPhase.IDLE,
        mouthOpen = 0f,
        viseme = 0,
        urgency = if (frame.authority == VanAuthorityState.NONE) 0f else frame.urgency,
    )
}
