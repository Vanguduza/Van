package com.dial.van.session

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Rev 1.5 §20.12 — a lost acknowledgement is not a lost command.
 *
 * The version this replaced satisfied its own tests completely, because the two halves of
 * it were wrong in opposite directions and cancelled out: the phone asked about *message*
 * ids while the Gateway answered about *command* ids, so every answer was `UNKNOWN` — and
 * the phone then dropped everything it had asked about, `UNKNOWN`s included. Nothing was
 * resent because nothing was recognised, and nothing looked wrong because nothing was
 * left behind.
 *
 * Every test here is written as the owner's outcome rather than the field's value, because
 * the field was right in the old version too.
 */
class SessionReconciliationTest {

    @Test fun `a durable admission with no recorded result remains recoverable`() {
        val plan = SessionReconciliation.plan(
            pending("msg_pending" to "cmd_pending"), mapOf("cmd_pending" to SessionReconciliation.RESULT_PENDING),
        )
        assertEquals(listOf("msg_pending"), plan.hold)
        assertTrue(plan.resend.isEmpty())
        assertTrue(plan.settle.isEmpty())
    }

    private fun pending(vararg ids: Pair<String, String?>) =
        ids.map { (messageId, commandId) -> SessionReconciliation.Pending(messageId, commandId) }

    @Test
    fun `an ambiguous original not known to the Gateway is held`() {
        // POLICY_CORRECTION LAC234: the actual direct-HTTP reservation is invisible
        // to the old session-only lookup. UNKNOWN cannot prove it was never submitted.
        val plan = SessionReconciliation.plan(
            pending("msg_1" to "cmd_1"),
            mapOf("cmd_1" to SessionReconciliation.UNKNOWN),
        )
        assertEquals(listOf("msg_1"), plan.hold)
        assertTrue(plan.resend.isEmpty())
        assertTrue(plan.settle.isEmpty(), "an unknown command was treated as delivered")
    }

    @Test
    fun `an unanswered ambiguous original is held`() {
        // A bounded/missing answer is not a receipt and not evidence of absence.
        val plan = SessionReconciliation.plan(pending("msg_2" to "cmd_2"), emptyMap())
        assertEquals(listOf("msg_2"), plan.hold)
        assertTrue(plan.resend.isEmpty())
    }

    @Test
    fun `a command the Gateway is running is not sent a second time`() {
        val plan = SessionReconciliation.plan(
            pending("msg_3" to "cmd_3"), mapOf("cmd_3" to "RUNNING"),
        )
        assertEquals(listOf("msg_3"), plan.settle)
        assertTrue(plan.resend.isEmpty(), "the owner's command would have run twice")
    }

    @Test
    fun `a command the Gateway admitted without opening a mission is settled`() {
        // Not every envelope becomes a mission. The Gateway's §20.12 admission table is
        // the authority on "I have this", and an answer from it must settle — otherwise
        // the phone resends on every resume for the life of the session and nothing it
        // can ever receive stops it.
        val plan = SessionReconciliation.plan(
            pending("msg_4" to "cmd_4"), mapOf("cmd_4" to "ADMITTED"),
        )
        assertEquals(listOf("msg_4"), plan.settle)
    }

    @Test
    fun `the identity asked about is the identity the answer is matched by`() {
        // The first half of the original defect, isolated. One function produces both, so
        // that asking by one and matching by the other is not expressible.
        assertEquals("cmd_9", SessionReconciliation.identityOf("msg_9", "cmd_9"))
        assertEquals("msg_9", SessionReconciliation.identityOf("msg_9", null))
        assertEquals("msg_9", SessionReconciliation.identityOf("msg_9", ""))
        assertEquals("msg_9", SessionReconciliation.identityOf("msg_9", "msg_9"))
    }

    @Test
    fun `a legacy original with no command id keeps its message identity and is held`() {
        // Preserve the original fallback identity without promoting uncertainty to delivery.
        val plan = SessionReconciliation.plan(
            pending("msg_5" to null), mapOf("msg_5" to SessionReconciliation.UNKNOWN),
        )
        assertEquals(listOf("msg_5"), plan.hold)
        assertTrue(plan.resend.isEmpty())
    }

    @Test
    fun `a mixed answer settles owned results and holds ambiguous originals`() {
        // The realistic case, and the one neither original half could produce: the
        // Gateway received some of what was in flight and not the rest.
        val plan = SessionReconciliation.plan(
            pending("msg_a" to "cmd_a", "msg_b" to "cmd_b", "msg_c" to "cmd_c"),
            mapOf(
                "cmd_a" to "VERIFIED_SUCCESS",
                "cmd_b" to SessionReconciliation.UNKNOWN,
                "cmd_c" to "WAITING_FOR_OWNER",
            ),
        )
        assertEquals(listOf("msg_b"), plan.hold)
        assertTrue(plan.resend.isEmpty())
        assertEquals(listOf("msg_a", "msg_c"), plan.settle)
    }

    @Test
    fun `order is preserved, because the owner issued these in an order`() {
        val plan = SessionReconciliation.plan(
            pending("msg_1" to "cmd_1", "msg_2" to "cmd_2", "msg_3" to "cmd_3"),
            mapOf(
                "cmd_1" to SessionReconciliation.UNKNOWN,
                "cmd_2" to SessionReconciliation.UNKNOWN,
                "cmd_3" to SessionReconciliation.UNKNOWN,
            ),
        )
        assertEquals(listOf("msg_1", "msg_2", "msg_3"), plan.hold)
        assertTrue(plan.resend.isEmpty())
    }

    @Test
    fun `a terminal mission settles rather than being asked about forever`() {
        for (state in listOf("VERIFIED_SUCCESS", "FAILED", "CANCELLED", "EXPIRED")) {
            val plan = SessionReconciliation.plan(
                pending("msg_t" to "cmd_t"), mapOf("cmd_t" to state),
            )
            assertEquals(listOf("msg_t"), plan.settle, state)
        }
    }
    @Test fun `producer proven fresh work still delivers while absence and pending remain distinct`() {
        val fresh = SessionReconciliation.Pending("fresh", "fresh-command", neverDispatched = true)
        assertEquals(listOf("fresh"), SessionReconciliation.plan(listOf(fresh), emptyMap()).resend)
        assertEquals(listOf("fresh"), SessionReconciliation.plan(listOf(fresh), mapOf("fresh-command" to "UNKNOWN")).resend)
        assertEquals(listOf("fresh"), SessionReconciliation.plan(listOf(fresh), mapOf("fresh-command" to "RESULT_PENDING")).hold)
    }
    @Test fun `all existing idempotent session owners retain original transport recovery only with producer lineage`() {
        for (kind in listOf("mission.message", "mission.cancel", "decision.answer")) {
            val original = SessionReconciliation.Pending("original", null, kind = kind, sessionOnlyOrigin = true, sameOriginalSession = true)
            for (state in listOf("UNKNOWN", "RESULT_PENDING"))
                assertEquals(listOf("original"), SessionReconciliation.plan(listOf(original), mapOf("original" to state)).resend)
            assertEquals(listOf("original"), SessionReconciliation.plan(listOf(original), emptyMap()).hold)
            assertEquals(listOf("original"), SessionReconciliation.plan(listOf(original.copy(sessionOnlyOrigin = false)), mapOf("original" to "UNKNOWN")).hold)
        }
    }

    @Test fun `attempted command settlement requires the verified original lookup rather than an ID only state`() {
        val original = SessionReconciliation.Pending("message", "command", kind = "command.submit")
        for (state in listOf("ADMITTED", "RUNNING", "ORIGINAL_COMPLETED"))
            assertEquals(listOf("message"), SessionReconciliation.plan(listOf(original), mapOf("command" to state)).hold)
        assertEquals(listOf("message"), SessionReconciliation.plan(listOf(original.copy(verifiedOriginalRead = true)),
            mapOf("command" to "ORIGINAL_COMPLETED")).settle)
    }

}
