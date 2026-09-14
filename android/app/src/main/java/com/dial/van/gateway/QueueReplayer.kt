package com.dial.van.gateway

import com.dial.van.degraded.DegradedModeStore
import com.dial.van.degraded.RestoreAction
import com.dial.van.queue.EncryptedCommandQueue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Replays encrypted offline queue through the gateway. Preserves idempotency keys.
 * Expired sensitive commands are never dispatched (queue already drops them).
 */
class QueueReplayer(
    private val queue: EncryptedCommandQueue,
    private val gateway: VanGatewayClient,
    private val degraded: DegradedModeStore,
    private val scope: CoroutineScope,
) {
    fun replayAsync() {
        scope.launch(Dispatchers.IO) {
            replayNow()
        }
    }

    suspend fun replayNow(): Int {
        if (!gateway.isEnrolled()) {
            degraded.markBroken("gateway", "Device not enrolled", RestoreAction.OPEN_SETTINGS)
            return 0
        }
        var sent = 0
        for (cmd in queue.drainExecutable()) {
            try {
                val payload = JSONObject(cmd.payloadJson)
                val text = payload.optString("text", payload.toString())
                val action = payload.optString("action_class", "A1")
                val project = if (payload.has("project_id")) payload.optString("project_id") else null
                val result = gateway.dispatchCommand(
                    text = text,
                    actionClass = action,
                    projectId = project?.takeIf { it.isNotBlank() },
                    idempotencyKey = cmd.idempotencyKey,
                    issuedAtUnix = cmd.createdAtEpochMs / 1000L,
                )
                val status = result.optString("status")
                if (
                    status == "expired" ||
                    status == "accepted" ||
                    status == "denied" ||
                    status == "degraded" ||
                    status == "approval_required" ||
                    status == "conflict" ||
                    status == "rejected_untrusted"
                ) {
                    queue.remove(cmd.id)
                    sent += 1
                } else {
                    queue.markAttempt(cmd.id, status)
                }
                degraded.markWorking("gateway")
            } catch (ex: Exception) {
                queue.markAttempt(cmd.id, ex.message)
                degraded.markBroken("gateway", ex.message ?: "replay_failed", RestoreAction.RETRY_CONNECTION)
            }
        }
        return sent
    }
}
