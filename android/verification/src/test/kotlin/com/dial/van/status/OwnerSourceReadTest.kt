package com.dial.van.status

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.supervisorScope
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

class OwnerSourceReadTest {
    @Test
    fun `failed source cannot masquerade as an observed empty list`() = runBlocking {
        val result = readOwnerSource<List<String>>(clock = { 300 }) { error("unreachable") }
        assertTrue(result.unavailable)
        assertFalse(result.hasObservation)
        assertNull(result.value)
        assertNull(result.observedAtMs)
    }

    @Test
    fun `failed refresh retains original data and original observation time`() = runBlocking {
        val before = readOwnerSource(clock = { 100 }) { listOf("mission-original") }
        val result = readOwnerSource(before, clock = { 500 }) { error("lost response") }
        assertEquals(listOf("mission-original"), result.value)
        assertEquals(100L, result.observedAtMs)
        assertEquals(400L, result.ageMs(500))
        assertTrue(result.unavailable)
    }

    @Test
    fun `recovery replaces cached data and clears source failure`() = runBlocking {
        val before = OwnerSourceRead(listOf("old"), 100, unavailable = true)
        val result = readOwnerSource(before, clock = { 600 }) { emptyList<String>() }
        assertTrue(result.hasObservation)
        assertFalse(result.unavailable)
        assertEquals(emptyList(), result.value)
        assertEquals(600L, result.observedAtMs)
    }

    @Test
    fun `independent failed read leaves sibling source observable`() = runBlocking {
        supervisorScope {
            val unavailable = async { readOwnerSource<String> { error("attention failed") } }
            val working = async { readOwnerSource(clock = { 200 }) { "reminder-live" } }
            assertTrue(unavailable.await().unavailable)
            assertEquals("reminder-live", working.await().value)
        }
    }

    @Test
    fun `cancellation is propagated rather than presented as a source outage`() = runBlocking {
        assertFailsWith<CancellationException> {
            readOwnerSource<String> { throw CancellationException("screen closed") }
        }
    }

    @Test
    fun `a stalled source becomes unavailable within its budget without losing confirmed data`() = runBlocking {
        val before = OwnerSourceRead("confirmed", 100)
        val result = readOwnerSource(before, timeoutMs = 20) { delay(2_000); "late" }
        assertEquals("confirmed", result.value)
        assertEquals(100L, result.observedAtMs)
        assertTrue(result.unavailable)
    }
}
