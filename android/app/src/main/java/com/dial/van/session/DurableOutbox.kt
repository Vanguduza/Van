package com.dial.van.session

/**
 * Rev 1.5 §§20.14, 20.15 — what the phone holds while there is no path, and what it is
 * allowed to do with it later.
 *
 * §2.7 forbids a parallel replacement for `EncryptedCommandQueue`, so this is not one. It
 * is the metadata §20.14 asks that queue to carry, and the rules that read it: the queue
 * still owns the bytes and their encryption; this owns the question "may this still be
 * sent, and does the owner have to be asked again first".
 *
 * The sentence that shapes it is §20.14's last: **A4/destructive actions do not silently
 * execute hours later because connectivity returned.** [OutboxPolicy] already classified
 * commands before storage; what was missing was everything after storage — expiry, the
 * attempt count, the path an attempt was made on, and the difference between a command
 * that may flush silently and one that needs the owner asked again.
 *
 * Pure. The encryption and the disk are the existing queue's; the decisions are here,
 * where a flush an hour after an outage can be executed in a test rather than waited for.
 */

/**
 * §20.14's record, on top of whatever the queue already stores.
 *
 * `payloadRef` rather than a payload: the command body is in the encrypted queue and has
 * no business being in a metadata record that gets logged, compared and counted.
 */
data class OutboxEntry(
    val messageId: String,
    val commandId: String,
    val idempotencyKey: String,
    val turnId: String,
    val createdAtMs: Long,
    val expiresAtMs: Long,
    val storability: CommandStorability,
    val actionClass: String,
    val requiresLiveOwnerContext: Boolean,
    val payloadRef: String,
    val lastAttemptPath: String? = null,
    val attemptCount: Int = 0,
    /** Set when the owner has been asked again and said yes. */
    val reconfirmedAtMs: Long? = null,
) {
    fun expired(nowMs: Long): Boolean = nowMs >= expiresAtMs
}

/** What the flush decided, and why — each is a different thing to tell the owner. */
sealed interface FlushVerdict {
    /** Goes now, on the authoritative path. */
    data class Send(val entry: OutboxEntry) : FlushVerdict

    /** §20.14 — the window closed. Dropped, and the owner is told it was not done. */
    data class Expired(val entry: OutboxEntry) : FlushVerdict

    /** §20.15 — the owner is asked again before anything happens. */
    data class NeedsReconfirmation(val entry: OutboxEntry) : FlushVerdict

    /** Never stored in the first place; present only if something bypassed the classifier. */
    data class Refused(val entry: OutboxEntry, val reason: String) : FlushVerdict
}

object DurableOutbox {

    /**
     * How long a stored command stays meaningful when nothing says otherwise.
     *
     * Four hours: long enough to cover a commute through a tunnel or an evening with no
     * signal, short enough that a command flushing when the owner has gone to bed is out
     * of scope rather than a surprise. §20.14 names `expires_at` as a field rather than a
     * constant, so this is the default a caller may override per command.
     */
    const val DEFAULT_TTL_MS = 4 * 60 * 60 * 1000L

    /**
     * Anything held longer than this needs asking again whatever its class.
     *
     * Distinct from expiry. A command that is still valid but is now *old* is one the
     * owner has probably forgotten issuing, and sending it silently is the surprise
     * §20.14 is about even when the action itself is reversible.
     */
    const val STALE_AFTER_MS = 30 * 60 * 1000L

    /**
     * Build the record. Classification happens here, before storage, as §20.14 requires.
     *
     * Returns null for what must never be stored, so the caller's only way to keep an A4
     * is to not call this — and there is no argument that overrides the classification.
     */
    fun admit(
        messageId: String,
        commandId: String,
        idempotencyKey: String,
        turnId: String,
        actionClass: String,
        requiresLiveOwnerContext: Boolean,
        payloadRef: String,
        nowMs: Long,
        ttlMs: Long = DEFAULT_TTL_MS,
    ): OutboxEntry? {
        val storability = OutboxPolicy.classify(actionClass, requiresLiveOwnerContext)
        if (storability == CommandStorability.NEVER_STORE) return null
        return OutboxEntry(
            messageId = messageId,
            commandId = commandId,
            idempotencyKey = idempotencyKey,
            turnId = turnId,
            createdAtMs = nowMs,
            expiresAtMs = nowMs + ttlMs,
            storability = storability,
            actionClass = actionClass,
            requiresLiveOwnerContext = requiresLiveOwnerContext,
            payloadRef = payloadRef,
        )
    }

    /**
     * What to do with one entry now that a path is back.
     *
     * Expiry is checked first, because an expired command is not a command to ask about:
     * "do you still want the thing you asked for four hours ago" is a worse question than
     * "that did not happen".
     */
    fun flush(entry: OutboxEntry, nowMs: Long): FlushVerdict = when {
        entry.storability == CommandStorability.NEVER_STORE ->
            FlushVerdict.Refused(entry, "outbox_never_store_was_stored")
        entry.expired(nowMs) -> FlushVerdict.Expired(entry)
        entry.reconfirmedAtMs != null -> FlushVerdict.Send(entry)
        entry.storability == CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT ->
            FlushVerdict.NeedsReconfirmation(entry)
        nowMs - entry.createdAtMs >= STALE_AFTER_MS -> FlushVerdict.NeedsReconfirmation(entry)
        else -> FlushVerdict.Send(entry)
    }

    /**
     * The owner said yes. The reconfirmation is stamped rather than the entry re-classified.
     *
     * Keeping the original storability means the record still says what kind of command
     * this was, which is what an audit of "why did this run at 11pm" needs to read.
     */
    fun reconfirm(entry: OutboxEntry, nowMs: Long): OutboxEntry =
        entry.copy(reconfirmedAtMs = nowMs)

    /**
     * One attempt made. The path is recorded because §20.14 asks for it, and because a
     * command that has failed three times on the same path is a different problem from
     * one that has failed once on each of three.
     */
    fun attempted(entry: OutboxEntry, pathId: String): OutboxEntry =
        entry.copy(attemptCount = entry.attemptCount + 1, lastAttemptPath = pathId)

    /** §20.15 — what the owner's screen shows, by what the queue may do with each item. */
    fun depthsByStorability(entries: List<OutboxEntry>): Map<CommandStorability, Int> =
        entries.groupingBy { it.storability }.eachCount()

    /**
     * §20.15 — "queued" is not "submitted".
     *
     * A single word, chosen here rather than at each call site, because the whole point of
     * the section is that the owner can tell the difference and three surfaces inventing
     * their own wording is how they stop being able to.
     */
    fun ownerReadableState(entry: OutboxEntry, nowMs: Long): String = when (flush(entry, nowMs)) {
        is FlushVerdict.Send -> "Queued — VAN will send this when it can reach the network"
        is FlushVerdict.Expired -> "Not done — this waited too long and VAN let it go"
        is FlushVerdict.NeedsReconfirmation -> "Waiting for you — VAN will ask before doing this"
        is FlushVerdict.Refused -> "Not done — VAN will not perform this from a queue"
    }
}
