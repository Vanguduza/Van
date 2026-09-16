package com.dial.van

import android.app.Application
import com.dial.van.degraded.DegradedModeStore
import com.dial.van.gateway.QueueReplayer
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.notification.NotificationPolicyStore
import com.dial.van.queue.EncryptedCommandQueue
import com.dial.van.visual.VanDurableState
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
        // Attempt reconnect replay; fails closed into degraded state if gateway down.
        queueReplayer.replayAsync()
    }

    override fun onPartial(text: String) {
        if (text.isNotBlank()) {
            VanLiveVisualState.transition(
                state = VanDurableState.LISTENING,
                listening = true,
            )
        }
    }

    override fun onFinal(text: String) {
        if (text.isBlank()) {
            VanLiveVisualState.settleToIdle()
        } else {
            // Recognition has ended but the owner turn is not resolved yet. THINKING gives the
            // hand-off to Hermes a distinct visual beat instead of snapping straight to idle.
            VanLiveVisualState.transition(VanDurableState.THINKING)
        }
    }

    override fun onError(code: Int) {
        // A recognizer failure is visible but does not masquerade as a system-wide outage;
        // degraded subsystem truth still has precedence in VanPresence.
        VanLiveVisualState.transition(
            state = VanDurableState.WARNING,
            urgency = 0.25f,
        )
        VanLiveVisualState.settleToIdle(delayMs = 1_200L)
    }

    override fun onListeningChanged(listening: Boolean) {
        if (listening) {
            VanLiveVisualState.transition(
                state = VanDurableState.LISTENING,
                listening = true,
            )
        } else {
            VanLiveVisualState.settleToIdle()
        }
    }

    override fun onSpeakingChanged(speaking: Boolean) {
        if (speaking) {
            VanLiveVisualState.transition(
                state = VanDurableState.SPEAKING,
                speaking = true,
            )
        } else {
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
        VanLiveVisualState.settleToIdle()
    }

    companion object {
        lateinit var instance: VanApplication
            private set
    }
}
