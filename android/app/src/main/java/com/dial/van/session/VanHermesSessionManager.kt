package com.dial.van.session

import com.dial.van.gateway.VanGatewayClient
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

/**
 * Rev 1.5 §20 — the durable VAN⇄Hermes logical session, from the phone's side.
 *
 * The session is not the socket. §20.3 makes that the whole point: the owner's
 * conversation, the mission they are watching and the browser they are holding all bind to
 * a `van_session_id` that survives a carrier change, a backgrounded app and a reconnect.
 * A design where the session *is* the socket loses the owner's turn every time the train
 * goes into a tunnel, and shows them an empty screen rather than an error.
 *
 * What lives here is the machinery — the socket, the coroutine, the outbox. What lives in
 * [TransportSupervisor], [SessionEnvelope] and [ResumePolicy] is every decision this makes,
 * because those are the parts that can be executed in the JVM harness and this is not.
 *
 * The rule this file exists to enforce, stated once: **a resend is the same message.**
 * `readdress` moves an envelope to a new path without touching its identity, and the outbox
 * holds the original. Minting a new message id on a failover would turn one owner command
 * into two, and it would only ever happen on a network nobody can reproduce.
 */
class VanHermesSessionManager(
    private val gateway: VanGatewayClient,
    private val scope: CoroutineScope,
    private val paths: List<TransportPathDescriptor> = DEFAULT_PATHS,
) {

    data class State(
        val vanSessionId: String? = null,
        val sessionEpoch: Int = 0,
        val pathEpoch: Int = 0,
        val supervisor: SupervisorState = SupervisorState.STARTING,
        val routeRedundant: Boolean = false,
        val reason: String = "not started",
    ) {
        /** §0B — what the owner is told. Never "multipath" for two carriers on one road. */
        val ownerReadableConnection: String
            get() = when (supervisor) {
                SupervisorState.MULTIPATH_HEALTHY -> "Connected, with a spare route"
                SupervisorState.SINGLE_PATH -> "Connected"
                SupervisorState.FAILOVER_PREPARING -> "Connection weak, preparing a switch"
                SupervisorState.FAILOVER_COMMITTING -> "Switching connection"
                SupervisorState.RECOVERING -> "Reconnecting"
                SupervisorState.STORE_AND_FORWARD -> "Offline — your work is queued"
                SupervisorState.OFFLINE_LOCAL -> "Offline"
                SupervisorState.STARTING, SupervisorState.PRIMARY_CONNECTING -> "Connecting"
            }
    }

    private val supervisor = TransportSupervisor(paths)
    private val outbox = ArrayDeque<JSONObject>()
    private val inFlight = LinkedHashMap<String, JSONObject>()
    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    private var socket: WebSocket? = null
    private var interactionActive: Boolean = false
    private var lastEventSeq: Long = 0

    private val http = OkHttpClient.Builder()
        .pingInterval(HeartbeatPolicy.ACTIVE_INTERVAL_MS, TimeUnit.MILLISECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS) // a WebSocket is supposed to be idle
        .build()

    /**
     * Submit owner work over the session.
     *
     * @param actionClass the command's action class, used only to decide what may be
     *   stored while there is no path. An A4 or A5 is never queued: a flush an hour later
     *   must not be able to perform an irreversible or approval-bearing action.
     * @param requiresLiveOwnerContext true when the request only means anything now —
     *   "read that back to me", "cancel it".
     */
    fun submit(
        kind: String,
        payload: JSONObject,
        actionClass: String,
        requiresLiveOwnerContext: Boolean = false,
    ): SubmissionOutcome {
        val sessionId = _state.value.vanSessionId
            ?: return SubmissionOutcome.Refused("session_not_established")
        val envelope = SessionEnvelope.build(
            messageId = "msg_${UUID.randomUUID()}",
            vanSessionId = sessionId,
            sessionEpoch = _state.value.sessionEpoch,
            pathEpoch = _state.value.pathEpoch,
            deviceId = gateway.deviceIdOrEmpty(),
            kind = kind,
            createdAtMs = System.currentTimeMillis(),
            payload = payload,
            // Minted once, here, and carried through every retry and failover below.
            idempotencyKey = "idem_${UUID.randomUUID()}",
        )

        val live = socket
        if (live != null && live.send(envelope.toString())) {
            inFlight[envelope.getString("message_id")] = envelope
            return SubmissionOutcome.Sent(envelope.getString("message_id"))
        }

        val storability = OutboxPolicy.classify(actionClass, requiresLiveOwnerContext)
        return when (storability) {
            CommandStorability.NEVER_STORE ->
                SubmissionOutcome.Refused("offline_and_not_storable")
            CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT -> {
                outbox.addLast(envelope.put("requires_reconfirm", true))
                SubmissionOutcome.QueuedNeedsReconfirm(envelope.getString("message_id"))
            }
            else -> {
                outbox.addLast(envelope)
                SubmissionOutcome.Queued(envelope.getString("message_id"))
            }
        }
    }

    sealed class SubmissionOutcome {
        data class Sent(val messageId: String) : SubmissionOutcome()
        data class Queued(val messageId: String) : SubmissionOutcome()

        /** Stored, but the owner is asked again before it runs. */
        data class QueuedNeedsReconfirm(val messageId: String) : SubmissionOutcome()
        data class Refused(val reason: String) : SubmissionOutcome()
    }

    /** Whether the owner is waiting on something, which sets the heartbeat cadence (§20.8). */
    fun setInteractionActive(active: Boolean) {
        interactionActive = active
    }

    /**
     * Open (or reopen) the session and connect the realtime path.
     *
     * The session is opened over HTTP first and the socket is attached to it, rather than
     * the socket creating the session. That order is what makes a reconnect a *resume*:
     * the identity already exists and outlives any one carrier (§20.3).
     */
    suspend fun start() {
        if (_state.value.vanSessionId == null) {
            val opened = runCatching {
                gateway.sessionOpen(pathId = PRIMARY_PATH_ID, routeId = "primary-ingress")
            }.getOrNull() ?: run {
                publish(SupervisorState.OFFLINE_LOCAL)
                return
            }
            _state.value = _state.value.copy(
                vanSessionId = opened.optString("van_session_id"),
                sessionEpoch = opened.optInt("session_epoch", 0),
                pathEpoch = opened.optInt("path_epoch", 0),
            )
        }
        val sessionId = _state.value.vanSessionId ?: return
        val request = Request.Builder().url(gateway.sessionSocketUrl(sessionId)).build()
        socket = http.newWebSocket(request, Listener())
        publish(SupervisorState.PRIMARY_CONNECTING)
    }

    fun close() {
        socket?.close(1000, "owner_closed")
        socket = null
        publish(SupervisorState.OFFLINE_LOCAL)
    }

    private inner class Listener : WebSocketListener() {

        override fun onOpen(webSocket: WebSocket, response: Response) {
            scope.launch(Dispatchers.IO) { resume() }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val message = runCatching { JSONObject(text) }.getOrNull() ?: return
            observe(connected = true, lastRxAgeMs = 0, writeFailures = 0)
            message.optLong("seq", 0).takeIf { it > lastEventSeq }?.let { lastEventSeq = it }
            when (message.optString("kind")) {
                "session.ack" -> inFlight.remove(message.optString("message_id"))
                "session.epoch_changed" -> _state.value = _state.value.copy(
                    sessionEpoch = message.optInt("session_epoch", _state.value.sessionEpoch),
                )
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            observe(connected = false, lastRxAgeMs = Long.MAX_VALUE / 2, writeFailures = 1)
            // The decision of what to do next is the supervisor's, not this callback's.
            val target = supervisor.failoverTarget(PRIMARY_PATH_ID)
            _state.value = _state.value.copy(
                supervisor = if (target == null) {
                    SupervisorState.OFFLINE_LOCAL
                } else {
                    supervisor.stateDuringFailover(supervisor.healthOf(PRIMARY_PATH_ID))
                },
                // §20.9 — a new carrier is a new path epoch, so the Gateway can fence work
                // that was in flight on the old one.
                pathEpoch = _state.value.pathEpoch + 1,
                reason = t.message ?: "transport_failed",
            )
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            observe(connected = false, lastRxAgeMs = Long.MAX_VALUE / 2, writeFailures = 0)
        }
    }

    private fun observe(connected: Boolean, lastRxAgeMs: Long, writeFailures: Int) {
        supervisor.observe(
            PRIMARY_PATH_ID,
            PathObservation(
                connected = connected,
                rttMs = 0,
                lastRxAgeMs = lastRxAgeMs,
                consecutiveWriteFailures = writeFailures,
                recentDisconnects = 0,
            ),
            interactionActive = interactionActive,
        )
        val verdict = supervisor.continuity()
        _state.value = _state.value.copy(
            supervisor = verdict.state,
            routeRedundant = verdict.routeRedundant,
            reason = verdict.reason,
        )
    }

    /**
     * §20.9 — re-establish the session, and say honestly which of the three things happened.
     *
     * A reconnect that silently created a new session would lose the turn the owner was in
     * the middle of. [ResumePolicy] separates the cases; this acts on them.
     */
    private suspend fun resume() {
        val local = _state.value
        val sessionId = local.vanSessionId ?: return
        val response = runCatching {
            gateway.sessionResume(
                vanSessionId = sessionId,
                sessionEpoch = local.sessionEpoch,
                lastEventSeq = lastEventSeq,
                pendingCommandIds = inFlight.keys.toList(),
                pathId = PRIMARY_PATH_ID,
                routeId = "primary-ingress",
            )
        }.getOrNull()
        val refusal = response?.optString("refusal")?.takeIf { it.isNotBlank() }
        val serverEpoch = if (refusal == null) {
            response?.optInt("session_epoch", -1)?.takeIf { it >= 0 }
        } else {
            null
        }

        when (ResumePolicy.classify(local.sessionEpoch, serverEpoch, refusal)) {
            ResumeOutcome.RESUMED -> {
                response?.let { adoptCursor(it) }
                flushOutbox()
            }
            ResumeOutcome.RESUMED_WITH_NEW_EPOCH -> {
                response?.let { adoptCursor(it) }
                _state.value = local.copy(sessionEpoch = serverEpoch ?: local.sessionEpoch)
                // Everything unacknowledged goes again under the new epoch, as itself.
                inFlight.values.forEach { outbox.addLast(it) }
                inFlight.clear()
                flushOutbox()
            }
            ResumeOutcome.SESSION_REPLACED -> {
                val fresh = runCatching {
                    gateway.sessionOpen(pathId = PRIMARY_PATH_ID, routeId = "primary-ingress")
                }.getOrNull() ?: return
                _state.value = local.copy(
                    vanSessionId = fresh.optString("van_session_id"),
                    sessionEpoch = fresh.optInt("session_epoch", 0),
                    pathEpoch = 0,
                    reason = "previous session is gone; this is a new one",
                )
                // Deliberately not flushed: work addressed to a session that no longer
                // exists is not the same work, and replaying it silently into a new one is
                // how an owner's cancelled instruction gets performed.
                outbox.clear()
                inFlight.clear()
            }
            ResumeOutcome.REFUSED -> _state.value = local.copy(
                supervisor = SupervisorState.OFFLINE_LOCAL,
                reason = refusal ?: "resume_refused",
            )
        }
    }

    /**
     * §20.11 — the Gateway's cursor wins.
     *
     * `replay_from_seq` is the authority on what this device has actually seen. Keeping a
     * local cursor and trusting it after a failover is how a client ends up quietly
     * skipping the events that were in flight when the path dropped.
     */
    private fun adoptCursor(resume: JSONObject) {
        lastEventSeq = resume.optLong("replay_from_seq", lastEventSeq)
        val states = resume.optJSONObject("command_states") ?: return
        // A command the Gateway already knows about is not resent, whatever the outbox
        // thinks: §20.12's whole purpose is that a lost acknowledgement is not a lost
        // command.
        states.keys().forEach { messageId -> inFlight.remove(messageId) }
    }

    private fun flushOutbox() {
        val live = socket ?: return
        val epoch = _state.value.pathEpoch
        while (outbox.isNotEmpty()) {
            val queued = outbox.first()
            if (queued.optBoolean("requires_reconfirm", false)) {
                // Left in place on purpose. Something the owner has to be asked about again
                // is not something a reconnect may send on their behalf.
                break
            }
            val readdressed = SessionEnvelope.readdress(queued, epoch)
            if (!live.send(readdressed.toString())) break
            outbox.removeFirst()
            inFlight[readdressed.getString("message_id")] = readdressed
        }
    }

    /** Anything the owner still has to be asked about before it runs. */
    fun awaitingReconfirmation(): List<JSONObject> =
        outbox.filter { it.optBoolean("requires_reconfirm", false) }

    private fun publish(state: SupervisorState) {
        _state.value = _state.value.copy(supervisor = state)
    }

    companion object {
        const val PRIMARY_PATH_ID = "primary-wss"

        /**
         * §20.6 — what this build actually has.
         *
         * One route, because there is one ingress. Declaring a second `routeId` here would
         * make [TransportSupervisor.continuity] report `MULTIPATH_HEALTHY` and tell the
         * owner they are covered for a failure that would take both paths out at once.
         * §0B is explicit that this is the honest answer until a second ingress exists.
         */
        val DEFAULT_PATHS = listOf(
            TransportPathDescriptor(
                pathId = PRIMARY_PATH_ID,
                pathClass = PathClass.A_REALTIME,
                protocol = "WSS",
                endpoint = "/v1/session/ws",
                routeId = "primary-ingress",
                priority = 10,
                supportsFullDuplex = true,
            ),
            TransportPathDescriptor(
                pathId = "fallback-http2",
                pathClass = PathClass.C_REPLAY_FLOOR,
                protocol = "HTTP2",
                endpoint = "/v1/session/events-stream",
                routeId = "primary-ingress",
                priority = 50,
            ),
        )
    }
}
