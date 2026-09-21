package com.dial.van.events

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Rev 1.5 §§5.6, 20.1 — one history, two carriers.
 *
 * The socket pushes and the REST floor polls, and they overlap by design. What must not
 * happen is the owner reading the same event twice, or the cursor going backwards and
 * replaying a morning they have already seen.
 */
class VanEventStreamStoreTest {

    private class Cursor(var value: Long = 0L) : EventCursorStore {
        var saves = 0
            private set
        override fun load(): Long = value
        override fun save(cursor: Long) { value = cursor; saves += 1 }
    }

    private fun page(vararg seqs: Long, truncated: Boolean = false) = EventPage(
        events = seqs.map { EventRecord(it, "mission.completed", """{"n":$it}""", 1) },
        nextCursor = seqs.maxOrNull() ?: 0L,
        truncated = truncated,
    )

    @Test
    fun `the history starts where the last one stopped`() {
        // The reason it is not a composable's `remember`: reopening a screen must not
        // restart the owner's day.
        val store = VanEventStreamStore(Cursor(value = 91L))
        assertEquals(91L, store.cursor())
    }

    @Test
    fun `a page from the socket and a page from the poll do not double an event`() {
        // Both carriers deliver seq 42 — which is the ordinary case, not a rare one,
        // because the poll is still running when the socket pushes.
        val store = VanEventStreamStore(Cursor())
        store.apply(page(41, 42))
        store.apply(page(42, 43))
        assertEquals(listOf(43L, 42L, 41L), store.state.value.events.map { it.seq })
    }

    @Test
    fun `the cursor is saved from the merged state rather than from the page`() {
        // `applyPage` refuses to rewind. Saving the page's own cursor would write a lower
        // number than the device holds and ask the Gateway to send it all again.
        val cursor = Cursor()
        val store = VanEventStreamStore(cursor)
        store.apply(page(41, 42, 43))
        assertEquals(43L, cursor.value)
        store.apply(EventPage(events = emptyList(), nextCursor = 7L, truncated = false))
        assertEquals(43L, cursor.value, "the cursor went backwards and the owner sees it twice")
    }

    @Test
    fun `a failure is counted without discarding what the owner already has`() {
        val store = VanEventStreamStore(Cursor())
        store.apply(page(41))
        store.fail("Unable to load activity")
        assertEquals(1, store.state.value.events.size)
        assertEquals("Unable to load activity", store.state.value.error)
        assertEquals(1, store.state.value.consecutiveFailures)
    }

    @Test
    fun `a recovery clears the failure`() {
        val store = VanEventStreamStore(Cursor())
        store.fail("gone")
        store.apply(page(41))
        assertEquals(null, store.state.value.error)
        assertTrue(store.state.value.loaded)
    }

    @Test
    fun `every applied page is written down`() {
        // Not once at the end: a process death between a merge and a save would show the
        // owner events the device would then ask for again.
        val cursor = Cursor()
        val store = VanEventStreamStore(cursor)
        store.apply(page(41))
        store.apply(page(42))
        assertEquals(2, cursor.saves)
    }
}
