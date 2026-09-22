package com.dial.van.command.work

import com.dial.van.status.VanCommandStatus
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ConversationReducerTest {

    @Test
    fun `needsPolling is true only for an unfinished status with a command id`() {
        assertTrue(ConversationReducer.needsPolling("c1", VanCommandStatus.ACCEPTED))
        assertTrue(ConversationReducer.needsPolling("c1", VanCommandStatus.IN_FLIGHT))
        assertTrue(ConversationReducer.needsPolling("c1", VanCommandStatus.QUEUED))
        assertFalse(ConversationReducer.needsPolling(null, VanCommandStatus.ACCEPTED))
        assertFalse(ConversationReducer.needsPolling("", VanCommandStatus.ACCEPTED))
        assertFalse(ConversationReducer.needsPolling("c1", null))
        assertFalse(ConversationReducer.needsPolling("c1", VanCommandStatus.SUCCEEDED))
        assertFalse(ConversationReducer.needsPolling("c1", VanCommandStatus.FAILED))
    }

    @Test
    fun `outcomeFor prefers final_outcome once the gateway says the work is finished`() {
        val outcome = ConversationReducer.outcomeFor(
            ConversationReducer.PollResult(
                ownerStatus = "DONE",
                sentence = "Done, and checked",
                finalOutcome = "Booked the 3pm with Thandi and sent the invite.",
                finished = true,
            ),
        )
        assertEquals("Booked the 3pm with Thandi and sent the invite.", outcome.text)
        assertEquals(VanCommandStatus.SUCCEEDED, outcome.status)
        assertFalse(outcome.keepPolling)
    }

    @Test
    fun `outcomeFor falls back to the sentence when finished but no final outcome was given`() {
        val outcome = ConversationReducer.outcomeFor(
            ConversationReducer.PollResult(
                ownerStatus = "FAILED",
                sentence = "Did not work",
                finalOutcome = null,
                finished = true,
            ),
        )
        assertEquals("Did not work", outcome.text)
        assertEquals(VanCommandStatus.FAILED, outcome.status)
        assertFalse(outcome.keepPolling)
    }

    @Test
    fun `outcomeFor keeps polling while the gateway still reports work under way`() {
        val outcome = ConversationReducer.outcomeFor(
            ConversationReducer.PollResult(
                ownerStatus = "WORKING",
                sentence = "Working on it",
                finalOutcome = null,
                finished = false,
            ),
        )
        assertEquals(VanCommandStatus.ACCEPTED, outcome.status)
        assertTrue(outcome.keepPolling)
    }

    @Test
    fun `outcomeFor never invents an optimistic status for one it does not recognise`() {
        val outcome = ConversationReducer.outcomeFor(
            ConversationReducer.PollResult(
                ownerStatus = "SOMETHING_NEW",
                sentence = null,
                finalOutcome = null,
                finished = false,
            ),
        )
        assertEquals(VanCommandStatus.UNKNOWN, outcome.status)
        assertEquals("VAN does not know the state of this", outcome.text)
    }

    @Test
    fun `outcomeFor treats a blank owner status the same as an unrecognised one`() {
        val outcome = ConversationReducer.outcomeFor(
            ConversationReducer.PollResult(ownerStatus = null, sentence = null, finalOutcome = null, finished = false),
        )
        assertEquals(VanCommandStatus.UNKNOWN, outcome.status)
    }

    @Test
    fun `contextGapsSentence names what VAN did not know`() {
        assertEquals(
            "VAN did not know: your timezone; who Thandi is",
            ConversationReducer.contextGapsSentence(listOf("your timezone", "who Thandi is")),
        )
    }

    @Test
    fun `contextGapsSentence is null when there is nothing to report`() {
        assertNull(ConversationReducer.contextGapsSentence(emptyList()))
        assertNull(ConversationReducer.contextGapsSentence(listOf("", "  ")))
    }
}
