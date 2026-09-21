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

    private fun pending(vararg ids: Pair<String, String?>) =
        ids.map { (messageId, commandId) -> SessionReconciliation.Pending(messageId, commandId) }

    @Test
    fun `a command the Gateway has never heard of is sent again`() {
        // The defect, stated as its consequence. The old code removed every key the
        // Gateway mentioned, and the Gateway mentions the unknown ones too — so an
        // owner's instruction issued seconds before a failover was silently discarded.
        val plan = SessionReconciliation.plan(
            pending("msg_1" to "cmd_1"),
            mapOf("cmd_1" to SessionReconciliation.UNKNOWN),
        )
        assertEquals(listOf("msg_1"), plan.resend)
        assertTrue(plan.settle.isEmpty(), "an unknown command was treated as delivered")
    }

    @Test
    fun `a command the Gateway did not answer for at all is sent again`() {
        // The Gateway caps its answer at fifty. Beyond that the phone gets no key, and
        // silence must mean the same as `UNKNOWN`: resend, and let §20.12's admission
        // de-duplicate it. Reading silence as "delivered" would lose every command past
        // the fiftieth.
        val plan = SessionReconciliation.plan(pending("msg_2" to "cmd_2"), emptyMap())
        assertEquals(listOf("msg_2"), plan.resend)
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
    fun `a command with no command id is asked about by message id and still resends`() {
        // The fallback, and the direction it fails in. An id the Gateway cannot resolve
        // comes back unknown, which resends — and the resend is de-duplicated by the
        // idempotency key. The opposite fallback would drop the owner's command.
        val plan = SessionReconciliation.plan(
            pending("msg_5" to null), mapOf("msg_5" to SessionReconciliation.UNKNOWN),
        )
        assertEquals(listOf("msg_5"), plan.resend)
    }

    @Test
    fun `a mixed answer splits rather than settling or resending everything`() {
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
        assertEquals(listOf("msg_b"), plan.resend)
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
        assertEquals(listOf("msg_1", "msg_2", "msg_3"), plan.resend)
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
}
