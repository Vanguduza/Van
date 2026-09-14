package com.dial.van

import android.app.Application
import com.dial.van.degraded.DegradedModeStore
import com.dial.van.notification.NotificationPolicyStore
import com.dial.van.queue.EncryptedCommandQueue
import com.dial.van.voice.TtsOutputCallback
import com.dial.van.voice.TtsOutputManager
import com.dial.van.voice.VoiceInputCallback
import com.dial.van.voice.VoiceInputManager
import com.dial.van.voice.VoiceSessionCoordinator
import com.dial.van.voice.SpeechSyncFrame

class VanApplication : Application(), VoiceInputCallback, TtsOutputCallback {

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

    override fun onCreate() {
        super.onCreate()
        instance = this
        commandQueue = EncryptedCommandQueue(this)
        notificationPolicyStore = NotificationPolicyStore(this)
        degradedModeStore = DegradedModeStore()
        voiceInput = VoiceInputManager(this, this)
        ttsOutput = TtsOutputManager(this, this)
        voiceSession = VoiceSessionCoordinator(voiceInput, ttsOutput)
    }

    override fun onPartial(text: String) = Unit
    override fun onFinal(text: String) = Unit
    override fun onError(code: Int) = Unit
    override fun onListeningChanged(listening: Boolean) = Unit
    override fun onSpeakingChanged(speaking: Boolean) = Unit
    override fun onSpeechFrame(frame: SpeechSyncFrame) = Unit
    override fun onUtteranceDone(utteranceId: String) = Unit

    companion object {
        lateinit var instance: VanApplication
            private set
    }
}
