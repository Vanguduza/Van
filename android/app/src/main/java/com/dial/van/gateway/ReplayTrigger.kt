package com.dial.van.gateway

/**
 * When the offline queue should be drained.
 *
 * P3-AND-006. `replayAsync()` was called exactly once, at application start, with no
 * connectivity trigger and no health trigger. So a command the owner issued in a tunnel sat
 * in the queue until they next killed and reopened the app — which for a floating assistant
 * that is meant to stay resident is approximately never. The queue worked perfectly and
 * nothing ever emptied it.
 *
 * The duplicate suppression is the part worth care. Connectivity callbacks fire in bursts —
 * Wi-Fi drops, mobile data takes over, Wi-Fi returns, all within a second — and a replay per
 * callback means the same queued command dispatched several times concurrently. The
 * gateway's idempotency keys would catch it, but relying on a server-side backstop for a
 * client-side stampede is how the backstop becomes load-bearing.
 */
enum class ReplayReason {
    /** The app started. */
    APP_START,

    /** The device went from no network to some network. */
    CONNECTIVITY_RECOVERED,

    /** The gateway went from unreachable to reachable. */
    GATEWAY_RECOVERED,

    /** Something was just queued while offline. */
    QUEUE_GREW,

    /** The owner asked. */
    OWNER_REQUESTED,
}

data class ReplayTriggerState(
    /**
     * Null means never, which is not the same as "at time zero".
     *
     * A `0L` default is read as a replay that happened at the epoch of whatever clock is
     * passed in. With `elapsedRealtime` that clock starts at boot, so on a phone that has
     * just started — exactly when the queue is fullest and the first network callback
     * arrives — the debounce would suppress the very first replay.
     */
    val lastReplayStartedAtMs: Long? = null,
    val replayInFlight: Boolean = false,
    val lastNetworkAvailable: Boolean = false,
    val lastGatewayReachable: Boolean = false,
)

object ReplayTrigger {

    /**
     * Two replays closer together than this are the same event. Sized to cover a Wi-Fi to
     * mobile handover, which is the burst that produces the duplicates.
     */
    const val DEBOUNCE_MS = 3_000L

    /** Whether to start a replay now, given why and what is already happening. */
    fun shouldReplay(
        state: ReplayTriggerState,
        reason: ReplayReason,
        nowMs: Long,
        queuedCommands: Int,
    ): Boolean {
        if (state.replayInFlight) return false
        if (queuedCommands <= 0 && reason != ReplayReason.OWNER_REQUESTED) return false
        // The owner asking is never debounced. They pressed a button and are watching.
        if (reason == ReplayReason.OWNER_REQUESTED) return true
        val last = state.lastReplayStartedAtMs ?: return true
        return nowMs - last >= DEBOUNCE_MS
    }

    /**
     * The transition, not the level.
     *
     * A connectivity callback fires with `available = true` repeatedly while the network is
     * up; replaying on each would be a loop. Only the edge from unavailable to available is
     * a recovery.
     */
    fun networkRecovered(state: ReplayTriggerState, available: Boolean): Boolean =
        available && !state.lastNetworkAvailable

    fun gatewayRecovered(state: ReplayTriggerState, reachable: Boolean): Boolean =
        reachable && !state.lastGatewayReachable

    fun started(state: ReplayTriggerState, nowMs: Long): ReplayTriggerState =
        state.copy(lastReplayStartedAtMs = nowMs, replayInFlight = true)

    fun finished(state: ReplayTriggerState): ReplayTriggerState =
        state.copy(replayInFlight = false)

    fun observedNetwork(state: ReplayTriggerState, available: Boolean): ReplayTriggerState =
        state.copy(lastNetworkAvailable = available)

    fun observedGateway(state: ReplayTriggerState, reachable: Boolean): ReplayTriggerState =
        state.copy(lastGatewayReachable = reachable)
}
