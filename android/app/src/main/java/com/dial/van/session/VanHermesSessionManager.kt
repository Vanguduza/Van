package com.dial.van.session

import com.dial.van.gateway.VanGatewayClient
import com.dial.van.gateway.SessionOpenRecoveryException
import com.dial.van.telemetry.SessionTelemetry
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
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
     * [TransportSupervisor], [SessionEnvelope] and [ResumePolicy] is the pure policy. The JVM
     * harness also executes this adapter with test-only gateway and socket implementations.
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
    /**
     * §§2.7, 20.14 — where a queued session envelope actually lives.
     *
     * Optional so the session still works without it, and the state that leaves is named
     * rather than hidden: with no store the outbox is in memory and does not survive the
     * process, which `State.outboxIsDurable` reports. It was in memory *unconditionally*
     * for a checkpoint, and that is the defect this parameter exists to close.
     *
     * The canonical queue rather than one of this class's own: §2.7 forbids a parallel
     * replacement, and a second store would also mean two writes per command with a
     * process death possible between them.
     */
    private val store: SessionOutboxStore? = null,
    /**
     * §§20.15, 20.16 — where the two numbers only this side can measure are left.
     *
     * Optional because the session is usable without telemetry and a null here must not
     * change a single decision below. Nothing in this class reads it back.
     */
    private val telemetry: SessionTelemetry? = null,
    /**
     * §20.15 — what to do when a stored command will not be sent after all.
     *
     * A callback rather than a list the caller has to remember to drain. `expired` and
     * `abandoned` accumulated correctly for two checkpoints and nothing read either, so
     * "the owner is told" was a property of a method nobody called. Push makes the
     * absence of a reader visible at construction instead.
     *
     * Called with `(messageId, ownerReadableLine)`, already in the owner's words, because
     * three callers inventing their own phrasing for "this did not happen" is how a
     * product stops sounding like one thing.
     */
    private val onUndelivered: (List<Pair<String, String>>) -> Unit = {},
    /**
     * §20.1 — where a durable downstream page goes.
     *
     * The blueprint says this SHALL be `EventStream.applyPage`, and naming the reducer
     * rather than owning one is the whole of that sentence: a second event store would
     * give the owner two histories that disagree about what has happened.
     *
     * Defaulted to doing nothing so the session is still constructible without one, and
     * a build with no reader drops events loudly in review rather than quietly at runtime.
     */
    private val onDownstreamPage: (com.dial.van.events.EventPage) -> Unit = {},
    /** Optional transport seam; production still uses the pinned TLS client below. */
    private val webSocketFactory: WebSocket.Factory? = null,
    private val httpCarrierFactory: ((Request, WebSocketListener, String, Long) -> WebSocket)? = null,
    private val reconnectDelayMillis: (Int) -> Long = { attempt ->
        (1_000L shl attempt.coerceIn(0, 5)).coerceAtMost(30_000L)
    },
) {

    data class State(
        val vanSessionId: String? = null,
        val sessionEpoch: Int = 0,
        val pathEpoch: Int = 0,
        val supervisor: SupervisorState = SupervisorState.STARTING,
        val routeRedundant: Boolean = false,
        val reason: String = "not started",
        /** §20.9 — which path may carry a new owner message, and which is merely warm. */
        val authoritativePathId: String = PRIMARY_PATH_ID,
        val standby: StandbyDecision = StandbyDecision(
            StandbyRole.COLD, "not started",
        ),
        /** §20.15 — how much is waiting, by what may be done with it. */
        val outboxDepth: Map<CommandStorability, Int> = emptyMap(),
        /**
         * §20.14 — whether what is waiting would survive this process being killed.
         *
         * Reported rather than assumed, because for one checkpoint it was false and
         * everything said otherwise. A build with no store still runs; it just cannot
         * claim store-and-forward, and this is the field that stops it claiming.
         */
        val outboxIsDurable: Boolean = false,
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

    /**
     * §20.14 — the envelope and the metadata that decides what may be done with it.
     *
     * Paired rather than merged: the envelope is what goes on the wire and the entry is
     * what the flush reasons about, and a flush that read the wire format would be
     * deciding policy from a field an envelope happens to carry.
     */
    private data class QueuedMessage(val entry: OutboxEntry, val envelope: JSONObject)

    private val outbox = ArrayDeque<QueuedMessage>()
    private val inFlight = LinkedHashMap<String, JSONObject>()
    private var outboxRestored = false
    private var restoredSessionConflict = false
    private val _state = MutableStateFlow(State(outboxIsDurable = store != null))
    val state: StateFlow<State> = _state.asStateFlow()

    @Volatile private var socket: WebSocket? = null
    private val connectMutex = Mutex()
    private var socketReady = false
    @Volatile private var reconnectWanted = false
    private var connectionGeneration = 0L
    private var reconnectJob: Job? = null
    private var failedWssConnections = 0
    private var usingHttpCarrier = false
    private val activePathId: String get() = if (usingHttpCarrier) HTTP_PATH_ID else PRIMARY_PATH_ID
    private var interactionActive: Boolean = false
    private var lastEventSeq: Long = 0

    /**
     * §20.10 — the switch currently in progress, or null when the path is healthy.
     *
     * A field rather than a local because the nine steps span two callbacks: the socket
     * failure opens it and the resume closes it, and there is no single function in which
     * a failover happens.
     */
    private var failover: FailoverTransaction? = null

    /**
     * When the primary was first marked suspect, on the monotonic clock.
     *
     * Monotonic, because this is a duration: a wall-clock step during a carrier change —
     * which is when NTP is most likely to correct — would produce a negative failover
     * time, and a negative sample drags a percentile down silently.
     */
    private var suspectAtNanos: Long = 0

    private val http = OkHttpClient.Builder()
        .pingInterval(HeartbeatPolicy.ACTIVE_INTERVAL_MS, TimeUnit.MILLISECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS) // a WebSocket is supposed to be idle
        .build()

    /**
     * The client for a socket to [url]. On the direct mutual-TLS endpoint: the pinned gateway
     * CA and this phone's client certificate. Anywhere else: platform trust. Derived from
     * [http], so both share one connection pool and dispatcher.
     */
    private fun clientFor(url: String): OkHttpClient =
        gateway.tlsTransport(url)?.let { (factory, trust) -> http.newBuilder().sslSocketFactory(factory, trust).build() } ?: http

    /**
     * Submit owner work over the session.
     *
     * @param actionClass the command's action class, used only to decide what may be
     *   stored while there is no path. An A4 or A5 is never queued: a flush an hour later
     *   must not be able to perform an irreversible or approval-bearing action.
     * @param requiresLiveOwnerContext true when the request only means anything now —
     *   "read that back to me", "cancel it".
     */
    @Synchronized
    fun submit(
        kind: String,
        payload: JSONObject,
        actionClass: String,
        requiresLiveOwnerContext: Boolean = false,
    ): SubmissionOutcome {
        // §20.14 — storable with no session, because that is what offline means.
        //
        // This used to refuse outright when `vanSessionId` was null, which made the outbox
        // useless in the one case it exists for: opening a session is an HTTP call, so a
        // phone with no network has no session id to address an envelope with. The command
        // is stored addressed to nothing and `flushOutbox` rebinds it to the session that
        // exists by then. A live socket is still required to *send*, which is the branch
        // below; only storage tolerates the placeholder.
        val sessionId = _state.value.vanSessionId ?: SessionEnvelope.UNBOUND_SESSION_ID
        val messageId = "msg_${UUID.randomUUID()}"
        // §20.12 — lifted out of the payload and onto the envelope.
        //
        // The Gateway stores `van_session_messages.command_id` from the envelope field,
        // and answers a resume by that identity. Leaving the command id buried in the
        // payload meant the column was always null, so the Gateway could not recognise a
        // resubmitted command as one it already held however the phone asked.
        val commandId = payload.optString("command_id").takeIf { it.isNotBlank() }
        val envelope = SessionEnvelope.build(
            messageId = messageId,
            vanSessionId = sessionId,
            sessionEpoch = _state.value.sessionEpoch,
            pathEpoch = _state.value.pathEpoch,
            deviceId = gateway.deviceIdOrEmpty(),
            kind = kind,
            createdAtMs = System.currentTimeMillis(),
            payload = payload,
            // Minted once, here, and carried through every retry and failover below.
            idempotencyKey = "idem_${UUID.randomUUID()}",
            commandId = commandId,
        )

        // Classify before either storage or a live write: send only queues bytes locally.
        // Eligible work must survive a kill even when the link looked healthy at submit.
        // A4/A5 and other prohibited classes stay solely in memory on a live path.
        val entry = DurableOutbox.admit(
            messageId = messageId,
            commandId = commandId ?: messageId,
            idempotencyKey = envelope.optString("idempotency_key", ""),
            turnId = payload.optString("turn_id", ""),
            actionClass = actionClass,
            requiresLiveOwnerContext = requiresLiveOwnerContext,
            payloadRef = envelope.getString("message_id"),
            nowMs = System.currentTimeMillis(),
        )
        if (entry != null) store?.persist(entry, envelope.toString())

        val live = socket.takeIf { socketReady }
        if (live != null && live.send(envelope.toString())) {
            inFlight[envelope.getString("message_id")] = envelope
            return SubmissionOutcome.Sent(envelope.getString("message_id"))
        }
        if (entry == null) return SubmissionOutcome.Refused("offline_and_not_storable")

        // Written before it is queued in memory, not after. The other order loses the
        // command to a kill in between, and the whole point of this record is the kill.
        outbox.addLast(QueuedMessage(entry, envelope))
        publishOutboxDepth()
        return if (entry.storability == CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT) {
            SubmissionOutcome.QueuedNeedsReconfirm(entry.messageId)
        } else {
            SubmissionOutcome.Queued(entry.messageId)
        }
    }

    /**
     * §20.15 — the owner was asked again and said yes.
     *
     * Stamped rather than re-classified, so the record still says what kind of command
     * this was when someone later asks why it ran.
     */
    @Synchronized
    fun reconfirm(messageId: String, nowMs: Long = System.currentTimeMillis()): Boolean {
        val index = outbox.indexOfFirst { it.entry.messageId == messageId }
        if (index < 0) return false
        val queued = outbox[index]
        val reconfirmed = OwnerReconfirmationSurface.reconfirm(queued.entry, nowMs)
            ?: return false
        // §20.15 — the owner said yes, and that has to outlive the app. A reconfirmation
        // held only in memory means the owner is asked twice for the same command, which
        // is the failure mode that trains someone to stop reading the question.
        store?.persist(reconfirmed, queued.envelope.toString())
        outbox[index] = queued.copy(entry = reconfirmed)
        return true
    }

    /**
     * §20.15 — the actual owner surface, projected from the canonical queue.
     *
     * The signed command text is read from the encrypted envelope already in memory; no
     * second copy is persisted for presentation. Only entries the deterministic outbox
     * currently classifies as NeedsReconfirmation are returned.
     */
    @Synchronized
    fun pendingOwnerReconfirmations(
        nowMs: Long = System.currentTimeMillis(),
    ): List<OwnerReconfirmationRequest> =
        outbox.mapNotNull { queued ->
            OwnerReconfirmationSurface.project(queued.entry, queued.envelope, nowMs)
        }

    /**
     * Explicit owner confirmation followed by an immediate flush when a live path exists.
     *
     * When still offline, the durable confirmation remains stamped on the canonical queue
     * and the ordinary reconnect flush sends it later. The same message/idempotency
     * identity is preserved in both cases.
     */
    @Synchronized
    fun reconfirmAndFlush(
        messageId: String,
        nowMs: Long = System.currentTimeMillis(),
    ): Boolean {
        if (!reconfirm(messageId, nowMs)) return false
        flushOutbox()
        return true
    }

    /**
     * Explicit owner cancellation of an item that is waiting for reconfirmation.
     *
     * This cannot be used as a generic queue-delete API: only an entry that the outbox is
     * presently holding for the owner's answer may be removed.
     */
    @Synchronized
    fun cancelReconfirmation(
        messageId: String,
        nowMs: Long = System.currentTimeMillis(),
    ): Boolean {
        val queued = outbox.firstOrNull { it.entry.messageId == messageId } ?: return false
        if (OwnerReconfirmationSurface.project(queued.entry, queued.envelope, nowMs) == null) {
            return false
        }
        if (!outbox.remove(queued)) return false
        store?.forget(messageId)
        publishOutboxDepth()
        return true
    }

    /** §20.15 — what the owner's screen shows for each queued item. */
    fun queuedForOwner(nowMs: Long = System.currentTimeMillis()): List<Pair<String, String>> =
        outbox.map { it.entry.messageId to DurableOutbox.ownerReadableState(it.entry, nowMs) }

    sealed class SubmissionOutcome {
        data class Sent(val messageId: String) : SubmissionOutcome()
        data class Queued(val messageId: String) : SubmissionOutcome()

        /** Stored, but the owner is asked again before it runs. */
        data class QueuedNeedsReconfirm(val messageId: String) : SubmissionOutcome()
        data class Refused(val reason: String) : SubmissionOutcome()
    }

    /** Whether the owner is waiting on something, which sets the heartbeat cadence (§20.8). */
    @Synchronized
    fun setInteractionActive(active: Boolean) {
        interactionActive = active
        reconsiderStandby()
    }

    /**
     * §20.9 — what the phone can afford, which decides whether a spare path is held open.
     *
     * Fed from the resource envelope rather than sampled here: the battery and Data Saver
     * readings are the runtime's, and a second sampler would be a second answer.
     */
    @Synchronized
    fun setStandbyConditions(
        batteryPercent: Int,
        charging: Boolean,
        standbyIsMetered: Boolean,
        dataSaverEnabled: Boolean,
    ) {
        standbyBattery = batteryPercent
        standbyCharging = charging
        standbyMetered = standbyIsMetered
        standbyDataSaver = dataSaverEnabled
        reconsiderStandby()
    }

    private var standbyBattery: Int = 100
    private var standbyCharging: Boolean = false
    private var standbyMetered: Boolean = false
    private var standbyDataSaver: Boolean = false

    private fun reconsiderStandby() {
        val decision = WarmStandbyPolicy.decide(
            StandbyConditions(
                interactionActive = interactionActive,
                batteryPercent = standbyBattery,
                charging = standbyCharging,
                standbyIsMetered = standbyMetered,
                dataSaverEnabled = standbyDataSaver,
                // §20.6 — a spare on the same road is not a spare. Asked of the
                // supervisor rather than assumed, because it is the thing that knows.
                independentRouteAvailable = paths.map { it.routeId }.toSet().size >= 2,
            ),
        )
        _state.value = _state.value.copy(standby = decision)
    }

    /**
     * Open (or reopen) the session and connect the realtime path.
     *
     * The session is opened over HTTP first and the socket is attached to it, rather than
     * the socket creating the session. That order is what makes a reconnect a *resume*:
     * the identity already exists and outlives any one carrier (§20.3).
     */
    suspend fun start() {
        reconnectWanted = true
        connect()
    }

    private suspend fun connect() = connectMutex.withLock {
        val generation = synchronized(this) {
            if (!reconnectWanted || !gateway.isPaired() || socket != null) return@withLock
            if (failedWssConnections >= 2 && (webSocketFactory == null || httpCarrierFactory != null)) usingHttpCarrier = true
            connectionGeneration += 1
            connectionGeneration
        }
        restoreOutbox()
        if (restoredSessionConflict) return@withLock
        val persistedIdentity = try { gateway.restoredSessionIdentity() }
        catch (_: Exception) {
            _state.value = _state.value.copy(supervisor = SupervisorState.OFFLINE_LOCAL, reason = "session_identity_invalid")
            return@withLock
        }
        if (persistedIdentity != null && _state.value.vanSessionId == null) {
            _state.value = _state.value.copy(vanSessionId = persistedIdentity.getString("van_session_id"),
                sessionEpoch = persistedIdentity.getInt("session_epoch"), pathEpoch = persistedIdentity.getInt("path_epoch"))
        } else if (persistedIdentity != null && persistedIdentity.optString("van_session_id") != _state.value.vanSessionId) {
            restoredSessionConflict = true
            _state.value = _state.value.copy(supervisor = SupervisorState.OFFLINE_LOCAL, reason = "stored_session_identity_conflict")
            return@withLock
        }
        runCatching { gateway.ensureTlsIdentity() }
        if (_state.value.vanSessionId == null) {
            val opened = try {
                gateway.sessionOpen(pathId = activePathId, routeId = "primary-ingress",
                    protocol = if (usingHttpCarrier) "HTTP_SSE" else "WSS",
                    pathClass = if (usingHttpCarrier) "B_STREAMING" else "A_REALTIME")
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (missing: SessionOpenRecoveryException) {
                reconnectWanted = false
                _state.value = _state.value.copy(supervisor = SupervisorState.OFFLINE_LOCAL, reason = missing.message.orEmpty())
                return@withLock
            } catch (failure: Exception) {
                synchronized(this) {
                    if (generation == connectionGeneration) {
                        _state.value = _state.value.copy(
                            supervisor = SupervisorState.OFFLINE_LOCAL,
                            reason = failure.message ?: "session_open_failed",
                        )
                        scheduleReconnect()
                    }
                }
                return@withLock
            }
            synchronized(this) {
                if (!reconnectWanted || generation != connectionGeneration) return@withLock
                val sessionId = opened.optString("van_session_id").takeIf { it.isNotBlank() }
                if (sessionId == null) {
                    scheduleReconnect()
                    return@withLock
                }
                _state.value = _state.value.copy(
                    vanSessionId = sessionId,
                    sessionEpoch = opened.optInt("session_epoch", 0),
                    pathEpoch = opened.optInt("path_epoch", 0),
                )
            }
        }
        val sessionId = _state.value.vanSessionId ?: return@withLock
        val socketUrl = gateway.sessionSocketUrl(sessionId)
        synchronized(this) {
            if (!reconnectWanted || generation != connectionGeneration) return@withLock
            socketReady = false
            publish(SupervisorState.PRIMARY_CONNECTING)
            val request = Request.Builder().url(socketUrl).apply {
                gateway.sessionSocketHeaders().forEach { (name, value) -> header(name, value) }
            }.build()
            val listener = Listener(generation)
            if (usingHttpCarrier) {
                socket = httpCarrierFactory?.invoke(request, listener, sessionId, lastEventSeq) ?:
                    HttpSessionCarrier(request, scope, listener,
                        post = { gateway.sessionUpstream(it) }, downstream = { gateway.sessionDownstream(sessionId, lastEventSeq) })
                (socket as? HttpSessionCarrier)?.start()
            } else socket = (webSocketFactory ?: clientFor(socketUrl)).newWebSocket(request, listener)
        }
    }

    /** One retry worker, with a bounded delay, shared by startup and transport recovery. */
    @Synchronized
    private fun scheduleReconnect() {
        if (!reconnectWanted || !gateway.isPaired() || reconnectJob?.isActive == true) return
        reconnectJob = scope.launch(Dispatchers.IO, start = CoroutineStart.LAZY) {
            try {
                var attempt = 0
                while (isActive && reconnectWanted && gateway.isPaired() && socket == null) {
                    delay(reconnectDelayMillis(attempt).coerceAtLeast(1L))
                    connect()
                    attempt += 1
                }
            } finally {
                val ownJob = currentCoroutineContext()[Job]
                synchronized(this@VanHermesSessionManager) {
                    if (reconnectJob === ownJob) reconnectJob = null
                    // A failure may arrive as this worker exits after creating a socket.
                    if (reconnectWanted && socket == null) scheduleReconnect()
                }
            }
        }
        reconnectJob?.start()
    }

    @Synchronized
    private fun transportFailed(webSocket: WebSocket, generation: Long, reason: String, failedHandshake: Boolean = true) {
        if (!reconnectWanted || generation != connectionGeneration || socket !== webSocket) return
        connectionGeneration += 1 // callbacks from this socket can no longer change the session
        socket = null
        socketReady = false
        if (!usingHttpCarrier && failedHandshake) failedWssConnections += 1
        webSocket.cancel()
        markSuspect()
        observe(connected = false, lastRxAgeMs = Long.MAX_VALUE / 2, writeFailures = 1)
        _state.value = _state.value.copy(supervisor = SupervisorState.RECOVERING, reason = reason)
        scheduleReconnect()
    }

    /**
     * §20.14 — pick the outbox back up after the process was killed.
     *
     * Called from [start] rather than from the constructor: a restore reads the disk, and
     * a constructor that did disk I/O would do it on whatever thread happened to build
     * this. Idempotent, because `start` is called again on every reconnect and a second
     * restore must not duplicate what the first one loaded.
     */
    @Synchronized
    private fun restoreOutbox() {
        val store = this.store ?: return
        if (outboxRestored) return
        val held = outbox.map { it.entry.messageId }.toSet() + inFlight.keys
        for ((entry, envelopeJson) in store.restore()) {
            if (entry.messageId in held) continue
            val envelope = runCatching { JSONObject(envelopeJson) }.getOrNull() ?: continue
            outbox.addLast(QueuedMessage(entry, envelope))
        }
        outboxRestored = true
        val addressed = outbox.map { it.envelope }.filterNot(SessionEnvelope::isUnbound)
        val sessions = addressed.map { it.optString("van_session_id") to it.optInt("session_epoch", -1) }.toSet()
        if (_state.value.vanSessionId == null && sessions.isNotEmpty()) {
            val address = sessions.singleOrNull()
            if (address == null || address.first.isBlank() || address.second < 0) {
                restoredSessionConflict = true
                _state.value = _state.value.copy(
                    supervisor = SupervisorState.OFFLINE_LOCAL,
                    reason = "queued work belongs to conflicting sessions; recovery needs review",
                )
            } else {
                // Recover the recorded logical authority before opening a fresh session.
                // A new socket resumes this identity and the server decides what it holds.
                _state.value = _state.value.copy(
                    vanSessionId = address.first, sessionEpoch = address.second,
                    pathEpoch = addressed.maxOf { it.optInt("path_epoch", 0) },
                )
            }
        }
        publishOutboxDepth()
    }

    @Synchronized
    fun close() {
        reconnectWanted = false
        connectionGeneration += 1
        reconnectJob?.cancel()
        reconnectJob = null
        socketReady = false
        socket?.close(1000, "owner_closed")
        socket = null
        failedWssConnections = 0
        usingHttpCarrier = false
        publish(SupervisorState.OFFLINE_LOCAL)
    }

    private inner class Listener(private val generation: Long) : WebSocketListener() {

        override fun onOpen(webSocket: WebSocket, response: Response) {
            scope.launch(Dispatchers.IO) { resume(webSocket, generation) }
        }

        /**
         * §§20.1, 20.4 — the two shapes the Gateway sends, read as it writes them.
         *
         * This used to take `seq` from the top of the frame, where there is none, and
         * switch on `kind` looking for `"session.ack"`, which the Gateway does not send —
         * its answer carries the *envelope's* kind. So the cursor never advanced, nothing
         * ever left `inFlight`, and every downstream event was parsed into nothing.
         *
         * The reading is [SessionDownstream]'s, which is pure and pinned against the
         * Gateway's own construction sites by a contract test. What is left here is what
         * to do about each shape.
         */
        override fun onMessage(webSocket: WebSocket, text: String) {
            synchronized(this@VanHermesSessionManager) {
                if (generation != connectionGeneration || socket !== webSocket) return
                val message = runCatching { JSONObject(text) }.getOrNull() ?: return
                observe(connected = true, lastRxAgeMs = 0, writeFailures = 0)
                when (val frame = SessionDownstream.parse(message)) {
                    is SessionDownstream.Frame.Event -> {
                        // §20.1's SHALL: durable downstream pages go into the existing
                        // reducer, not into a second one. `applyPage` is seq-keyed, so a
                        // frame that overlaps what a REST replay already delivered does not
                        // show the owner the same thing twice.
                        frame.page.nextCursor.takeIf { it > lastEventSeq }?.let { lastEventSeq = it }
                        onDownstreamPage(frame.page)
                    }
                    is SessionDownstream.Frame.Acknowledgement -> {
                        if (frame.resultPending) {
                            // The durable admission exists, but its result is not yet a
                            // receipt. Retain the original envelope and let resume ask
                            // whether execution finished, without minting another command.
                            if (frame.messageId in inFlight) {
                                transportFailed(webSocket, generation, "session_result_pending", failedHandshake = false)
                            }
                            return
                        }
                        // Accepted or refused, it is answered and no longer in flight. A
                        // refusal left in flight would be re-sent by the next resume, which
                        // is sending the Gateway something it has already declined.
                        inFlight.remove(frame.messageId)
                        store?.forget(frame.messageId)
                    }
                    SessionDownstream.Frame.Unrecognised -> Unit
                }
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            transportFailed(webSocket, generation, t.message ?: "transport_failed")
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, reason)
            transportFailed(webSocket, generation, reason.ifBlank { "transport_closed" })
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            transportFailed(webSocket, generation, reason.ifBlank { "transport_closed" })
        }
    }

    private fun observe(connected: Boolean, lastRxAgeMs: Long, writeFailures: Int) {
        supervisor.observe(
            activePathId,
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
     * §20.10 step 1 — the primary is suspect, and the clock starts.
     *
     * The local path epoch is deliberately *not* incremented here, and that is a fix
     * rather than an omission. It used to be: the client bumped its own `pathEpoch` on
     * every socket failure while the Gateway grants `authoritative_path_epoch + 1` on
     * each accepted resume. One failure and one resume agree. Two failures before a
     * resume succeeds do not — the client stamps 3 on every envelope, the Gateway fences
     * everything that is not 2, and the session is silently, permanently deaf with both
     * sides believing they are connected. §20.10 says the epoch is *granted*, and
     * [FailoverTransaction.promote] is where this adopts the grant.
     */
    private fun markSuspect() {
        val open = failover
        if (open != null && open.phase != FailoverTransaction.Phase.PROMOTED &&
            open.phase != FailoverTransaction.Phase.ABANDONED
        ) {
            // Already mid-switch. Restarting the clock would report the last few seconds
            // of a thirty-second outage as the owner's interruption.
            return
        }
        failover = FailoverTransaction(
            currentEpoch = _state.value.pathEpoch,
            activePathId = _state.value.authoritativePathId,
        ).also { it.markSuspect() }
        suspectAtNanos = System.nanoTime()
    }

    /**
     * §20.10 steps 6-8 — adopt the epoch the Gateway granted, and say how long it took.
     *
     * The duration is reported only on a promotion. A failover that was abandoned did not
     * end, and recording the time up to the point it was given up on would put the
     * failures into the same histogram as the successes and make the percentile look
     * better the worse things got.
     */
    private fun completeFailover(grantedPathEpoch: Int, pathId: String) {
        val open = failover ?: return
        if (open.phase == FailoverTransaction.Phase.SUSPECT) open.beginResume()
        if (!open.promote(pathId, grantedPathEpoch)) {
            // The Gateway re-granted an epoch that does not advance, so the session has
            // not actually moved. Left un-promoted on purpose: adopting it would leave
            // the old path believing it is still authoritative.
            return
        }
        _state.value = _state.value.copy(
            pathEpoch = open.epoch,
            authoritativePathId = open.authoritativePathId,
        )
        if (suspectAtNanos != 0L) {
            telemetry?.onFailoverCompleted((System.nanoTime() - suspectAtNanos) / 1_000_000L)
            suspectAtNanos = 0L
        }
        failover = null
    }

    /**
     * §20.9 — re-establish the session, and say honestly which of the three things happened.
     *
     * A reconnect that silently created a new session would lose the turn the owner was in
     * the middle of. [ResumePolicy] separates the cases; this acts on them.
     */
    private suspend fun resume(webSocket: WebSocket, generation: Long) {
        val local = synchronized(this) {
            if (generation != connectionGeneration || socket !== webSocket) return
            _state.value
        }
        val sessionId = local.vanSessionId ?: return
        val response = try {
            gateway.sessionResume(
                vanSessionId = sessionId,
                sessionEpoch = local.sessionEpoch,
                lastEventSeq = lastEventSeq,
                pendingCommandIds = pendingIdentities().map {
                    SessionReconciliation.identityOf(it.messageId, it.commandId)
                },
                pathId = activePathId,
                routeId = "primary-ingress",
                pathClass = if (usingHttpCarrier) "B_STREAMING" else "A_REALTIME",
            )
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            // A lost HTTP answer is not a server declaration that this session is gone.
            transportFailed(webSocket, generation, failure.message ?: "resume_failed")
            return
        }
        val refusal = response.optString("refusal").takeIf { it.isNotBlank() }
        val serverEpoch = if (refusal == null) {
            response.optInt("session_epoch", -1).takeIf { it >= 0 }
        } else {
            null
        }

        if (refusal == null && serverEpoch == null) {
            transportFailed(webSocket, generation, "resume_response_invalid")
            return
        }
        synchronized(this) {
            if (generation != connectionGeneration || socket !== webSocket) return
            when (ResumePolicy.classify(local.sessionEpoch, serverEpoch, refusal)) {
                ResumeOutcome.RESUMED -> {
                    if (!usingHttpCarrier) failedWssConnections = 0
                    adoptCursor(response)
                    adoptGrantedPathEpoch(response)
                    socketReady = true
                    observe(connected = true, lastRxAgeMs = 0, writeFailures = 0)
                    resendInFlight()
                    flushOutbox()
                }
                ResumeOutcome.RESUMED_WITH_NEW_EPOCH -> {
                    if (!usingHttpCarrier) failedWssConnections = 0
                    adoptCursor(response)
                    _state.value = _state.value.copy(sessionEpoch = serverEpoch ?: local.sessionEpoch)
                    adoptGrantedPathEpoch(response)
                    socketReady = true
                    observe(connected = true, lastRxAgeMs = 0, writeFailures = 0)
                    // Everything unacknowledged goes again under the new epoch, as itself.
                    //
                    // Re-sent directly rather than pushed through the outbox, because these
                    // are not the same kind of thing. The outbox holds work *stored across an
                    // outage*, and §20.14 forbids keeping an A4 there. This is work already
                    // sent on a live session whose acknowledgement was lost in the failover —
                    // seconds old, same turn, same idempotency key — and §20.12's
                    // effectively-once admission is exactly what makes re-sending it safe.
                    // Routing it through the outbox would refuse an unacknowledged A4 and the
                    // owner's instruction would vanish at the moment the path recovered.
                    resendInFlight()
                    flushOutbox()
                }
                ResumeOutcome.SESSION_REPLACED -> Unit // handled below, outside the state lock
                ResumeOutcome.REFUSED -> {
                    failover?.abandon()
                    // Authenticated refusals require owner/deployment recovery, not replay.
                    socketReady = false
                    reconnectWanted = false
                    socket = null
                    connectionGeneration += 1
                    webSocket.cancel()
                    _state.value = _state.value.copy(
                        supervisor = SupervisorState.OFFLINE_LOCAL,
                        reason = refusal ?: "resume_refused",
                    )
                }
            }
        }
        if (ResumePolicy.classify(local.sessionEpoch, serverEpoch, refusal) != ResumeOutcome.SESSION_REPLACED) return
        val fresh = try {
            gateway.sessionOpen(pathId = activePathId, routeId = "primary-ingress",
                protocol = if (usingHttpCarrier) "HTTP_SSE" else "WSS",
                pathClass = if (usingHttpCarrier) "B_STREAMING" else "A_REALTIME")
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (missing: SessionOpenRecoveryException) {
            synchronized(this) {
                reconnectWanted = false
                _state.value = _state.value.copy(supervisor = SupervisorState.OFFLINE_LOCAL, reason = missing.message.orEmpty())
            }
            return
        } catch (failure: Exception) {
            transportFailed(webSocket, generation, failure.message ?: "session_replacement_failed")
            return
        }
        synchronized(this) {
            if (generation != connectionGeneration || socket !== webSocket) return
            val freshId = fresh.optString("van_session_id").takeIf { it.isNotBlank() }
            if (freshId == null) {
                transportFailed(webSocket, generation, "session_open_response_invalid")
                return
            }
            failover?.abandon()
            _state.value = _state.value.copy(
                vanSessionId = freshId,
                sessionEpoch = fresh.optInt("session_epoch", 0),
                pathEpoch = fresh.optInt("path_epoch", 0),
                authoritativePathId = activePathId,
                reason = "previous session is gone; this is a new one",
            )
            failover = null
            suspectAtNanos = 0L
            val sentEntries = store?.restore().orEmpty().map { it.first }
                .filter { it.messageId in inFlight }
            val dropped = DurableOutbox.abandonAll(outbox.map { it.entry } + sentEntries, store)
            abandoned += dropped
            tell(dropped, System.currentTimeMillis())
            outbox.clear()
            inFlight.clear()
            publishOutboxDepth()
            // The socket's handshake belongs to the old id; attach to the new session.
            transportFailed(webSocket, generation, "previous session is gone; this is a new one")
        }
    }

    /**
     * §20.11 — the Gateway's cursor wins.
     *
     * `replay_from_seq` is the authority on what this device has actually seen. Keeping a
     * local cursor and trusting it after a failover is how a client ends up quietly
     * skipping the events that were in flight when the path dropped.
     */
    /**
     * §20.10 step 6 — the path epoch the Gateway granted, adopted whether or not this was
     * a failover.
     *
     * The "whether or not" is the bug this closes, and it was not a failover bug at all.
     * `POST /v1/session/resume` grants `authoritative_path_epoch + 1` on *every* accepted
     * resume, and the phone resumes on `onOpen` — so the very first connect moves the
     * Gateway's authoritative epoch to 2 while the device is still stamping the 1 it got
     * from `/open`. `accept_upstream` fences an envelope whose `path_epoch` is not the
     * authoritative one, so every message the owner sent was refused, on a session both
     * sides reported as connected, from the first second. Nothing in the client could
     * see it: the refusal is the Gateway's and the socket stays open.
     */
    private fun adoptGrantedPathEpoch(resume: JSONObject?) {
        // Absent only if the response was not parseable, in which case keeping the old
        // epoch is the safer of the two wrong answers: it fences this device's own work
        // rather than letting it race the path that is being replaced.
        val granted = resume?.optInt("new_path_epoch", -1) ?: -1
        if (granted < 0) return
        if (failover != null) {
            completeFailover(granted, activePathId)
            return
        }
        // An ordinary resume — a first connect, or a reconnect on the same path. There is
        // no transaction to promote and no interruption to time, but the grant is still
        // the grant.
        if (granted > _state.value.pathEpoch) {
            _state.value = _state.value.copy(pathEpoch = granted, authoritativePathId = activePathId)
        }
    }

    /**
     * §20.12 — everything this side is still holding, in the order it was issued.
     *
     * In-flight first, because those were sent on a live socket and are the most likely to
     * be at the Gateway already; then the restored outbox.
     *
     * The outbox is included **in full** rather than filtered to entries with an attempt
     * recorded, and that is the point rather than laziness. `flushOutbox` writes to the
     * socket and only then calls `store.forget`; a process death between those two lines
     * leaves a record on disk that the Gateway already has, with `attemptCount` still
     * zero — because the attempt counter is stamped on *failure*, not on send. Asking
     * about only the attempted ones would therefore miss precisely the kill this
     * reconciliation exists for, and that command would be delivered twice.
     */
    @Synchronized
    private fun pendingIdentities(): List<SessionReconciliation.Pending> {
        val pending = mutableListOf<SessionReconciliation.Pending>()
        for ((messageId, envelope) in inFlight) {
            pending += SessionReconciliation.Pending(
                messageId = messageId,
                commandId = envelope.optString("command_id").takeIf { it.isNotBlank() },
            )
        }
        for (queued in outbox) {
            pending += SessionReconciliation.Pending(
                messageId = queued.entry.messageId,
                commandId = queued.entry.commandId,
            )
        }
        return pending
    }

    @Synchronized
    private fun adoptCursor(resume: JSONObject) {
        lastEventSeq = resume.optLong("replay_from_seq", lastEventSeq)
        val answers = resume.optJSONObject("command_states") ?: return
        val states = buildMap<String, String> {
            answers.keys().forEach { key -> put(key, answers.optString(key)) }
        }
        // §20.12 — a lost acknowledgement is not a lost command, and a command the
        // Gateway already holds is not sent twice. Both halves, from one plan, so that
        // the identity the question was asked by is the identity the answer is matched
        // by. Anything the Gateway did not recognise stays exactly where it is and goes
        // again under its own message id and idempotency key.
        val settled = SessionReconciliation.plan(pendingIdentities(), states).settle.toSet()
        if (settled.isEmpty()) return
        inFlight.keys.removeAll(settled)
        settled.forEach { store?.forget(it) }
        // Removed from the queue *and* from the disk. Leaving the record behind is the
        // restart loop: restored on the next start, flushed again, and the owner's one
        // instruction performed once more after every process death.
        val kept = outbox.filterNot { it.entry.messageId in settled }
        outbox.clear()
        outbox.addAll(kept)
        publishOutboxDepth()
    }

    /**
     * §20.10 step 5 / §20.12 — unacknowledged work, re-addressed to the new path epoch.
     *
     * The envelope keeps its `message_id` and `idempotency_key`, so a Gateway that did
     * receive the first copy recognises this one and does not run it twice.
     */
    @Synchronized
    private fun resendInFlight() {
        val live = socket.takeIf { socketReady } ?: return
        val local = _state.value
        val sessionId = local.vanSessionId ?: return
        val pending = inFlight.values.toList()
        for (envelope in pending) {
            val readdressed = SessionEnvelope.readdress(
                SessionEnvelope.rebind(envelope, sessionId, local.sessionEpoch), local.pathEpoch,
            )
            if (!live.send(readdressed.toString())) {
                // The new path died during the resume. Keep it in flight rather than
                // dropping it: the next resume will try again, and losing it here would
                // lose an owner instruction to a transient socket failure.
                inFlight[envelope.getString("message_id")] = envelope
                return
            }
            inFlight[readdressed.getString("message_id")] = readdressed
        }
    }

    @Synchronized
    private fun flushOutbox() {
        val live = socket.takeIf { socketReady } ?: return
        // A socket implies a session, because the socket is opened against one. Guarded
        // anyway and guarded *here*, so the rebind below cannot be the thing that decides
        // to stop mid-flush — an early return inside the loop would append what was held
        // after what had not been reached yet, and the owner's instructions would go out
        // in an order they did not give them in.
        val liveSessionId = _state.value.vanSessionId ?: return
        val epoch = _state.value.pathEpoch
        val now = System.currentTimeMillis()
        val held = ArrayDeque<QueuedMessage>()
        var stop = false
        while (outbox.isNotEmpty()) {
            val queued = outbox.removeFirst()
            if (stop) {
                held.addLast(queued)
                continue
            }
            when (DurableOutbox.flush(queued.entry, now)) {
                is FlushVerdict.Expired -> {
                    // Dropped, not held: the window closed and the owner is told it did
                    // not happen rather than asked about something they have forgotten.
                    expired += queued.entry
                    store?.forget(queued.entry.messageId)
                    tell(listOf(queued.entry), now)
                }
                is FlushVerdict.NeedsReconfirmation, is FlushVerdict.Refused -> {
                    // Kept in place. Something the owner has to be asked about is not
                    // something a reconnect may send on their behalf — and skipping past
                    // it rather than stopping means the rest of the queue still moves.
                    held.addLast(queued)
                }
                is FlushVerdict.Send -> {
                    // Addressed to this session first, then to this path. A command stored
                    // while offline carries the unbound placeholder, and sending that would
                    // be refused by the Gateway as an unknown session — the owner's command
                    // lost at the moment the network came back, which is the worst possible
                    // time for it.
                    val bound = if (SessionEnvelope.isUnbound(queued.envelope)) {
                        SessionEnvelope.rebind(
                            queued.envelope, liveSessionId, _state.value.sessionEpoch,
                        )
                    } else {
                        queued.envelope
                    }
                    val readdressed = SessionEnvelope.readdress(bound, epoch)
                    if (live.send(readdressed.toString())) {
                        inFlight[readdressed.getString("message_id")] = readdressed
                        // WebSocket.send only enqueues bytes. Keep the durable record until
                        // an acknowledgement or resume reconciliation confirms admission.
                    } else {
                        // The socket went away mid-flush. Everything after this keeps its
                        // order, which is why the remainder is moved rather than retried.
                        val attempted = queued.copy(
                            entry = DurableOutbox.attempted(queued.entry, _state.value.authoritativePathId),
                        )
                        store?.persist(attempted.entry, attempted.envelope.toString())
                        held.addLast(attempted)
                        stop = true
                    }
                }
            }
        }
        outbox.addAll(held)
        publishOutboxDepth()
    }

    /** §20.14 — commands whose window closed while there was no path. */
    private val expired = mutableListOf<OutboxEntry>()

    /**
     * §20.9 — commands dropped because the session they were addressed to is gone.
     *
     * Kept apart from [expired] because the two are different things to say. One is "the
     * time you gave it ran out"; the other is "the conversation this belonged to ended".
     * Both are read through [undeliveredSinceLastRead], because what the owner needs is
     * the single fact that it did not happen — and a command dropped without anyone being
     * told is the failure this list exists to prevent.
     */
    private val abandoned = mutableListOf<OutboxEntry>()

    @Synchronized
    fun expiredSinceLastRead(): List<OutboxEntry> {
        val taken = expired.toList()
        expired.clear()
        return taken
    }

    /**
     * Say it, in the owner's words, once per command.
     *
     * `ownerReadableState` is §20.15's single vocabulary for this, chosen there rather
     * than here so that the sentence an owner reads does not depend on which of the two
     * reasons produced it.
     */
    private fun tell(entries: List<OutboxEntry>, nowMs: Long) {
        if (entries.isEmpty()) return
        onUndelivered(
            entries.map { it.messageId to DurableOutbox.ownerReadableState(it, nowMs) },
        )
    }

    /** Everything that will not be sent, whatever the reason, taken once. */
    @Synchronized
    fun undeliveredSinceLastRead(): List<OutboxEntry> {
        val taken = expired + abandoned
        expired.clear()
        abandoned.clear()
        return taken
    }

    /** Anything the owner still has to be asked about before it runs. */
    @Synchronized
    fun awaitingReconfirmation(): List<OutboxEntry> =
        outbox.map { it.entry }.filter {
            DurableOutbox.flush(it, System.currentTimeMillis()) is FlushVerdict.NeedsReconfirmation
        }

    private fun publishOutboxDepth() {
        val depths = DurableOutbox.depthsByStorability(outbox.map { it.entry })
        _state.value = _state.value.copy(outboxDepth = depths)
        // Every class, not only the non-empty ones. A gauge holds its last value, so a
        // class that emptied and stopped being reported would keep telling an operator
        // that someone is waiting to be asked about a command that went an hour ago.
        telemetry?.onOutboxDepth(
            CommandStorability.entries.associate { it.name to (depths[it] ?: 0) },
        )
    }

    private fun publish(state: SupervisorState) {
        _state.value = _state.value.copy(supervisor = state)
    }

    companion object {
        const val PRIMARY_PATH_ID = "primary-wss"
        const val HTTP_PATH_ID = "fallback-http2"

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
                pathId = HTTP_PATH_ID,
                pathClass = PathClass.B_STREAMING,
                protocol = "HTTP_SSE",
                endpoint = "/v1/session/events-stream",
                routeId = "primary-ingress",
                priority = 50,
            ),
        )
    }
}
