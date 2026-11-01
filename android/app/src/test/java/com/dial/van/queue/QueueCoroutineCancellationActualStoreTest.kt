package com.dial.van.queue

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

/** SOURCE real coroutine Job→existing writer predicate→actual canonical prefs/receipt. Native storage uses named fixtures. */
class QueueCoroutineCancellationActualStoreTest {
    private fun fixture() = QueueRestorationActualStoreTest().also { it.setup() }
    @Test fun cancellationBeforeEffectRefusesOriginalAndPreservesSelectedBytes() {
        val f = fixture()
        val command = QueueRestorationActualStoreTest.enqueue(f.queue, "SOURCE-cancel-before")
        val request = f.queue.reviewDiscard()
        val originalBytes = f.store.memory["cmd_${command.id}"]
        val job = Job()
        f.store.nextSuccessfulCommit = Runnable {
            job.cancel()
            assertFalse(Thread.currentThread().isInterrupted) // Thread interruption is not this cancellation signal.
        }
        val failure = runCatching { runBlocking {
            withContext(Dispatchers.IO + job) {
                val operation = currentCoroutineContext()
                f.queue.discardReviewed(request) { !operation.isActive }
            }
        } }.exceptionOrNull()
        assertTrue(failure is CancellationException)
        val receipt = f.queue.restoreResult(request.operationId)!!
        assertEquals("REFUSED", receipt.state)
        assertTrue(receipt.removedIds.isEmpty())
        assertEquals(originalBytes, f.store.memory["cmd_${command.id}"])
        assertFalse(receipt.externalCancellationClaimed)
        val sealedReceipt = f.store.memory["restore_operation_${request.operationId}"]
        assertEquals(receipt, QueueRestorationActualStoreTest.discard(f.queue, request))
        assertEquals(sealedReceipt, f.store.memory["restore_operation_${request.operationId}"])
    }
    @Test fun cancellationAfterSuccessfulCommitRecoversOriginalAppliedWithoutAnotherOperation() {
        val f = fixture()
        val command = QueueRestorationActualStoreTest.enqueue(f.queue, "SOURCE-cancel-after")
        val request = f.queue.reviewDiscard()
        val job = Job()
        f.store.nextSuccessfulCommit = Runnable {
            f.store.nextSuccessfulCommit = Runnable { job.cancel() }
        }
        val failure = runCatching { runBlocking {
            withContext(Dispatchers.IO + job) {
                val operation = currentCoroutineContext()
                f.queue.discardReviewed(request) { !operation.isActive }
            }
        } }.exceptionOrNull()
        assertTrue(failure is CancellationException)
        val receipt = f.queue.restoreResult(request.operationId)!!
        assertEquals("APPLIED", receipt.state)
        assertEquals(listOf(command.id), receipt.removedIds)
        assertNull(f.queue.findByIdempotencyKey(command.idempotencyKey))
        assertFalse(receipt.externalCancellationClaimed)
        val originalSealed = f.store.memory["restore_operation_${request.operationId}"]
        val commits = f.store.commits
        assertEquals(receipt, QueueRestorationActualStoreTest.discard(f.queue, request))
        assertEquals(commits, f.store.commits)
        assertEquals(originalSealed, f.store.memory["restore_operation_${request.operationId}"])
        assertEquals(request.deadlineMs, receipt.requestDeadlineMs)
    }
}
