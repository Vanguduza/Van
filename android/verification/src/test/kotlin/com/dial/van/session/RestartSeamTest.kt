package com.dial.van.session

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The joined seam: queued owner command → process death → recovery → epoch adoption →
 * reconfirmation/expiry decision → exactly-once send.
 *
 * Each half of this was already tested and the join was not, which is where the defect
 * was. C11's path-epoch fix made the Gateway and the phone agree about *which* epoch to
 * stamp; C11's outbox held the policy deciding *whether to send at all* in RAM. Both
 * correct, and a process death between them produced a command that came back with an
 * authoritative epoch and no policy — so the epoch fix would have addressed it perfectly
 * and sent something nobody was asked about.
 *
 * `SessionOutboxStore` is the seam and it is an interface for this reason: the store is
 * Android and cannot run here, but a fake implements it in nine lines and every decision
 * around it becomes executable. What is *not* proven here is `EncryptedCommandQueue`
 * itself — the Keystore, the disk — which is CI's to compile and Gate 14's to observe.
 */
class RestartSeamTest {

    private val NOW = 1_700_000_000_000L

    /**
     * A process death, modelled honestly: everything in RAM is gone and the store is not.
     *
     * Deliberately not a "clear the list" helper. The point of the class is that a restart
     * keeps exactly what was written down and nothing else, so the fake holds only the
     * bytes and a second instance reads them back.
     */
    private class FakeStore : SessionOutboxStore {
        val rows = linkedMapOf<String, Pair<OutboxEntry, String>>()
        override fun persist(entry: OutboxEntry, envelopeJson: String) {
            rows[entry.messageId] = entry to envelopeJson
        }
        override fun restore(): List<Pair<OutboxEntry, String>> = rows.values.toList()
        override fun forget(messageId: String) { rows.remove(messageId) }

        /** What a restarted process would find, through the real mapping rather than a copy. */
        fun afterProcessDeath(): List<Pair<OutboxEntry, String>> = rows.values.map { (entry, json) ->
            val command = OutboxPersistence.toCommand(entry, json)
            assertNotNull(OutboxPersistence.toEntry(command)) to json
        }
    }

    private fun admit(
        messageId: String, actionClass: String = "A1",
        requiresLiveOwnerContext: Boolean = false, nowMs: Long = NOW,
    ) = DurableOutbox.admit(
        messageId = messageId, commandId = "cmd_$messageId", idempotencyKey = "idem_$messageId",
        turnId = "turn_1", actionClass = actionClass,
        requiresLiveOwnerContext = requiresLiveOwnerContext, payloadRef = messageId, nowMs = nowMs,
    )

    @Test
    fun `an ordinary command survives a restart and is sent exactly once`() {
        val store = FakeStore()
        val entry = assertNotNull(admit("msg_1"))
        store.persist(entry, "{\"message_id\":\"msg_1\"}")

        // --- the process dies here ---
        val recovered = store.afterProcessDeath()
        assertEquals(1, recovered.size)

        val (restored, _) = recovered.single()
        assertTrue(DurableOutbox.flush(restored, NOW + 1_000) is FlushVerdict.Send)
        // Sent, then forgotten. Forgetting first would lose it to a second kill.
        store.forget(restored.messageId)
        assertTrue(store.afterProcessDeath().isEmpty())
    }

    @Test
    fun `a command awaiting the owner still awaits them after a restart`() {
        // The one that matters most. If the policy did not survive, this command comes
        // back looking ordinary and is sent without the owner ever being asked.
        val store = FakeStore()
        val entry = assertNotNull(admit("msg_2", requiresLiveOwnerContext = true))
        store.persist(entry, "{}")

        val (restored, _) = store.afterProcessDeath().single()
        assertTrue(
            DurableOutbox.flush(restored, NOW + 1_000) is FlushVerdict.NeedsReconfirmation,
            "a restart turned a question for the owner into a silent send",
        )
    }

    @Test
    fun `an answered question stays answered across a restart`() {
        val store = FakeStore()
        val entry = assertNotNull(admit("msg_3", requiresLiveOwnerContext = true))
        store.persist(entry, "{}")
        store.persist(DurableOutbox.reconfirm(entry, NOW + 500), "{}")

        val (restored, _) = store.afterProcessDeath().single()
        assertTrue(DurableOutbox.flush(restored, NOW + 1_000) is FlushVerdict.Send)
        assertEquals(NOW + 500, restored.reconfirmedAtMs)
    }

    @Test
    fun `a command that expired while the process was dead is dropped and the owner told`() {
        val store = FakeStore()
        store.persist(assertNotNull(admit("msg_4")), "{}")

        val (restored, _) = store.afterProcessDeath().single()
        val verdict = DurableOutbox.flush(restored, NOW + DurableOutbox.DEFAULT_TTL_MS + 1)
        assertTrue(verdict is FlushVerdict.Expired)
        assertTrue(
            DurableOutbox.ownerReadableState(restored, NOW + DurableOutbox.DEFAULT_TTL_MS + 1)
                .startsWith("Not done"),
        )
    }

    @Test
    fun `an irreversible command is not in the store to be found after a restart`() {
        // §20.14's last sentence, across the seam. There is nothing to recover because
        // there was never anything to write: `admit` returned null at submission.
        val store = FakeStore()
        assertNull(admit("msg_5", actionClass = "A4"))
        assertTrue(store.afterProcessDeath().isEmpty())
    }

    @Test
    fun `the restored command carries the identity the Gateway will match it by`() {
        // §20.12's ACK-unknown reconciliation. A restart that lost the command id would
        // leave the resume unable to match what the Gateway already has, and the command
        // would go a second time.
        val store = FakeStore()
        val entry = assertNotNull(admit("msg_6"))
        store.persist(entry, "{}")

        val (restored, _) = store.afterProcessDeath().single()
        assertEquals("cmd_msg_6", restored.commandId)
        assertEquals("idem_msg_6", restored.idempotencyKey)
    }

    @Test
    fun `the epoch is adopted after the restore, not carried across the restart`() {
        // The join with C11. The path epoch is the Gateway's to grant on resume, so the
        // restored envelope is re-addressed rather than replayed at whatever epoch it was
        // written with — and `readdress` keeps the identity, so the re-address is not a
        // second command.
        val store = FakeStore()
        val entry = assertNotNull(admit("msg_7"))
        store.persist(entry, "{\"message_id\":\"msg_7\",\"path_epoch\":3,\"idempotency_key\":\"idem_msg_7\"}")

        val (restored, json) = store.afterProcessDeath().single()
        val readdressed = SessionEnvelope.readdress(org.json.JSONObject(json), 9)
        assertEquals(9, readdressed.getInt("path_epoch"))
        assertEquals("msg_7", readdressed.getString("message_id"))
        assertEquals("idem_msg_7", readdressed.getString("idempotency_key"))
        assertEquals(restored.messageId, readdressed.getString("message_id"))
    }

    @Test
    fun `order is preserved across a restart`() {
        // A queue that came back shuffled would send the owner's instructions out of the
        // order they gave them, which for two commands about the same thing is a
        // different outcome.
        val store = FakeStore()
        for (n in 1..5) store.persist(assertNotNull(admit("msg_$n", nowMs = NOW + n)), "{}")
        assertEquals(
            (1..5).map { "msg_$it" },
            store.afterProcessDeath().map { (entry, _) -> entry.messageId },
        )
    }
}
