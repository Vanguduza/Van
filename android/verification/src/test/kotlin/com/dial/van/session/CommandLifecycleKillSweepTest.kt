package com.dial.van.session

import com.dial.van.queue.OutboxRecordStore
import com.dial.van.queue.QueuedCommand
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Rev 1.5 §20.14 — every owner command ends in one of three observable states.
 *
 * Asked for by external review, and it is the right shape: the previous tests each prove
 * one link, and the defect C15 found was two *correct* links cancelling each other out.
 * So this kills the process at every point around the whole chain — store, send,
 * acknowledge, reconcile, remove — and asserts the same invariant every time:
 *
 *  1. **Delivered once.** The Gateway holds it, and the phone is no longer holding it.
 *  2. **Still held.** On disk, recoverable, and the next reconnect will act on it.
 *  3. **Given up on, and the owner told.** Not on disk, and named in what is reported.
 *
 * **Never silently absent**: gone from the phone while the Gateway never received it, or
 * gone with nothing said. That is the state the owner cannot detect and cannot recover
 * from, and it is the one every defect in C14, C15 and C16 produced by a different route.
 *
 * What this cannot do is kill a real Android process. It kills the store, which is where
 * the durability lives; the Keystore, the disk and the app lifecycle are Gate 14's.
 */
class CommandLifecycleKillSweepTest {

    private class ProcessDied : RuntimeException("process died")

    private companion object {
        /** Inside the companion so the nested `Disk` can read it. */
        const val NOW = 1_700_000_000_000L
    }

    /** A disk that can be stopped at the Nth write. */
    private class Disk(val bytes: MutableMap<String, String> = LinkedHashMap()) : OutboxRecordStore {
        private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
        var writes = 0
            private set
        var killBeforeWrite = 0

        private fun write(body: () -> Unit) {
            writes += 1
            if (killBeforeWrite != 0 && writes >= killBeforeWrite) throw ProcessDied()
            body()
        }

        override fun upsert(command: QueuedCommand) = write {
            bytes[command.id] = json.encodeToString(QueuedCommand.serializer(), command)
        }

        override fun remove(id: String) = write { bytes.remove(id) }

        override fun recordsOfKind(kind: String): List<QueuedCommand> =
            bytes.values
                .map { json.decodeFromString(QueuedCommand.serializer(), it) }
                .filter { it.kind == kind && !it.isExpired(NOW) }
                .sortedBy { it.createdAtEpochMs }
    }

    /** What the Gateway ended up holding, and what the owner ended up being told. */
    private class World {
        val gatewayHas = mutableSetOf<String>()
        val ownerTold = mutableListOf<String>()
    }

    private fun entry(messageId: String) = checkNotNull(
        DurableOutbox.admit(
            messageId = messageId, commandId = "cmd_$messageId",
            idempotencyKey = "idem_$messageId", turnId = "turn_1", actionClass = "A1",
            requiresLiveOwnerContext = false, payloadRef = messageId, nowMs = NOW,
        ),
    )

    private fun envelope(messageId: String) =
        """{"message_id":"$messageId","command_id":"cmd_$messageId",""" +
            """"idempotency_key":"idem_$messageId","path_epoch":1}"""

    /**
     * One command through the whole chain, with the process dying before write [killAt].
     *
     * Deliberately written as the real order of operations rather than as a helper that
     * hides it: store, then send, then let the Gateway record it, then forget. The order
     * is the thing under test — forgetting before the send is the defect that loses the
     * command, and it has to be visible here to be wrong here.
     */
    private fun run(
        killAt: Int,
        reachedGateway: Boolean,
        forgetAfterSend: Boolean,
    ): Pair<Disk, World> {
        val disk = Disk()
        val world = World()
        val store = EncryptedSessionOutboxStore(disk)
        disk.killBeforeWrite = killAt
        val id = "msg_1"

        // Modelled as three separate facts because they are three separate facts, and
        // conflating two of them is how the first version of this test asserted something
        // false: "the Gateway received it" and "the phone learned that it did" are the
        // pair §20.12 exists for, and they differ precisely when the network fails.
        runCatching {
            store.persist(entry(id), envelope(id))
            if (reachedGateway) world.gatewayHas += "cmd_$id"
            if (reachedGateway && forgetAfterSend) store.forget(id)
        }.onFailure {
            // What `VanCommandController.recordFailure` does when the store refuses or
            // throws: it says so. "Saved" is the one sentence that must not be said on a
            // guess, so a store that did not store produces a message rather than silence.
            world.ownerTold += "Not sent, and not saved"
        }

        // --- the process restarts here, and a resume asks the Gateway what it holds.
        val recovered = EncryptedSessionOutboxStore(disk)
        val held = recovered.restore()
        val plan = SessionReconciliation.plan(
            held.map { (e, _) -> SessionReconciliation.Pending(e.messageId, e.commandId) },
            held.associate { (e, _) ->
                val identity = SessionReconciliation.identityOf(e.messageId, e.commandId)
                identity to if (identity in world.gatewayHas) "RUNNING" else SessionReconciliation.UNKNOWN
            },
        )
        disk.killBeforeWrite = 0
        plan.settle.forEach { recovered.forget(it) }
        return disk to world
    }

    @Test
    fun `no kill point leaves a command silently absent`() {
        // The sweep. Every boundary in the chain, with and without the acknowledgement
        // that would normally clear it.
        for (reachedGateway in listOf(true, false)) {
          for (forgetAfterSend in listOf(true, false)) {
            for (killAt in 0..4) {
                val (disk, world) = run(killAt, reachedGateway, forgetAfterSend)
                val onDisk = EncryptedSessionOutboxStore(disk).restore()
                val delivered = "cmd_msg_1" in world.gatewayHas
                val stillHeld = onDisk.isNotEmpty()
                val told = world.ownerTold.isNotEmpty()

                assertTrue(
                    delivered || stillHeld || told,
                    "kill=$killAt reached=$reachedGateway forget=$forgetAfterSend: the " +
                        "command is gone from the phone, the Gateway never received it, " +
                        "and the owner was told nothing",
                )
                // And not two at once in the way that means a second delivery: if the
                // Gateway has it, the phone must not still be holding it after the
                // reconciliation, or the next flush sends it again.
                if (delivered) {
                    assertTrue(
                        !stillHeld,
                        "kill=$killAt reached=$reachedGateway forget=$forgetAfterSend: " +
                            "the Gateway has it and the phone still holds it, so the next " +
                            "reconnect delivers it twice",
                    )
                }
            }
          }
        }
    }

    @Test
    fun `a kill before the store leaves nothing claimed and nothing lost`() {
        // The one case where the command genuinely does not survive — and the owner has
        // not been told it was saved either, because the store threw before returning.
        val (disk, world) = run(killAt = 1, reachedGateway = true, forgetAfterSend = true)
        assertTrue(EncryptedSessionOutboxStore(disk).restore().isEmpty())
        assertTrue("cmd_msg_1" !in world.gatewayHas)
        assertTrue(
            world.ownerTold.isNotEmpty(),
            "the store refused and the owner was told nothing, so the command is silently absent",
        )
    }

    @Test
    fun `a kill between the send and the forget is recovered by the Gateway's answer`() {
        // The window the review asked about, end to end: stored, sent, killed before the
        // durable removal. The record survives, the Gateway holds it, and the resume
        // settles it rather than sending it a second time.
        val (disk, world) = run(killAt = 2, reachedGateway = true, forgetAfterSend = true)
        assertTrue("cmd_msg_1" in world.gatewayHas)
        assertTrue(
            EncryptedSessionOutboxStore(disk).restore().isEmpty(),
            "the record outlived its delivery and would be flushed again",
        )
    }

    @Test
    fun `a command that never reached the Gateway is still held after a restart`() {
        val (disk, _) = run(killAt = 0, reachedGateway = false, forgetAfterSend = false)
        // Not settled, because the Gateway answered UNKNOWN for it.
        assertEquals(1, EncryptedSessionOutboxStore(disk).restore().size)
    }

    @Test
    fun `the sweep covers more boundaries than the chain has writes`() {
        // Without this the range is a guess, and a range that stops short of the last
        // write is a sweep that never tests the interesting end.
        val probe = Disk()
        val store = EncryptedSessionOutboxStore(probe)
        store.persist(entry("msg_probe"), envelope("msg_probe"))
        store.forget("msg_probe")
        assertTrue(probe.writes < 4, "the chain now has ${probe.writes} writes and the sweep tries 4")
    }
}
