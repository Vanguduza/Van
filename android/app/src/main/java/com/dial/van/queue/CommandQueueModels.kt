package com.dial.van.queue

import kotlinx.serialization.Serializable

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
    val createdAtEpochMs: Long,
    val expiresAtEpochMs: Long,
    val attemptCount: Int = 0,
    val lastError: String? = null,
) {
    fun isExpired(nowMs: Long = System.currentTimeMillis()): Boolean = nowMs >= expiresAtEpochMs

    fun sensitivityEnum(): CommandSensitivity =
        runCatching { CommandSensitivity.valueOf(sensitivity) }.getOrDefault(CommandSensitivity.NORMAL)

    fun kindEnum(): CommandKind =
        runCatching { CommandKind.valueOf(kind) }.getOrDefault(CommandKind.CONTEXT_INGEST)
}

data class QueueEnqueueRequest(
    val kind: CommandKind,
    val payloadJson: String,
    val sensitivity: CommandSensitivity = CommandSensitivity.NORMAL,
    val idempotencyKey: String? = null,
    val ttlMs: Long = EncryptedCommandQueue.DEFAULT_TTL_MS,
)
