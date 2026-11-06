package com.dial.van.overlay

import com.dial.van.visual.*
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals

class OverlayPresentationFrameTest {
    @Test fun tenThousandLipAndGazeSamplesDoNotChangeTheWorkboardChromeSnapshot() {
        val base = VanPresenceFrame(activity = VanDurableState.WORKING, speech = VanSpeechState.SPEAKING)
        repeat(10_000) { i ->
            val live = base.copy(mouthOpen = (i % 100) / 100f, viseme = i % 5,
                attentionX = (i % 200) / 100f - 1f, attentionY = 1f - (i % 200) / 100f)
            assertEquals(OverlayPresentationFrame.chrome(base), OverlayPresentationFrame.chrome(live))
        }
    }
    @Test fun authorityHealthTurnAndTaskChangesStillUpdateTheChrome() {
        val base = VanPresenceFrame()
        for (changed in listOf(base.copy(health = VanHealthState.OFFLINE), base.copy(authority = VanAuthorityState.WAITING_FOR_OWNER),
            base.copy(activity = VanDurableState.ERROR), base.copy(speech = VanSpeechState.LISTENING), base.copy(actionCode = 9), base.copy(contextCode = 24))) {
            assertNotEquals(OverlayPresentationFrame.chrome(base), OverlayPresentationFrame.chrome(changed))
        }
    }
    @Test fun characterStillReceivesRealLipAndGazeUpdates() {
        val model = VanVisualState(durableState = VanDurableState.SPEAKING, speaking = true)
        val result = OverlayPresentationFrame.character(model, VanPresenceFrame(mouthOpen = .8f, viseme = 4, attentionX = -.6f, attentionY = .5f))
        assertEquals(.8f, result.mouthOpen); assertEquals(4, result.viseme); assertEquals(-.6f, result.attentionX); assertEquals(.5f, result.attentionY)
    }
    @Test fun offlineAuthorityIsNotBypassedByAStaleAudioFrame() {
        val model = VanVisualState(durableState = VanDurableState.OFFLINE, speaking = false)
        val result = OverlayPresentationFrame.character(model, VanPresenceFrame(mouthOpen = 1f, viseme = 4))
        assertEquals(model.durableState, result.durableState); assertEquals(0f, result.mouthOpen); assertEquals(0, result.viseme); assertEquals(false, result.speaking)
    }
    @Test fun warningApprovalAndTradeSemanticsCannotBeChangedByAnimationSamples() {
        val model = VanVisualState(durableState = VanDurableState.WAITING_FOR_OWNER, semanticState = VanDurableState.URGENT, urgency = .9f, actionCode = 9)
        val result = OverlayPresentationFrame.character(model, VanPresenceFrame(activity = VanDurableState.SUCCESS, mouthOpen = .3f))
        assertEquals(model.durableState, result.durableState); assertEquals(model.semanticState, result.semanticState)
        assertEquals(model.urgency, result.urgency); assertEquals(9, result.actionCode)
    }
    @Test fun corruptTransientSamplesCannotPoisonRendererInputs() {
        val result = OverlayPresentationFrame.character(VanVisualState(), VanPresenceFrame(attentionX = Float.NaN, attentionY = Float.POSITIVE_INFINITY, mouthOpen = Float.NaN, viseme = 99))
        assertEquals(0f, result.attentionX); assertEquals(0f, result.attentionY); assertEquals(0f, result.mouthOpen); assertEquals(1, result.viseme)
    }
    @Test fun transientRangesAreClampedWithoutChangingPublicActionCodes() {
        val result = OverlayPresentationFrame.character(VanVisualState(actionCode = 7), VanPresenceFrame(attentionX = -9f, attentionY = 12f, mouthOpen = 3f, viseme = -4))
        assertEquals(-1f, result.attentionX); assertEquals(1f, result.attentionY); assertEquals(1f, result.mouthOpen); assertEquals(0, result.viseme); assertEquals(7, result.actionCode)
    }
}
