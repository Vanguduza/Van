package com.dial.van.visual

import com.dial.van.degraded.DegradedMode
import com.dial.van.degraded.RestoreAction
import com.dial.van.degraded.SubsystemStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

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
        val cue = VanPresence.cue(DegradedMode.healthy(), live = VanPresenceFrame())
        assertEquals(VanDurableState.DEGRADED, cue.durableState)
        assertEquals(VanHealthState.DEGRADED, cue.health)
        assertTrue(cue.detail.contains("Google mesh"))
        assertEquals("Google mesh unverified", VanPresence.meshCue(DegradedMode.healthy()))
    }

    @Test
    fun googleUnverifiedDoesNotSuppressLiveListeningPose() {
        val live = VanPresenceReducer.listeningStarted(VanPresenceFrame())
        val cue = VanPresence.cue(DegradedMode.healthy(), live = live)
        val resolved = VanPresence.visualState(cue, live)

        assertEquals(VanDurableState.DEGRADED, cue.durableState)
        assertEquals(VanDurableState.LISTENING, resolved.durableState)
        assertEquals(VanDurableState.DEGRADED, resolved.resolvedSemanticState)
        assertTrue(resolved.listening)
        assertFalse(resolved.speaking)
    }

    @Test
    fun lostUplinkForcesOfflinePoseAndSemanticState() {
        val live = VanPresenceReducer.listeningStarted(VanPresenceFrame())
        val cue = VanPresence.cue(mode("gateway"), live = live)
        val resolved = VanPresence.visualState(cue, live)

        assertEquals(VanDurableState.OFFLINE, cue.durableState)
        assertEquals(VanDurableState.OFFLINE, resolved.durableState)
        assertEquals(VanDurableState.OFFLINE, resolved.resolvedSemanticState)
        assertFalse(resolved.listening)
    }

    @Test
    fun uplinkLossOutranksOtherBrokenSubsystems() {
        val cue = VanPresence.cue(mode("gateway", "google", "voice"), live = VanPresenceFrame())
        assertEquals(VanDurableState.OFFLINE, cue.durableState)
        assertEquals(3, cue.brokenLabels.size)
    }

    @Test
    fun nonUplinkBreakagePresentsDegradedSemanticTruth() {
        val cue = VanPresence.cue(mode("voice"), live = VanPresenceFrame())
        assertEquals(VanDurableState.DEGRADED, cue.durableState)
        assertTrue(cue.degraded)
    }

    @Test
    fun healthyMeshReachesLiveStates() {
        val healthy = mode()
        val idle = VanPresenceFrame()
        assertEquals(VanDurableState.IDLE, VanPresence.cue(healthy, live = idle).durableState)
        assertEquals(VanDurableState.LISTENING, VanPresence.cue(healthy, listening = true, live = idle).durableState)
        assertEquals(VanDurableState.SPEAKING, VanPresence.cue(healthy, speaking = true, live = idle).durableState)
        assertEquals("Google mesh verified", VanPresence.meshCue(healthy))
        assertFalse(VanPresence.cue(healthy, live = idle).degraded)
    }

    @Test
    fun nominalTruthAllowsLiveWorkingStateToDriveChromeAndEmbodiment() {
        val live = VanPresenceFrame(activity = VanDurableState.WORKING, urgency = 0.2f)
        val cue = VanPresence.cue(mode(), live = live)
        val resolved = VanPresence.visualState(cue, live)

        assertEquals(VanDurableState.WORKING, cue.durableState)
        assertEquals(VanDurableState.WORKING, resolved.durableState)
        assertEquals(VanDurableState.WORKING, resolved.resolvedSemanticState)
        assertEquals(0.2f, resolved.urgency, 0.0001f)
    }

    @Test
    fun ownerDecisionCanCoexistWithGoogleUnverified() {
        val waiting = VanPresenceReducer.authority(VanPresenceFrame(), VanAuthorityState.WAITING_FOR_OWNER)
        val cue = VanPresence.cue(mode("google"), live = waiting)
        val resolved = VanPresence.visualState(cue, waiting)

        assertEquals(VanDurableState.WAITING_FOR_OWNER, cue.durableState)
        assertEquals(VanHealthState.DEGRADED, cue.health)
        assertEquals(VanDurableState.WAITING_FOR_OWNER, resolved.durableState)
        assertEquals(VanDurableState.WAITING_FOR_OWNER, resolved.resolvedSemanticState)
    }

    @Test
    fun visualStateNeverLowersExistingUrgencyAndDoesNotLeakHealthIntoPose() {
        val live = VanPresenceFrame(activity = VanDurableState.THINKING, urgency = 0.9f)
        val cue = VanPresence.cue(mode("google"), live = live)
        val state = VanPresence.visualState(cue, live)

        assertEquals(0.9f, state.urgency, 0.0001f)
        assertEquals(VanDurableState.THINKING, state.durableState)
        assertEquals(VanDurableState.DEGRADED, state.resolvedSemanticState)
    }

    @Test
    fun everyDurableStateHasALabelForTheOverlayChrome() {
        VanDurableState.entries.forEach { state ->
            assertTrue("missing label for $state", VanScene.statusLabel(state).isNotBlank())
        }
    }
}
