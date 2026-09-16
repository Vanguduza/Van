package com.dial.van.visual

import com.dial.van.degraded.DegradedMode
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
        val cue = VanPresence.cue(DegradedMode.healthy(), live = VanVisualState())
        assertEquals(VanDurableState.DEGRADED, cue.durableState)
        assertTrue("google mesh should lead the cue", cue.detail.contains("Google mesh"))
        assertEquals("Google mesh unverified", VanPresence.meshCue(DegradedMode.healthy()))
    }

    @Test
    fun lostUplinkPresentsOfflineNotMerelyDegraded() {
        assertEquals(VanDurableState.OFFLINE, VanPresence.cue(mode("hermes"), live = VanVisualState()).durableState)
        assertEquals(VanDurableState.OFFLINE, VanPresence.cue(mode("gateway"), live = VanVisualState()).durableState)
    }

    @Test
    fun uplinkLossOutranksOtherBrokenSubsystems() {
        val cue = VanPresence.cue(mode("gateway", "google", "voice"), live = VanVisualState())
        assertEquals(VanDurableState.OFFLINE, cue.durableState)
        assertEquals(3, cue.brokenLabels.size)
    }

    @Test
    fun nonUplinkBreakagePresentsDegraded() {
        val cue = VanPresence.cue(mode("voice"), live = VanVisualState())
        assertEquals(VanDurableState.DEGRADED, cue.durableState)
        assertTrue(cue.degraded)
    }

    @Test
    fun healthyMeshReachesTheCalmStates() {
        val healthy = mode()
        val idle = VanVisualState()
        assertEquals(VanDurableState.IDLE, VanPresence.cue(healthy, live = idle).durableState)
        assertEquals(VanDurableState.LISTENING, VanPresence.cue(healthy, listening = true, live = idle).durableState)
        assertEquals(VanDurableState.SPEAKING, VanPresence.cue(healthy, speaking = true, live = idle).durableState)
        assertEquals("Google mesh verified", VanPresence.meshCue(healthy))
        assertFalse(VanPresence.cue(healthy, live = idle).degraded)
    }

    @Test
    fun nominalTruthAllowsLiveWorkingStateToDriveChromeAndEmbodiment() {
        val live = VanVisualState(durableState = VanDurableState.WORKING, urgency = 0.2f)
        val cue = VanPresence.cue(mode(), live = live)
        val resolved = VanPresence.visualState(cue, live)

        assertEquals(VanDurableState.WORKING, cue.durableState)
        assertEquals(VanDurableState.WORKING, resolved.durableState)
        assertEquals(0.2f, resolved.urgency, 0.0001f)
    }

    @Test
    fun brokenTruthAlwaysOverridesOptimisticLiveState() {
        val live = VanVisualState(durableState = VanDurableState.SUCCESS)
        val cue = VanPresence.cue(mode("gateway"), live = live)
        val resolved = VanPresence.visualState(cue, live)

        assertEquals(VanDurableState.OFFLINE, cue.durableState)
        assertEquals(VanDurableState.OFFLINE, resolved.durableState)
    }

    @Test
    fun ownerDecisionOutranksIdleButNotBreakage() {
        val idle = VanVisualState()
        assertEquals(
            VanDurableState.WAITING_FOR_OWNER,
            VanPresence.cue(mode(), awaitingOwner = true, live = idle).durableState,
        )
        assertEquals(
            VanDurableState.DEGRADED,
            VanPresence.cue(mode("google"), awaitingOwner = true, live = idle).durableState,
        )
    }

    @Test
    fun visualStateNeverLowersAnExistingUrgency() {
        val cue = VanPresence.cue(mode("google"), live = VanVisualState())
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
