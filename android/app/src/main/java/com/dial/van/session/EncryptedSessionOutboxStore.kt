package com.dial.van.session

import com.dial.van.queue.CommandKind
import com.dial.van.queue.EncryptedCommandQueue
import com.dial.van.queue.QueueEnqueueRequest

/**
 * Rev 1.5 §§2.7, 20.14 — the session outbox, stored in the queue that already exists.
 *
 * The whole of the Android binding, kept this thin on purpose. Every decision it could have
 * made lives in [OutboxPersistence], which is pure and executed in the harness; what is left
 * here is `EncryptedCommandQueue`'s API, which needs a Keystore and a disk and therefore
 * cannot be executed anywhere in this repository. CI compiles it; nothing runs it.
 *
 * §2.7 forbids a parallel replacement for that queue, so this is an adapter rather than a
 * store. The practical consequence is the one that matters: the envelope's bytes and
 * §20.14's policy metadata are one record and one write, so a process death cannot leave a
 * command whose payload survived and whose expiry, attempt count or reconfirmation did not.
 */
class EncryptedSessionOutboxStore(
    private val queue: EncryptedCommandQueue,
) : SessionOutboxStore {

    override fun persist(entry: OutboxEntry, envelopeJson: String) {
        // Remove-then-enqueue rather than an in-place update, because the queue has no
        // update: the id is the message id, so this replaces the record rather than
        // leaving two for a restore to choose between.
        queue.remove(entry.messageId)
        queue.enqueue(
            QueueEnqueueRequest(
                kind = CommandKind.SESSION_ENVELOPE,
                payloadJson = envelopeJson,
                sensitivity = OutboxPersistence.sensitivityFor(entry.actionClass),
                actionClass = runCatching {
                    com.dial.van.queue.ActionClass.valueOf(entry.actionClass)
                }.getOrNull(),
                replayPolicy = OutboxPersistence.replayPolicyFor(entry),
                idempotencyKey = entry.idempotencyKey,
                ttlMs = (entry.expiresAtMs - entry.createdAtMs).coerceAtLeast(1L),
            ),
        )
    }

    override fun restore(): List<Pair<OutboxEntry, String>> =
        queue.peekReady()
            .mapNotNull { command ->
                OutboxPersistence.toEntry(command)?.let { it to command.payloadJson }
            }
            .sortedBy { (entry, _) -> entry.createdAtMs }

    override fun forget(messageId: String) {
        queue.remove(messageId)
    }
}
