package com.dial.van.visual

import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * Main-thread visual-state arbiter shared by the floating overlay and live I/O sources.
 *
 * This is deliberately a visual presence controller, not a claim of consciousness. It gives VAN
 * attention-aware, lifelike continuity: transient voice/task states are held long enough to read,
 * weak transitions cannot flicker over stronger ones, and returning to idle is eased rather than
 * snapping on every speech/listening callback.
 *
 * [current] is Compose snapshot state. Reading it during composition registers observation, so the
 * existing overlay can react without polling or owning a second animation loop.
 */
object VanLiveVisualState {
    private const val IDLE_SETTLE_MS = 420L
    private const val TRANSIENT_HOLD_MS = 320L

    private val main = Handler(Looper.getMainLooper())
    private var generation = 0L
    private var stateStartedAtMs = 0L

    var current: VanVisualState by mutableStateOf(VanVisualState())
        private set

    fun transition(
        state: VanDurableState,
        urgency: Float = current.urgency,
        listening: Boolean = state == VanDurableState.LISTENING,
        speaking: Boolean = state == VanDurableState.SPEAKING,
    ) = onMain {
        val now = SystemClock.uptimeMillis()
        val nextPriority = priority(state)
        val currentPriority = priority(current.durableState)
        val insideHold = now - stateStartedAtMs < TRANSIENT_HOLD_MS

        // Safety/error truth and direct owner interaction always win immediately. A low-priority
        // cosmetic transition may not erase a stronger state during its minimum readable hold.
        if (insideHold && nextPriority < currentPriority && !isCritical(state)) return@onMain

        generation += 1L
        stateStartedAtMs = now
        current = current.copy(
            durableState = state,
            listening = listening,
            speaking = speaking,
            urgency = urgency.coerceIn(0f, 1f),
            mouthOpen = if (speaking) current.mouthOpen else 0f,
        )
    }

    fun settleToIdle(delayMs: Long = IDLE_SETTLE_MS) = onMain {
        val token = ++generation
        main.postDelayed({
            if (token != generation) return@postDelayed
            if (isCritical(current.durableState)) return@postDelayed
            stateStartedAtMs = SystemClock.uptimeMillis()
            current = current.copy(
                durableState = VanDurableState.IDLE,
                listening = false,
                speaking = false,
                mouthOpen = 0f,
                viseme = 0,
                urgency = 0f,
            )
        }, delayMs.coerceAtLeast(0L))
    }

    fun speechFrame(mouthOpen: Float, viseme: Int) = onMain {
        generation += 1L
        current = current.copy(
            durableState = VanDurableState.SPEAKING,
            speaking = true,
            listening = false,
            mouthOpen = mouthOpen.coerceIn(0f, 1f),
            viseme = viseme.coerceAtLeast(0),
        )
    }

    /** Allows future pointer/voice/vision integrations to steer gaze without changing state. */
    fun attention(x: Float, y: Float) = onMain {
        current = current.copy(
            attentionX = x.coerceIn(-1f, 1f),
            attentionY = y.coerceIn(-1f, 1f),
        )
    }

    fun action(action: VanFiniteAction?) = onMain {
        current = current.copy(actionCode = action?.code ?: 0)
    }

    /** Clears one-shot action without disturbing the durable state or gaze. */
    fun clearAction() = action(null)

    private fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else main.post(block)
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
