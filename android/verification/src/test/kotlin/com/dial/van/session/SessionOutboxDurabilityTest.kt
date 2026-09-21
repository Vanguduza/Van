package com.dial.van.session

import com.dial.van.queue.OutboxRecordStore
import com.dial.van.queue.QueuedCommand
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Rev 1.5 §§20.12, 20.14 — the seam a kill fits through.
 *
 * `RestartSeamTest` proves the *mapping* survives a restart, using a fake store. It proves
 * nothing about the production adapter, because until now the production adapter could not
 * be executed: it took `EncryptedCommandQueue`, which is Keystore and disk. So the thing
 * every test exercised was a nine-line fake, and the thing that would run on the owner's
 * phone was:
 *
 * ```
 * queue.remove(entry.messageId)          // (1)
 * queue.enqueue(QueueEnqueueRequest(…))  // (2)
 * ```
 *
 * Three defects in two lines, none of which any passing test could see:
 *
 *  * A process death between (1) and (2) loses the owner's command entirely — the exact
 *    failure a durable outbox exists to prevent.
 *  * `enqueue` mints a fresh row id, so (1) never matched anything and neither did
 *    `forget`. Delivered commands stayed on disk and were re-sent after every restart.
 *  * `enqueue` de-duplicates on the idempotency key and returns the *existing* row, so a
 *    reconfirmation — the owner's "yes" — was silently discarded.
 *
 * These tests execute [EncryptedSessionOutboxStore] itself, over an [OutboxRecordStore]
 * that can be killed between operations. The Keystore and the disk remain CI's to compile
 * and Gate 14's to observe; what is proven here is everything above them.
 */
class SessionOutboxDurabilityTest {

    private val NOW = 1_700_000_000_000L

    /** Kill points the sweep tries. Asserted to exceed what a persist actually does. */
    private val KILL_SWEEP_BOUND = 4

    /** Thrown where a real process would simply stop existing. */
    private class ProcessDied : RuntimeException("process died")

    /**
     * A disk, and a kill switch.
     *
     * Records are stored as JSON rather than as objects, because a process death that
     * left live references behind would be modelling a different event. Every mutating
     * call is counted, and [FaultyRecordStore.killBeforeOperation] stops the world at a
     * chosen boundary — which is how a
     * multi-step write is caught: a store whose `persist` takes two operations has a
     * kill point *between* them, and a store whose persist is one does not.
     */
    private class FaultyRecordStore(
        private val disk: MutableMap<String, String> = LinkedHashMap(),
    ) : OutboxRecordStore {

        private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

        /** Mutating calls seen since the last [resetCount]. */
        var mutations: Int = 0
            private set

        /**
         * Stop *before* the Nth mutating call (1-based). Zero means never.
         *
         * Named for the boundary rather than for the operation. The first version of this
         * was named for the operation and meant the opposite, and a fault-injection switch
         * that is off by one injects the fault into a gap that is not the one under test —
         * which passes, and proves nothing.
         */
        var killBeforeOperation: Int = 0

        fun resetCount() { mutations = 0 }

        /** Everything the next process would find. The same bytes, nothing else. */
        fun survivingIds(): Set<String> = disk.keys.toSet()

        private fun mutate(body: () -> Unit) {
            mutations += 1
            if (killBeforeOperation != 0 && mutations >= killBeforeOperation) throw ProcessDied()
            body()
        }

        override fun upsert(command: QueuedCommand) = mutate {
            disk[command.id] = json.encodeToString(QueuedCommand.serializer(), command)
        }

        override fun remove(id: String) = mutate { disk.remove(id) }

        override fun recordsOfKind(kind: String): List<QueuedCommand> =
            disk.values
                .map { json.decodeFromString(QueuedCommand.serializer(), it) }
                .filter { it.kind == kind && !it.isExpired(NOW_FOR_READS) }
                .sortedBy { it.createdAtEpochMs }

        companion object {
            /** Reads are not the subject here; expiry has its own tests. */
            const val NOW_FOR_READS = 1_700_000_000_000L
        }
    }

    private fun admit(
        messageId: String,
        actionClass: String = "A1",
        requiresLiveOwnerContext: Boolean = false,
        nowMs: Long = NOW,
    ): OutboxEntry = assertNotNull(
        DurableOutbox.admit(
            messageId = messageId, commandId = "cmd_$messageId",
            idempotencyKey = "idem_$messageId", turnId = "turn_1", actionClass = actionClass,
            requiresLiveOwnerContext = requiresLiveOwnerContext, payloadRef = messageId,
            nowMs = nowMs,
        ),
    )

    private fun envelope(messageId: String, pathEpoch: Int = 1): String =
        """{"message_id":"$messageId","command_id":"cmd_$messageId",""" +
            """"idempotency_key":"idem_$messageId","path_epoch":$pathEpoch}"""

    // ------------------------------------------------------------------ one write

    @Test
    fun `a persist is exactly one mutating operation`() {
        // The property, stated directly. Everything below is its consequence, and this is
        // the assertion that fails first if someone reintroduces a two-step write.
        val disk = FaultyRecordStore()
        val store = EncryptedSessionOutboxStore(disk)

        store.persist(admit("msg_1"), envelope("msg_1"))
        assertEquals(1, disk.mutations, "a persist that is two operations has a gap in it")

        disk.resetCount()
        store.persist(admit("msg_1"), envelope("msg_1"))
        assertEquals(1, disk.mutations, "replacing an existing record is also one operation")
    }

    @Test
    fun `no kill during a persist can lose a command that was already on disk`() {
        // The sweep. For every operation a persist performs, kill at it and check the
        // owner's earlier command is still there. With the remove-then-enqueue version
        // this fails at kill point 1: the remove lands, the process dies, and a command
        // the owner was told was queued is gone.
        val first = admit("msg_keep")
        // The bound has to be known to cover every kill point that exists, or the sweep
        // passes by finding nothing — which is how a check of this shape usually fails.
        val probe = FaultyRecordStore()
        EncryptedSessionOutboxStore(probe).persist(first, envelope("msg_keep"))
        assertTrue(probe.mutations < KILL_SWEEP_BOUND, "the sweep does not cover every operation")

        for (killPoint in 1..KILL_SWEEP_BOUND) {
            val disk = FaultyRecordStore()
            val store = EncryptedSessionOutboxStore(disk)
            store.persist(first, envelope("msg_keep"))
            assertEquals(setOf("msg_keep"), disk.survivingIds())

            disk.resetCount()
            disk.killBeforeOperation = killPoint
            runCatching { store.persist(admit("msg_keep"), envelope("msg_keep", pathEpoch = 7)) }

            assertTrue(
                "msg_keep" in disk.survivingIds(),
                "a kill at operation $killPoint lost a command the owner had been told was queued",
            )
        }
    }

    /**
     * The adapter exactly as it was, so the test above is shown to discriminate.
     *
     * A sweep that catches nothing passes, and a sweep whose bound is too small catches
     * nothing quietly. This is the counterexample kept executable: the same property, the
     * same fake, the previous implementation — and it fails.
     */
    private class TwoStepOutboxStore(private val records: OutboxRecordStore) : SessionOutboxStore {
        override fun persist(entry: OutboxEntry, envelopeJson: String) {
            records.remove(entry.messageId)
            records.upsert(OutboxPersistence.toCommand(entry, envelopeJson))
        }
        override fun restore(): List<Pair<OutboxEntry, String>> =
            records.recordsOfKind(OutboxPersistence.SESSION_KIND)
                .mapNotNull { c -> OutboxPersistence.toEntry(c)?.let { it to c.payloadJson } }
        override fun forget(messageId: String) = records.remove(messageId)
    }

    @Test
    fun `the previous two-step persist does lose the command, which is why the sweep exists`() {
        val disk = FaultyRecordStore()
        val store = TwoStepOutboxStore(disk)
        store.persist(admit("msg_gap"), envelope("msg_gap"))
        assertEquals(setOf("msg_gap"), disk.survivingIds())

        disk.resetCount()
        // Before the second operation: the remove has landed, the write has not.
        disk.killBeforeOperation = 2
        assertFailsWith<ProcessDied> { store.persist(admit("msg_gap"), envelope("msg_gap")) }

        assertTrue(
            disk.survivingIds().isEmpty(),
            "this is the failure the atomic upsert removes; if it no longer reproduces, " +
                "the sweep above is no longer testing anything",
        )
    }

    @Test
    fun `the record is keyed by the message id, so forgetting it finds it`() {
        // The defect that made `forget` a no-op: `enqueue` minted its own row id, so
        // nothing the outbox asked to remove was ever removable. Every delivered command
        // stayed on disk and came back on the next restart.
        val disk = FaultyRecordStore()
        val store = EncryptedSessionOutboxStore(disk)
        store.persist(admit("msg_2"), envelope("msg_2"))
        assertEquals(setOf("msg_2"), disk.survivingIds())

        store.forget("msg_2")
        assertTrue(disk.survivingIds().isEmpty(), "forget did not find the record it wrote")
        assertTrue(store.restore().isEmpty())
    }

    @Test
    fun `a reconfirmation replaces the record rather than being discarded`() {
        // The third defect. `enqueue` returns the existing row for a known idempotency
        // key, so the owner's "yes" was written nowhere and they were asked again after
        // the next restart — the failure that teaches someone to stop reading the
        // question.
        val disk = FaultyRecordStore()
        val store = EncryptedSessionOutboxStore(disk)
        val entry = admit("msg_3", requiresLiveOwnerContext = true)
        store.persist(entry, envelope("msg_3"))
        store.persist(DurableOutbox.reconfirm(entry, NOW + 500), envelope("msg_3"))

        // One record, not two: a restore must not have to choose which is current.
        assertEquals(1, store.restore().size)
        val (restored, _) = store.restore().single()
        assertEquals(NOW + 500, restored.reconfirmedAtMs)
        assertTrue(DurableOutbox.flush(restored, NOW + 1_000) is FlushVerdict.Send)
    }

    @Test
    fun `a command awaiting the owner is restored rather than filtered away`() {
        // §20.14's most dangerous read. `EncryptedCommandQueue.peekReady` drops a
        // NO_STALE_REPLAY record once it has been attempted, which is exactly this class
        // — so restoring through that reader would silently discard the commands the
        // owner most needs to be asked about, with every mapping test still green.
        val disk = FaultyRecordStore()
        val store = EncryptedSessionOutboxStore(disk)
        val entry = DurableOutbox.attempted(
            admit("msg_4", requiresLiveOwnerContext = true), "path_primary",
        )
        store.persist(entry, envelope("msg_4"))

        val (restored, _) = assertNotNull(store.restore().singleOrNull())
        assertEquals(1, restored.attemptCount)
        assertTrue(
            DurableOutbox.flush(restored, NOW + 1_000) is FlushVerdict.NeedsReconfirmation,
        )
    }

    // ------------------------------------------- persist → death → restore → delivery

    @Test
    fun `persist then process death then restore then exactly-once delivery`() {
        // The whole seam in one test, because each half of it was already proven and the
        // join was not.
        val disk = FaultyRecordStore()
        val store = EncryptedSessionOutboxStore(disk)
        store.persist(admit("msg_5"), envelope("msg_5"))

        // --- the process dies. A new adapter over the same bytes is all that survives.
        val afterRestart = EncryptedSessionOutboxStore(disk)
        val (restored, json) = assertNotNull(afterRestart.restore().singleOrNull())
        assertEquals("msg_5", restored.messageId)
        assertEquals("cmd_msg_5", restored.commandId)

        // §20.12 — the Gateway has never heard of it, so it goes.
        val plan = SessionReconciliation.plan(
            listOf(SessionReconciliation.Pending(restored.messageId, restored.commandId)),
            mapOf("cmd_msg_5" to SessionReconciliation.UNKNOWN),
        )
        assertEquals(listOf("msg_5"), plan.resend)
        assertTrue(plan.settle.isEmpty())

        assertTrue(DurableOutbox.flush(restored, NOW + 1_000) is FlushVerdict.Send)
        // Re-addressed to the granted epoch, and still the same command.
        val readdressed = SessionEnvelope.readdress(org.json.JSONObject(json), 9)
        assertEquals("msg_5", readdressed.getString("message_id"))
        assertEquals("idem_msg_5", readdressed.getString("idempotency_key"))
        assertEquals(9, readdressed.getInt("path_epoch"))

        // Durable removal only after the send is acknowledged.
        afterRestart.forget(restored.messageId)
        assertTrue(EncryptedSessionOutboxStore(disk).restore().isEmpty())
    }

    @Test
    fun `a command killed between the send and the forget is not delivered twice`() {
        // The kill the reviewer asked about, end to end. `flushOutbox` writes to the
        // socket and only then calls `forget`; a process death in that gap leaves a
        // record on disk that the Gateway already holds — and the attempt counter is
        // stamped on *failure*, so it is still zero and looks like something never sent.
        val disk = FaultyRecordStore()
        EncryptedSessionOutboxStore(disk).persist(admit("msg_6"), envelope("msg_6"))
        // ... sent on the wire here, and the process dies before `forget` runs.

        val afterRestart = EncryptedSessionOutboxStore(disk)
        val (restored, _) = assertNotNull(afterRestart.restore().singleOrNull())
        assertEquals(0, restored.attemptCount, "the record gives no hint that it was sent")

        // The Gateway is the only thing that knows, and it does.
        val plan = SessionReconciliation.plan(
            listOf(SessionReconciliation.Pending(restored.messageId, restored.commandId)),
            mapOf("cmd_msg_6" to "RUNNING"),
        )
        assertEquals(listOf("msg_6"), plan.settle)
        assertTrue(plan.resend.isEmpty(), "the owner's command would have run twice")

        // Settled means forgotten, or it comes back on the next restart and the next.
        plan.settle.forEach { afterRestart.forget(it) }
        assertTrue(EncryptedSessionOutboxStore(disk).restore().isEmpty())
    }

    @Test
    fun `a kill while forgetting leaves the record, and the next restart settles it`() {
        // The remaining window, and the reason it is survivable rather than a defect: the
        // record outliving its delivery is recoverable — the next resume asks and is told
        // — while the command outliving nothing is not.
        val disk = FaultyRecordStore()
        val store = EncryptedSessionOutboxStore(disk)
        store.persist(admit("msg_7"), envelope("msg_7"))
        disk.resetCount()
        disk.killBeforeOperation = 1
        assertFailsWith<ProcessDied> { store.forget("msg_7") }
        assertTrue("msg_7" in disk.survivingIds())

        val afterRestart = EncryptedSessionOutboxStore(disk)
        val (restored, _) = assertNotNull(afterRestart.restore().singleOrNull())
        val plan = SessionReconciliation.plan(
            listOf(SessionReconciliation.Pending(restored.messageId, restored.commandId)),
            mapOf("cmd_msg_7" to "VERIFIED_SUCCESS"),
        )
        assertEquals(listOf("msg_7"), plan.settle)
    }

    @Test
    fun `a replaced session drops its work from the disk and tells the owner`() {
        // §20.9. The branch used to clear the in-memory queue and leave the records on
        // disk, so the next start restored them and flushed the abandoned session's work
        // into the new one — the decision reversed by a restart. It also dropped them
        // without telling the owner anything.
        val disk = FaultyRecordStore()
        val store = EncryptedSessionOutboxStore(disk)
        val entries = (1..3).map { admit("msg_gone$it", nowMs = NOW + it) }
        entries.forEach { store.persist(it, envelope(it.messageId)) }

        val told = DurableOutbox.abandonAll(entries, store)

        assertTrue(
            EncryptedSessionOutboxStore(disk).restore().isEmpty(),
            "a restart would flush a dead session's work into the new one",
        )
        assertEquals(
            entries.map { it.messageId }, told.map { it.messageId },
            "the owner's work was dropped without the owner being told",
        )
    }

    @Test
    fun `order is preserved across the real adapter`() {
        val disk = FaultyRecordStore()
        val store = EncryptedSessionOutboxStore(disk)
        for (n in 1..5) store.persist(admit("msg_o$n", nowMs = NOW + n), envelope("msg_o$n"))
        assertEquals(
            (1..5).map { "msg_o$it" },
            EncryptedSessionOutboxStore(disk).restore().map { (entry, _) -> entry.messageId },
        )
    }
}

/**
 * Rev 1.5 §20.14 — the command given with no network at all.
 *
 * The case the outbox exists for, and the one it could not handle. `submit` refused
 * outright when `vanSessionId` was null — and opening a session is an HTTP call, so a
 * phone in a tunnel never has one. Storage was therefore available exactly when it was
 * not needed (P0-SESS-011).
 */
class UnboundEnvelopeTest {

    private fun envelope(sessionId: String) = org.json.JSONObject(
        """{"message_id":"msg_1","van_session_id":"$sessionId","session_epoch":0,""" +
            """"path_epoch":0,"idempotency_key":"idem_1","payload_digest":"d"}""",
    )

    @Test
    fun `an envelope stored with no session is recognisable as unbound`() {
        assertTrue(SessionEnvelope.isUnbound(envelope(SessionEnvelope.UNBOUND_SESSION_ID)))
        assertTrue(!SessionEnvelope.isUnbound(envelope("van_sess_9")))
    }

    @Test
    fun `rebinding addresses it to the live session and changes nothing else`() {
        // The identity is what stops one instruction becoming two. A rebind that minted a
        // new message id or idempotency key would do exactly that, on the reconnect — the
        // moment the owner is most likely to be watching.
        val stored = envelope(SessionEnvelope.UNBOUND_SESSION_ID)
        val bound = SessionEnvelope.rebind(stored, "van_sess_9", 4)
        assertEquals("van_sess_9", bound.getString("van_session_id"))
        assertEquals(4, bound.getInt("session_epoch"))
        assertEquals("msg_1", bound.getString("message_id"))
        assertEquals("idem_1", bound.getString("idempotency_key"))
        assertEquals("d", bound.getString("payload_digest"))
    }

    @Test
    fun `rebinding does not mutate the stored envelope`() {
        // The stored bytes are the record. If a rebind edited them in place, a failed send
        // would leave the outbox holding a command addressed to a session that did not
        // accept it, and the next attempt would carry the wrong id.
        val stored = envelope(SessionEnvelope.UNBOUND_SESSION_ID)
        SessionEnvelope.rebind(stored, "van_sess_9", 4)
        assertTrue(SessionEnvelope.isUnbound(stored), "the rebind edited the stored record")
    }

    @Test
    fun `an already-bound envelope is left alone`() {
        val stored = envelope("van_sess_original")
        assertTrue(!SessionEnvelope.isUnbound(stored))
    }

    @Test
    fun `rebinding then readdressing is the full journey of a stored command`() {
        // Stored offline, bound to the session that exists on reconnect, addressed to the
        // path the Gateway granted. Three separate facts, applied in that order, none of
        // which touches what the command says.
        val stored = envelope(SessionEnvelope.UNBOUND_SESSION_ID)
        val sent = SessionEnvelope.readdress(
            SessionEnvelope.rebind(stored, "van_sess_9", 2), 7,
        )
        assertEquals("van_sess_9", sent.getString("van_session_id"))
        assertEquals(2, sent.getInt("session_epoch"))
        assertEquals(7, sent.getInt("path_epoch"))
        assertEquals("msg_1", sent.getString("message_id"))
    }
}
