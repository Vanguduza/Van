package com.dial.van.projects

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ProjectSourceReadTest {
    @Test fun `failed source remains unavailable and later independent sources can be read`() = runBlocking {
        val context = readProjectSource<List<String>> { throw IllegalStateException("context offline") }
        val missions = readProjectSource { listOf("mission-1") }
        assertFalse(context.available)
        assertNull(context.value)
        assertEquals("context offline", context.failure)
        assertTrue(missions.available)
        assertEquals(listOf("mission-1"), missions.value)
    }

    @Test fun `confirmed empty source is distinct from source failure`() = runBlocking {
        val empty = readProjectSource { emptyList<String>() }
        assertTrue(empty.available)
        assertEquals(emptyList(), empty.value)
        assertNull(empty.failure)
    }

    @Test fun `cancellation is not a failed project source`() {
        assertFailsWith<CancellationException> { runBlocking {
            readProjectSource<String> { throw CancellationException("screen closed") }
        } }
    }

    @Test fun `partial health never reports quiet active stale or at risk as complete`() {
        for (health in listOf(ProjectHealth.QUIET, ProjectHealth.ACTIVE, ProjectHealth.STALE_TRUTH, ProjectHealth.AT_RISK)) {
            for (missing in 0..2) assertEquals(ProjectHealth.UNKNOWN,
                ProjectSourcePresentation.health(health, missing != 0, missing != 1, missing != 2))
            assertEquals(health, ProjectSourcePresentation.health(health, true, true, true))
        }
        assertEquals(ProjectHealth.BLOCKED, ProjectSourcePresentation.health(ProjectHealth.BLOCKED, false, false, false))
    }

    @Test fun `missing phase inputs never produce idle from empty defaults`() {
        assertEquals("Phase could not be confirmed", ProjectSourcePresentation.phase("Idle", false, true))
        assertEquals("Phase could not be confirmed", ProjectSourcePresentation.phase("Idle", true, false))
        assertEquals("Delivery", ProjectSourcePresentation.phase("Delivery", true, true))
    }
}
