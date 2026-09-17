package com.dial.van.voice

import android.content.Context
import android.content.Intent
import android.media.AudioFormat
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.speech.AlternativeSpans
import android.speech.RecognitionListener
import android.speech.RecognitionPart
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
import java.util.UUID
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
    fun onFinal(text: String) = Unit
    fun onFinalResult(result: VoiceRecognitionResult) = onFinal(result.text)
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
 * Rev 3.1 speech edge. Android is not an agent loop: this class only produces a
 * provenance-rich transcript. It never uses the generic/cloud-capable recognizer.
 */
class VoiceInputManager(
    context: Context,
    private val callback: VoiceInputCallback,
    val audioArbiter: VoiceAudioArbiter = VoiceAudioArbiter(context.applicationContext),
    private val biasingStringsProvider: () -> List<String> = { emptyList() },
) {
    private val appContext = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    private val listening = AtomicBoolean(false)
    private val onDeviceAvailable =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && SpeechRecognizer.isOnDeviceRecognitionAvailable(appContext)
    val capability: VoiceRecognitionCapabilityDecision =
        VoiceRecognitionPolicy.decide(Build.VERSION.SDK_INT, onDeviceAvailable)

    private val recognizer: SpeechRecognizer? = when (capability.backend) {
        VoiceRecognitionBackend.ANDROID_ON_DEVICE_CALLER_AUDIO,
        VoiceRecognitionBackend.ANDROID_ON_DEVICE_DIRECT_MIC ->
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && onDeviceAvailable) {
                SpeechRecognizer.createOnDeviceSpeechRecognizer(appContext)
            } else null
        VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED,
        VoiceRecognitionBackend.UNAVAILABLE -> null
    }

    private var pipeSession: VoiceAudioPipeSession? = null
    private var activeTurnId: String? = null
    private var activeTurnStartedAtMs: Long = 0L

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            listening.set(true)
            callback.onListeningChanged(true)
        }

        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit

        override fun onEndOfSpeech() {
            closePipeOnly()
            listening.set(false)
            callback.onListeningChanged(false)
        }

        override fun onError(error: Int) {
            cleanupTurnCapture()
            listening.set(false)
            callback.onListeningChanged(false)
            callback.onError(error)
        }

        override fun onResults(results: Bundle?) {
            val hypotheses = results
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.filter { it.isNotBlank() }
                .orEmpty()
            val confidence = results
                ?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)
                ?.toList()
                .orEmpty()
            val words = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                results?.getParcelableArrayList(
                    SpeechRecognizer.RECOGNITION_PARTS,
                    RecognitionPart::class.java,
                ).orEmpty().map { part ->
                    VoiceWordEvidence(
                        rawText = part.rawText,
                        formattedText = part.formattedText,
                        timestampMs = part.timestampMillis,
                        confidenceLevel = part.confidenceLevel,
                    )
                }
            } else emptyList()
            val alternatives = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                results?.getParcelableArrayList(
                    SpeechRecognizer.RESULTS_ALTERNATIVES,
                    AlternativeSpans::class.java,
                )?.firstOrNull()?.spans.orEmpty().map { span ->
                    VoiceAlternativeSpanEvidence(
                        start = span.startPosition,
                        end = span.endPosition,
                        alternatives = span.alternatives.toList(),
                    )
                }
            } else emptyList()

            val turnId = activeTurnId ?: UUID.randomUUID().toString()
            val result = VoiceRecognitionResult(
                turnId = turnId,
                text = hypotheses.firstOrNull().orEmpty(),
                hypotheses = hypotheses,
                hypothesisConfidence = confidence,
                words = words,
                alternatives = alternatives,
                backend = capability.backend,
                callerAudioInjected = capability.callerAudioSupported,
                startedAtMs = activeTurnStartedAtMs,
                finalizedAtMs = System.currentTimeMillis(),
            )
            cleanupTurnCapture()
            listening.set(false)
            callback.onListeningChanged(false)
            callback.onFinalResult(result)
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val text = partialResults
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                .orEmpty()
            callback.onPartial(text)
        }

        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }

    init {
        recognizer?.setRecognitionListener(listener)
    }

    fun startListening(turnId: String = UUID.randomUUID().toString()): String {
        mainHandler.post { startListeningOnMain(turnId) }
        return turnId
    }

    private fun startListeningOnMain(turnId: String) {
        stopListeningOnMain(notify = false)
        activeTurnId = turnId
        activeTurnStartedAtMs = System.currentTimeMillis()

        val localRecognizer = recognizer
        if (localRecognizer == null) {
            callback.onListeningChanged(false)
            callback.onError(
                if (capability.backend == VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED) {
                    ERROR_SHERPA_PRIMARY_REQUIRED
                } else ERROR_LOCAL_ASR_UNAVAILABLE,
            )
            return
        }

        val callerAudio = if (capability.callerAudioSupported) {
            try {
                audioArbiter.openRecognitionPipe().also { pipeSession = it }.readFd
            } catch (_: Throwable) {
                callback.onError(ERROR_AUDIO_ARBITER_UNAVAILABLE)
                return
            }
        } else {
            if (capability.requiresArbiterYield) audioArbiter.yieldToSystemCapture()
            null
        }

        val intent = buildRecognitionIntent(callerAudio)
        runCatching { localRecognizer.startListening(intent) }
            .onFailure {
                cleanupTurnCapture()
                callback.onError(ERROR_LOCAL_ASR_START_FAILED)
            }
    }

    private fun buildRecognitionIntent(audioSource: ParcelFileDescriptor?): Intent =
        Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, MAX_HYPOTHESES)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val bias = biasingStringsProvider()
                    .asSequence()
                    .map { it.trim() }
                    .filter { it.isNotBlank() && it.length <= MAX_BIAS_STRING_LENGTH }
                    .distinct()
                    .take(MAX_BIAS_STRINGS)
                    .toCollection(ArrayList())
                if (bias.isNotEmpty()) putStringArrayListExtra(RecognizerIntent.EXTRA_BIASING_STRINGS, bias)
                putExtra(RecognizerIntent.EXTRA_ENABLE_FORMATTING, RecognizerIntent.FORMATTING_OPTIMIZE_LATENCY)
                putExtra(RecognizerIntent.EXTRA_HIDE_PARTIAL_TRAILING_PUNCTUATION, true)

                if (audioSource != null) {
                    putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, audioSource)
                    putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
                    putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
                    putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, VoiceAudioArbiter.SAMPLE_RATE_HZ)
                } else {
                    putExtra(RecognizerIntent.EXTRA_ENABLE_BIASING_DEVICE_CONTEXT, true)
                }
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                putExtra(RecognizerIntent.EXTRA_REQUEST_WORD_CONFIDENCE, true)
                putExtra(RecognizerIntent.EXTRA_REQUEST_WORD_TIMING, true)
            }
        }

    fun stopListening() {
        mainHandler.post { stopListeningOnMain(notify = true) }
    }

    private fun stopListeningOnMain(notify: Boolean) {
        closePipeOnly()
        runCatching { recognizer?.stopListening() }
        if (capability.callerAudioSupported) audioArbiter.stopCapture(clearPreRoll = false)
        listening.set(false)
        if (notify) callback.onListeningChanged(false)
    }

    private fun closePipeOnly() {
        pipeSession?.close()
        pipeSession = null
    }

    private fun cleanupTurnCapture() {
        closePipeOnly()
        if (capability.callerAudioSupported) audioArbiter.stopCapture(clearPreRoll = false)
        activeTurnId = null
    }

    fun destroy() {
        mainHandler.post {
            stopListeningOnMain(notify = false)
            recognizer?.destroy()
            audioArbiter.close()
        }
    }

    fun isListening(): Boolean = listening.get()

    companion object {
        const val ERROR_SHERPA_PRIMARY_REQUIRED = -10_001
        const val ERROR_LOCAL_ASR_UNAVAILABLE = -10_002
        const val ERROR_AUDIO_ARBITER_UNAVAILABLE = -10_003
        const val ERROR_LOCAL_ASR_START_FAILED = -10_004
        private const val MAX_HYPOTHESES = 5
        private const val MAX_BIAS_STRINGS = 40
        private const val MAX_BIAS_STRING_LENGTH = 64
    }
}

/** TTS output with barge-in support and speech sync frames for avatar animation. */
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
            _visualState.value = _visualState.value.copy(
                speaking = false,
                mouthOpen = 0f,
                durableState = VanDurableState.LISTENING,
            )
        }
    }

    override fun isSpeaking(): Boolean = speaking.get()

    fun shutdown() {
        tts?.shutdown()
        tts = null
    }
}

/** Bridges voice I/O barge-in: user speech cancels ordinary TTS before recognition. */
class VoiceSessionCoordinator(
    private val input: VoiceInputManager,
    private val output: TtsOutputManager,
) {
    fun beginOwnerTurn(turnId: String = UUID.randomUUID().toString()): String {
        if (output.isSpeaking()) output.onBargeInRequested()
        return input.startListening(turnId)
    }

    fun endOwnerTurn() {
        input.stopListening()
    }
}
