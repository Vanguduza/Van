package com.dial.van.events

import com.dial.van.runtime.RuntimePressure
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P3-AND-002 — the event stream, actually streamed.
 *
 * There was one `events(0)` call in the activity feed's initial composition. The cursor was
 * the literal zero, it was never persisted, and nothing polled again, so anything the
 * gateway published after that first composition never reached the owner.
 */
class EventStreamTest {

    private fun event(seq: Long) = EventRecord(seq, "mission.state", """{"n":$seq}""", seq)

    private fun page(vararg seqs: Long, truncated: Boolean = false) = EventPage(
        events = seqs.map(::event),
        nextCursor = seqs.maxOrNull() ?: 0L,
        truncated = truncated,
    )

    @Test
    fun `the cursor advances instead of staying at zero`() {
        var state = EventStreamState()
        assertEquals(0L, state.cursor)
        state = EventStream.applyPage(state, page(1, 2, 3))
        assertEquals(3L, state.cursor)
        state = EventStream.applyPage(state, page(4, 5))
        assertEquals(5L, state.cursor)
        assertEquals(5, state.events.size)
    }

    @Test
    fun `a restored cursor resumes instead of replaying everything`() {
        val store = InMemoryEventCursorStore(1_204L)
        val state = EventStreamState(cursor = store.load())
        assertEquals(1_204L, state.cursor)
    }

    @Test
    fun `a cursor is saved so a restart does not replay`() {
        val store = InMemoryEventCursorStore()
        var state = EventStreamState(cursor = store.load())
        state = EventStream.applyPage(state, page(7, 8))
        store.save(state.cursor)
        assertEquals(8L, InMemoryEventCursorStore(store.load()).load())
    }

    @Test
    fun `an overlapping page does not produce duplicate rows`() {
        // Happens whenever a persisted cursor is restored slightly behind the gateway.
        var state = EventStream.applyPage(EventStreamState(), page(1, 2, 3))
        state = EventStream.applyPage(state, page(2, 3, 4))
        assertEquals(listOf(4L, 3L, 2L, 1L), state.events.map { it.seq })
    }

    @Test
    fun `the cursor never rewinds`() {
        var state = EventStream.applyPage(EventStreamState(), page(50))
        state = EventStream.applyPage(state, EventPage(emptyList(), nextCursor = 10L, truncated = false))
        assertEquals(50L, state.cursor, "a low cursor from the gateway rewound the client")
    }

    @Test
    fun `newest events are kept and the list is bounded`() {
        var state = EventStreamState()
        state = EventStream.applyPage(state, EventPage(
            events = (1L..(EventStream.MAX_RETAINED + 50L)).map(::event),
            nextCursor = EventStream.MAX_RETAINED + 50L,
            truncated = false,
        ))
        assertEquals(EventStream.MAX_RETAINED, state.events.size)
        assertEquals(EventStream.MAX_RETAINED + 50L, state.events.first().seq)
    }

    @Test
    fun `a truncated page catches up immediately`() {
        // Waiting the idle interval per page would make catching up take pages x interval.
        val state = EventStream.applyPage(EventStreamState(), page(1, 2, truncated = true))
        assertEquals(EventStream.CATCH_UP_POLL_MS, EventStream.nextDelayMillis(state, true))
        assertEquals(EventStream.IDLE_POLL_MS, EventStream.nextDelayMillis(state, false))
    }

    @Test
    fun `failures back off exponentially and stop at a ceiling`() {
        var state = EventStreamState()
        val delays = mutableListOf<Long>()
        repeat(12) {
            state = EventStream.applyFailure(state, "gateway unreachable")
            // Non-null is the assertion, not a convenience: on a healthy device there is
            // always a next poll. Only the runtime envelope at SURVIVAL returns null
            // (P3-PERF-003), and a backoff that silently became "never" would look like a
            // very patient client and be a dead one.
            delays += assertNotNull(EventStream.nextDelayMillis(state, false))
        }
        assertEquals(EventStream.MIN_BACKOFF_MS, delays.first())
        assertTrue(delays[1] > delays[0], "the backoff did not grow")
        assertTrue(delays.all { it <= EventStream.MAX_BACKOFF_MS }, "the backoff has no ceiling")
        assertEquals(EventStream.MAX_BACKOFF_MS, delays.last())
    }

    @Test
    fun `a success clears the backoff`() {
        var state = EventStreamState()
        repeat(4) { state = EventStream.applyFailure(state, "down") }
        assertNotNull(state.error)
        state = EventStream.applyPage(state, page(9))
        assertNull(state.error)
        assertEquals(0, state.consecutiveFailures)
        assertEquals(EventStream.IDLE_POLL_MS, EventStream.nextDelayMillis(state, false))
    }

    @Test
    fun `a feed that failed is not a feed with nothing in it`() {
        // The distinction the audit kept finding collapsed. An unloaded stream and an empty
        // one are different things and the screen reads `loaded` to tell them apart.
        val fresh = EventStreamState()
        assertFalse(fresh.loaded)
        val empty = EventStream.applyPage(fresh, EventPage(emptyList(), 0L, false))
        assertTrue(empty.loaded)
        assertTrue(empty.events.isEmpty())
        val failed = EventStream.applyFailure(fresh, "gateway unreachable")
        assertFalse(failed.loaded)
        assertEquals("gateway unreachable", failed.error)
    }

    // ---- P3-PERF-003: the poll rate answers to the whole-runtime envelope ----------

    @Test
    fun `a constrained device polls the event stream less often`() {
        val state = EventStream.applyPage(EventStreamState(), page(1, 2))
        val healthy = assertNotNull(EventStream.nextDelayMillis(state, false, RuntimePressure.NOMINAL))
        val constrained =
            assertNotNull(EventStream.nextDelayMillis(state, false, RuntimePressure.CONSTRAINED))
        val critical =
            assertNotNull(EventStream.nextDelayMillis(state, false, RuntimePressure.CRITICAL))

        assertEquals(EventStream.IDLE_POLL_MS, healthy)
        assertTrue(constrained > healthy, "a constrained device polled as fast as a healthy one")
        assertTrue(critical > constrained, "pressure stopped stretching the cadence")
    }

    @Test
    fun `a device with minutes left stops polling rather than polling slowly`() {
        // Null is the answer, not a very large delay. A caller that received a number would
        // keep a coroutine alive holding a wake lock's worth of intent for nothing.
        val state = EventStream.applyPage(EventStreamState(), page(1))
        assertNull(EventStream.nextDelayMillis(state, false, RuntimePressure.SURVIVAL))
    }

    @Test
    fun `catching up is not slowed down`() {
        // A truncated page means the owner's screen is behind and more is already waiting.
        // Spacing out catch-up makes the device do the same total work over longer, which is
        // more battery and not less.
        val state = EventStream.applyPage(EventStreamState(), page(1, 2, truncated = true))
        for (pressure in RuntimePressure.entries) {
            if (!EventStream.pollsAt(pressure)) continue
            assertEquals(
                EventStream.CATCH_UP_POLL_MS,
                EventStream.nextDelayMillis(state, true, pressure),
                "catch-up was stretched at $pressure",
            )
        }
    }

    @Test
    fun `catch-up is immediate because the constant is zero, and that is load-bearing`() {
        // The property above holds by arithmetic rather than by a branch: any cadence scale
        // multiplied by zero is zero. That makes this constant load-bearing in a way its
        // name does not advertise, so changing it should mean re-reading the reasoning in
        // nextDelayMillis rather than discovering later that catch-up got slower under
        // pressure.
        assertEquals(0L, EventStream.CATCH_UP_POLL_MS)
    }

    @Test
    fun `the envelope never makes a stretched backoff exceed the ceiling`() {
        // MAX_BACKOFF_MS is what the gateway's operator can reason about. Multiplying a
        // backoff already at the ceiling would put the client hours away from recovering.
        var state = EventStreamState()
        repeat(12) { state = EventStream.applyFailure(state, "down") }
        val delay = assertNotNull(EventStream.nextDelayMillis(state, false, RuntimePressure.CRITICAL))
        assertEquals(EventStream.MAX_BACKOFF_MS, delay)
    }

    @Test
    fun `the default pressure changes nothing for a caller that has no reading`() {
        // A caller that silently got a slower stream from a default would be worse than one
        // that got no envelope at all.
        val state = EventStream.applyPage(EventStreamState(), page(1))
        assertEquals(
            EventStream.nextDelayMillis(state, false),
            EventStream.nextDelayMillis(state, false, RuntimePressure.NOMINAL),
        )
    }
}
