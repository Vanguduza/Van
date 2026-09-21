package com.dial.van

import android.app.Application
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import com.dial.van.control.VanCommandController
import com.dial.van.control.VanCommandSource
import com.dial.van.degraded.DegradedModeStore
import com.dial.van.events.PreferencesEventCursorStore
import com.dial.van.events.VanEventStreamStore
import com.dial.van.degraded.DeviceSignals
import com.dial.van.gateway.ReplayReason
import com.dial.van.gateway.QueueReplayer
import com.dial.van.connectivity.ConnectivityRegistry
import com.dial.van.connectivity.ProvisioningIntake
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.session.EncryptedSessionOutboxStore
import com.dial.van.session.VanHermesSessionManager
import com.dial.van.voice.VoiceEdge
import com.dial.van.notification.NotificationPolicyStore
import com.dial.van.queue.EncryptedCommandQueue
import com.dial.van.runtime.DeviceRuntimeReadings
import com.dial.van.runtime.RuntimeReading
import com.dial.van.browser.BrowserShortcutStore
import com.dial.van.browser.PersistedBrowserSession
import com.dial.van.telemetry.DeviceTelemetryReporter
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.voice.PersonalSpeechModel
import com.dial.van.voice.SherpaLocalSecondPassAsr
import com.dial.van.voice.SherpaSpeakerSimilarityScorer
import com.dial.van.voice.SpeechContext
import com.dial.van.voice.SpeechSyncFrame
import com.dial.van.voice.TtsOutputCallback
import com.dial.van.voice.TtsOutputManager
import com.dial.van.voice.VanVoiceUiStore
import com.dial.van.voice.VoiceInputCallback
import com.dial.van.voice.VoiceInputManager
import com.dial.van.voice.VoiceRecognitionResult
import com.dial.van.voice.VoiceSessionCoordinator
import com.dial.van.voice.VoiceAudioArbiter
import com.dial.van.voice.WakeAcknowledgementManager
import com.dial.van.voice.WakeCoordinator
import com.dial.van.voice.WakeModelLoader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject

class VanApplication : Application(), VoiceInputCallback, TtsOutputCallback {

    /**
     * Internal rather than private: `ProvisioningActivity` finishes immediately and needs
     * a scope that outlives it, because a provisioning run cancelled halfway would leave
     * this device paired and unbound — §0D.3's failure state exactly.
     */
    internal val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    lateinit var commandQueue: EncryptedCommandQueue
        private set
    lateinit var notificationPolicyStore: NotificationPolicyStore
        private set
    lateinit var degradedModeStore: DegradedModeStore
        private set
    lateinit var personalSpeechModel: PersonalSpeechModel
        private set
    lateinit var wakeAcknowledgement: WakeAcknowledgementManager
        private set
    lateinit var voiceInput: VoiceInputManager
        private set
    lateinit var ttsOutput: TtsOutputManager
        private set
    lateinit var voiceSession: VoiceSessionCoordinator
        private set
    lateinit var voiceUi: VanVoiceUiStore
        private set

    /**
     * P1-VOICE-001 — the wake path is constructed on boot, whether or not it can run.
     *
     * `WakePipeline` was never constructed anywhere in the app, so "Hey Van" did nothing and
     * nothing said so: `WakeCoordinator.KWS_NOT_READY` existed and was unreachable because
     * no coordinator existed either. It exists now, it fails closed without a model, and the
     * reason reaches the owner's degraded-subsystem list instead of being silence.
     */
    lateinit var wakeModel: WakeModelLoader
        private set
    lateinit var voiceArbiter: VoiceAudioArbiter
        private set
    lateinit var wakeCoordinator: WakeCoordinator
        private set
    lateinit var gatewayClient: VanGatewayClient
        private set
    lateinit var commandController: VanCommandController
        private set
    lateinit var queueReplayer: QueueReplayer
        private set

    /**
     * P3-OBS-002 — the producer for the six device-sourced metrics. The gateway declared
     * them and the ingest route has existed since Gate 11; nothing on the phone posted to
     * it, so the scrape reported them as unobserved forever.
     */
    lateinit var telemetry: DeviceTelemetryReporter

    /**
     * ADR-RB-023 — the registry a home-screen shortcut resolves through.
     *
     * Held on the application rather than on the browser Activity, because the Activity
     * that resolves a shortcut is a different one from the Activity that creates it, and
     * a registry owned by either would be gone when the other needed it.
     */
    val browserShortcuts = BrowserShortcutStore()

    /**
     * §5.8 — whether this phone is the owner's bound device.
     *
     * A shortcut on a home screen is on a home screen someone else may be holding, so
     * this is asked every time one resolves rather than cached at startup.
     */
    fun deviceIsBound(): Boolean = gatewayClient.isPaired()

    /** Which browser profiles a shortcut may open into. */
    fun availableBrowserProfiles(): Set<String> = setOf("public_research", "authenticated_owner")

    /**
     * Rev 1.5 §29.10 step 1 — the browser session record that has to survive a process
     * death.
     *
     * In encrypted preferences, because it names the profile the owner was logged into.
     * Held on the application rather than in the Activity's saved instance state: a
     * process death does not save instance state, which is the case this exists for.
     */
    fun persistBrowserSession(record: PersistedBrowserSession) {
        browserSessionStore.edit()
            .putString(KEY_BROWSER_SESSION_ID, record.sessionId)
            .putString(KEY_BROWSER_PROFILE, record.profileAlias)
            .putInt(KEY_BROWSER_VIEWPORT, record.lastViewportRevision)
            .putLong(KEY_BROWSER_EVENT_CURSOR, record.lastEventCursor)
            .putInt(KEY_BROWSER_SPOKEN, record.lastSpokenSegment)
            .putLong(KEY_BROWSER_PERSISTED_AT, record.persistedAtMs)
            .putString(KEY_BROWSER_OBSERVED, record.lastObservedState)
            .putInt(KEY_BROWSER_GENERATION, record.lastObservedControlGeneration)
            .apply()
    }

    fun restorePersistedBrowserSession(): PersistedBrowserSession? {
        val sessionId = browserSessionStore.getString(KEY_BROWSER_SESSION_ID, null)
            ?: return null
        return PersistedBrowserSession(
            sessionId = sessionId,
            profileAlias = browserSessionStore.getString(KEY_BROWSER_PROFILE, "").orEmpty(),
            lastViewportRevision = browserSessionStore.getInt(KEY_BROWSER_VIEWPORT, 0),
            lastEventCursor = browserSessionStore.getLong(KEY_BROWSER_EVENT_CURSOR, 0),
            lastSpokenSegment = browserSessionStore.getInt(KEY_BROWSER_SPOKEN, 0),
            persistedAtMs = browserSessionStore.getLong(KEY_BROWSER_PERSISTED_AT, 0),
            lastObservedState = browserSessionStore.getString(KEY_BROWSER_OBSERVED, "").orEmpty(),
            lastObservedControlGeneration = browserSessionStore.getInt(KEY_BROWSER_GENERATION, 0),
        )
    }

    fun clearPersistedBrowserSession() {
        browserSessionStore.edit().clear().apply()
    }

    private val browserSessionStore by lazy {
        getSharedPreferences("van_browser_session", MODE_PRIVATE)
    }

    /**
     * ADR-RB-027 — where VAN connects, from a signed manifest rather than a text field.
     *
     * Held on the application because it is read before anything else can talk to the
     * gateway, and because an endpoint the owner can be talked into typing is a phishing
     * surface with their whole assistant behind it (§0D.2).
     */
    lateinit var connectivity: ConnectivityRegistry

    /** ADR-RB-026 — the installer's payload intake. Read by the onboarding status. */
    lateinit var provisioning: ProvisioningIntake

    /**
     * Rev 1.5 §20 — the durable logical session the owner's conversation binds to.
     *
     * Application-scoped because §20.3's whole claim is that the session outlives any one
     * screen or socket. An instance owned by an Activity would be a session that ends when
     * the owner rotates the phone.
     */
    lateinit var vanSession: VanHermesSessionManager

    /**
     * Rev 1.5 §§5.6, 20.1 — the owner's event history, for the whole app.
     *
     * Application-scoped for the same reason the session is: it has to outlive the screen
     * that happens to be open. It lived in the Work screen's `remember` until C18, so a
     * mission finishing while the owner was elsewhere produced nothing they could see —
     * and §20.1's "SHALL feed durable downstream pages into `EventStream.applyPage`" had
     * nowhere to feed, because an application-scoped socket cannot write into a
     * composable's local state.
     */
    lateinit var eventStream: VanEventStreamStore

    /**
     * Rev 1.5 §21 — the local voice edge: what VAN can hear and say with no network.
     *
     * Application-scoped because the answer to "can I hear you" must be the same on every
     * screen, and because the asset classification is read once at start rather than each
     * time something asks.
     */
    lateinit var voiceEdge: VoiceEdge
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        commandQueue = EncryptedCommandQueue(this)
        notificationPolicyStore = NotificationPolicyStore(this)
        degradedModeStore = DegradedModeStore()
        personalSpeechModel = PersonalSpeechModel(this)
        wakeAcknowledgement = WakeAcknowledgementManager(this)
        voiceUi = VanVoiceUiStore()
        gatewayClient = VanGatewayClient(this)
        eventStream = VanEventStreamStore(PreferencesEventCursorStore(this))
        // P1-VOICE-001 — TtsOutputManager.speak finally has a caller. Bound to the
        // outcome projection, so VAN speaks when work finished or needs the owner and
        // stays quiet otherwise.
        ttsOutput = TtsOutputManager(this, this)
        // P1-VOICE-001 — TtsOutputManager.speak finally has a caller. Bound to the outcome
        // projection, so VAN speaks when work finished or needs the owner and stays quiet
        // otherwise.
        commandController = VanCommandController(
            gatewayClient, appScope, speak = { text -> ttsOutput.speak(text) },
        )
        val secondPassCoordinator = SherpaLocalSecondPassAsr.fromFiles(this)
            ?.let(::VoiceSecondPassCoordinator)
        val speakerSimilarityScorer = SherpaSpeakerSimilarityScorer.fromFiles(this)
        voiceInput = VoiceInputManager(
            context = this,
            callback = this,
            biasingStringsProvider = { personalSpeechModel.biasingStrings(activeSpeechContexts()) },
            secondPassCoordinator = secondPassCoordinator,
            personalConfusionProvider = { transcript ->
                personalSpeechModel.correctionFor(transcript, activeSpeechContexts()) != null
            },
            speakerSimilarityScorer = speakerSimilarityScorer,
        )
        voiceSession = VoiceSessionCoordinator(voiceInput, ttsOutput)
        queueReplayer = QueueReplayer(commandQueue, gatewayClient, degradedModeStore, appScope)
        telemetry = DeviceTelemetryReporter(this, gatewayClient, appScope)
        connectivity = ConnectivityRegistry(this)
        // ADR-RB-026 — the installer's way in, and the only one. Built before the
        // session so the onboarding screen can say whether this build can ever be
        // provisioned rather than telling the owner to wait for something that will
        // never arrive.
        provisioning = ProvisioningIntake(this)
        vanSession = VanHermesSessionManager(
            gatewayClient, appScope, telemetry = telemetry.session,
            // §§2.7, 20.14 — the session outbox is stored in the queue that already
            // exists, not beside it. Without this the queue survives the process and the
            // policy governing whether a command may be silently replayed does not.
            store = EncryptedSessionOutboxStore(commandQueue),
            // §20.15 — a command the outbox gives up on reaches the owner's conversation,
            // which is the surface they are already looking at. Without a reader here the
            // work is dropped in silence, which is the half of the failure that is worse.
            onUndelivered = { commandController.reportUndelivered(it) },
            // §20.1's SHALL. Durable downstream pages go into the reducer the REST floor
            // already uses, so the owner has one history rather than two that disagree.
            onDownstreamPage = { eventStream.apply(it) },
        )
        voiceEdge = VoiceEdge(this, ttsOutput, appScope)
        voiceEdge.loadAssets()
        wakeModel = WakeModelLoader(this)
        voiceArbiter = VoiceAudioArbiter(this)
        wakeCoordinator = WakeCoordinator(
            arbiter = voiceArbiter,
            pipeline = wakeModel.pipelineOrNull(),
            acknowledgementReady = { wakeAcknowledgement.isReady() },
            playAcknowledgement = { wakeAcknowledgement.play() },
            beginRecognition = { turnId -> voiceSession.beginOwnerTurn(turnId) },
        )
        publishWakeModelState()
        // P3-AND-004 — the five subsystems that reported WORKING because nothing wrote
        // them now have a writer, and it runs before the owner can open a health screen.
        DeviceSignals.publish(this)
        queueReplayer.replayAsync(ReplayReason.APP_START)
        telemetry.start()
        startVanSession()
        // §20.9 — the standby policy has to be told what the phone can afford before it
        // decides anything. Without this first call it runs on its constructor defaults
        // (a full battery on an unmetered link), which is the one combination that says
        // "hold a spare socket open" for a device nobody has measured.
        refreshStandbyConditions()
        startInteractionWatch()
        startConnectivityMonitor()
        startGatewayHealthMonitor()
        startSignedConnectivityRefresh()
    }

    /**
     * Rev 1.5 §20 — open the durable session, and give a failed command somewhere to go.
     *
     * This call did not exist. `VanHermesSessionManager` was constructed here and fed two
     * inputs, and `start()` had no caller anywhere in the app — so no socket opened, no
     * resume ran, the outbox was never restored, and `submit` was never reached. Two
     * checkpoints hardened an outbox that nothing put anything in (P0-SESS-009).
     *
     * Not enrolled means not started, rather than started and failing: opening a session
     * needs a device token, and a provisioning build that has not been given one should
     * wait quietly rather than retry a call that cannot succeed. `startGatewayHealthMonitor`
     * already re-checks enrolment, and a later `start()` is a resume rather than a new
     * session, which is §20.3's whole point.
     */
    private fun startVanSession() {
        commandController.storeForLater = ::storeCommandForLater
        // `Dispatchers.IO`, not the scope's default. `start()` restores the outbox, which
        // reads and decrypts every stored record, and `Dispatchers.Default` is sized to
        // the CPU count: a blocking read there stalls work that has nothing to do with
        // this. Not a UI-thread bug — `appScope` has never been the main thread — but the
        // wrong pool for a call that waits on a disk.
        appScope.launch(Dispatchers.IO) {
            if (!gatewayClient.isEnrolled()) return@launch
            runCatching { vanSession.start() }
        }
    }

    /**
     * §20.14 — hold a command that could not be sent, and say whether it was held.
     *
     * Returns false rather than throwing when the session refuses it, because the caller
     * has to tell the owner the truth either way and "saved" is the one sentence that
     * must not be said on a guess. `submit` refuses an A4 or A5 on its own — the
     * classification is `DurableOutbox.admit`'s — so this cannot be the place that
     * smuggles one in.
     */
    private fun storeCommandForLater(
        body: JSONObject,
        requiresLiveOwnerContext: Boolean,
    ): Boolean {
        val outcome = runCatching {
            vanSession.submit(
                kind = "command.submit",
                // The signed body the Gateway would have received, unchanged. Anything
                // less is refused as `command_payload_invalid` when the outbox flushes,
                // hours after the owner was told it was saved.
                payload = body,
                actionClass = body.optString("action_class", "A1"),
                requiresLiveOwnerContext = requiresLiveOwnerContext,
            )
        }.getOrNull() ?: return false
        return outcome is VanHermesSessionManager.SubmissionOutcome.Queued ||
            outcome is VanHermesSessionManager.SubmissionOutcome.QueuedNeedsReconfirm
    }

    /**
     * ADR-RB-027 — ask for a newer signed manifest, and apply it only if it verifies.
     *
     * Failure here is deliberately quiet in the log and loud in the registry: the device
     * keeps the endpoints it already had, which is the safe direction. The dangerous
     * design is the other one, where a refused manifest leaves the device with nothing.
     */
    private fun startSignedConnectivityRefresh() {
        if (!connectivity.configured) return
        appScope.launch {
            runCatching {
                connectivity.refresh { knownVersion ->
                    gatewayClient.connectivityManifest(knownVersion)
                }
            }
        }
    }

    /**
     * Drain the queue when the network comes back (P3-AND-006).
     *
     * A registered callback rather than a poll: the queue should empty when connectivity
     * returns, not up to a minute later, and the edge detection that stops a Wi-Fi to
     * mobile handover producing four concurrent replays lives in `ReplayTrigger`.
     */
    private fun startConnectivityMonitor() {
        val manager = getSystemService(ConnectivityManager::class.java) ?: return
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .addCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
            .build()
        val registered = runCatching {
            manager.registerNetworkCallback(
                request,
                object : ConnectivityManager.NetworkCallback() {
                    override fun onAvailable(network: Network) {
                        queueReplayer.onNetworkChanged(true)
                        // A Wi-Fi to mobile handover changes what a warm standby costs,
                        // and §20.9's answer is different on either side of it.
                        refreshStandbyConditions()
                    }

                    override fun onLost(network: Network) {
                        // Recorded, not acted on: the recovery is the edge back up, and a
                        // replay attempt with no network is a guaranteed failure that would
                        // count against the queue's health.
                        queueReplayer.onNetworkChanged(false)
                        refreshStandbyConditions()
                    }
                },
            )
        }
        // P1-AND-014 — the failure is reported rather than swallowed.
        //
        // This was a bare `runCatching { }`, so a missing ACCESS_NETWORK_STATE turned into
        // silence: the registration threw, nothing observed connectivity, and the queue
        // simply never drained when the network came back. A feature that quietly does not
        // exist is worse than one that fails loudly, and the whole point of the degraded
        // registry is that VAN says which parts of itself are not working.
        if (registered.isFailure) {
            degradedModeStore.markBroken(
                "queue",
                "VAN cannot watch for the network returning, so queued commands wait for " +
                    "you to send them rather than going out on their own",
                com.dial.van.degraded.RestoreAction.RETRY_CONNECTION,
            )
        }
    }

    /** The owner pressing "Try again" on a degraded subsystem (P3-AND-005). */
    fun requestReplay() = queueReplayer.replayAsync(ReplayReason.OWNER_REQUESTED)

    /** Re-read what the device actually reports. Called when a screen resumes. */
    fun refreshSubsystemHealth() {
        DeviceSignals.publish(this)
        // The battery moves while a screen is open, and §20.9's threshold is a battery
        // threshold. Re-read here rather than on a timer of its own: the readings are
        // binder calls, and a second poller would show up in the first one's numbers.
        refreshStandbyConditions()
    }

    /**
     * Rev 1.5 §§20.8, 20.9 — whether the owner is waiting on VAN right now.
     *
     * "Active interaction" is deliberately not "the app is in the foreground". A phone
     * face-down on a desk with a command in flight is exactly the case a failover has to
     * be invisible for, and a phone in the owner's hand with nothing outstanding is not
     * worth a second socket's battery. So the signal is the conversation's own: something
     * submitted and unanswered, or an A4 the owner is being asked to approve.
     *
     * This drives two things at once — the heartbeat cadence and whether a warm standby
     * is held open — which is why it is one signal rather than two.
     */
    private fun startInteractionWatch() {
        appScope.launch {
            commandController.state.collect { conversation ->
                vanSession.setInteractionActive(
                    conversation.submitting || conversation.pendingA4Approval != null,
                )
            }
        }
    }

    /**
     * Rev 1.5 §20.9 — tell the session what the phone can afford.
     *
     * One reader, one caller per event that can change the answer. The session manager
     * deliberately samples nothing itself: a second sampler would be a second answer, and
     * the two would disagree exactly when the phone was under pressure.
     */
    private fun refreshStandbyConditions() {
        val reading = DeviceRuntimeReadings.read(this)
        val cost = DeviceRuntimeReadings.networkCost(this)
        vanSession.setStandbyConditions(
            // §20.9 — an unreadable battery does not authorise optional spending.
            //
            // This read `UNKNOWN -> 100`, which is the right instinct applied to the
            // wrong question. `VanResourceEnvelope` treats an unknown reading as
            // contributing no pressure, and that is correct there: an OEM that will not
            // answer the capacity property must not leave VAN permanently crippled.
            // A warm standby is not capability, it is *cost* — a second authenticated
            // socket with its own heartbeats — and the asymmetry `networkCost` already
            // states applies: an unreadable battery should cost VAN an optional extra
            // connection, not cost the owner one they never authorised.
            //
            // So unknown is passed through as the envelope's own sentinel, and
            // `WarmStandbyPolicy` refuses on it rather than this file inventing a number.
            batteryPercent = reading.batteryPercent,
            charging = reading.charging,
            standbyIsMetered = cost.metered,
            dataSaverEnabled = cost.dataSaverEnabled,
        )
    }

    /**
     * Put the wake word's real state in front of the owner.
     *
     * The absence of a model is a fact about VAN's capability, not a fact to hide: without
     * this the owner says "Hey Van" into a phone that was never going to answer and has no
     * way to find out why.
     */
    private fun publishWakeModelState() {
        val status = wakeModel.status()
        if (status.ready) {
            degradedModeStore.markWorking("wake_word")
        } else {
            degradedModeStore.markBroken(
                "wake_word",
                status.sentence,
                com.dial.van.degraded.RestoreAction.OPEN_SETTINGS,
            )
        }
    }

    private fun activeSpeechContexts(): Set<SpeechContext> {
        val project = commandController.state.value.selectedProjectId?.lowercase()
        val projectContext = when (project) {
            "dde" -> SpeechContext.DDE
            "dial" -> SpeechContext.DIAL
            "vati", "trading" -> SpeechContext.VATI_TRADING
            else -> null
        }
        return buildSet {
            add(SpeechContext.GENERAL)
            add(SpeechContext.VAN_SYSTEM)
            projectContext?.let(::add)
        }
    }

    private fun startGatewayHealthMonitor() {
        appScope.launch {
            while (isActive) {
                refreshGatewayHealth()
                delay(GATEWAY_HEALTH_INTERVAL_MS)
            }
        }
    }

    private suspend fun refreshGatewayHealth() {
        try {
            val health = gatewayClient.health()
            degradedModeStore.markWorking("gateway")
            // P3-AND-006 — the gateway coming back is the other recovery edge. A phone with
            // a working network and an unreachable gateway is the normal condition of a
            // self-hosted service on a home connection.
            queueReplayer.onGatewayReachable(true)

            if (health.optBoolean("ok", false)) {
                degradedModeStore.markWorking("hermes")
            } else {
                val detail = health.optJSONObject("hermes")
                    ?.optString("degraded")
                    ?.takeIf { it.isNotBlank() }
                    ?: "Hermes health check failed"
                degradedModeStore.markBroken(
                    "hermes",
                    detail,
                    com.dial.van.degraded.RestoreAction.RETRY_CONNECTION,
                )
            }

            val mesh = health.optJSONObject("google_mesh")
            val principalRegistered =
                mesh?.optJSONObject("principal")?.optBoolean("registered", false) == true
            degradedModeStore.applyGoogleMesh(
                configuredCapabilities = mesh?.optInt("configured_capabilities", 0) ?: 0,
                totalCapabilities = mesh?.optInt("total_capabilities", 0) ?: 0,
                principalRegistered = principalRegistered,
                workspaceApiState = mesh?.optString("workspace_api_state")
                    ?.takeIf { it.isNotBlank() },
            )
        } catch (exc: Throwable) {
            queueReplayer.onGatewayReachable(false)
            degradedModeStore.markBroken(
                "gateway",
                "Gateway health unavailable: ${exc.javaClass.simpleName}",
                com.dial.van.degraded.RestoreAction.RETRY_CONNECTION,
            )
            degradedModeStore.markBroken(
                "hermes",
                "Hermes health unavailable through gateway",
                com.dial.van.degraded.RestoreAction.RETRY_CONNECTION,
            )
        }
    }

    override fun onPartial(text: String) {
        voiceUi.partial(text)
        if (text.isNotBlank()) VanLiveVisualState.listeningStarted()
    }

    override fun onFinalResult(result: VoiceRecognitionResult) {
        val corrected = personalSpeechModel.correctionFor(result.text, activeSpeechContexts()) ?: result.text
        val hasText = corrected.isNotBlank()
        voiceUi.final(corrected)
        VanLiveVisualState.finalTranscript(hasText = hasText)
        if (hasText) {
            commandController.submitText(
                text = corrected,
                source = VanCommandSource.VOICE,
                turnId = result.turnId,
                speechEvidenceRef = result.speechEvidenceRef,
                speakerScore = result.speakerSimilarity,
            )
        }
        // Re-arm only when this was the exact turn opened by WakeCoordinator. Manual voice
        // turns have no active wake turn and therefore cannot enable background listening.
        wakeCoordinator.commandTurnFinished(turnId = result.turnId)
    }

    override fun onError(code: Int) {
        voiceUi.error(code)
        VanLiveVisualState.warning(urgency = 0.25f)
        VanLiveVisualState.settleToIdle(delayMs = 1_200L, allowCritical = true)
        wakeCoordinator.commandTurnFinished()
    }

    override fun onListeningChanged(listening: Boolean) {
        voiceUi.listening(listening)
        if (listening) VanLiveVisualState.listeningStarted() else VanLiveVisualState.listeningEnded()
    }

    override fun onSpeakingChanged(speaking: Boolean) {
        if (speaking) {
            VanLiveVisualState.speakingStarted()
        } else {
            VanLiveVisualState.speakingEnded()
            VanLiveVisualState.settleToIdle()
        }
    }

    override fun onSpeechFrame(frame: SpeechSyncFrame) {
        VanLiveVisualState.speechFrame(mouthOpen = frame.mouthOpen, viseme = frame.viseme)
    }

    override fun onUtteranceDone(utteranceId: String) {
        VanLiveVisualState.speakingEnded()
        VanLiveVisualState.settleToIdle()
    }

    companion object {
        private const val GATEWAY_HEALTH_INTERVAL_MS = 60_000L

        // Rev 1.5 §29.10 — the browser session record's keys. Named constants rather
        // than literals at each call site, because a typo in one of eight strings
        // produces a record that writes and never reads back.
        private const val KEY_BROWSER_SESSION_ID = "browser.session_id"
        private const val KEY_BROWSER_PROFILE = "browser.profile_alias"
        private const val KEY_BROWSER_VIEWPORT = "browser.viewport_revision"
        private const val KEY_BROWSER_EVENT_CURSOR = "browser.event_cursor"
        private const val KEY_BROWSER_SPOKEN = "browser.last_spoken_segment"
        private const val KEY_BROWSER_PERSISTED_AT = "browser.persisted_at_ms"
        private const val KEY_BROWSER_OBSERVED = "browser.last_observed_state"
        private const val KEY_BROWSER_GENERATION = "browser.control_generation"

        lateinit var instance: VanApplication
            private set
    }
}
