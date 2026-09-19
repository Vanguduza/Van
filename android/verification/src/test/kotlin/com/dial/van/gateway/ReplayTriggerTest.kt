package com.dial.van.gateway

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P3-AND-006 — `replayAsync()` was called once, at application start, with no connectivity
 * or health trigger. A command issued in a tunnel sat in the queue until the owner killed
 * and reopened the app, which for a resident floating assistant is approximately never.
 */
class ReplayTriggerTest {

    @Test
    fun `recovery replays a queue that has something in it`() {
        assertTrue(
            ReplayTrigger.shouldReplay(
                ReplayTriggerState(), ReplayReason.CONNECTIVITY_RECOVERED,
                nowMs = 10_000L, queuedCommands = 1,
            ),
        )
    }

    @Test
    fun `an empty queue is not replayed`() {
        assertFalse(
            ReplayTrigger.shouldReplay(
                ReplayTriggerState(), ReplayReason.CONNECTIVITY_RECOVERED,
                nowMs = 10_000L, queuedCommands = 0,
            ),
        )
    }

    @Test
    fun `a handover burst produces one replay, not four`() {
        // Wi-Fi drops, mobile takes over, Wi-Fi returns, all inside a second. One replay per
        // callback means the same queued command dispatched four times concurrently, and
        // relying on the gateway's idempotency keys for a client-side stampede is how a
        // backstop becomes load-bearing.
        var state = ReplayTriggerState()
        var replays = 0
        for (t in listOf(0L, 200L, 900L, 1_500L)) {
            if (ReplayTrigger.shouldReplay(state, ReplayReason.CONNECTIVITY_RECOVERED, t, 2)) {
                replays += 1
                state = ReplayTrigger.finished(ReplayTrigger.started(state, t))
            }
        }
        assertEquals(1, replays)
    }

    @Test
    fun `after the debounce window a genuinely new recovery replays again`() {
        val started = ReplayTrigger.finished(ReplayTrigger.started(ReplayTriggerState(), 0L))
        assertFalse(
            ReplayTrigger.shouldReplay(
                started, ReplayReason.CONNECTIVITY_RECOVERED,
                ReplayTrigger.DEBOUNCE_MS - 1, 2,
            ),
        )
        assertTrue(
            ReplayTrigger.shouldReplay(
                started, ReplayReason.CONNECTIVITY_RECOVERED, ReplayTrigger.DEBOUNCE_MS, 2,
            ),
        )
    }

    @Test
    fun `a replay already running is never started twice`() {
        val running = ReplayTrigger.started(ReplayTriggerState(), 0L)
        for (reason in ReplayReason.entries) {
            assertFalse(
                ReplayTrigger.shouldReplay(running, reason, 100_000L, 5),
                reason.name,
            )
        }
    }

    @Test
    fun `the owner pressing the button is never debounced`() {
        val justReplayed = ReplayTrigger.finished(ReplayTrigger.started(ReplayTriggerState(), 0L))
        assertTrue(
            ReplayTrigger.shouldReplay(justReplayed, ReplayReason.OWNER_REQUESTED, 10L, 0),
            "the owner pressed a button and is watching",
        )
    }

    @Test
    fun `only the edge into availability is a recovery`() {
        val down = ReplayTriggerState(lastNetworkAvailable = false)
        assertTrue(ReplayTrigger.networkRecovered(down, available = true))
        val up = ReplayTrigger.observedNetwork(down, available = true)
        // The callback fires repeatedly while the network is up. Replaying on the level
        // rather than the edge is a loop.
        assertFalse(ReplayTrigger.networkRecovered(up, available = true))
        assertFalse(ReplayTrigger.networkRecovered(up, available = false))
        assertTrue(
            ReplayTrigger.networkRecovered(ReplayTrigger.observedNetwork(up, false), true),
        )
    }

    @Test
    fun `the gateway coming back is its own edge`() {
        val unreachable = ReplayTriggerState(lastGatewayReachable = false)
        assertTrue(ReplayTrigger.gatewayRecovered(unreachable, reachable = true))
        val reachable = ReplayTrigger.observedGateway(unreachable, reachable = true)
        assertFalse(ReplayTrigger.gatewayRecovered(reachable, reachable = true))
    }
}
