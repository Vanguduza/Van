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

    /** Gateway acceptance means delegated/in-flight, never SUCCESS. */
    fun dispatchAccepted() = transition(VanDurableState.WORKING)

    fun waitingForOwner() = mutate { VanPresenceReducer.authority(it, VanAuthorityState.WAITING_FOR_OWNER) }

    fun clearAuthority() = mutate { VanPresenceReducer.authority(it, VanAuthorityState.NONE) }

    fun warning(urgency: Float = 0.35f) = mutate {
        VanPresenceReducer.authority(it, VanAuthorityState.WARNING).copy(urgency = urgency.coerceIn(0f, 1f))
    }

    fun error(urgency: Float = 0.75f) = mutate {
        VanPresenceReducer.authority(it, VanAuthorityState.ERROR).copy(urgency = urgency.coerceIn(0f, 1f))
    }

    fun urgent() = mutate { VanPresenceReducer.authority(it, VanAuthorityState.URGENT) }

    fun speakingStarted() = mutate { VanPresenceReducer.speechStarted(it) }

    fun speakingEnded() = mutate { VanPresenceReducer.speechEnded(it) }

    fun speechFrame(mouthOpen: Float, viseme: Int) = mutate {
        VanPresenceReducer.speechFrame(it, mouthOpen, viseme)
    }

    /** Generic activity bridge kept for task/gateway callers. Critical states become authority. */
    fun transition(
        state: VanDurableState,
        urgency: Float = 0f,
        listening: Boolean = state == VanDurableState.LISTENING,
        speaking: Boolean = state == VanDurableState.SPEAKING,
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
    }

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
            frame = VanPresenceReducer.idle(frame)
        }, delayMs.coerceAtLeast(0L))
    }

    fun attention(x: Float, y: Float) = mutate {
        it.copy(attentionX = x.coerceIn(-1f, 1f), attentionY = y.coerceIn(-1f, 1f))
    }

    fun action(action: VanFiniteAction?) = mutate { it.copy(actionCode = action?.code ?: 0) }

    fun clearAction() = action(null)

    /** Test/debug hook; production callers should transition rather than reset. */
    internal fun resetForTest() = onMain {
        generation += 1L
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

    private fun priority(state: VanDurableState): Int = when (state) {
        VanDurableState.ERROR, VanDurableState.URGENT -> 100
        VanDurableState.OFFLINE -> 95
        VanDurableState.DEGRADED, VanDurableState.WARNING -> 90
        VanDurableState.WAITING_FOR_OWNER -> 80
        VanDurableState.SPEAKING, VanDurableState.LISTENING -> 70
        VanDurableState.WORKING, VanDurableState.SEARCHING, VanDurableState.DELEGATING -> 60
        VanDurableState.THINKING, VanDurableState.CONNECTING, VanDurableState.ATTENTIVE -> 50
        VanDurableState.SUCCESS -> 45
        VanDurableState.WAITING -> 30
        VanDurableState.IDLE, VanDurableState.SLEEPING -> 10
    }
}
