package com.dial.van.degraded

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class DegradedModeStoreTest {
    @Test
    fun configuredWorkspaceDoesNotClearGoogleDegraded() {
        val store = DegradedModeStore()
        store.applyGoogleMesh(
            configuredCapabilities = 13,
            totalCapabilities = 15,
            principalRegistered = true,
            workspaceApiState = "CONFIGURED",
        )

        val google = store.snapshot().subsystems.single { it.id == "google" }
        assertEquals(SubsystemStatus.BROKEN, google.status)
        assertTrue(store.snapshot().active)
    }

    @Test
    fun liveWorkspaceReadyClearsGoogleWithoutClearingTheBanner() {
        // P0-AND-013 — this asserted that a live Google mesh cleared degraded mode
        // entirely, and stopped being true when P1-VOICE-001 made `wake_word` its own
        // subsystem, BROKEN until a model is installed. The assertion was pre-P1-VOICE-001
        // behaviour and nothing could see it, because the app did not compile.
        //
        // What it now pins is better than what it pinned before: recovery is scoped. One
        // subsystem coming back does not speak for the others, and the banner stays up
        // while something is still broken — which is the whole point of listing subsystems
        // separately rather than reporting one health bit.
        val store = DegradedModeStore()
        store.applyGoogleMesh(
            configuredCapabilities = 13,
            totalCapabilities = 15,
            principalRegistered = true,
            workspaceApiState = "READY",
        )

        val google = store.snapshot().subsystems.single { it.id == "google" }
        assertEquals(SubsystemStatus.WORKING, google.status)

        val wake = store.snapshot().subsystems.single { it.id == "wake_word" }
        assertEquals(SubsystemStatus.BROKEN, wake.status)
        assertTrue(store.snapshot().active)
        assertEquals("Awaiting Google mesh evidence", store.snapshot().reason)
    }

    @Test
    fun theBannerClearsOnceNothingIsBroken() {
        // The other half, so "stays active" is not mistaken for "can never clear".
        val store = DegradedModeStore()
        store.applyGoogleMesh(
            configuredCapabilities = 15,
            totalCapabilities = 15,
            principalRegistered = true,
            workspaceApiState = "READY",
        )
        store.markWorking("wake_word")

        assertFalse(store.snapshot().active)
        assertEquals("All subsystems nominal", store.snapshot().reason)
    }
}
