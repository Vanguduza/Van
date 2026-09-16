package com.dial.van

import android.app.Application
import com.dial.van.degraded.DegradedModeStore
import com.dial.van.gateway.QueueReplayer
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.notification.NotificationPolicyStore
import com.dial.van.queue.EncryptedCommandQueue
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.voice.SpeechSyncFrame
import com.dial.van.voice.TtsOutputCallback
import com.dial.van.voice.TtsOutputManager
import com.dial.van.voice.VoiceInputCallback
import com.dial.van.voice.VoiceInputManager
import com.dial.van.voice.VoiceSessionCoordinator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class VanApplication : Application(), VoiceInputCallback, TtsOutputCallback {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    lateinit var commandQueue: EncryptedCommandQueue
        private set
    lateinit var notificationPolicyStore: NotificationPolicyStore
        private set
    lateinit var degradedModeStore: DegradedModeStore
        private set
    lateinit var voiceInput: VoiceInputManager
        private set
    lateinit var ttsOutput: TtsOutputManager
        private set
    lateinit var voiceSession: VoiceSessionCoordinator
        private set
    lateinit var gatewayClient: VanGatewayClient
        private set
    lateinit var queueReplayer: QueueReplayer
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        commandQueue = EncryptedCommandQueue(this)
        notificationPolicyStore = NotificationPolicyStore(this)
        degradedModeStore = DegradedModeStore()
        voiceInput = VoiceInputManager(this, this)
        ttsOutput = TtsOutputManager(this, this)
        voiceSession = VoiceSessionCoordinator(voiceInput, ttsOutput)
        gatewayClient = VanGatewayClient(this)
        queueReplayer = QueueReplayer(commandQueue, gatewayClient, degradedModeStore, appScope)
        queueReplayer.replayAsync()
    }

    override fun onPartial(text: String) {
        if (text.isNotBlank()) VanLiveVisualState.listeningStarted()
    }

    override fun onFinal(text: String) {
        // Final recognition explicitly owns the THINKING transition. Microphone end is a separate
        // event and can no longer erase this owner-turn phase.
        VanLiveVisualState.finalTranscript(hasText = text.isNotBlank())
    }

    override fun onError(code: Int) {
        VanLiveVisualState.warning(urgency = 0.25f)
        VanLiveVisualState.settleToIdle(delayMs = 1_200L, allowCritical = true)
    }

    override fun onListeningChanged(listening: Boolean) {
        if (listening) {
            VanLiveVisualState.listeningStarted()
        } else {
            // Capture ended; the turn may still be THINKING/DISPATCHING.
            VanLiveVisualState.listeningEnded()
        }
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
        VanLiveVisualState.speechFrame(
            mouthOpen = frame.mouthOpen,
            viseme = frame.viseme,
        )
    }

    override fun onUtteranceDone(utteranceId: String) {
        VanLiveVisualState.speakingEnded()
        VanLiveVisualState.settleToIdle()
    }

    companion object {
        lateinit var instance: VanApplication
            private set
    }
}
