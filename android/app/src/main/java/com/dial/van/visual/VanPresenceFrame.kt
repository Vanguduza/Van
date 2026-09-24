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
    /**
     * P1-AURA-003 — live trading state, as a semantic fact alongside the others.
     *
     * Orthogonal like everything else in this frame: VAN can be listening to the owner while
     * a position is under risk pressure, and both must be true at once. Null means no trading
     * state has been published, which is different from [VanTradeSemantic.FLAT] ("nothing is
     * open") and from [VanTradeSemantic.UNKNOWN] ("I cannot read the ledger").
     */
    val trade: VanTradeSemantic? = null,
    /** Aura Rev 2 — counts closed positions, so the field can pulse once per close. */
    val tradeClosePulse: Int = 0,
) {
    /** DEGRADED does not suppress local activity; OFFLINE uplink truth does. */
    val poseState: VanDurableState
        get() {
            if (health == VanHealthState.OFFLINE) return VanDurableState.OFFLINE
            return when (authority) {
                VanAuthorityState.WAITING_FOR_OWNER -> VanDurableState.WAITING_FOR_OWNER
                VanAuthorityState.WARNING -> VanDurableState.WARNING
                VanAuthorityState.ERROR -> VanDurableState.ERROR
                VanAuthorityState.URGENT -> VanDurableState.URGENT
                VanAuthorityState.NONE -> when (speech) {
                    VanSpeechState.SPEAKING -> VanDurableState.SPEAKING
                    VanSpeechState.LISTENING -> VanDurableState.LISTENING
                    VanSpeechState.QUIET -> activity
                }
            }
        }

    /** Outer semantic field/chrome truth. */
    val semanticState: VanDurableState
        get() {
            if (health == VanHealthState.OFFLINE) return VanDurableState.OFFLINE
            return when (authority) {
                VanAuthorityState.WAITING_FOR_OWNER -> VanDurableState.WAITING_FOR_OWNER
                VanAuthorityState.WARNING -> VanDurableState.WARNING
                VanAuthorityState.ERROR -> VanDurableState.ERROR
                VanAuthorityState.URGENT -> VanDurableState.URGENT
                // P1-AURA-003 — a trade state the owner has to act on reaches the outer
                // field, below explicit authority (an owner approval outranks a market) and
                // above ordinary health. It never reaches the pose from here: semantic
                // colour lives in Zone C, not on VAN's body (Rev 2.2).
                VanAuthorityState.NONE -> tradeSemanticState()
                    ?: when (health) {
                        VanHealthState.DEGRADED -> VanDurableState.DEGRADED
                        VanHealthState.NOMINAL -> poseState
                        VanHealthState.OFFLINE -> VanDurableState.OFFLINE
                    }
            }
        }

    private fun tradeSemanticState(): VanDurableState? {
        val semantic = trade ?: return null
        // A degraded subsystem still outranks a calm market: the reason VAN cannot be
        // trusted is more urgent than the fact that nothing is happening.
        val derived = VanTradeSemantics.durableStateFor(semantic) ?: return null
        if (health == VanHealthState.DEGRADED && derived == VanDurableState.DEGRADED) {
            return VanDurableState.DEGRADED
        }
        return derived
    }

    /**
     * Aura Rev 2 — which trade, if any, shapes the outer field. Explicit authority (an owner
     * approval, a warning, an error, urgent) and offline truth outrank a market; a degraded
     * subsystem outranks a calm market. What is left drives the field's colour and energy.
     */
    private fun tradeAuraSemantic(): VanTradeSemantic? {
        val semantic = trade ?: return null
        if (health == VanHealthState.OFFLINE || authority != VanAuthorityState.NONE) return null
        if (health == VanHealthState.DEGRADED && VanTradeSemantics.durableStateFor(semantic) == null) return null
        return semantic
    }

    fun toVisualState(): VanVisualState = VanVisualState(
        durableState = poseState,
        semanticState = semanticState,
        speaking = health != VanHealthState.OFFLINE && speech == VanSpeechState.SPEAKING,
        listening = health != VanHealthState.OFFLINE && speech == VanSpeechState.LISTENING,
        attentionX = attentionX.coerceIn(-1f, 1f),
        attentionY = attentionY.coerceIn(-1f, 1f),
        mouthOpen = if (health == VanHealthState.OFFLINE) 0f else mouthOpen.coerceIn(0f, 1f),
        urgency = urgency.coerceIn(0f, 1f),
        viseme = if (health == VanHealthState.OFFLINE) 0 else viseme.coerceAtLeast(0),
        actionCode = actionCode,
        trade = tradeAuraSemantic(),
        auraPulseGeneration = tradeClosePulse,
    )
}

/** Pure reducer used by the Android runtime and JVM tests. */
object VanPresenceReducer {
    /**
     * P1-AURA-003 — publish a classified trade state onto the presence frame.
     *
     * A reducer rather than a direct `copy` so the one place that decides what a trade state
     * does to VAN is the same place that decides what voice and health do, and so the JVM
     * tests exercise the production transition rather than an imitation of it.
     */
    fun trade(frame: VanPresenceFrame, semantic: VanTradeSemantic?): VanPresenceFrame {
        if (frame.trade == semantic) return frame
        // A live position that becomes flat (or merely watched/setting up) has closed: the
        // field answers with one brief white expansion, then returns to the new state.
        val closed = frame.trade?.isLive == true && semantic != null && !semantic.isLive &&
            (semantic == VanTradeSemantic.FLAT || semantic == VanTradeSemantic.WATCHING || semantic == VanTradeSemantic.SETUP)
        return frame.copy(trade = semantic, tradeClosePulse = frame.tradeClosePulse + if (closed) 1 else 0)
    }

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

    /**
     * Speech is an articulation channel, not an activity transition. [VanPresenceFrame.poseState]
     * gives SPEAKING temporary visual precedence while preserving THINKING/DELEGATING/WORKING
     * underneath so the correct activity automatically reappears when TTS ends.
     */
    fun speechStarted(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        speech = VanSpeechState.SPEAKING,
    )

    fun speechFrame(frame: VanPresenceFrame, mouthOpen: Float, viseme: Int): VanPresenceFrame = frame.copy(
        speech = VanSpeechState.SPEAKING,
        mouthOpen = mouthOpen.coerceIn(0f, 1f),
        viseme = viseme.coerceAtLeast(0),
    )

    fun speechEnded(frame: VanPresenceFrame): VanPresenceFrame = frame.copy(
        speech = VanSpeechState.QUIET,
        mouthOpen = 0f,
        viseme = 0,
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
