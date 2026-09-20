package com.dial.van.session

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Rev 1.5 §20.14 — the command that failed to send.
 *
 * `VanCommandController.recordFailure` appended "Command dispatch failed" and stopped, so
 * an instruction given with no signal was lost (P0-SESS-011). These are the rules that
 * replace it, and each is written as the owner's outcome rather than as a returned type,
 * because the returned type was never the thing that was wrong.
 */
class OfflineSubmissionTest {

    private fun decide(
        actionClass: String = "A1",
        requiresLiveOwnerContext: Boolean = false,
        gatewayAnswered: Boolean = false,
        failure: String = "timeout",
    ) = OfflineSubmission.decide(actionClass, requiresLiveOwnerContext, gatewayAnswered, failure)

    @Test
    fun `an ordinary command that never arrived is saved and sent later`() {
        val verdict = decide()
        assertTrue(verdict is OfflineSubmission.Verdict.Store)
        assertTrue(!verdict.needsReconfirm)
        assertTrue("Saved" in verdict.ownerMessage)
    }

    @Test
    fun `a command the Gateway refused is not saved and replayed later`() {
        // The distinction the catch block could not make. A refusal means the command
        // arrived; holding it would replay, silently and hours later, something the
        // Gateway has already declined.
        val verdict = decide(gatewayAnswered = true, failure = "gateway_http_403: forbidden")
        assertTrue(verdict is OfflineSubmission.Verdict.Drop)
        assertTrue("forbidden" in verdict.ownerMessage)
    }

    @Test
    fun `an irreversible command is never stored, whatever the network did`() {
        // §20.14's last sentence, at the one call site that could have violated it.
        for (actionClass in listOf("A4", "A5")) {
            val verdict = decide(actionClass = actionClass)
            assertTrue(
                verdict is OfflineSubmission.Verdict.Drop,
                "$actionClass was stored for a silent replay when connectivity returns",
            )
            assertTrue("Nothing was changed" in verdict.ownerMessage, actionClass)
        }
    }

    @Test
    fun `an irreversible command is not told it will be retried`() {
        // Wording, and it is load-bearing. "I'll send this when you're back online" for a
        // command that will never be sent is the sentence that makes an owner stop
        // checking — and then the transfer they think is queued never happens.
        val verdict = decide(actionClass = "A4")
        assertTrue("back online" !in verdict.ownerMessage)
        assertTrue("Not sent" in verdict.ownerMessage)
    }

    @Test
    fun `something that needs the owner present is saved and asked about again`() {
        val verdict = decide(requiresLiveOwnerContext = true)
        assertTrue(verdict is OfflineSubmission.Verdict.Store)
        assertTrue(verdict.needsReconfirm, "the owner is never asked, so it sends on its own")
        assertTrue("won't be sent without you" in verdict.ownerMessage)
    }

    @Test
    fun `an elevated but reversible command is stored rather than dropped`() {
        // A3 is `STORE_UNTIL_TTL`, not `NEVER_STORE`. Dropping it would be the safe-looking
        // mistake: the owner loses work for no reason, which is the failure that trains
        // someone to stop using the offline path at all.
        val verdict = decide(actionClass = "A3")
        assertTrue(verdict is OfflineSubmission.Verdict.Store)
    }

    @Test
    fun `a held command is not promised a question that nothing asks`() {
        // §20.15's reconfirmation surface does not exist yet (P1-SESS-012). Until it
        // does, "I'll check with you" is a promise of an interaction that will never
        // happen, and an owner who waits for it waits forever. What is true is that the
        // command is kept and will not go out on its own.
        val verdict = decide(requiresLiveOwnerContext = true)
        assertTrue("check with you" !in verdict.ownerMessage)
        assertTrue("ask you" !in verdict.ownerMessage)
        assertTrue("Saved" in verdict.ownerMessage && "held" in verdict.ownerMessage)
    }

    @Test
    fun `the three outcomes do not share a sentence`() {
        // They are similar to write and completely different to receive.
        val messages = listOf(
            decide().ownerMessage,
            decide(requiresLiveOwnerContext = true).ownerMessage,
            decide(actionClass = "A4").ownerMessage,
        )
        assertEquals(messages.size, messages.toSet().size, "two outcomes read the same")
    }

    @Test
    fun `the classification comes from OutboxPolicy rather than a second copy`() {
        // One rule, not two that agree today. If `OutboxPolicy` changes its mind about a
        // class, this must follow rather than drift.
        for (actionClass in listOf("A1", "A2", "A3", "A4", "A5")) {
            val stored = decide(actionClass = actionClass) is OfflineSubmission.Verdict.Store
            val storable = OutboxPolicy.classify(actionClass, false) != CommandStorability.NEVER_STORE
            assertEquals(storable, stored, actionClass)
        }
    }
}
