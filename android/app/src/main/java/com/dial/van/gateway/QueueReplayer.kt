package com.dial.van.gateway

import com.dial.van.degraded.DegradedModeStore
import com.dial.van.degraded.RestoreAction
import com.dial.van.queue.CommandKind
import com.dial.van.queue.EncryptedCommandQueue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Replays encrypted offline queue through the gateway. Preserves idempotency keys.
 * Expired sensitive commands are never dispatched (queue already drops them).
 *
 * CONTEXT_INGEST items are never dispatched as commands. They are captured third-party
 * content (notifications, shares) and carry no owner authority; elevating them into a
 * command requires an explicit owner action, not a queue drain.
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
            // Captured third-party content is data, not an owner command. The previous
            // version fell through to `payload.toString()` when a payload had no "text"
            // key, which is exactly what a notification envelope looks like — so an
            // arbitrary app's notification JSON became the text of a device-signed owner
            // command (finding P0-SEC-002). Context ingress now has no path to dispatch.
            if (!ReplayDispatchPolicy.mayDispatch(cmd.kind)) {
                queue.remove(cmd.id)
                continue
            }
            try {
                val payload = JSONObject(cmd.payloadJson)
                // No fallback to the serialized envelope. A queued command without command
                // text is malformed, not an invitation to send the whole payload.
                val text = ReplayDispatchPolicy.commandTextOrNull(payload)
                if (text == null) {
                    queue.remove(cmd.id)
                    continue
                }
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

/**
 * The two rules that keep captured third-party content out of the owner-command path,
 * as pure functions so they can be unit tested without an Android runtime.
 *
 * Finding P0-SEC-002: the replayer dispatched `payload.optString("text", payload.toString())`
 * for every queued item. A notification envelope has no "text" key, so the whole JSON —
 * including an arbitrary app's attacker-controlled body — became the text of a
 * device-signed owner command.
 */
object ReplayDispatchPolicy {

    /** Kinds that are captured data rather than owner intent, and may never be dispatched. */
    private val NEVER_DISPATCHABLE = setOf(CommandKind.CONTEXT_INGEST.name)

    /** True only for queue kinds that represent an owner-authored command. */
    fun mayDispatch(kind: String): Boolean = kind !in NEVER_DISPATCHABLE

    /**
     * The command text, or null when the payload carries none.
     *
     * There is deliberately no fallback to the serialized payload: a queued command without
     * command text is malformed, not an invitation to send the whole envelope.
     */
    fun commandTextOrNull(payload: JSONObject): String? =
        payload.optString("text", "").takeIf { it.isNotBlank() }
}
