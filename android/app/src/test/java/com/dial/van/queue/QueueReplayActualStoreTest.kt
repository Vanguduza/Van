package com.dial.van.queue

import com.dial.van.degraded.DegradedModeStore
import com.dial.van.gateway.QueueReplayTransport
import com.dial.van.gateway.QueueReplayer
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Actual canonical producer/store/replayer code; SOURCE transport and native storage boundaries. */
class QueueReplayActualStoreTest {
    private class SourceTransport : QueueReplayTransport {
        var calls = 0
        var sends = 0
        var reads = mutableListOf<String>()
        var context = 0
        var afterPrepared: () -> Unit = {}
        var loseReply = false
        var unavailable = false
        var wrongReceipt = false
        override fun isEnrolled() = true
        override suspend fun ingestCapturedContext(payload: JSONObject) { context++ }
        override suspend fun commandStatus(commandId: String, profile: String, device: String): JSONObject {
            assertEquals("SOURCE-profile", profile)
            assertEquals("SOURCE-device", device)
            reads += commandId
            if (unavailable) error("SOURCE original read unavailable")
            return JSONObject().put("command_id", if (wrongReceipt) "foreign-command" else commandId)
                .put("mission_id", "SOURCE-original-mission").put("mission_state", "RUNNING")
        }
        override suspend fun dispatch(command: QueuedCommand, text: String, onPrepared: (String) -> Unit,
                                      beforeDispatch: () -> Unit): JSONObject {
            calls++
            val original = JSONObject().put("command_id", "SOURCE-original-command")
                .put("idempotency_key", command.idempotencyKey).put("device_id", "SOURCE-device")
                .put("signature", "SOURCE-original-signature").put("text", text)
            onPrepared(original.toString())
            afterPrepared()
            beforeDispatch()
            sends++
            if (loseReply) error("SOURCE lost reply after possible delivery")
            return JSONObject().put("status", "accepted").put("command_id", "SOURCE-original-command")
                .put("mission_id", "SOURCE-original-mission")
        }
    }
    private fun fixture() = QueueRestorationActualStoreTest().also { it.setup() }
    private fun replayer(queue: EncryptedCommandQueue, transport: SourceTransport) = QueueReplayer(
        queue, transport, DegradedModeStore(), CoroutineScope(SupervisorJob() + Dispatchers.Unconfined), { 0L })

    @Test fun producerClaimPreparedBodyAndOriginalReceiptSurviveWithoutResending() = runBlocking {
        val f = fixture(); val t = SourceTransport(); val command = QueueRestorationActualStoreTest.enqueue(f.queue, "original")
        assertEquals(1, replayer(f.queue, t).replayNow())
        val stored = f.queue.findByIdempotencyKey(command.idempotencyKey)!!
        assertEquals("SUBMITTED", stored.genericDeliveryState)
        assertEquals("SOURCE-original-command", JSONObject(stored.genericPreparedBody!!).getString("command_id"))
        assertEquals("SOURCE-original-mission", JSONObject(stored.genericReceiptJson!!).getString("mission_id"))
        replayer(f.queue, t).replayNow()
        assertEquals(1, t.calls); assertEquals(1, t.sends)
        assertEquals(stored, f.queue.findByIdempotencyKey(command.idempotencyKey))
    }
    @Test fun lostReplyRestartReadsOriginalIdentityAndNeverBuildsAnotherCommand() = runBlocking {
        val f = fixture(); val t = SourceTransport().also { it.loseReply = true }
        val command = QueueRestorationActualStoreTest.enqueue(f.queue, "original")
        replayer(f.queue, t).replayNow()
        val unknown = f.queue.findByIdempotencyKey(command.idempotencyKey)!!
        assertEquals("UNKNOWN", unknown.genericDeliveryState)
        val reloaded = QueueRestorationActualStoreTest.queue(
            QueueRestorationActualStoreTest.Store(f.store.file), f.actor)
        replayer(reloaded, t).replayNow()
        val recovered = reloaded.findByIdempotencyKey(command.idempotencyKey)!!
        assertEquals(unknown.genericPreparedBody, recovered.genericPreparedBody)
        assertEquals(unknown.genericClaimId, recovered.genericClaimId)
        assertEquals(listOf("SOURCE-original-command"), t.reads)
        assertEquals("SUBMITTED", recovered.genericDeliveryState)
        assertEquals(1, t.calls); assertEquals(1, t.sends)
    }
    @Test fun unavailableOrForeignOriginalReadHoldsEvidenceWithoutNewSend() = runBlocking {
        for (wrong in listOf(false, true)) {
            val f = fixture(); val t = SourceTransport().also { it.loseReply = true }
            val command = QueueRestorationActualStoreTest.enqueue(f.queue, "original")
            replayer(f.queue, t).replayNow()
            val original = f.queue.findByIdempotencyKey(command.idempotencyKey)!!
            t.unavailable = !wrong; t.wrongReceipt = wrong
            replayer(f.queue, t).replayNow()
            assertEquals(original, f.queue.findByIdempotencyKey(command.idempotencyKey))
            assertEquals(1, t.calls); assertEquals(1, t.sends)
        }
    }
    @Test fun currentActorChangeBetweenPreparationAndEffectPreventsDispatch() = runBlocking {
        val f = fixture(); val t = SourceTransport()
        val command = QueueRestorationActualStoreTest.enqueue(f.queue, "original")
        t.afterPrepared = { f.actor.set(QueueRestorationActualStoreTest.owner("SOURCE-profile", "changed-token")) }
        replayer(f.queue, t).replayNow()
        assertEquals(0, t.sends)
        assertEquals("UNKNOWN", f.queue.findByIdempotencyKey(command.idempotencyKey)!!.genericDeliveryState)
        assertTrue(f.queue.restoreInventory().eligibleUnsent == 0)
    }
    @Test fun claimedOriginalSurvivesConcurrentExactUnsentDiscard() = runBlocking {
        val f = fixture(); val t = SourceTransport()
        val original = QueueRestorationActualStoreTest.enqueue(f.queue, "original")
        t.afterPrepared = {
            val other = QueueRestorationActualStoreTest.enqueue(f.queue, "concurrent-unsent")
            val request = f.queue.reviewDiscard()
            assertEquals(listOf(other.id), request.items.map { it.id })
            assertEquals("APPLIED", QueueRestorationActualStoreTest.discard(f.queue, request).state)
            assertNotNull(f.queue.findByIdempotencyKey(original.idempotencyKey))
        }
        replayer(f.queue, t).replayNow()
        assertEquals(1, t.sends)
        assertNull(f.queue.findByIdempotencyKey("concurrent-unsent"))
        assertEquals("SUBMITTED", f.queue.findByIdempotencyKey(original.idempotencyKey)!!.genericDeliveryState)
    }
    @Test fun typedContextOwnerExpiresOnlyItsOwnOriginalAndPreservesSessionAndUnknownKinds() = runBlocking {
        val f = fixture(); val t = SourceTransport()
        f.queue.upsert(QueueRestorationActualStoreTest.legacy("expired-context", "CONTEXT_INGEST", 1))
        f.queue.upsert(QueueRestorationActualStoreTest.legacy("expired-session", "SESSION_ENVELOPE", 1))
        f.queue.upsert(QueueRestorationActualStoreTest.legacy("unknown-kind", "FUTURE_FOREIGN_OWNER", Long.MAX_VALUE))
        f.queue.upsert(QueueRestorationActualStoreTest.legacy("legacy-generic", "TASK", Long.MAX_VALUE))
        val before = f.store.memory["cmd_expired-session"]
        replayer(f.queue, t).replayNow()
        assertNull(f.queue.findByIdempotencyKey("expired-context"))
        assertEquals(before, f.store.memory["cmd_expired-session"])
        assertNotNull(f.queue.findByIdempotencyKey("unknown-kind"))
        assertNotNull(f.queue.findByIdempotencyKey("legacy-generic"))
        assertEquals(0, t.calls); assertEquals(0, t.context)
    }
}
