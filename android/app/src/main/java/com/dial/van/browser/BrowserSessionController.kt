package com.dial.van.browser

import android.view.MotionEvent
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.visual.VanDurableState
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
    /**
     * Rev 1.5 §24 — where an arbitrated visual state goes.
     *
     * A function rather than a reference to `VanLiveVisualState`, because that object
     * needs Android and this class is easier to reason about without it. The default does
     * nothing, so a caller that has no embodiment — a test, a headless path — is not
     * forced to invent one.
     */
    private val visual: (VanDurableState) -> Unit = {},
    /**
     * What the embodiment is showing right now.
     *
     * Read at the moment of arbitration rather than cached, because the thing this has to
     * not displace — a trading warning — can arrive between two browser events.
     */
    private val visualNow: () -> VanDurableState = { VanDurableState.IDLE },
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

    /** §17.1 — the projection of Chromium's targets. Never a tab this side invented. */
    private var tabs = TabState()

    /** §12.3 — what reaches the server while the owner drags a window edge. */
    private var coalescer = ResizeCoalescer()

    /** §12.4 — what is drawn between a revision being sent and its first frame. */
    private var swap: ViewportSwap? = null

    fun tabState(): TabState = tabs

    /**
     * §17.1 — one event from the Browser Runtime.
     *
     * The projection is replaced wholesale from the reducer rather than mutated in place,
     * so there is no path where half an event has been applied.
     */
    fun onTabEvent(event: TabEvent) {
        tabs = BrowserTabs.reduce(tabs, event)
        publishVisualState()
    }

    /** §17.6 — what the system Back gesture does here. */
    fun onBackPressed(transientPanelOpen: Boolean, addressBarEditing: Boolean): BackOutcome {
        val outcome = BrowserBackPolicy.decide(
            transientPanelOpen = transientPanelOpen,
            addressBarEditing = addressBarEditing,
            canGoBack = tabs.active?.canGoBack == true,
        )
        if (outcome == BackOutcome.BROWSER_BACK) {
            sendNavigation(BrowserInputProtocol.Kind.HISTORY_BACK)
        }
        return outcome
    }

    /**
     * §17.2 — the owner typed something and committed it.
     *
     * The classification happens on the phone and the *result* travels, so the host is
     * told "navigate here" or "search for this" rather than being handed raw text to
     * guess about. A host that guessed would guess differently from the address bar the
     * owner is looking at.
     */
    fun onOmniboxCommitted(typed: String): OmniboxResolution? {
        val resolved = BrowserOmnibox.resolve(typed)
        if (resolved.value.isBlank()) return null
        val kind = when (resolved.intent) {
            OmniboxIntent.NAVIGATE -> BrowserInputProtocol.Kind.NAVIGATE
            OmniboxIntent.SEARCH -> BrowserInputProtocol.Kind.SEARCH
        }
        return if (sendNavigation(kind, resolved.value)) resolved else null
    }

    /**
     * §19 — the owner picked a file and it passed the admission checks.
     *
     * The ticket carries a name, a size and a type. There is no argument for the bytes,
     * because §19's prohibition — the content is not logged or sent to Hermes — is easier
     * to keep when there is nowhere here to put it.
     */
    fun beginUpload(request: FileChooserRequest, displayName: String, byteSize: Long) {
        val sessionId = _state.value.snapshot?.sessionId ?: return
        uploads += UploadTicket(
            uploadId = "up_${'$'}{System.nanoTime()}",
            sessionId = sessionId,
            targetId = request.targetId,
            displayName = displayName,
            byteSize = byteSize,
            declaredMime = "application/octet-stream",
            createdAtMs = System.currentTimeMillis(),
            state = UploadState.TRANSFERRING,
        )
    }

    fun reportUploadRefused(refusal: UploadRefusal) {
        _state.value = _state.value.copy(lastError = uploadRefusalText(refusal))
    }

    /** §19 step 8 — drop the tickets whose ephemeral copies have expired. */
    fun reapExpiredUploads(nowMs: Long) {
        uploads = uploads.filterNot { BrowserUploadPolicy.expired(it, nowMs) }
    }

    fun uploadTickets(): List<UploadTicket> = uploads

    private var uploads: List<UploadTicket> = emptyList()

    private fun uploadRefusalText(refusal: UploadRefusal): String = when (refusal) {
        UploadRefusal.TYPE_NOT_ACCEPTED -> "That page will not take that kind of file."
        UploadRefusal.TOO_LARGE -> "That file is too large for VAN to send."
        UploadRefusal.NAME_UNSAFE -> "VAN could not read that file's name."
        UploadRefusal.SESSION_STALE -> "That browser session has moved on. Try again."
        UploadRefusal.OWNER_CANCELLED -> "Upload cancelled."
    }

    /**
     * §17.5 — go to an address that came from outside VAN.
     *
     * Through the same [sendNavigation] as the address bar, so an external link cannot
     * reach the page by a route a tap cannot: the control lease and the viewport revision
     * fence it exactly as they fence a touch.
     */
    fun navigateTo(url: String): Boolean =
        sendNavigation(BrowserInputProtocol.Kind.NAVIGATE, url)

    fun reload() = sendNavigation(BrowserInputProtocol.Kind.RELOAD)

    fun stopLoading() = sendNavigation(BrowserInputProtocol.Kind.STOP_LOADING)

    fun goForward() = sendNavigation(BrowserInputProtocol.Kind.HISTORY_FORWARD)

    /**
     * §17.2 — navigation on the reliable channel, under the same authority as a tap.
     *
     * Through [mayActuate] rather than around it: navigating is an actuation, and an
     * address bar that worked while an agent held the control lease would be the owner
     * steering a browser VAN believes it is driving.
     */
    private fun sendNavigation(
        kind: BrowserInputProtocol.Kind,
        text: String = "",
    ): Boolean {
        if (!mayActuate()) return false
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
     * §12.3 — the window changed shape.
     *
     * The local stage happens in the view: the decoded frame is scaled to the new
     * rectangle immediately. This is only the remote half, and most callbacks produce
     * nothing at all, which is the design rather than a failure.
     */
    fun onWindowChanged(candidate: ViewportCandidate, nowMs: Long) {
        val due = coalescer.onWindowChanged(candidate, nowMs) ?: return
        sendViewport(due)
    }

    /** The drag ended, or the timer fired. */
    fun onWindowTick(nowMs: Long, settled: Boolean = false) {
        val due = if (settled) coalescer.onSettled(nowMs) else coalescer.onTick(nowMs)
        if (due != null) sendViewport(due)
    }

    /** §12.4 — a frame arrived carrying the revision it was rendered at. */
    fun onFrameForRevision(revision: Int) {
        swap?.onFrame(revision)
    }

    private fun sendViewport(candidate: ViewportCandidate) {
        val sessionId = _state.value.snapshot?.sessionId ?: return
        scope.launch {
            runCatching {
                gateway.interactiveBrowserProposeViewport(
                    sessionId = sessionId,
                    widthPx = candidate.contentWidthPx,
                    heightPx = candidate.contentHeightPx,
                    deviceScaleFactor = candidate.density,
                )
            }.onSuccess { revision ->
                // The revision the Gateway issued, not the one the candidate guessed:
                // the server owns the sequence, and a phone that numbered its own would
                // eventually disagree with it.
                val issued = candidate.copy(revision = revision)
                val current = swap ?: ViewportSwap(issued).also { swap = it }
                if (issued.revision > current.live.revision) current.onSent(issued)
                // §8.6 — acknowledge the size we are drawing, which is what re-opens the
                // input gate. The frame carrying that revision completes the swap.
                runCatching {
                    gateway.interactiveBrowserAckViewport(sessionId, revision)
                }.onSuccess {
                    current.onAcked(revision)
                    _state.value.snapshot?.let { snapshot ->
                        _state.value = _state.value.copy(
                            snapshot = snapshot.copy(ackedViewportRevision = revision),
                        )
                    }
                }
            }.onFailure { failure ->
                _state.value = _state.value.copy(lastError = readable(failure))
            }
        }
    }

    /** §12.4 — how the held frame is drawn while a revision is in flight. */
    fun letterbox(frameWidthPx: Int, frameHeightPx: Int): Letterbox? =
        swap?.letterbox(frameWidthPx, frameHeightPx)

    /**
     * §24 — what the browser says about how VAN looks, if the arbitration lets it.
     *
     * Called from every place the state moves rather than from a timer, so the embodiment
     * follows the browser rather than sampling it.
     */
    private fun publishVisualState() {
        val snapshot = _state.value.snapshot
        val proposal = BrowserVisualState.arbitrate(
            current = visualNow(),
            snapshot = BrowserVisualSnapshot(
                connecting = _state.value.link == BrowserStreamClient.Link.CONNECTING,
                connected = _state.value.link == BrowserStreamClient.Link.LIVE,
                degraded = _state.value.link == BrowserStreamClient.Link.RECOVERING,
                ownerBrowsing = snapshot?.controlHolder?.isAgent == false,
                agentDriving = snapshot?.controlHolder?.isAgent == true,
                navigating = tabs.active?.loading == true,
                ownerRequired = snapshot?.ownerReadableState?.contains("need", ignoreCase = true) == true,
                idle = snapshot == null,
            ),
        ) ?: return
        visual(proposal)
    }

    fun attachRenderer(target: SurfaceViewRenderer) {
        renderer = target
    }

    /**
     * §29.10 — what VAN writes down before the process can be killed.
     *
     * Called on every state change that matters rather than only on stop: a process death
     * does not announce itself, and a snapshot taken in `onStop` is missing everything
     * that happened after the owner last backgrounded the app.
     */
    fun persistable(nowMs: Long): PersistedBrowserSession? {
        val snapshot = _state.value.snapshot ?: return null
        return PersistedBrowserSession(
            sessionId = snapshot.sessionId,
            profileAlias = snapshot.profileAlias,
            lastViewportRevision = snapshot.viewport.revision,
            lastEventCursor = lastEventCursor,
            lastSpokenSegment = lastSpokenSegment,
            persistedAtMs = nowMs,
            lastObservedState = snapshot.ownerReadableState,
            lastObservedControlGeneration = snapshot.controlGeneration,
        )
    }

    private var lastEventCursor: Long = 0
    private var lastSpokenSegment: Int = 0

    /**
     * §29.10 — come back after a process death.
     *
     * The restored record is a *claim*: it supplies the session id to ask about and
     * nothing the owner is shown. Whether it is true is the Gateway's answer, which is why
     * the read below is `interactiveBrowserRead` and not a copy of the cached state.
     */
    suspend fun resumeAfterProcessDeath(
        persisted: PersistedBrowserSession?,
        nowMs: Long,
    ): RestoredBrowserSession {
        val restored = BrowserProcessRecovery.restore(persisted, nowMs)
        val sessionId = restored.sessionId ?: return restored
        val fresh = runCatching { gateway.interactiveBrowserRead(sessionId) }.getOrNull()
        val reconciled = BrowserProcessRecovery.reconcile(
            restored = restored,
            gatewaySaysResumable = fresh != null && !fresh.state.isTerminal,
            gatewayState = fresh?.ownerReadableState,
        )
        if (BrowserProcessRecovery.mayReconnectMedia(reconciled) && fresh != null) {
            lastEventCursor = restored.resumeEventCursor
            lastSpokenSegment = restored.resumeSpeechSegment
            _state.value = State(snapshot = fresh)
            publishVisualState()
            // §29.8 — the media plane reconnects separately, and only now: negotiating
            // against a grant for a session the Gateway has ended fails in a way that
            // looks like a network problem and is not.
            connectStream()
        }
        return reconciled
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
        publishVisualState()

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
                onLink = { link ->
                    _state.value = _state.value.copy(link = link)
                    // §24 — CONNECTING and DEGRADED are the two the owner most needs to
                    // see, and they only ever come from here.
                    publishVisualState()
                },
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
                // Rev 1.5 §28.1 — the decoder's dropped-frame total, asked for on the
                // beat that is already running rather than on a timer of its own. It is
                // a JNI round trip into the native stack; doing it per frame to measure
                // dropped frames would be the thing dropping them.
                stream.pollDecoderStats()
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
                    publishVisualState()
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
