package com.dial.van.browser

import android.view.MotionEvent
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.visual.VanDurableState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CancellationException
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
        val controlUncertain: Boolean = false,
        val controlMutationPending: Boolean = false,
        val frameConfirmed: Boolean = false,
        val pendingChooser: FileChooserRequest? = null,
        val transferNotice: String? = null,
        val tabState: TabState = TabState(),
    ) {
        /**
         * One sentence for the owner, and never an enum name or an internal state.
         *
         * The link is reported before the session, because "Connected" over a dead media
         * link is the sentence that makes the owner keep tapping.
         */
        val ownerReadableState: String
            get() = when {
                controlMutationPending -> "Confirming the browser control change…"
                lastError != null -> lastError
                snapshot == null -> "Opening the browser…"
                link == BrowserStreamClient.Link.FAILED -> "The picture stopped. Reconnecting."
                link == BrowserStreamClient.Link.RECOVERING -> "Connection wobbled — holding on"
                link != BrowserStreamClient.Link.LIVE -> "Connecting to the browser…"
                snapshot.controlHolder.isAgent -> "VAN is driving — tap Take Control to steer"
                !frameConfirmed -> "Waiting for a verified browser frame…"
                snapshot.viewportUnacknowledged -> "Resizing…"
                else -> snapshot.ownerReadableState
            }
    }

    private val sequencer = BrowserGestureSequencer()
    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    private var heartbeat: Job? = null
    private var streamConnection: Job? = null
    private var frameAcknowledgement: Job? = null
    private var mediaBinding: BrowserStreamMetadata.Binding? = null
    private var pendingExternalUrl: String? = null
    private var renderer: SurfaceViewRenderer? = null
    private val pendingControl = BrowserControlMutation.PendingGate()

    private fun controlMutation(action: String, snapshot: BrowserSessionSnapshot,
        request: suspend () -> BrowserControlMutation.Outcome) {
        val lease = pendingControl.acquire() ?: return
        _state.value = _state.value.copy(controlMutationPending = true, controlUncertain = true, lastError = null)
        val job = scope.launch {
            val outcome = request()
            if (applyControlOutcome(snapshot.sessionId, outcome)) sequencer.reset()
        }
        // Completion also runs when lifecycleScope was already cancelled before launch.
        job.invokeOnCompletion { failure ->
            if (failure is CancellationException) applyControlOutcome(snapshot.sessionId, BrowserControlMutation.cancelled(action))
            pendingControl.release(lease)
            _state.value = _state.value.copy(controlMutationPending = pendingControl.isPending)
        }
    }

    private fun applyControlOutcome(sessionId: String, outcome: BrowserControlMutation.Outcome): Boolean {
        val current = _state.value
        val snapshot = current.snapshot ?: return false
        if (snapshot.sessionId != sessionId) return false
        val fresh = outcome.confirmedSnapshot
        if (fresh != null && !BrowserControlMutation.mayReplaceSnapshot(snapshot, fresh)) {
            _state.value = current.copy(lastError = "The browser changed while the request was being confirmed. Check its current state.",
                controlUncertain = true)
            return false
        }
        val changedBinding = fresh != null && (fresh.controlGeneration != snapshot.controlGeneration || fresh.viewport.revision != snapshot.viewport.revision)
        _state.value = current.copy(snapshot = outcome.snapshotOr(snapshot), lastError = outcome.error,
            controlUncertain = outcome.inputHeld, frameConfirmed = current.frameConfirmed && !changedBinding)
        if (changedBinding && fresh != null && !fresh.state.isTerminal && fresh.state != BrowserSessionState.SUSPENDED) requestStreamConnection()
        publishVisualState()
        return fresh != null
    }

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
        _state.value = _state.value.copy(tabState = tabs)
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
    fun transferContext(): BrowserTransfers.Context? {
        if (!mayActuate()) return null
        val snapshot = _state.value.snapshot ?: return null
        val binding = mediaBinding ?: return null
        val target = tabs.activeTargetId ?: return null
        if (binding.sessionId != snapshot.sessionId || binding.controlGeneration != snapshot.controlGeneration ||
            binding.viewportRevision != snapshot.viewport.revision) return null
        return BrowserTransfers.Context(snapshot.sessionId, target, binding.mediaEpoch)
    }

    fun reportTransfer(message: String, clearChooser: Boolean = false) {
        _state.value = _state.value.copy(transferNotice = message,
            pendingChooser = if (clearChooser) null else _state.value.pendingChooser)
    }

    fun reportUploadRefused(refusal: UploadRefusal) {
        reportTransfer(uploadRefusalText(refusal), clearChooser = true)
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
        UploadRefusal.TRANSPORT_UNAVAILABLE -> BrowserDownloadReview.UPLOAD_UNAVAILABLE
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

    private fun runPendingNavigation() {
        val url = pendingExternalUrl ?: return
        if (navigateTo(url)) pendingExternalUrl = null
    }
    fun historyBack() = if (tabs.active?.canGoBack == true) sendNavigation(BrowserInputProtocol.Kind.HISTORY_BACK) else false

    fun openExternalUrl(url: String) {
        val resolved = BrowserOmnibox.resolve(url)
        if (resolved.intent != OmniboxIntent.NAVIGATE || resolved.value.isBlank()) return
        if (!navigateTo(resolved.value)) pendingExternalUrl = resolved.value
    }

    fun reload() = sendNavigation(BrowserInputProtocol.Kind.RELOAD)

    fun stopLoading() = sendNavigation(BrowserInputProtocol.Kind.STOP_LOADING)

    fun goForward() = if (tabs.active?.canGoForward == true) sendNavigation(BrowserInputProtocol.Kind.HISTORY_FORWARD) else false

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
            BrowserControlMutation.capture {
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
                _state.value.snapshot?.takeIf { it.sessionId == sessionId }?.let { snapshot ->
                    if (revision < snapshot.viewport.revision) return@let
                    val proposed = snapshot.copy(viewport = BrowserViewport(issued.contentWidthPx, issued.contentHeightPx,
                        issued.density, revision))
                    _state.value = _state.value.copy(snapshot = proposed, frameConfirmed = false)
                    requestStreamConnection()
                }
            }.onFailure { failure ->
                _state.value = _state.value.copy(lastError = readable(failure), controlUncertain = true)
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
        val fresh = BrowserControlMutation.capture { gateway.interactiveBrowserRead(sessionId) }.getOrNull()
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
            if (fresh.state == BrowserSessionState.SUSPENDED) reconnect() else {
                startHeartbeat()
                requestStreamConnection()
            }
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
        val snapshot = BrowserControlMutation.capture {
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

        // Owner input is held until current peer metadata and a decoded frame are bound
        // to the broker's exact viewport, then acknowledged and read back.
        if (snapshot.state == BrowserSessionState.SUSPENDED) reconnect() else {
            startHeartbeat()
            requestStreamConnection()
        }
    }

    fun reconnect() {
        val snapshot = _state.value.snapshot ?: return
        if (snapshot.state.isTerminal || _state.value.controlMutationPending) return
        if (snapshot.state == BrowserSessionState.SUSPENDED) {
            controlMutation("resume the browser", snapshot) {
                BrowserControlMutation.resume(snapshot, request = { gateway.interactiveBrowserResume(snapshot.sessionId) },
                    read = { gateway.interactiveBrowserRead(snapshot.sessionId) }).also { outcome ->
                    if (outcome.confirmedSnapshot != null) startHeartbeat()
                }
            }
        } else requestStreamConnection()
    }

    private fun requestStreamConnection() {
        streamConnection?.cancel()
        frameAcknowledgement?.cancel()
        mediaBinding = null
        _state.value = _state.value.copy(frameConfirmed = false, pendingChooser = null, link = BrowserStreamClient.Link.CONNECTING)
        streamConnection = scope.launch { connectStream() }
    }

    private suspend fun connectStream() {
        val sessionId = _state.value.snapshot?.sessionId ?: return
        val fresh = BrowserControlMutation.capture { gateway.interactiveBrowserRead(sessionId) }.getOrElse { failure ->
            _state.value = _state.value.copy(lastError = readable(failure), frameConfirmed = false)
            return
        }
        if (fresh.sessionId != sessionId || fresh.state.isTerminal) return
        val previous = _state.value.snapshot ?: return
        if (!BrowserControlMutation.mayReplaceSnapshot(previous, fresh)) return
        _state.value = _state.value.copy(snapshot = fresh, frameConfirmed = false, lastError = null)
        val grant = BrowserControlMutation.capture { gateway.interactiveBrowserStreamGrant(sessionId) }.getOrElse { failure ->
            _state.value = _state.value.copy(lastError = readable(failure), frameConfirmed = false)
            return
        }
        BrowserControlMutation.capture {
            stream.connect(grant = grant, expected = fresh,
                onVideo = { track: VideoTrack -> renderer?.let(track::addSink) },
                onLink = { link -> scope.launch {
                    _state.value = _state.value.copy(link = link, frameConfirmed = _state.value.frameConfirmed && link == BrowserStreamClient.Link.LIVE)
                    if (link == BrowserStreamClient.Link.LIVE) runPendingNavigation()
                    publishVisualState()
                } },
                onBinding = { binding -> scope.launch { mediaBinding = binding } },
                onMetadata = { event -> scope.launch {
                    if (event.binding != mediaBinding) return@launch
                    val snapshot = _state.value.snapshot ?: return@launch
                    if (snapshot.sessionId != event.binding.sessionId || snapshot.controlGeneration != event.binding.controlGeneration ||
                        snapshot.viewport.revision != event.binding.viewportRevision) return@launch
                    when (event) {
                        is BrowserStreamMetadata.Event.Tabs -> {
                            val known = event.tabs.map { it.targetId }.toSet()
                            tabs.tabs.filter { it.targetId !in known }.forEach { onTabEvent(TabEvent.Closed(it.targetId)) }
                            event.tabs.forEach { tab -> onTabEvent(TabEvent.Updated(tab.targetId, tab.title, tab.url, tab.urlDigest,
                                tab.faviconRef, tab.loading, tab.canGoBack, tab.canGoForward, tab.securityState)) }
                            event.activeTargetId?.let { onTabEvent(TabEvent.Activated(it)) }
                            if (event.activeTargetId == null) {
                                tabs = tabs.copy(activeTargetId = null)
                                _state.value = _state.value.copy(tabState = tabs)
                            }
                        }
                        is BrowserStreamMetadata.Event.Session -> {
                            // A stream observation is not a gateway authority snapshot.
                            if (!event.state.acceptsInput) _state.value = _state.value.copy(frameConfirmed = false)
                        }
                        is BrowserStreamMetadata.Event.Frame -> Unit
                        is BrowserStreamMetadata.Event.Chooser -> {
                            if (tabs.tabs.any { it.targetId == event.targetId }) _state.value = _state.value.copy(
                                pendingChooser = FileChooserRequest(event.binding.sessionId, event.targetId, event.acceptTypes,
                                    false, event.chooserId, event.binding.mediaEpoch, System.currentTimeMillis() + event.expiresInMs),
                                transferNotice = "This page requested a file. Choose a phone file to send only to this page.")
                        }
                        is BrowserStreamMetadata.Event.Download -> _state.value = _state.value.copy(
                            transferNotice = if (event.state == "COMPLETED") "A completed download is ready to review in Downloads & phone files."
                                else "The browser host recorded download progress. Review its current state in Downloads & phone files.")
                        is BrowserStreamMetadata.Event.Refused -> {
                            if (event.input) _state.value = _state.value.copy(frameConfirmed = false, controlUncertain = true,
                                lastError = "The browser host refused an input. Input is held; reconnect to confirm the current browser state.")
                            else reportTransfer("The browser host refused a file action. No completed transfer was confirmed.", clearChooser = true)
                        }
                    }
                } },
                onRenderedFrame = { frame -> scope.launch { confirmRenderedFrame(frame) } },
                onMetadataError = { error -> scope.launch {
                    mediaBinding = null
                    frameAcknowledgement?.cancel()
                    _state.value = _state.value.copy(lastError = error, frameConfirmed = false, controlUncertain = true)
                } },
            )
        }.onFailure { failure ->
            _state.value = _state.value.copy(lastError = readable(failure), frameConfirmed = false)
        }
    }

    private fun confirmRenderedFrame(frame: BrowserStreamMetadata.RenderedFrame) {
        if (frame.binding != mediaBinding || frameAcknowledgement?.isActive == true) return
        val snapshot = _state.value.snapshot ?: return
        if (snapshot.sessionId != frame.binding.sessionId || snapshot.controlGeneration != frame.binding.controlGeneration ||
            snapshot.viewport.revision != frame.binding.viewportRevision) return
        frameAcknowledgement = scope.launch {
            val outcome = BrowserControlMutation.acknowledgeRenderedViewport(snapshot, frame,
                request = { gateway.interactiveBrowserAckViewport(snapshot.sessionId, snapshot.viewport.revision,
                    frameSequence = frame.frameSequence, mediaEpoch = frame.binding.mediaEpoch) },
                read = { gateway.interactiveBrowserRead(snapshot.sessionId) })
            if (frame.binding != mediaBinding) return@launch
            if (applyControlOutcome(snapshot.sessionId, outcome) && outcome.error == null) {
                _state.value = _state.value.copy(frameConfirmed = true)
                runPendingNavigation()
                swap?.onAcked(frame.binding.viewportRevision)
                onFrameForRevision(frame.binding.viewportRevision)
            }
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
                BrowserControlMutation.capture { gateway.interactiveBrowserHeartbeat(sessionId) }
                    .onSuccess { fresh -> applyControlOutcome(sessionId, BrowserControlMutation.Outcome(confirmedSnapshot = fresh)) }
                    .onFailure { failure ->
                        _state.value = _state.value.copy(lastError = readable(failure))
                    }
            }
        }
    }

    /** ADR-RB-007 — taking control becomes a fact only after the matching receipt and readback. */
    fun takeControl() {
        val snapshot = _state.value.snapshot ?: return
        if (!BrowserControlMutation.mayRequestControl(snapshot, _state.value.controlUncertain, _state.value.controlMutationPending)) return
        val sessionId = snapshot.sessionId
        controlMutation("take control", snapshot) {
            BrowserControlMutation.takeControl(snapshot,
                request = { gateway.interactiveBrowserTakeControl(sessionId) },
                read = { gateway.interactiveBrowserRead(sessionId) })
        }
    }

    /** The owner delegates only the existing linked mission; this does not launch new work. */
    fun delegateControl(holder: BrowserControlHolder) {
        val current = _state.value
        val snapshot = current.snapshot ?: return
        if (!holder.isAgent || !BrowserControlMutation.mayDelegate(snapshot, current.controlUncertain, current.controlMutationPending)) return
        val sessionId = snapshot.sessionId
        val issuedFor = snapshot.controlDelegateIssuedFor ?: return
        controlMutation("hand browser control to VAN", snapshot) {
            BrowserControlMutation.delegate(snapshot, holder,
                request = { gateway.interactiveBrowserDelegateControl(sessionId, holder.name, issuedFor) },
                read = { gateway.interactiveBrowserRead(sessionId) })
        }
    }

    fun suspendSession() {
        val snapshot = _state.value.snapshot ?: return
        if (snapshot.state.isTerminal || snapshot.state == BrowserSessionState.SUSPENDED) return
        val sessionId = snapshot.sessionId
        heartbeat?.cancel()
        _state.value = _state.value.copy(frameConfirmed = false)
        controlMutation("pause the browser", snapshot) {
            BrowserControlMutation.suspendSession(snapshot) {
                gateway.interactiveBrowserSuspend(sessionId)
            }
        }
    }

    fun close() {
        heartbeat?.cancel()
        streamConnection?.cancel()
        frameAcknowledgement?.cancel()
        mediaBinding = null
        val snapshot = _state.value.snapshot
        stream.close()
        renderer = null
        _state.value = _state.value.copy(link = BrowserStreamClient.Link.CLOSED,
            lastError = if (snapshot != null && !snapshot.state.isTerminal) "The remote browser has not been confirmed closed." else null,
            controlUncertain = snapshot != null && !snapshot.state.isTerminal)
        if (snapshot != null && !snapshot.state.isTerminal) {
            controlMutation("close the remote browser", snapshot) {
                BrowserControlMutation.close(snapshot) {
                    gateway.interactiveBrowserEnd(snapshot.sessionId)
                }
            }
        }
    }

    /** The one gate. See the class note for what each clause prevents. */
    fun mayActuate(): Boolean {
        val current = _state.value
        val snapshot = current.snapshot ?: return false
        return BrowserControlMutation.mayActuate(snapshot,
            mediaLive = current.link == BrowserStreamClient.Link.LIVE,
            controlUnconfirmed = current.controlUncertain || current.controlMutationPending || !current.frameConfirmed)
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
        val viewport = _state.value.snapshot?.viewport ?: return false
        val down = event.actionMasked == MotionEvent.ACTION_DOWN || event.actionMasked == MotionEvent.ACTION_POINTER_DOWN
        val position = BrowserSurfaceCoordinates.map(event.getX(event.actionIndex), event.getY(event.actionIndex),
            viewWidth, viewHeight, viewport.width, viewport.height, clamp = !down) ?: return false
        val (x, y) = position

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
                    val move = BrowserSurfaceCoordinates.map(event.getX(index), event.getY(index), viewWidth, viewHeight,
                        viewport.width, viewport.height, clamp = true) ?: continue
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
                            x = move.first,
                            y = move.second,
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
        val viewport = _state.value.snapshot?.viewport ?: return false
        val position = BrowserSurfaceCoordinates.map(event.x, event.y, viewWidth, viewHeight,
            viewport.width, viewport.height) ?: return false
        return stream.send(
            BrowserInputProtocol.Packet(
                authority = authority,
                kind = BrowserInputProtocol.Kind.SCROLL,
                channel = BrowserInputProtocol.Channel.RELIABLE,
                reliableSeq = sequencer.nextReliable(),
                x = position.first,
                y = position.second,
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
    fun onKey(keyCode: Int, unicodeChar: Int, down: Boolean, metaState: Int = 0): Boolean {
        val authority = authority() ?: return false
        val key = BrowserKeyMapping.key(keyCode, unicodeChar, metaState, down) ?: return false
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
                valueA = key.virtualKey,
                valueB = key.modifiers,
                text = key.text,
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
