package com.dial.van

import android.app.Application
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import com.dial.van.control.VanCommandController
import com.dial.van.control.VanCommandSource
import com.dial.van.degraded.DegradedModeStore
import com.dial.van.degraded.DeviceSignals
import com.dial.van.gateway.ReplayReason
import com.dial.van.gateway.QueueReplayer
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.notification.NotificationPolicyStore
import com.dial.van.queue.EncryptedCommandQueue
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.voice.PersonalSpeechModel
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

class VanApplication : Application(), VoiceInputCallback, TtsOutputCallback {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

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
        voiceInput = VoiceInputManager(
            context = this,
            callback = this,
            biasingStringsProvider = { personalSpeechModel.biasingStrings(activeSpeechContexts()) },
        )
        voiceSession = VoiceSessionCoordinator(voiceInput, ttsOutput)
        queueReplayer = QueueReplayer(commandQueue, gatewayClient, degradedModeStore, appScope)
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
        startConnectivityMonitor()
        startGatewayHealthMonitor()
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
        runCatching {
            manager.registerNetworkCallback(
                request,
                object : ConnectivityManager.NetworkCallback() {
                    override fun onAvailable(network: Network) {
                        queueReplayer.onNetworkChanged(true)
                    }

                    override fun onLost(network: Network) {
                        // Recorded, not acted on: the recovery is the edge back up, and a
                        // replay attempt with no network is a guaranteed failure that would
                        // count against the queue's health.
                        queueReplayer.onNetworkChanged(false)
                    }
                },
            )
        }
    }

    /** The owner pressing "Try again" on a degraded subsystem (P3-AND-005). */
    fun requestReplay() = queueReplayer.replayAsync(ReplayReason.OWNER_REQUESTED)

    /** Re-read what the device actually reports. Called when a screen resumes. */
    fun refreshSubsystemHealth() = DeviceSignals.publish(this)

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
            )
        }
    }

    override fun onError(code: Int) {
        voiceUi.error(code)
        VanLiveVisualState.warning(urgency = 0.25f)
        VanLiveVisualState.settleToIdle(delayMs = 1_200L, allowCritical = true)
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

        lateinit var instance: VanApplication
            private set
    }
}
