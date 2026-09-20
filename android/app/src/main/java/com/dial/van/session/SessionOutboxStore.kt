package com.dial.van.session

/**
 * Rev 1.5 §§2.7, 20.14 — the seam between the session outbox and the canonical queue.
 *
 * An interface, and that is the point rather than a convenience. `EncryptedCommandQueue` is
 * Android — Keystore, `EncryptedSharedPreferences`, a disk — so nothing in this repository
 * can execute it. What *can* be executed is every decision either side of it, and an
 * interface is where that line falls: `VanHermesSessionManager` persists and restores
 * through this, a fake implements it in the JVM harness, and the production binding is
 * twenty lines of adapter that CI compiles.
 *
 * It is deliberately small. Three operations, because §20.14 needs exactly three moments to
 * survive a process death — admission, reconfirmation, and the command leaving.
 */
interface SessionOutboxStore {

    /**
     * Write or overwrite one entry with its envelope.
     *
     * Overwrite rather than append, keyed on the message id: a reconfirmation is the same
     * command with one more fact known about it, and appending would leave two records
     * where a restore has to decide which is current.
     */
    fun persist(entry: OutboxEntry, envelopeJson: String)

    /** Everything still queued, oldest first, as `(entry, envelopeJson)`. */
    fun restore(): List<Pair<OutboxEntry, String>>

    /**
     * Forget one, because it has been sent or has expired.
     *
     * Called after the send succeeds, never before. Removing first would lose the command
     * to a kill between the removal and the socket write — which is the same defect as not
     * persisting at all, arriving one instruction later.
     */
    fun forget(messageId: String)
}
