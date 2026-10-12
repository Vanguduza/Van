package com.dial.van.muse

/** The browser alone owns approval truth. Both VAN Android and the Site are projections. */
enum class MuseDecision { ALLOW_ONCE, DENY }

/**
 * The exact command fence. A user-visible card is NOT an authorization unless its
 * source is fresh, the browser control generation is positive and the prompt is still
 * waiting. The gateway must independently re-read and enforce every field before actuation.
 */
data class MuseApprovalFence(
    val approvalId: String,
    val sessionId: String,
    val taskId: String,
    val projectId: String?,
    val actionFingerprint: String,
    val controlGeneration: Long,
    val revision: Long,
    val expiresAtEpochMs: Long,
    val state: String,
    val allowed: Set<MuseDecision>,
) {
    fun canAct(choice: MuseDecision, nowEpochMs: Long, sourceFresh: Boolean): Boolean =
        sourceFresh && choice in allowed && state == "AWAITING_OWNER" &&
            approvalId.isNotBlank() && sessionId.isNotBlank() && taskId.isNotBlank() &&
            actionFingerprint.matches(Regex("^[a-fA-F0-9]{64}$")) &&
            controlGeneration > 0L && revision > 0L &&
            expiresAtEpochMs > nowEpochMs
}

/** Never infer a valid approval from a green worker heartbeat. */
data class MuseSourceHealth(
    val sessionGreen: Boolean,
    val watchdogGreen: Boolean,
    val relayLive: Boolean,
    val lastSourceAtEpochMs: Long?,
) {
    fun fresh(nowEpochMs: Long): Boolean =
        sessionGreen && watchdogGreen && relayLive &&
            lastSourceAtEpochMs != null &&
            nowEpochMs >= lastSourceAtEpochMs &&
            nowEpochMs - lastSourceAtEpochMs <= MAX_AGE_MS

    companion object { const val MAX_AGE_MS = 90_000L }
}
