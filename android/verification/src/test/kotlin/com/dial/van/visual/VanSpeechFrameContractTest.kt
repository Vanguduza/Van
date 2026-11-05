package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class VanSpeechFrameContractTest {
    @Test fun speechNeverEmitsUnsupportedViseme() {
        for (value in listOf(-5, -1, 0, 1, 2, 3, 4, 5, 14, Int.MAX_VALUE)) {
            val frame = VanPresenceReducer.speechFrame(VanPresenceFrame(), 0.4f, value)
            assertTrue(frame.viseme in 0..4)
            if (value > 4) assertEquals(1, frame.viseme)
        }
    }
    @Test fun negativeVisemeBecomesNeutral() {
        assertEquals(0, VanPresenceReducer.speechFrame(VanPresenceFrame(), 0.3f, -99).viseme)
    }
    @Test fun infiniteAndNaNAmplitudeCloseRatherThanCorruptMouth() {
        for (input in listOf(Float.NaN, Float.NEGATIVE_INFINITY, Float.POSITIVE_INFINITY)) {
            assertEquals(0f, VanPresenceReducer.speechFrame(VanPresenceFrame(), input, 3).mouthOpen)
        }
    }
    @Test fun finiteAmplitudeIsBounded() {
        assertEquals(1f, VanPresenceReducer.speechFrame(VanPresenceFrame(), 5f, 2).mouthOpen)
        assertEquals(0f, VanPresenceReducer.speechFrame(VanPresenceFrame(), -5f, 2).mouthOpen)
    }
    @Test fun interruptionReturnsLipsToQuietWithoutForgettingWork() {
        val base = VanPresenceFrame(activity = VanDurableState.WORKING)
        val speaking = VanPresenceReducer.speechFrame(base, 0.8f, 4)
        val ended = VanPresenceReducer.speechEnded(speaking)
        assertEquals(VanSpeechState.QUIET, ended.speech)
        assertEquals(0f, ended.mouthOpen)
        assertEquals(0, ended.viseme)
        assertEquals(VanDurableState.WORKING, ended.activity)
    }
    @Test fun offlineHealthMasksSpeechEvenWhenAudioFrameArrives() {
        val frame = VanPresenceReducer.speechFrame(
            VanPresenceFrame(health = VanHealthState.OFFLINE), 0.6f, 4,
        ).toVisualState()
        assertFalse(frame.speaking)
        assertEquals(0f, frame.mouthOpen)
        assertEquals(0, frame.viseme)
    }
}
