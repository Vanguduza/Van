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
    fun liveWorkspaceReadyClearsInitialGoogleDegraded() {
        val store = DegradedModeStore()
        store.applyGoogleMesh(
            configuredCapabilities = 13,
            totalCapabilities = 15,
            principalRegistered = true,
            workspaceApiState = "READY",
        )

        val google = store.snapshot().subsystems.single { it.id == "google" }
        assertEquals(SubsystemStatus.WORKING, google.status)
        assertFalse(store.snapshot().active)
        assertEquals("All subsystems nominal", store.snapshot().reason)
    }
}
