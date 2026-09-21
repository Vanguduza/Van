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

data class QueueEnqueueRequest(
    val kind: CommandKind,
    val payloadJson: String,
    val sensitivity: CommandSensitivity = CommandSensitivity.NORMAL,
    val actionClass: ActionClass? = null,
    val replayPolicy: ReplayPolicy = ReplayPolicy.NORMAL,
    val idempotencyKey: String? = null,
    val ttlMs: Long = EncryptedCommandQueue.DEFAULT_TTL_MS,
)
