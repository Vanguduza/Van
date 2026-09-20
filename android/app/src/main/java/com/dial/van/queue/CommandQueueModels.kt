package com.dial.van.queue

import kotlinx.serialization.Serializable

enum class ActionClass {
    A1,
    A2,
    A3,
    A4,
    A5,
}

enum class ReplayPolicy {
    NORMAL,
    NO_STALE_REPLAY,
}

enum class CommandSensitivity {
    /** Safe read / deterministic local (A1). */
    NORMAL,
    /** Bounded write or external (A2–A3). */
    ELEVATED,
    /** Destructive / send-as-owner (A4) — requires biometric. */
    DESTRUCTIVE,
    /** Must never leave device or be executed from share/context (A5). */
    SECRET,
}

enum class CommandKind {
    ATTENTION,
    DECISION,
    TASK,
    REMINDER,
    MEMORY,
    CONNECTION,
    HERMES_DISPATCH,
    CONTEXT_INGEST,

    /**
     * Rev 1.5 §20.14 — a durable logical-session envelope, waiting for a path.
     *
     * Its own kind, and `ReplayDispatchPolicy` refuses to dispatch it. Sharing a kind
     * with owner commands would mean the replayer picked session envelopes up after a
     * process death and posted them to `POST /v1/commands` — a second delivery of work
     * that is already addressed to the session path, down a path that does not
     * understand it. That is the shape of P0-SEC-002 and it does not get a second
     * chance here.
     */
    SESSION_ENVELOPE,
}

@Serializable
data class QueuedCommand(
    val id: String,
    val idempotencyKey: String,
    val kind: String,
    val payloadJson: String,
    val sensitivity: String,
    val actionClass: String? = null,
    val replayPolicy: String = ReplayPolicy.NORMAL.name,
    val createdAtEpochMs: Long,
    val expiresAtEpochMs: Long,
    val attemptCount: Int = 0,
    val lastError: String? = null,

    // ---------------------------------------------------------------- Rev 1.5 §20.14
    //
    // The durable logical session's outbox metadata, carried on this record rather than
    // beside it.
    //
    // Beside it was the first design and it was wrong in a way that only shows up after a
    // process death: two stores mean two writes, and a kill between them leaves a command
    // whose bytes survived and whose policy did not — so a reconfirmation the owner never
    // gave, or an expiry nobody can see, decides whether it is replayed. One record is
    // atomic by construction.
    //
    // §2.7 forbids a parallel replacement for this queue, and this is the other half of
    // obeying that: the session does not get its own store, it gets these fields.
    //
    // All nullable or defaulted, so a record written before this existed still loads.

    /** The session envelope's `message_id`, which is what the outbox is keyed by. */
    val sessionMessageId: String? = null,

    /**
     * The session envelope's `command_id`.
     *
     * Separate from [id] because they are different identities and the first version of
     * this mapping conflated them: [id] is the queue's key, which is the message id, and
     * losing the command id means a restored command cannot be matched against the
     * Gateway's `command_states` on resume — §20.12's ACK-unknown reconciliation, broken
     * silently by a process death.
     */
    val sessionCommandId: String? = null,

    /** `CommandStorability`, as its enum name. Null for a command that is not session work. */
    val storability: String? = null,

    /** §20.14 — "read that back to me" means nothing an hour later. */
    val requiresLiveOwnerContext: Boolean = false,

    /** §20.15 — set when the owner was asked again and said yes. */
    val reconfirmedAtEpochMs: Long? = null,

    /** Which path the last attempt went out on; three failures on one path is not three on three. */
    val lastAttemptPath: String? = null,

    /** The owner turn this belongs to, so a resumed session can group it. */
    val turnId: String? = null,
) {
    fun isExpired(nowMs: Long = System.currentTimeMillis()): Boolean = nowMs >= expiresAtEpochMs

    fun sensitivityEnum(): CommandSensitivity =
        runCatching { CommandSensitivity.valueOf(sensitivity) }.getOrDefault(CommandSensitivity.NORMAL)

    /** Exact Rev 3.1 class. Older queue entries fall back conservatively from sensitivity. */
    fun actionClassEnum(): ActionClass =
        actionClass?.let { runCatching { ActionClass.valueOf(it) }.getOrNull() }
            ?: when (sensitivityEnum()) {
                CommandSensitivity.NORMAL -> ActionClass.A1
                CommandSensitivity.ELEVATED -> ActionClass.A3
                CommandSensitivity.DESTRUCTIVE -> ActionClass.A4
                CommandSensitivity.SECRET -> ActionClass.A5
            }

    fun replayPolicyEnum(): ReplayPolicy =
        runCatching { ReplayPolicy.valueOf(replayPolicy) }.getOrDefault(ReplayPolicy.NORMAL)

    fun isReplayEligible(nowMs: Long = System.currentTimeMillis()): Boolean {
        if (isExpired(nowMs)) return false
        if (actionClassEnum() == ActionClass.A5) return false
        if (replayPolicyEnum() == ReplayPolicy.NO_STALE_REPLAY && attemptCount > 0) return false
        return true
    }

    fun kindEnum(): CommandKind =
        runCatching { CommandKind.valueOf(kind) }.getOrDefault(CommandKind.CONTEXT_INGEST)
}

/**
 * How long a queued command stays meaningful when nothing says otherwise.
 *
 * Here rather than on `EncryptedCommandQueue` so that this file has no Android reference
 * at all: the record and its defaults are the part `android/verification` can execute, and
 * one class name in a default argument was enough to keep the whole model out of the
 * harness. `EncryptedCommandQueue.DEFAULT_TTL_MS` still resolves, and still to this.
 */
const val COMMAND_QUEUE_DEFAULT_TTL_MS: Long = 24L * 60 * 60 * 1000

data class QueueEnqueueRequest(
    val kind: CommandKind,
    val payloadJson: String,
    val sensitivity: CommandSensitivity = CommandSensitivity.NORMAL,
    val actionClass: ActionClass? = null,
    val replayPolicy: ReplayPolicy = ReplayPolicy.NORMAL,
    val idempotencyKey: String? = null,
    val ttlMs: Long = COMMAND_QUEUE_DEFAULT_TTL_MS,
)
