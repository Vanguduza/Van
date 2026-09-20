package com.dial.van.browser

import android.view.MotionEvent
import com.dial.van.gateway.VanGatewayClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.webrtc.SurfaceViewRenderer
import org.webrtc.VideoTrack

/**
 * Rev 1.5 §§5, 7, 8 — everything the browser surface decides, kept out of the Activity.
 *
 * The Activity draws and receives touches. This decides whether a touch may become an
 * actuation, keeps the session alive, and holds the one piece of state the whole design
 * turns on: whether VAN is currently entitled to act.
 *
 * `mayActuate` is a conjunction of four facts and every one of them has a failure behind it:
 *
 *  * the session state accepts input — otherwise a suspended session takes taps that are
 *    applied when it resumes, minutes later, to a page that has moved on;
 *  * the owner holds the control lease — §ADR-RB-007: watching an agent work is a view;
 *  * the media link is live — §7: a frozen frame with live touch handling is the owner
 *    tapping a picture;
 *  * the device has acknowledged the current viewport revision — §8.6: a tap mapped
 *    through the old viewport lands somewhere the owner did not touch.
 *
 * Any one of those being false and the other three true produces a surface that looks
 * completely normal and does the wrong thing, which is why they are one predicate rather
 * than four checks in four places.
 */
class BrowserSessionController(
    private val gateway: VanGatewayClient,
    private val stream: BrowserStreamClient,
    private val scope: CoroutineScope,
) {

    data class State(
        val snapshot: BrowserSessionSnapshot? = null,
        val link: BrowserStreamClient.Link = BrowserStreamClient.Link.CLOSED,
        val lastError: String? = null,
    ) {
        /**
         * One sentence for the owner, and never an enum name or an internal state.
         *
         * The link is reported before the session, because "Connected" over a dead media
         * link is the sentence that makes the owner keep tapping.
         */
        val ownerReadableState: String
            get() = when {
                lastError != null -> lastError
                snapshot == null -> "Opening the browser…"
                link == BrowserStreamClient.Link.FAILED -> "The picture stopped. Reconnecting."
                link == BrowserStreamClient.Link.RECOVERING -> "Connection wobbled — holding on"
                link != BrowserStreamClient.Link.LIVE -> "Connecting to the browser…"
                snapshot.controlHolder.isAgent -> "VAN is driving — tap Take Control to steer"
                snapshot.viewportUnacknowledged -> "Resizing…"
                else -> snapshot.ownerReadableState
            }
    }

    private val sequencer = BrowserGestureSequencer()
    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    private var heartbeat: Job? = null
    private var renderer: SurfaceViewRenderer? = null

    fun attachRenderer(target: SurfaceViewRenderer) {
        renderer = target
    }

    /** §5.1 — open a session, or re-attach to the one the owner already had. */
    suspend fun open(
        existingSessionId: String?,
        profileAlias: String,
        widthPx: Int,
        heightPx: Int,
        deviceScaleFactor: Float,
    ) {
        val snapshot = runCatching {
            if (existingSessionId != null) {
                gateway.interactiveBrowserRead(existingSessionId)
            } else {
                gateway.interactiveBrowserCreate(
                    profileAlias = profileAlias,
                    widthPx = widthPx,
                    heightPx = heightPx,
                    deviceScaleFactor = deviceScaleFactor,
                )
            }
        }.getOrElse { failure ->
            _state.value = _state.value.copy(lastError = readable(failure))
            return
        }
        _state.value = State(snapshot = snapshot)

        // §8.6 — acknowledge the viewport we are actually drawing before any input is
        // allowed through. The gate below reads this, so forgetting it fails closed.
        acknowledgeViewport(snapshot)
        startHeartbeat()
        connectStream()
    }

    private suspend fun acknowledgeViewport(snapshot: BrowserSessionSnapshot) {
        if (snapshot.ackedViewportRevision == snapshot.viewport.revision) return
        runCatching {
            gateway.interactiveBrowserAckViewport(snapshot.sessionId, snapshot.viewport.revision)
        }.onSuccess {
            _state.value = _state.value.copy(
                snapshot = snapshot.copy(ackedViewportRevision = snapshot.viewport.revision),
            )
        }
    }

    private suspend fun connectStream() {
        val sessionId = _state.value.snapshot?.sessionId ?: return
        val grant = runCatching { gateway.interactiveBrowserStreamGrant(sessionId) }
            .getOrElse { failure ->
                _state.value = _state.value.copy(lastError = readable(failure))
                return
            }
        runCatching {
            stream.connect(
                grant = grant,
                onVideo = { track: VideoTrack -> renderer?.let(track::addSink) },
                onLink = { link -> _state.value = _state.value.copy(link = link) },
            )
        }.onFailure { failure ->
            _state.value = _state.value.copy(lastError = readable(failure))
        }
    }

    /**
     * §5.3 — the session stays alive only while the owner is here.
     *
     * Every heartbeat refreshes the snapshot, so a lease the Gateway could not renew shows
     * up as the session losing `acceptsInput` rather than as input that silently stops
     * working. The cadence is well inside the 120-second lease: two missed beats must not
     * be able to end a session the owner is looking at.
     */
    private fun startHeartbeat() {
        heartbeat?.cancel()
        heartbeat = scope.launch {
            while (isActive) {
                delay(HEARTBEAT_INTERVAL_MS)
                val sessionId = _state.value.snapshot?.sessionId ?: return@launch
                runCatching { gateway.interactiveBrowserHeartbeat(sessionId) }
                    .onSuccess { fresh -> _state.value = _state.value.copy(snapshot = fresh) }
                    .onFailure { failure ->
                        _state.value = _state.value.copy(lastError = readable(failure))
                    }
            }
        }
    }

    /** ADR-RB-007 — the owner takes control back. Not a request; a fact. */
    fun takeControl() {
        val sessionId = _state.value.snapshot?.sessionId ?: return
        scope.launch {
            runCatching { gateway.interactiveBrowserTakeControl(sessionId) }
            runCatching { gateway.interactiveBrowserRead(sessionId) }
                .onSuccess { fresh ->
                    // The gesture space is reset: a gesture begun while an agent held the
                    // lease must not continue into the owner's, or the host would apply
                    // half a drag under the new generation.
                    sequencer.reset()
                    _state.value = _state.value.copy(snapshot = fresh)
                }
        }
    }

    fun suspendSession() {
        val sessionId = _state.value.snapshot?.sessionId ?: return
        heartbeat?.cancel()
        scope.launch { runCatching { gateway.interactiveBrowserSuspend(sessionId) } }
    }

    fun close() {
        heartbeat?.cancel()
        val sessionId = _state.value.snapshot?.sessionId
        stream.close()
        renderer = null
        if (sessionId != null) {
            scope.launch { runCatching { gateway.interactiveBrowserEnd(sessionId) } }
        }
    }

    /** The one gate. See the class note for what each clause prevents. */
    fun mayActuate(): Boolean {
        val current = _state.value
        val snapshot = current.snapshot ?: return false
        return snapshot.mayActuate &&
            current.link == BrowserStreamClient.Link.LIVE &&
            !snapshot.viewportUnacknowledged
    }

    /**
     * Turn one `MotionEvent` into packets.
     *
     * Edges — down and up — go on both channels with one identity, because losing an up is
     * not a degraded gesture but a corrupted one: the page is left holding a drag the owner
     * finished. Moves go on the fast channel only, unordered: a move that arrives late is
     * worse than one that never arrives.
     */
    fun onTouch(event: MotionEvent, viewWidth: Int, viewHeight: Int): Boolean {
        val authority = authority() ?: return false
        val pointerId = event.getPointerId(event.actionIndex)
        val x = BrowserInputProtocol.normalize(event.getX(event.actionIndex), viewWidth)
        val y = BrowserInputProtocol.normalize(event.getY(event.actionIndex), viewHeight)

        return when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                val (gestureId, epoch) = sequencer.beginGesture(pointerId)
                sendEdge(authority, BrowserInputProtocol.Kind.POINTER_DOWN, gestureId, epoch, pointerId, x, y)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> sendEdge(
                authority, BrowserInputProtocol.Kind.POINTER_UP,
                sequencer.gestureFor(pointerId), sequencer.epochFor(pointerId), pointerId, x, y,
            )
            MotionEvent.ACTION_CANCEL -> sendEdge(
                authority, BrowserInputProtocol.Kind.POINTER_CANCEL,
                sequencer.gestureFor(pointerId), sequencer.epochFor(pointerId), pointerId, x, y,
            )
            MotionEvent.ACTION_MOVE -> {
                var delivered = false
                for (index in 0 until event.pointerCount) {
                    val id = event.getPointerId(index)
                    // A pointer with no open gesture is one whose DOWN this controller
                    // never sent — a touch that began while actuation was withheld, and
                    // then continued after it was allowed. The server would hold the MOVE
                    // waiting for a DOWN that is not coming and drop it eight milliseconds
                    // later; not sending it says the same thing without the round trip.
                    if (sequencer.gestureFor(id) == 0) continue
                    delivered = stream.send(
                        BrowserInputProtocol.Packet(
                            authority = authority,
                            kind = BrowserInputProtocol.Kind.POINTER_MOVE,
                            channel = BrowserInputProtocol.Channel.FAST,
                            gestureId = sequencer.gestureFor(id),
                            pointerId = id,
                            gestureEpoch = sequencer.epochFor(id),
                            fastSeq = sequencer.nextFast(),
                            motionSeq = sequencer.nextMotion(id),
                            x = BrowserInputProtocol.normalize(event.getX(index), viewWidth),
                            y = BrowserInputProtocol.normalize(event.getY(index), viewHeight),
                            sentAtMs = System.currentTimeMillis(),
                        ),
                    ) || delivered
                }
                delivered
            }
            else -> false
        }
    }

    /**
     * §8.4 — a wheel or trackpad scroll, which is not a touch and does not arrive as one.
     *
     * Sent on the reliable channel: a dropped scroll is not a stale position that the next
     * event corrects, it is a page that ends up in the wrong place and stays there.
     */
    fun onScroll(event: MotionEvent, viewWidth: Int, viewHeight: Int): Boolean {
        val authority = authority() ?: return false
        return stream.send(
            BrowserInputProtocol.Packet(
                authority = authority,
                kind = BrowserInputProtocol.Kind.SCROLL,
                channel = BrowserInputProtocol.Channel.RELIABLE,
                reliableSeq = sequencer.nextReliable(),
                x = BrowserInputProtocol.normalize(event.x, viewWidth),
                y = BrowserInputProtocol.normalize(event.y, viewHeight),
                // Whole wheel clicks, scaled on the host against its own viewport. Sending
                // pixels would mean this phone's density decided how far a page scrolls on
                // a desktop-sized remote viewport.
                valueA = (event.getAxisValue(MotionEvent.AXIS_HSCROLL) * SCROLL_UNITS).toInt(),
                valueB = (event.getAxisValue(MotionEvent.AXIS_VSCROLL) * SCROLL_UNITS).toInt(),
                sentAtMs = System.currentTimeMillis(),
            ),
        )
    }

    /** §8.4 — a key, both edges, on the reliable channel. A lost key-up is a stuck modifier. */
    fun onKey(keyCode: Int, unicodeChar: Int, down: Boolean): Boolean {
        val authority = authority() ?: return false
        return stream.send(
            BrowserInputProtocol.Packet(
                authority = authority,
                kind = if (down) {
                    BrowserInputProtocol.Kind.KEY_DOWN
                } else {
                    BrowserInputProtocol.Kind.KEY_UP
                },
                channel = BrowserInputProtocol.Channel.RELIABLE,
                reliableSeq = sequencer.nextReliable(),
                valueA = keyCode,
                valueB = unicodeChar,
                sentAtMs = System.currentTimeMillis(),
            ),
        )
    }

    /**
     * §8.4 — text the owner has finished typing.
     *
     * A commit rather than a sequence of key events, because an IME that produced a word
     * from five keystrokes did not produce five keys, and replaying it as keys is how
     * non-Latin input arrives in the page as nonsense.
     */
    fun onTextCommit(text: String): Boolean = sendText(
        BrowserInputProtocol.Kind.TEXT_COMMIT, text,
    )

    /** Text the owner is still in the middle of. Replaced, not appended, by the next one. */
    fun onComposition(text: String): Boolean = sendText(
        BrowserInputProtocol.Kind.IME_COMPOSITION, text,
    )

    private fun sendText(kind: BrowserInputProtocol.Kind, text: String): Boolean {
        val authority = authority() ?: return false
        return stream.send(
            BrowserInputProtocol.Packet(
                authority = authority,
                kind = kind,
                channel = BrowserInputProtocol.Channel.RELIABLE,
                reliableSeq = sequencer.nextReliable(),
                text = text,
                sentAtMs = System.currentTimeMillis(),
            ),
        )
    }

    /**
     * The authority every packet carries, or null when there is none to carry.
     *
     * Null rather than a default: a packet with a zero control generation is a packet the
     * host will fence, and building one would turn "VAN is not entitled to act" into
     * "VAN acted and was refused", which reads differently in every log.
     */
    private fun authority(): BrowserInputProtocol.Authority? {
        val snapshot = _state.value.snapshot ?: return null
        return BrowserInputProtocol.Authority(
            sessionId = snapshot.sessionId,
            controlLeaseId = snapshot.controlLeaseId ?: return null,
            controlGeneration = snapshot.controlGeneration,
            viewportRevision = snapshot.viewport.revision,
        )
    }

    private fun sendEdge(
        authority: BrowserInputProtocol.Authority,
        kind: BrowserInputProtocol.Kind,
        gestureId: Int,
        epoch: Int,
        pointerId: Int,
        x: Int,
        y: Int,
    ): Boolean {
        val edge = BrowserInputProtocol.Packet(
            authority = authority,
            kind = kind,
            channel = BrowserInputProtocol.Channel.RELIABLE,
            gestureId = gestureId,
            pointerId = pointerId,
            gestureEpoch = epoch,
            edgeId = sequencer.nextEdge(),
            x = x,
            y = y,
            sentAtMs = System.currentTimeMillis(),
        )
        // `duplicateEdge` stamps each copy's sequence number itself. Doing it again here
        // would burn two numbers per copy and make the server see gaps that are not there.
        var delivered = false
        for (copy in sequencer.duplicateEdge(edge)) {
            delivered = stream.send(copy) || delivered
        }
        return delivered
    }

    /**
     * A failure the owner can read.
     *
     * Not the exception's message: `gateway_http_409: {"detail":"interactive_session_ended"}`
     * tells the owner nothing and tells an attacker something.
     */
    private fun readable(failure: Throwable): String = when {
        failure.message?.contains("grant_expired") == true ->
            "That browser session timed out. Open it again."
        failure.message?.contains("409") == true ->
            "That browser is busy — VAN is using the same profile."
        else -> "Could not reach the browser. VAN will keep trying."
    }

    private companion object {
        /**
         * §5.3. The Gateway's interactive lease is 120 seconds and renews at 80 seconds
         * remaining, so a 30-second beat leaves room for two to be lost on a bad network
         * without the owner's session dying under them.
         */
        const val HEARTBEAT_INTERVAL_MS = 30_000L

        /**
         * §8.4 — one wheel detent, in the units the host scales against its own viewport.
         *
         * Android reports scroll axes in detents, already density-independent. Multiplying
         * by a fixed number here keeps the packet integral without deciding, from this
         * phone, how far a page scrolls on a desktop-sized remote viewport.
         */
        const val SCROLL_UNITS = 120
    }
}
