package com.dial.van.session

import com.dial.van.queue.ActionClass
import com.dial.van.queue.CommandSensitivity
import com.dial.van.queue.QueuedCommand
import com.dial.van.queue.ReplayPolicy

/**
 * Rev 1.5 §§20.14, 20.15 — the session outbox, as it survives the process dying.
 *
 * `DurableOutbox` decides; this is what makes the decision outlive the app. The two were
 * separate for a checkpoint and the gap between them was the defect: the outbox policy
 * lived in an `ArrayDeque` in `VanHermesSessionManager`, so a command could survive in
 * `EncryptedCommandQueue` while the metadata governing whether it may be silently replayed
 * did not. Android kills backgrounded processes routinely; "durable" that does not survive
 * that is a word rather than a property.
 *
 * **One record, not two.** §2.7 forbids a parallel replacement for `EncryptedCommandQueue`,
 * and obeying that is also what makes this correct: a second store means two writes, and a
 * kill between them leaves the bytes and the policy disagreeing. A reader that found a
 * command with no policy would have to guess, and every guess is wrong in a way that
 * matters — guess `SAFE_TO_RETRY` and an approval-bearing command replays silently; guess
 * `NEVER_STORE` and the owner's work is dropped without being told.
 *
 * Pure: `QueuedCommand` carries no Android, so both directions of this mapping are executed
 * in `android/verification` rather than reasoned about.
 */
object OutboxPersistence {

    /**
     * The queue `kind` a session envelope is stored under.
     *
     * Its own kind so that `EncryptedCommandQueue`'s existing readers — the replayer, which
     * posts to `POST /v1/commands` — do not pick session envelopes up and send them down a
     * path that does not understand them. A shared kind would make a process death replay
     * every queued session message as an owner command.
     */
    const val SESSION_KIND: String = "SESSION_ENVELOPE"

    /**
     * §20.14's record, as a row of the canonical queue.
     *
     * `expiresAtEpochMs` is the entry's own expiry rather than the queue's default: the two
     * mean the same thing and storing the queue's would silently extend a window the outbox
     * had already decided.
     */
    fun toCommand(
        entry: OutboxEntry,
        envelopeJson: String,
        id: String = entry.messageId,
    ): QueuedCommand = QueuedCommand(
        id = id,
        idempotencyKey = entry.idempotencyKey,
        kind = SESSION_KIND,
        payloadJson = envelopeJson,
        // Derived from the action class rather than stored twice. `sensitivity` is the
        // queue's older vocabulary and `actionClass` is the exact one; keeping both in
        // agreement here means a reader of either gets the same answer.
        sensitivity = sensitivityFor(entry.actionClass).name,
        actionClass = entry.actionClass,
        replayPolicy = replayPolicyFor(entry).name,
        createdAtEpochMs = entry.createdAtMs,
        expiresAtEpochMs = entry.expiresAtMs,
        attemptCount = entry.attemptCount,
        sessionMessageId = entry.messageId,
        sessionCommandId = entry.commandId,
        storability = entry.storability.name,
        requiresLiveOwnerContext = entry.requiresLiveOwnerContext,
        reconfirmedAtEpochMs = entry.reconfirmedAtMs,
        lastAttemptPath = entry.lastAttemptPath,
        turnId = entry.turnId,
    )

    /**
     * Back again, or null when this row is not session work.
     *
     * Null rather than a best-effort reconstruction. A row with no `storability` was not
     * written by this path, and inventing one would be the guess described above — the
     * thing that turns a missing field into a silently replayed approval.
     */
    fun toEntry(command: QueuedCommand): OutboxEntry? {
        if (command.kind != SESSION_KIND) return null
        val messageId = command.sessionMessageId ?: return null
        val storability = command.storability
            ?.let { name -> runCatching { CommandStorability.valueOf(name) }.getOrNull() }
            ?: return null
        return OutboxEntry(
            messageId = messageId,
            // The session's command id, not the queue's row id. Those are different
            // identities, and reading the row id here is what silently broke §20.12's
            // reconciliation across a restart.
            commandId = command.sessionCommandId ?: messageId,
            idempotencyKey = command.idempotencyKey,
            turnId = command.turnId.orEmpty(),
            createdAtMs = command.createdAtEpochMs,
            expiresAtMs = command.expiresAtEpochMs,
            storability = storability,
            actionClass = command.actionClass ?: command.actionClassEnum().name,
            requiresLiveOwnerContext = command.requiresLiveOwnerContext,
            payloadRef = messageId,
            lastAttemptPath = command.lastAttemptPath,
            attemptCount = command.attemptCount,
            reconfirmedAtMs = command.reconfirmedAtEpochMs,
        )
    }

    /**
     * The queue's older sensitivity vocabulary, from the exact action class.
     *
     * Both fields exist on the record and a reader may use either, so they must not be
     * able to disagree. Derived rather than passed in for that reason.
     */
    fun sensitivityFor(actionClass: String): CommandSensitivity = when (actionClass) {
        ActionClass.A5.name -> CommandSensitivity.SECRET
        ActionClass.A4.name -> CommandSensitivity.DESTRUCTIVE
        ActionClass.A3.name -> CommandSensitivity.ELEVATED
        else -> CommandSensitivity.NORMAL
    }

    /**
     * §20.14 in the queue's own terms.
     *
     * Anything that needs the owner present is `NO_STALE_REPLAY`, which the queue already
     * honours by never retrying it after a dispatch attempt. That is the same rule the
     * outbox states as `REQUIRE_RECONFIRM_ON_RECONNECT`, and writing it into the field the
     * queue reads means the older machinery enforces it too — rather than both being
     * correct and only one of them being consulted.
     */
    fun replayPolicyFor(entry: OutboxEntry): ReplayPolicy =
        if (entry.requiresLiveOwnerContext ||
            entry.storability == CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT
        ) {
            ReplayPolicy.NO_STALE_REPLAY
        } else {
            ReplayPolicy.NORMAL
        }
}
