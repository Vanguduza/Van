package com.dial.van.overlay

import com.dial.van.visual.VanAuthorityState
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanHealthState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresenceFrame
import com.dial.van.visual.VanSpeechState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class VanOverlayChromeTest {

    @Test
    fun googleDegradedListeningKeepsListeningAsPrimaryChrome() {
        val live = VanPresenceFrame(
            activity = VanDurableState.LISTENING,
            health = VanHealthState.DEGRADED,
            speech = VanSpeechState.LISTENING,
        )
        val cue = VanPresence.Cue(
            durableState = VanDurableState.DEGRADED,
            health = VanHealthState.DEGRADED,
            headline = "Degraded",
            detail = "Google mesh unverified",
            brokenLabels = listOf("Google mesh"),
            urgency = 0.3f,
        )

        val chrome = VanOverlayChrome.resolve(cue, live, "Google mesh unverified")

        assertEquals(VanDurableState.LISTENING, chrome.primaryState)
        assertEquals("Listening", chrome.headline)
        assertNotNull(chrome.healthLine)
    }

    @Test
    fun offlineTakesOverPrimaryChrome() {
        val live = VanPresenceFrame(
            activity = VanDurableState.LISTENING,
            health = VanHealthState.OFFLINE,
            speech = VanSpeechState.LISTENING,
        )
        val cue = VanPresence.Cue(
            durableState = VanDurableState.OFFLINE,
            health = VanHealthState.OFFLINE,
            headline = "Offline",
            detail = "Hermes uplink unavailable",
            brokenLabels = listOf("Hermes uplink"),
            urgency = 0.25f,
        )

        val chrome = VanOverlayChrome.resolve(cue, live, "Hermes uplink unavailable")

        assertEquals(VanDurableState.OFFLINE, chrome.primaryState)
    }

    @Test
    fun ownerAuthorityTakesOverWhileHealthRemainsSecondary() {
        val live = VanPresenceFrame(
            activity = VanDurableState.WORKING,
            health = VanHealthState.DEGRADED,
            authority = VanAuthorityState.WAITING_FOR_OWNER,
            speech = VanSpeechState.SPEAKING,
        )
        val cue = VanPresence.Cue(
            durableState = VanDurableState.WAITING_FOR_OWNER,
            health = VanHealthState.DEGRADED,
            headline = "Waiting for owner",
            detail = "Waiting on your decision",
            brokenLabels = listOf("Google mesh"),
            urgency = 0.45f,
        )

        val chrome = VanOverlayChrome.resolve(cue, live, "Google mesh unverified")

        assertEquals(VanDurableState.WAITING_FOR_OWNER, chrome.primaryState)
        assertEquals("Google mesh unverified", chrome.healthLine)
    }

    @Test
    fun nominalActivityHasNoSecondaryHealthLine() {
        val live = VanPresenceFrame(activity = VanDurableState.WORKING)
        val cue = VanPresence.Cue(
            durableState = VanDurableState.WORKING,
            health = VanHealthState.NOMINAL,
            headline = "Working",
            detail = "Working",
            brokenLabels = emptyList(),
            urgency = 0f,
        )

        val chrome = VanOverlayChrome.resolve(cue, live, null)

        assertEquals(VanDurableState.WORKING, chrome.primaryState)
        assertNull(chrome.healthLine)
    }
}
