package com.dial.van.gateway

import android.os.SystemClock
import com.dial.van.degraded.DegradedModeStore
import com.dial.van.degraded.RestoreAction
import com.dial.van.queue.CommandKind
import com.dial.van.queue.EncryptedCommandQueue
import kotlinx.coroutines.CancellationException
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
    private val transport: QueueReplayTransport,
    private val degraded: DegradedModeStore,
    private val scope: CoroutineScope,
    private val clock: () -> Long = SystemClock::elapsedRealtime,
) {
    constructor(queue: EncryptedCommandQueue, gateway: VanGatewayClient, degraded: DegradedModeStore,
                scope: CoroutineScope, clock: () -> Long = SystemClock::elapsedRealtime) :
        this(queue, GatewayQueueReplayTransport(gateway), degraded, scope, clock)

    /**
     * P3-AND-006 — `replayAsync()` was called exactly once, at application start. A command
     * the owner issued in a tunnel sat in the queue until they next killed and reopened the
     * app, which for a resident floating assistant is approximately never.
     *
     * The trigger state is guarded because connectivity callbacks arrive on the framework's
     * thread while a replay is running on an IO dispatcher, and the whole point of the
     * debounce is that two threads must not both decide to start.
     */
    private val lock = Any()
    private var trigger = ReplayTriggerState()
    private var failures = 0

    /** Consecutive failed replays, for the owner's health surface (P3-AND-004). */
    fun consecutiveFailures(): Int = synchronized(lock) { failures }

    /** Called on a connectivity callback. Replays only on the edge into availability. */
    fun onNetworkChanged(available: Boolean) {
        val recovered = synchronized(lock) {
            val edge = ReplayTrigger.networkRecovered(trigger, available)
            trigger = ReplayTrigger.observedNetwork(trigger, available)
            edge
        }
        if (recovered) replayAsync(ReplayReason.CONNECTIVITY_RECOVERED)
    }

    /** Called when the gateway health poll changes verdict. */
    fun onGatewayReachable(reachable: Boolean) {
        val recovered = synchronized(lock) {
            val edge = ReplayTrigger.gatewayRecovered(trigger, reachable)
            trigger = ReplayTrigger.observedGateway(trigger, reachable)
            edge
        }
        if (recovered) replayAsync(ReplayReason.GATEWAY_RECOVERED)
    }

    fun onQueued() = replayAsync(ReplayReason.QUEUE_GREW)

    fun replayAsync(reason: ReplayReason = ReplayReason.APP_START) {
        val now = clock()
        val start = synchronized(lock) {
            val queued = runCatching { queue.size() }.getOrDefault(0)
            if (!ReplayTrigger.shouldReplay(trigger, reason, now, queued)) return
            trigger = ReplayTrigger.started(trigger, now)
            true
        }
        if (!start) return
        scope.launch(Dispatchers.IO) {
            try {
                replayNow()
            } catch (exc: Throwable) {
                synchronized(lock) { failures += 1 }
                throw exc
            } finally {
                synchronized(lock) { trigger = ReplayTrigger.finished(trigger) }
            }
        }
    }

    suspend fun replayNow(): Int {
        if (!transport.isEnrolled()) {
            degraded.markBroken("gateway", "Device not enrolled", RestoreAction.OPEN_SETTINGS)
            synchronized(lock) { failures += 1 }
            return 0
        }
        var sent = 0
        var failed = false
        // Already claimed work is read by its original command identity; never remint it.
        for (held in queue.heldGeneric()) {
            val heldOwner = held.genericOwner ?: continue
            val original = held.genericPreparedBody?.let { runCatching { JSONObject(it) }.getOrNull() } ?: continue
            try {
                val receipt = transport.commandStatus(original.getString("command_id"), heldOwner.profileId, heldOwner.deviceId)
                queue.recordGenericReceipt(held.id, held.genericClaimId ?: continue, receipt.toString())
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { failed = true } // Missing/unavailable is not authoritative absence.
        }
        for (cmd in queue.drainExecutable()) {
            when (ReplayDispatchPolicy.route(cmd.kind)) {
                QueueReplayRoute.SESSION_OUTBOX, QueueReplayRoute.UNKNOWN_HELD -> continue
                QueueReplayRoute.CAPTURED_CONTEXT -> {
                    // Captured data's existing owner applies its own expiry; generic
                    // cleanup never makes that decision on behalf of this branch.
                    if (cmd.isExpired()) {
                        queue.finishCapturedContext(cmd, expiredOnly = true)
                        continue
                    }
                    try {
                        transport.ingestCapturedContext(JSONObject(cmd.payloadJson))
                        queue.finishCapturedContext(cmd)
                        sent += 1
                    } catch (cancelled: CancellationException) { throw cancelled }
                    catch (ex: Exception) { failed = true }
                    continue
                }
                QueueReplayRoute.OWNER_COMMAND -> Unit
            }
            val claimed = queue.claimGeneric(cmd.id, queue.genericRevision(cmd)) ?: continue
            val claim = claimed.genericClaimId ?: continue
            var prepared: String? = null
            try {
                val payload = JSONObject(claimed.payloadJson)
                val text = ReplayDispatchPolicy.commandTextOrNull(payload) ?: error("Original command text unavailable")
                val result = transport.dispatch(claimed, text,
                    onPrepared = { exact -> queue.recordGenericPrepared(claimed.id, claim, exact); prepared = exact },
                    beforeDispatch = {
                        queue.recordGenericPrepared(claimed.id, claim, prepared ?: error("Original command unavailable"))
                    })
                if (result.optString("status") == "in_flight") {
                    queue.recordGenericUnknown(claimed.id, claim, "Original command result pending")
                    failed = true
                } else {
                    queue.recordGenericReceipt(claimed.id, claim, result.toString())
                    sent += 1
                }
            } catch (cancelled: CancellationException) {
                queue.recordGenericUnknown(claimed.id, claim, "Delivery cancelled; original outcome unconfirmed")
                throw cancelled
            } catch (ex: Exception) {
                queue.recordGenericUnknown(claimed.id, claim, "Original outcome unconfirmed")
                failed = true
            }
        }
        synchronized(lock) { failures = if (failed) failures + 1 else 0 }
        if (failed) degraded.markBroken("gateway", "Original queued outcomes need recovery", RestoreAction.RETRY_CONNECTION)
        else degraded.markWorking("gateway")
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
enum class QueueReplayRoute {
    OWNER_COMMAND,
    CAPTURED_CONTEXT,
    SESSION_OUTBOX,
    UNKNOWN_HELD,
}

object ReplayDispatchPolicy {

    /**
     * One routing answer for every queue kind.
     *
     * "Not a command" is not a disposal policy. CONTEXT_INGEST has its own data plane and
     * SESSION_ENVELOPE has its own durable-session consumer. Keeping those states distinct
     * is what prevents both authority escalation and startup data loss.
     */
    fun route(kind: String): QueueReplayRoute = when (kind) {
        CommandKind.CONTEXT_INGEST.name -> QueueReplayRoute.CAPTURED_CONTEXT
        CommandKind.SESSION_ENVELOPE.name -> QueueReplayRoute.SESSION_OUTBOX
        CommandKind.ATTENTION.name, CommandKind.DECISION.name, CommandKind.TASK.name,
        CommandKind.REMINDER.name, CommandKind.MEMORY.name, CommandKind.CONNECTION.name,
        CommandKind.HERMES_DISPATCH.name -> QueueReplayRoute.OWNER_COMMAND
        else -> QueueReplayRoute.UNKNOWN_HELD
    }

    /** True only for queue kinds that represent an owner-authored command. */
    fun mayDispatch(kind: String): Boolean = route(kind) == QueueReplayRoute.OWNER_COMMAND

    /**
     * The command text, or null when the payload carries none.
     *
     * There is deliberately no fallback to the serialized payload: a queued command without
     * command text is malformed, not an invitation to send the whole envelope.
     */
    fun commandTextOrNull(payload: JSONObject): String? =
        payload.optString("text", "").takeIf { it.isNotBlank() }
}


/** Existing gateway transport seam; owns no queue, retry identity or execution authority. */
interface QueueReplayTransport {
    fun isEnrolled(): Boolean
    suspend fun ingestCapturedContext(payload: JSONObject)
    suspend fun commandStatus(commandId: String, profile: String, device: String): JSONObject
    suspend fun dispatch(command: com.dial.van.queue.QueuedCommand, text: String,
                         onPrepared: (String) -> Unit, beforeDispatch: () -> Unit): JSONObject
}

private class GatewayQueueReplayTransport(private val gateway: VanGatewayClient) : QueueReplayTransport {
    override fun isEnrolled() = gateway.isEnrolled()
    override suspend fun ingestCapturedContext(payload: JSONObject) { gateway.ingestCapturedContext(payload) }
    override suspend fun commandStatus(commandId: String, profile: String, device: String) = gateway.originalCommandStatus(commandId, profile, device)
    override suspend fun dispatch(command: com.dial.van.queue.QueuedCommand, text: String,
                                  onPrepared: (String) -> Unit, beforeDispatch: () -> Unit): JSONObject {
        val payload = JSONObject(command.payloadJson)
        return gateway.dispatchCommand(text = text, actionClass = command.actionClassEnum().name,
            projectId = payload.optString("project_id").takeIf { it.isNotBlank() },
            idempotencyKey = command.idempotencyKey, issuedAtUnix = command.createdAtEpochMs / 1000,
            expiresAtUnix = command.expiresAtEpochMs / 1000,
            noStaleReplay = command.replayPolicyEnum() == com.dial.van.queue.ReplayPolicy.NO_STALE_REPLAY,
            onPreparedCommand = onPrepared, beforeDispatch = beforeDispatch)
    }
}
