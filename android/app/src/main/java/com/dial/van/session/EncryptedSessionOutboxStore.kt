package com.dial.van.session

import com.dial.van.queue.OutboxRecordStore

/**
 * Rev 1.5 §§2.7, 20.14 — the session outbox, stored in the queue that already exists.
 *
 * §2.7 forbids a parallel replacement for `EncryptedCommandQueue`, so this is an adapter
 * rather than a store: the envelope's bytes and §20.14's policy metadata are one record
 * and **one write**, so a process death cannot leave a command whose payload survived and
 * whose expiry, attempt count or reconfirmation did not.
 *
 * It depends on [OutboxRecordStore] rather than on the concrete queue, and that is what
 * makes it executable. The production implementation needs a Keystore and a disk and can
 * be compiled in this repository and run nowhere; three methods can be faked in a dozen
 * lines, so the decisions below — that a persist is one mutating call, that removal
 * happens only after an acknowledged send — are executed in the harness rather than read.
 *
 * ## What the previous version actually did
 *
 * Worth recording, because every one of these was invisible and all its tests passed.
 *
 *  * It wrote by `remove(messageId)` then `enqueue(...)`. Two persistent operations, so a
 *    kill between them lost the owner's command outright — the defect a durable outbox
 *    exists to prevent, arriving by a different door.
 *  * `enqueue` mints a **fresh** row id. The row was therefore never keyed by the message
 *    id, so that `remove(messageId)` matched nothing, and neither did [forget]. A
 *    delivered command stayed on disk and was restored and re-sent after every restart.
 *  * `enqueue` also de-duplicates on the idempotency key and returns the existing row
 *    unchanged. A reconfirmation — the same command with the owner's "yes" now attached —
 *    was therefore silently discarded, and the owner was asked again after the next
 *    restart.
 *
 * All three are the same mistake: an *insert* API used where the outbox needs an
 * *upsert keyed on the message id*. [OutboxRecordStore.upsert] is that operation.
 */
class EncryptedSessionOutboxStore(
    private val records: OutboxRecordStore,
) : SessionOutboxStore {

    /**
     * One call, and the record's id is the message id.
     *
     * Both halves matter. One call means a process death leaves the old record or the new
     * one and never neither; the message id as the key means a second persist of the same
     * command replaces the first rather than adding a row a restore would have to choose
     * between — and means [forget] can find it.
     */
    override fun persist(entry: OutboxEntry, envelopeJson: String) {
        records.upsert(OutboxPersistence.toCommand(entry, envelopeJson))
    }

    /**
     * Everything still queued, oldest first.
     *
     * A row that does not map back is skipped rather than guessed at: [OutboxPersistence]
     * returns null for a record that was not written by this path, and inventing the
     * missing policy is how a stored approval becomes a silent replay.
     */
    override fun restore(): List<Pair<OutboxEntry, String>> =
        records.recordsOfKind(OutboxPersistence.SESSION_KIND)
            .mapNotNull { command ->
                OutboxPersistence.toEntry(command)?.let { it to command.payloadJson }
            }

    override fun forget(messageId: String) {
        records.remove(messageId)
    }
}
