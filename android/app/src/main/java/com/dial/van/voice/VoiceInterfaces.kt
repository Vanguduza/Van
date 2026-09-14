package com.dial.van.voice

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanVisualState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

/** Speech sync clock feeding viseme/RMS/mouth_open into [VanVisualState]. */
data class SpeechSyncFrame(
    val timestampMs: Long,
    val rmsDb: Float,
    val mouthOpen: Float,
    val viseme: Int,
)

interface VoiceInputCallback {
    fun onPartial(text: String)
    fun onFinal(text: String)
    fun onError(code: Int)
    fun onListeningChanged(listening: Boolean)
}

interface TtsOutputCallback {
    fun onSpeakingChanged(speaking: Boolean)
    fun onSpeechFrame(frame: SpeechSyncFrame)
    fun onUtteranceDone(utteranceId: String)
}

interface BargeInHook {
    fun onBargeInRequested()
    fun isSpeaking(): Boolean
}

/**
 * Voice input via SpeechRecognizer. Does not embed an agent loop — transcripts
 * are enqueued for Hermes dispatch upstream.
 */
class VoiceInputManager(
    context: Context,
    private val callback: VoiceInputCallback,
) {
    private val recognizer: SpeechRecognizer? =
        if (SpeechRecognizer.isRecognitionAvailable(context)) SpeechRecognizer.createSpeechRecognizer(context)
        else null

    private val listening = AtomicBoolean(false)

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            listening.set(true)
            callback.onListeningChanged(true)
        }

        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit
        override fun onEndOfSpeech() {
            listening.set(false)
            callback.onListeningChanged(false)
        }

        override fun onError(error: Int) {
            listening.set(false)
            callback.onListeningChanged(false)
            callback.onError(error)
        }

        override fun onResults(results: Bundle?) {
            val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
            callback.onFinal(text)
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val text = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
            callback.onPartial(text)
        }

        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }

    init {
        recognizer?.setRecognitionListener(listener)
    }

    fun startListening() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        recognizer?.startListening(intent)
    }

    fun stopListening() {
        recognizer?.stopListening()
        listening.set(false)
        callback.onListeningChanged(false)
    }

    fun destroy() {
        recognizer?.destroy()
    }

    fun isListening(): Boolean = listening.get()
}

/**
 * TTS output with barge-in support and speech sync frames for avatar animation.
 */
class TtsOutputManager(
    context: Context,
    private val callback: TtsOutputCallback,
) : BargeInHook, TextToSpeech.OnInitListener {

    private var tts: TextToSpeech? = TextToSpeech(context.applicationContext, this)
    private val speaking = AtomicBoolean(false)
    private var ready = false

    private val _visualState = MutableStateFlow(VanVisualState())
    val visualState: StateFlow<VanVisualState> = _visualState.asStateFlow()

    override fun onInit(status: Int) {
        ready = status == TextToSpeech.SUCCESS
        tts?.language = Locale.getDefault()
        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {
                speaking.set(true)
                callback.onSpeakingChanged(true)
                _visualState.value = _visualState.value.copy(
                    durableState = VanDurableState.SPEAKING,
                    speaking = true,
                )
            }

            override fun onDone(utteranceId: String?) {
                speaking.set(false)
                callback.onSpeakingChanged(false)
                callback.onUtteranceDone(utteranceId.orEmpty())
                _visualState.value = _visualState.value.copy(
                    durableState = VanDurableState.IDLE,
                    speaking = false,
                    mouthOpen = 0f,
                )
            }

            @Deprecated("Deprecated in API")
            override fun onError(utteranceId: String?) {
                speaking.set(false)
                callback.onSpeakingChanged(false)
            }

            override fun onRangeStart(utteranceId: String?, start: Int, end: Int, frame: Int) {
                val open = ((frame % 10) / 10f).coerceIn(0f, 1f)
                val viseme = frame % 15
                val sync = SpeechSyncFrame(System.currentTimeMillis(), rmsDb = open, mouthOpen = open, viseme = viseme)
                callback.onSpeechFrame(sync)
                _visualState.value = _visualState.value.copy(mouthOpen = open, viseme = viseme)
            }
        })
    }

    fun speak(text: String, utteranceId: String = "van-tts-${System.currentTimeMillis()}") {
        if (!ready) return
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, utteranceId)
    }

    override fun onBargeInRequested() {
        if (speaking.get()) {
            tts?.stop()
            speaking.set(false)
            callback.onSpeakingChanged(false)
            _visualState.value = _visualState.value.copy(speaking = false, mouthOpen = 0f, durableState = VanDurableState.LISTENING)
        }
    }

    override fun isSpeaking(): Boolean = speaking.get()

    fun shutdown() {
        tts?.shutdown()
        tts = null
    }
}

/** Bridges voice I/O barge-in: user speech cancels TTS. */
class VoiceSessionCoordinator(
    private val input: VoiceInputManager,
    private val output: TtsOutputManager,
) {
    fun beginOwnerTurn() {
        if (output.isSpeaking()) output.onBargeInRequested()
        input.startListening()
    }

    fun endOwnerTurn() {
        input.stopListening()
    }
}
