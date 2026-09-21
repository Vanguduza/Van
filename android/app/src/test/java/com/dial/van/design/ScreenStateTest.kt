package com.dial.van.design

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JVM coverage for [ScreenState]/[ScreenStateMerge]/[DegradedCatalog], run in `:app`'s own
 * unit-test task (CI) as well as `android/verification` — see that module's
 * `ScreenStateTest.kt` for the fuller case list; this file exists so the design package's own
 * module runs these in place, per the worker task's file list.
 */
class ScreenStateTest {

    @Test
    fun `merge with no content and loading is Loading`() {
        val state = ScreenStateMerge.merge<String>(content = null, loading = true)
        assertTrue(state is ScreenState.Loading)
    }

    @Test
    fun `merge stale overrides both content and degraded`() {
        val state = ScreenStateMerge.merge(
            content = "positions",
            degradedSubsystems = listOf("trading"),
            ageMs = ScreenStateMerge.DEFAULT_STALE_THRESHOLD_MS,
        )
        assertTrue(state is ScreenState.Stale<*>)
        assertEquals("positions", (state as ScreenState.Stale<String>).content)
    }

    @Test
    fun `merge with content and degraded subsystems is Degraded`() {
        val state = ScreenStateMerge.merge(content = "positions", degradedSubsystems = listOf("voice"))
        assertTrue(state is ScreenState.Degraded<*>)
        assertEquals("voice", (state as ScreenState.Degraded<String>).rows.single().subsystem)
    }

    @Test
    fun `merge with plain content is Content`() {
        val state = ScreenStateMerge.merge(content = "positions")
        assertTrue(state is ScreenState.Content<*>)
        assertEquals("positions", (state as ScreenState.Content<String>).data)
    }

    @Test
    fun `unknown degraded subsystem keys still get a sentence`() {
        val rows = DegradedCatalog.rowsFor(listOf("some_future_subsystem"))
        assertEquals(1, rows.size)
        assertTrue(rows.single().sentence.isNotBlank())
    }

    @Test
    fun `health json array parses to rows in order`() {
        val rows = DegradedCatalog.rowsFromHealthJson("""["trading","voice"]""")
        assertEquals(listOf("trading", "voice"), rows.map { it.subsystem })
    }

    @Test
    fun `malformed health json is an empty list, not a thrown exception`() {
        assertEquals(emptyList<DegradedRow>(), DegradedCatalog.rowsFromHealthJson("not json"))
    }
}
