package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VanPresenceFrameTest {

    @Test
    fun microphoneEndCannotEraseThinkingAfterFinalTranscript() {
        var frame = VanPresenceFrame()
        frame = VanPresenceReducer.listeningStarted(frame)
        frame = VanPresenceReducer.listeningEnded(frame)
        frame = VanPresenceReducer.finalTranscript(frame, hasText = true)

        assertEquals(VanTurnPhase.THINKING, frame.turn)
        assertEquals(VanDurableState.THINKING, frame.poseState)

        // A late duplicate capture-end callback must not reset THINKING.
        frame = VanPresenceReducer.listeningEnded(frame)
        assertEquals(VanTurnPhase.THINKING, frame.turn)
        assertEquals(VanDurableState.THINKING, frame.poseState)
    }

    @Test
    fun finalTranscriptThenListeningEndAlsoKeepsThinking() {
        var frame = VanPresenceReducer.listeningStarted(VanPresenceFrame())
        frame = VanPresenceReducer.finalTranscript(frame, hasText = true)
        frame = VanPresenceReducer.listeningEnded(frame)

        assertEquals(VanTurnPhase.THINKING, frame.turn)
        assertEquals(VanDurableState.THINKING, frame.poseState)
    }

    @Test
    fun dispatchTransitionsThinkingToDelegatingWithoutIdleGap() {
        var frame = VanPresenceReducer.finalTranscript(VanPresenceFrame(), hasText = true)
        frame = VanPresenceReducer.dispatchStarted(frame)

        assertEquals(VanTurnPhase.DISPATCHING, frame.turn)
        assertEquals(VanDurableState.DELEGATING, frame.poseState)
    }

    @Test
    fun thinkingActivityReturnsAfterTtsRoundTrip() {
        var frame = VanPresenceReducer.finalTranscript(VanPresenceFrame(), hasText = true)
        assertEquals(VanDurableState.THINKING, frame.activity)

        frame = VanPresenceReducer.speechStarted(frame)
        assertEquals(VanDurableState.SPEAKING, frame.poseState)
        assertEquals(VanDurableState.THINKING, frame.activity)

        frame = VanPresenceReducer.speechFrame(frame, mouthOpen = 0.72f, viseme = 5)
        assertEquals(VanDurableState.SPEAKING, frame.poseState)
        assertEquals(VanDurableState.THINKING, frame.activity)

        frame = VanPresenceReducer.speechEnded(frame)
        assertEquals(VanDurableState.THINKING, frame.poseState)
        assertEquals(VanDurableState.THINKING, frame.activity)
        assertEquals(VanTurnPhase.THINKING, frame.turn)
    }

    @Test
    fun delegatingActivityReturnsAfterTtsRoundTrip() {
        var frame = VanPresenceReducer.dispatchStarted(
            VanPresenceReducer.finalTranscript(VanPresenceFrame(), hasText = true),
        )
        assertEquals(VanDurableState.DELEGATING, frame.activity)

        frame = VanPresenceReducer.speechFrame(frame, mouthOpen = 0.4f, viseme = 2)
        assertEquals(VanDurableState.SPEAKING, frame.poseState)
        assertEquals(VanDurableState.DELEGATING, frame.activity)

        frame = VanPresenceReducer.speechEnded(frame)
        assertEquals(VanDurableState.DELEGATING, frame.poseState)
        assertEquals(VanDurableState.DELEGATING, frame.activity)
        assertEquals(VanTurnPhase.DISPATCHING, frame.turn)
    }

    @Test
    fun speechFrameCannotReplaceWaitingForOwnerAuthority() {
        var frame = VanPresenceReducer.authority(
            VanPresenceFrame(activity = VanDurableState.WORKING),
            VanAuthorityState.WAITING_FOR_OWNER,
        )
        frame = VanPresenceReducer.speechFrame(frame, mouthOpen = 0.8f, viseme = 7)

        assertEquals(VanAuthorityState.WAITING_FOR_OWNER, frame.authority)
        assertEquals(VanDurableState.WAITING_FOR_OWNER, frame.poseState)
        assertEquals(VanDurableState.WAITING_FOR_OWNER, frame.semanticState)
        assertEquals(VanSpeechState.SPEAKING, frame.speech)
        assertEquals(VanDurableState.WORKING, frame.activity)
        assertEquals(0.8f, frame.mouthOpen, 0.0001f)

        frame = VanPresenceReducer.speechEnded(frame)
        assertEquals(VanDurableState.WAITING_FOR_OWNER, frame.poseState)
        assertEquals(VanDurableState.WORKING, frame.activity)
    }

    @Test
    fun speechFrameCannotReplaceErrorAuthority() {
        var frame = VanPresenceReducer.authority(VanPresenceFrame(), VanAuthorityState.ERROR)
        frame = VanPresenceReducer.speechFrame(frame, mouthOpen = 0.6f, viseme = 4)

        assertEquals(VanDurableState.ERROR, frame.poseState)
        assertEquals(VanDurableState.ERROR, frame.semanticState)
        assertEquals(VanAuthorityState.ERROR, frame.authority)
    }

    @Test
    fun degradedHealthAndListeningRemainOrthogonal() {
        val frame = VanPresenceReducer.listeningStarted(VanPresenceFrame()).copy(
            health = VanHealthState.DEGRADED,
        )
        val visual = frame.toVisualState()

        assertEquals(VanDurableState.LISTENING, visual.durableState)
        assertEquals(VanDurableState.DEGRADED, visual.resolvedSemanticState)
        assertTrue(visual.listening)
        assertFalse(visual.speaking)
    }

    @Test
    fun offlineHealthStillForcesOfflinePose() {
        val frame = VanPresenceReducer.listeningStarted(VanPresenceFrame()).copy(
            health = VanHealthState.OFFLINE,
        )

        assertEquals(VanDurableState.OFFLINE, frame.poseState)
        assertEquals(VanDurableState.OFFLINE, frame.semanticState)
    }
}
