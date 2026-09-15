package com.dial.van.visual

import com.dial.van.degraded.DegradedMode
import com.dial.van.degraded.DegradedSubsystem
import com.dial.van.degraded.RestoreAction
import com.dial.van.degraded.SubsystemStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Van's appearance must never be calmer than the truth. These cases pin the fail-closed
 * mapping from subsystem health to the visible durable state.
 */
class VanPresenceTest {

    private fun mode(vararg broken: String): DegradedMode {
        val subsystems = DegradedMode.defaultSubsystems().map { sub ->
            when {
                sub.id in broken -> sub.copy(status = SubsystemStatus.BROKEN, restoreAction = RestoreAction.RETRY_CONNECTION)
                else -> sub.copy(status = SubsystemStatus.WORKING, restoreAction = RestoreAction.NONE)
            }
        }
        val anyBroken = subsystems.any { it.status == SubsystemStatus.BROKEN }
        return DegradedMode(
            active = anyBroken,
            reason = if (anyBroken) "subsystem unavailable" else "All subsystems nominal",
            subsystems = subsystems,
        )
    }

    @Test
    fun defaultRuntimeTruthPresentsDegradedBecauseGoogleMeshIsUnverified() {
        val cue = VanPresence.cue(DegradedMode.healthy())
        assertEquals(VanDurableState.DEGRADED, cue.durableState)
        assertTrue("google mesh should lead the cue", cue.detail.contains("Google mesh"))
        assertEquals("Google mesh unverified", VanPresence.meshCue(DegradedMode.healthy()))
    }

    @Test
    fun lostUplinkPresentsOfflineNotMerelyDegraded() {
        assertEquals(VanDurableState.OFFLINE, VanPresence.cue(mode("hermes")).durableState)
        assertEquals(VanDurableState.OFFLINE, VanPresence.cue(mode("gateway")).durableState)
    }

    @Test
    fun uplinkLossOutranksOtherBrokenSubsystems() {
        val cue = VanPresence.cue(mode("gateway", "google", "voice"))
        assertEquals(VanDurableState.OFFLINE, cue.durableState)
        assertEquals(3, cue.brokenLabels.size)
    }

    @Test
    fun nonUplinkBreakagePresentsDegraded() {
        val cue = VanPresence.cue(mode("voice"))
        assertEquals(VanDurableState.DEGRADED, cue.durableState)
        assertTrue(cue.degraded)
    }

    @Test
    fun healthyMeshReachesTheCalmStates() {
        val healthy = mode()
        assertEquals(VanDurableState.IDLE, VanPresence.cue(healthy).durableState)
        assertEquals(VanDurableState.LISTENING, VanPresence.cue(healthy, listening = true).durableState)
        assertEquals(VanDurableState.SPEAKING, VanPresence.cue(healthy, speaking = true).durableState)
        assertEquals("Google mesh verified", VanPresence.meshCue(healthy))
        assertFalse(VanPresence.cue(healthy).degraded)
    }

    @Test
    fun ownerDecisionOutranksIdleButNotBreakage() {
        assertEquals(
            VanDurableState.WAITING_FOR_OWNER,
            VanPresence.cue(mode(), awaitingOwner = true).durableState,
        )
        assertEquals(
            VanDurableState.DEGRADED,
            VanPresence.cue(mode("google"), awaitingOwner = true).durableState,
        )
    }

    @Test
    fun visualStateNeverLowersAnExistingUrgency() {
        val cue = VanPresence.cue(mode("google"))
        val state = VanPresence.visualState(cue, VanVisualState(urgency = 0.9f))
        assertEquals(0.9f, state.urgency, 0.0001f)
        assertEquals(VanDurableState.DEGRADED, state.durableState)
    }

    @Test
    fun everyDurableStateHasALabelForTheOverlayChrome() {
        VanDurableState.entries.forEach { state ->
            assertTrue("missing label for $state", VanScene.statusLabel(state).isNotBlank())
        }
    }
}
