package com.dial.van.visual

import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * Application-scoped visual presence runtime.
 *
 * The mutable Android shell is intentionally thin: all semantic transitions are delegated to the
 * pure [VanPresenceReducer], while this object provides main-thread delivery, readable holds and
 * delayed idle settling. The actual truth model is orthogonal in [VanPresenceFrame].
 */
object VanLiveVisualState {
    private const val IDLE_SETTLE_MS = 420L
    private const val TRANSIENT_HOLD_MS = 320L

    private val main by lazy(LazyThreadSafetyMode.SYNCHRONIZED) { Handler(Looper.getMainLooper()) }
    private var generation = 0L
    private var stateStartedAtMs = 0L

    /** Separate from [generation] — see [action]'s doc for why. */
    private var actionGeneration = 0L

    var frame: VanPresenceFrame by mutableStateOf(VanPresenceFrame())
        private set

    /** Backwards-compatible renderer view. Reading this observes [frame] in Compose. */
    val current: VanVisualState
        get() = frame.toVisualState()

    fun listeningStarted() = mutate { VanPresenceReducer.listeningStarted(it) }

    /** Ending microphone capture does not settle the owner turn to idle. */
    fun listeningEnded() = mutate { VanPresenceReducer.listeningEnded(it) }

    fun finalTranscript(hasText: Boolean) = mutate { VanPresenceReducer.finalTranscript(it, hasText) }

    fun dispatchStarted() = mutate { VanPresenceReducer.dispatchStarted(it) }

    /**
     * Gateway acceptance means delegated/in-flight, never SUCCESS.
     *
     * GAP-F-012 — this is the real call site `VanGatewayClient.dispatchCommand` reaches on an
     * `accepted`/`in_flight`/`submitted`/`executing`/`verifying` response, so it is also
     * ACK_NOD's producer (DNA §6: "ACK_NOD: command accepted") rather than a second,
     * unreachable path for the same fact.
     */
    fun dispatchAccepted() = mutate {
        it.copy(
            activity = VanDurableState.WORKING,
            turn = VanTurnPhase.IDLE,
            speech = VanSpeechState.QUIET,
            authority = VanAuthorityState.NONE,
            urgency = 0f,
        )
    }.also { action(VanFiniteAction.ACK_NOD) }

    /** GAP-F-012 — CAUTION's producer for the approval-required half of DNA §6's rule. */
    fun waitingForOwner() = mutate {
        VanPresenceReducer.authority(it, VanAuthorityState.WAITING_FOR_OWNER)
    }.also { action(VanFiniteAction.CAUTION) }

    fun clearAuthority() = mutate { VanPresenceReducer.authority(it, VanAuthorityState.NONE) }

    /**
     * GAP-F-012 — `VanGatewayClient.publishCommandVisualStatus` calls this from two branches
     * that share this one method and differ only by [urgency]: `degraded`/`UNVERIFIABLE`/
     * `VERIFICATION_FAILED`/`PARTIAL_SUCCESS` at 0.35, and `denied`/`expired`/`rejected`/
     * `failed`/`error` at 0.40 (a local ASR failure also lands here, at 0.25). DNA §6 gives
     * SHRUG to the "uncertain outcome" cases, which is the lower band; the higher band is a
     * plain failure with no action of its own. `VanGatewayClient.kt` is out of scope for this
     * change, so the literal status string never reaches here — the urgency value already
     * varies by call site and is the only signal available to tell the two apart.
     */
    fun warning(urgency: Float = 0.35f) = mutate {
        VanPresenceReducer.authority(it, VanAuthorityState.WARNING).copy(urgency = urgency.coerceIn(0f, 1f))
    }.also { if (urgency <= 0.35f) action(VanFiniteAction.SHRUG) }

    fun error(urgency: Float = 0.75f) = mutate {
        VanPresenceReducer.authority(it, VanAuthorityState.ERROR).copy(urgency = urgency.coerceIn(0f, 1f))
    }

    /**
     * GAP-F-012 — URGENT's producer is `VanEmbodimentReducer.forAttentionEvent` reacting to
     * an `attention.upserted` severity-URGENT record off the event stream (wired in
     * `VanApplication`); this is the method it calls. It had no caller anywhere in the app
     * before that wiring existed, which is the "dead path" the embodiment audit found.
     */
    fun urgent() = mutate {
        VanPresenceReducer.authority(it, VanAuthorityState.URGENT)
    }.also { action(VanFiniteAction.CAUTION) }

    fun speakingStarted() = mutate { VanPresenceReducer.speechStarted(it) }

    fun speakingEnded() = mutate { VanPresenceReducer.speechEnded(it) }

    fun speechFrame(mouthOpen: Float, viseme: Int) = mutate {
        VanPresenceReducer.speechFrame(it, mouthOpen, viseme)
    }

    /**
     * Generic activity bridge kept for task/gateway callers. Critical states become authority.
     *
     * GAP-F-012 — `VanGatewayClient.publishCommandVisualStatus` calls `transition(SUCCESS)`
     * on the synchronous `VERIFIED_SUCCESS`/`verified_success`/`succeeded`/`success`/
     * `completed` command response, which makes this CONFIRM's producer for DNA §6's
     * "CONFIRM: VERIFIED_SUCCESS". A mission completing asynchronously off the event stream
     * is a different moment and gets PRESENT_CARD instead — see
     * `VanEmbodimentReducer.forMissionEvent`, which passes [finiteAction] explicitly to
     * override the default below rather than fighting it after the fact.
     */
    fun transition(
        state: VanDurableState,
        urgency: Float = 0f,
        listening: Boolean = state == VanDurableState.LISTENING,
        speaking: Boolean = state == VanDurableState.SPEAKING,
        finiteAction: VanFiniteAction? = defaultActionFor(state),
    ) = onMain {
        val now = SystemClock.uptimeMillis()
        val nextPriority = priority(state)
        val currentPriority = priority(frame.poseState)
        val insideHold = now - stateStartedAtMs < TRANSIENT_HOLD_MS
        if (insideHold && nextPriority < currentPriority && !isDirectInteraction(state) && !isCritical(state)) {
            return@onMain
        }

        generation += 1L
        stateStartedAtMs = now
        frame = when (state) {
            VanDurableState.WAITING_FOR_OWNER ->
                VanPresenceReducer.authority(frame, VanAuthorityState.WAITING_FOR_OWNER)
            VanDurableState.WARNING ->
                VanPresenceReducer.authority(frame, VanAuthorityState.WARNING).copy(urgency = urgency.coerceIn(0f, 1f))
            VanDurableState.ERROR ->
                VanPresenceReducer.authority(frame, VanAuthorityState.ERROR).copy(urgency = urgency.coerceIn(0f, 1f))
            VanDurableState.URGENT -> VanPresenceReducer.authority(frame, VanAuthorityState.URGENT)
            VanDurableState.LISTENING -> VanPresenceReducer.listeningStarted(frame)
            VanDurableState.SPEAKING -> VanPresenceReducer.speechStarted(frame)
            else -> frame.copy(
                activity = state,
                speech = when {
                    speaking -> VanSpeechState.SPEAKING
                    listening -> VanSpeechState.LISTENING
                    else -> VanSpeechState.QUIET
                },
                urgency = urgency.coerceIn(0f, 1f),
            )
        }
        if (finiteAction != null) action(finiteAction)
    }

    /** The action a bare `transition(state)` implies when the caller does not name one. */
    private fun defaultActionFor(state: VanDurableState): VanFiniteAction? = when (state) {
        VanDurableState.SUCCESS -> VanFiniteAction.CONFIRM
        else -> null
    }

    /**
     * Settles only after the owner turn has actually ended. allowCritical is reserved for local,
     * time-bounded indications (for example SpeechRecognizer failure), and clears that transient
     * authority before idling; subsystem health truth is held separately by [VanPresence].
     */
    fun settleToIdle(
        delayMs: Long = IDLE_SETTLE_MS,
        allowCritical: Boolean = false,
    ) = onMain {
        val token = ++generation
        main.postDelayed({
            if (token != generation) return@postDelayed
            if (frame.turn != VanTurnPhase.IDLE) return@postDelayed
            if (!allowCritical && frame.authority != VanAuthorityState.NONE) return@postDelayed
            stateStartedAtMs = SystemClock.uptimeMillis()
            val cleared = if (allowCritical) {
                VanPresenceReducer.authority(frame, VanAuthorityState.NONE)
            } else {
                frame
            }
            frame = VanPresenceReducer.idle(cleared)
        }, delayMs.coerceAtLeast(0L))
    }

    fun attention(x: Float, y: Float) = mutate {
        it.copy(attentionX = x.coerceIn(-1f, 1f), attentionY = y.coerceIn(-1f, 1f))
    }

    /**
     * P1-AURA-003 — the trading system's only route into VAN's visual state.
     *
     * Called by the trading screen from the same gateway read models it renders from, so the
     * field and the numbers on screen cannot disagree. Passing null clears it, which is what
     * leaving the trading surface should do: VAN should not keep showing a trade field
     * because the owner once looked at a position.
     */
    fun tradeSemantic(semantic: VanTradeSemantic?) = mutate {
        VanPresenceReducer.trade(it, semantic)
    }

    /**
     * DNA §6 — "Every action must auto-clear after its duration". [VanMotionMap] names how
     * long each gesture plays; this schedules [clearAction] itself rather than asking every
     * producer to remember to. A separate `actionGeneration` token (not the frame's shared
     * `generation`) so an unrelated state change does not also cancel a still-playing gesture,
     * and so a second action fired before the first clears re-arms the timer instead of the
     * first action's stale callback clearing the second one early.
     */
    fun action(action: VanFiniteAction?) = onMain {
        frame = frame.copy(actionCode = action?.code ?: 0)
        actionGeneration += 1L
        if (action != null) {
            val token = actionGeneration
            main.postDelayed({
                if (token != actionGeneration) return@postDelayed
                frame = frame.copy(actionCode = 0)
            }, VanMotionMap.actionDurationMs(action))
        }
    }

    fun clearAction() = action(null)

    internal fun resetForTest() = onMain {
        generation += 1L
        actionGeneration += 1L
        stateStartedAtMs = 0L
        frame = VanPresenceFrame()
    }

    private fun mutate(reducer: (VanPresenceFrame) -> VanPresenceFrame) = onMain {
        generation += 1L
        stateStartedAtMs = SystemClock.uptimeMillis()
        frame = reducer(frame)
    }

    private fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else main.post(block)
    }

    private fun isDirectInteraction(state: VanDurableState): Boolean = when (state) {
        VanDurableState.ATTENTIVE, VanDurableState.LISTENING, VanDurableState.SPEAKING -> true
        else -> false
    }

    private fun isCritical(state: VanDurableState): Boolean = when (state) {
        VanDurableState.OFFLINE,
        VanDurableState.DEGRADED,
        VanDurableState.WARNING,
        VanDurableState.ERROR,
        VanDurableState.URGENT,
        VanDurableState.WAITING_FOR_OWNER,
        -> true
        else -> false
    }

    /**
     * The ladder lives in [VanStatePriority] so the browser arbitration (Rev 1.5 §24) asks
     * the same question this does. It was private here, which is why §24 would otherwise
     * have needed a second copy — and two copies of a precedence ordering diverge on the
     * state that matters.
     */
    private fun priority(state: VanDurableState): Int = VanStatePriority.of(state)
}
