package com.dial.van.design

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class ScreenStateTest {

    // ---- DegradedCatalog --------------------------------------------------------------

    @Test
    fun `known subsystem keys get their owner sentence`() {
        val rows = DegradedCatalog.rowsFor(listOf("trading", "voice"))
        assertEquals(2, rows.size)
        assertEquals("trading", rows[0].subsystem)
        assertTrue(rows[0].sentence.contains("Trading"))
        assertEquals("voice", rows[1].subsystem)
    }

    @Test
    fun `unknown subsystem keys still get a sentence, not dropped`() {
        val rows = DegradedCatalog.rowsFor(listOf("some_new_subsystem"))
        assertEquals(1, rows.size)
        assertEquals("some_new_subsystem", rows[0].subsystem)
        assertTrue(rows[0].sentence.isNotBlank())
        assertTrue(rows[0].sentence.contains("degraded", ignoreCase = true))
    }

    @Test
    fun `blank subsystem keys are dropped`() {
        assertEquals(emptyList(), DegradedCatalog.rowsFor(listOf("", "  ")))
    }

    @Test
    fun `health json array parses into rows`() {
        val rows = DegradedCatalog.rowsFromHealthJson("""["trading","gateway"]""")
        assertEquals(listOf("trading", "gateway"), rows.map { it.subsystem })
    }

    @Test
    fun `malformed health json yields no rows rather than throwing`() {
        assertEquals(emptyList(), DegradedCatalog.rowsFromHealthJson("not json"))
        assertEquals(emptyList(), DegradedCatalog.rowsFromHealthJson("""{"degraded":["trading"]}"""))
    }

    @Test
    fun `non-string entries in the health array are ignored`() {
        val rows = DegradedCatalog.rowsFromHealthJson("""["trading", 42, null, "voice"]""")
        assertEquals(listOf("trading", "voice"), rows.map { it.subsystem })
    }

    // ---- ScreenStateMerge ---------------------------------------------------------------

    @Test
    fun `no content and loading is Loading`() {
        val state = ScreenStateMerge.merge<String>(content = null, loading = true)
        assertIs<ScreenState.Loading>(state)
    }

    @Test
    fun `no content, not loading, with an error is Error`() {
        val state = ScreenStateMerge.merge<String>(content = null, errorMessage = "network down")
        val error = assertIs<ScreenState.Error>(state)
        assertEquals("network down", error.message)
    }

    @Test
    fun `no content and queued offline work is Offline, ahead of a stale error message`() {
        val state = ScreenStateMerge.merge<String>(
            content = null,
            errorMessage = "network down",
            offlineQueuedCount = 3,
        )
        val offline = assertIs<ScreenState.Offline>(state)
        assertEquals(3, offline.queuedCount)
    }

    @Test
    fun `no content, no loading, no error is Empty with the given sentence`() {
        val state = ScreenStateMerge.merge<String>(content = null, emptySentence = "Nothing yet.")
        val empty = assertIs<ScreenState.Empty>(state)
        assertEquals("Nothing yet.", empty.sentence)
    }

    @Test
    fun `content with no staleness or degradation is plain Content`() {
        val state = ScreenStateMerge.merge(content = "positions")
        val content = assertIs<ScreenState.Content<String>>(state)
        assertEquals("positions", content.data)
    }

    @Test
    fun `content with degraded subsystems and no staleness is Degraded, carrying the content`() {
        val state = ScreenStateMerge.merge(content = "positions", degradedSubsystems = listOf("trading"))
        val degraded = assertIs<ScreenState.Degraded<String>>(state)
        assertEquals("positions", degraded.data)
        assertEquals("trading", degraded.rows.single().subsystem)
    }

    @Test
    fun `stale overrides content`() {
        val state = ScreenStateMerge.merge(content = "positions", ageMs = 120_000L)
        val stale = assertIs<ScreenState.Stale<String>>(state)
        assertEquals(120_000L, stale.ageMs)
        assertEquals("positions", stale.content)
    }

    @Test
    fun `stale overrides degraded too — merge rule is stale first`() {
        val state = ScreenStateMerge.merge(
            content = "positions",
            degradedSubsystems = listOf("trading"),
            ageMs = 120_000L,
        )
        assertIs<ScreenState.Stale<String>>(state)
    }

    @Test
    fun `age below the stale threshold does not trigger staleness`() {
        val state = ScreenStateMerge.merge(
            content = "positions",
            ageMs = ScreenStateMerge.DEFAULT_STALE_THRESHOLD_MS - 1,
        )
        assertIs<ScreenState.Content<String>>(state)
    }

    @Test
    fun `age at exactly the threshold is stale`() {
        val state = ScreenStateMerge.merge(
            content = "positions",
            ageMs = ScreenStateMerge.DEFAULT_STALE_THRESHOLD_MS,
        )
        assertIs<ScreenState.Stale<String>>(state)
    }

    @Test
    fun `a custom stale threshold is honoured`() {
        val state = ScreenStateMerge.merge(content = "positions", ageMs = 5_000L, staleThresholdMs = 4_000L)
        assertIs<ScreenState.Stale<String>>(state)
    }
}
