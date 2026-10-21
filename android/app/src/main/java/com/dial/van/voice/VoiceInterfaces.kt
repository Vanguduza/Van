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
import java.util.concurrent.Executors
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
    /**
     * P1-VOICE-003 — why VAN cannot listen, in words the owner can act on.
     *
     * Defaulted so every existing implementation keeps compiling and the ones that care
     * can override. An error code alone cannot distinguish "your Android is too old" from
     * "your speech recognizer is disabled", and only the second is something the owner can
     * fix.
     */
    fun onUnavailable(reason: String?) = Unit
    fun onCancelled(turnId: String) = Unit
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
    private var secondPassCoordinator: VoiceSecondPassCoordinator? = null,
    private val personalConfusionProvider: (String) -> Boolean = { false },
    private var speakerSimilarityScorer: SpeakerSimilarityScorer? = null,
) {
    private val appContext = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    private val evidenceExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "van-voice-evidence").apply { isDaemon = true }
    }
    private val listening = AtomicBoolean(false)
    private val speakerEvidenceRevision = SpeakerEvidenceRevision()
    @Volatile private var speakerEnrollmentCapture = false
    private val onDeviceAvailable =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && SpeechRecognizer.isOnDeviceRecognitionAvailable(appContext)
    val capability: VoiceRecognitionCapabilityDecision
        get() = VoiceRecognitionPolicy.decide(
            Build.VERSION.SDK_INT, onDeviceAvailable && recognizer != null,
            secondPassCoordinator?.isReady() == true,
        )

    private val recognizer: SpeechRecognizer? = runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && onDeviceAvailable) {
                SpeechRecognizer.createOnDeviceSpeechRecognizer(appContext)
            } else null
        }.getOrNull()

    private var pipeSession: VoiceAudioPipeSession? = null
    private var turnAudioCapture: VoiceTurnAudioCapture? = null
    private val turnLifecycle = VoiceTurnLifecycle()
    private val _ownerTurnActive = MutableStateFlow(false)
    val ownerTurnActive: StateFlow<Boolean> = _ownerTurnActive.asStateFlow()
    private var activeTurnStartedAtMs: Long = 0L
    private var offlineToken: VoiceTurnLifecycle.Token? = null
    private var offlineSink: ((ByteArray) -> Unit)? = null
    private var offlineTimeout: Runnable? = null
    private var offlineEndpoint: OfflineVoiceTurn? = null

    private fun recognitionListener(token: VoiceTurnLifecycle.Token) = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            if (!turnLifecycle.acceptsRecognition(token)) return
            listening.set(true)
            callback.onListeningChanged(true)
        }

        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit

        override fun onEndOfSpeech() {
            if (!turnLifecycle.acceptsRecognition(token)) return
            // Closing caller audio signals EOS to the recognizer but deliberately leaves the
            // arbiter capture session alive so wake can resume without reopening AudioRecord.
            closePipeOnly()
            listening.set(false)
            callback.onListeningChanged(false)
        }

        override fun onError(error: Int) {
            if (!turnLifecycle.acceptsRecognition(token)) return
            cleanupTurn(preserveCapture = true)
            listening.set(false)
            callback.onListeningChanged(false)
            callback.onError(error)
        }

        override fun onResults(results: Bundle?) {
            if (!turnLifecycle.claimFinal(token)) return
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

            val androidResult = VoiceRecognitionResult(
                turnId = token.turnId,
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
            val capturedPcm = turnAudioCapture?.snapshot() ?: ByteArray(0)
            val biasingStrings = if (secondPassCoordinator != null) biasingStringsProvider() else emptyList()
            val knownConfusion = personalConfusionProvider(androidResult.text)
            val secondPassDecision = secondPassCoordinator?.shouldRun(androidResult, knownConfusion)
            val hasCapturedEvidence = capturedPcm.isNotEmpty()
            val needsSecondPass =
                secondPassCoordinator != null && secondPassDecision?.run == true && hasCapturedEvidence
            val speakerForTurn = speakerSimilarityScorer
            val speakerRevision = speakerEvidenceRevision.snapshot()
            val needsSpeakerEvidence = speakerForTurn != null && hasCapturedEvidence

            cleanupTurn(preserveCapture = true, discardResult = false)

            if (needsSecondPass || needsSpeakerEvidence) {
                evidenceExecutor.execute {
                    val resolved = if (needsSecondPass) {
                        runCatching {
                            secondPassCoordinator!!.resolve(
                                android = androidResult,
                                pcm16 = capturedPcm,
                                biasingStrings = biasingStrings,
                                knownPersonalConfusion = knownConfusion,
                            )
                        }.getOrDefault(androidResult)
                    } else {
                        androidResult
                    }
                    val speakerScore = if (needsSpeakerEvidence) {
                        runCatching { speakerForTurn!!.similarity(capturedPcm) }
                            .getOrNull()
                            ?.takeIf { it.isFinite() }
                            ?.coerceIn(0f, 1f)
                    } else {
                        null
                    }
                    mainHandler.post {
                        finishRecognition(token, resolved.copy(speakerSimilarity = speakerEvidenceRevision.admit(speakerRevision, speakerScore)))
                        capturedPcm.fill(0)
                    }
                }
            } else {
                finishRecognition(token, androidResult)
            }
        }

        override fun onPartialResults(partialResults: Bundle?) {
            if (!turnLifecycle.acceptsRecognition(token)) return
            val text = partialResults
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                .orEmpty()
            callback.onPartial(text)
        }

        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }

    fun startListening(turnId: String = UUID.randomUUID().toString()): String {
        mainHandler.post { startListeningOnMain(turnId) }
        return turnId
    }

    private fun startListeningOnMain(turnId: String) {
        if (speakerEnrollmentCapture) {
            callback.onUnavailable("Local speaker enrollment owns the microphone; finish or cancel it before speaking a command.")
            callback.onCancelled(turnId)
            return
        }
        prepareRecognizerForNewTurn()
        val token = turnLifecycle.begin(turnId)
        _ownerTurnActive.value = true
        activeTurnStartedAtMs = System.currentTimeMillis()

        if (capability.backend == VoiceRecognitionBackend.SHERPA_PRIMARY) {
            startOfflineTurn(token)
            return
        }

        val localRecognizer = recognizer
        if (localRecognizer == null) {
            cleanupTurn(preserveCapture = true)
            callback.onListeningChanged(false)
            // P1-VOICE-003 — the reason travels with the code. An owner told only
            // "-10002" learns nothing, and the two situations behind these codes need
            // different things from them: one is an unsupported Android version, the
            // other is a recognizer they can install or re-enable.
            callback.onUnavailable(unavailableReason())
            callback.onError(
                if (capability.backend == VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED) {
                    ERROR_SHERPA_PRIMARY_REQUIRED
                } else ERROR_LOCAL_ASR_UNAVAILABLE,
            )
            return
        }

        val callerAudio = if (capability.callerAudioSupported) {
            try {
                // If wake is already capturing, start() is idempotent and both the turn evidence
                // buffer and recognizer pipe attach to the same AudioRecord/pre-roll.
                check(audioArbiter.start()) { "voice_audio_capture_unavailable" }
                turnAudioCapture = VoiceTurnAudioCapture(audioArbiter)
                audioArbiter.openRecognitionPipe().also { pipeSession = it }.readFd
            } catch (_: Throwable) {
                cleanupTurn(preserveCapture = true)
                callback.onError(ERROR_AUDIO_ARBITER_UNAVAILABLE)
                return
            }
        } else {
            if (capability.requiresArbiterYield) audioArbiter.yieldToSystemCapture()
            null
        }

        val intent = buildRecognitionIntent(callerAudio)
        runCatching {
            localRecognizer.setRecognitionListener(recognitionListener(token))
            localRecognizer.startListening(intent)
        }
            .onFailure {
                cleanupTurn(preserveCapture = true)
                callback.onError(ERROR_LOCAL_ASR_START_FAILED)
            }
    }

    /** Reset only recognizer-owned turn resources. Never tears down caller-audio capture. */
    private fun prepareRecognizerForNewTurn() {
        closeOfflineTurn()
        closePipeOnly()
        closeTurnAudioCapture()
        turnLifecycle.cancel()
        if (_ownerTurnActive.value) runCatching { recognizer?.cancel() }
        listening.set(false)
        _ownerTurnActive.value = false
    }

    private fun finishRecognition(token: VoiceTurnLifecycle.Token, result: VoiceRecognitionResult) {
        if (!turnLifecycle.finish(token)) return
        _ownerTurnActive.value = false
        listening.set(false)
        callback.onListeningChanged(false)
        callback.onFinalResult(result)
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

    fun stopListening(preserveCapture: Boolean = false) {
        mainHandler.post { stopListeningOnMain(notify = true, preserveCapture = preserveCapture) }
    }

    private fun stopListeningOnMain(notify: Boolean, preserveCapture: Boolean) {
        offlineToken?.let { token ->
            finishOfflineTurn(token, preserveCapture)
            return
        }
        closePipeOnly()
        runCatching { recognizer?.stopListening() }
        if (capability.callerAudioSupported && !preserveCapture) {
            audioArbiter.stopCapture(clearPreRoll = false)
        }
        listening.set(false)
        if (notify) callback.onListeningChanged(false)
    }

    /** Discard this turn, including a final already queued for local evidence processing. */
    fun cancelListening(preserveCapture: Boolean = false) {
        mainHandler.post {
            val cancelled = turnLifecycle.cancel()
            _ownerTurnActive.value = false
            runCatching { recognizer?.cancel() }
            cleanupTurn(preserveCapture)
            listening.set(false)
            callback.onListeningChanged(false)
            cancelled?.let { callback.onCancelled(it.turnId) }
        }
    }

    private fun closePipeOnly() {
        pipeSession?.close()
        pipeSession = null
    }

    private fun closeTurnAudioCapture() {
        turnAudioCapture?.close()
        turnAudioCapture = null
    }

    private fun cleanupTurn(preserveCapture: Boolean, discardResult: Boolean = true) {
        closeOfflineTurn()
        closePipeOnly()
        closeTurnAudioCapture()
        if (capability.callerAudioSupported && !preserveCapture) {
            audioArbiter.stopCapture(clearPreRoll = false)
        }
        if (discardResult) {
            turnLifecycle.cancel()
            _ownerTurnActive.value = false
        }
    }

    fun destroy() {
        mainHandler.post {
            turnLifecycle.cancel()
            _ownerTurnActive.value = false
            closeOfflineTurn()
            stopListeningOnMain(notify = false, preserveCapture = false)
            closeTurnAudioCapture()
            recognizer?.destroy()
            audioArbiter.close()
            evidenceExecutor.shutdownNow()
        }
    }

    fun isListening(): Boolean = listening.get()

    /**
     * Why VAN cannot listen on this device, or null when it can.
     *
     * P1-VOICE-003 — the reason exists so the owner can be told something they can act on.
     * A field only the tests read is the defect this whole audit is about, so this is the
     * production consumer: the surface that decides what to show when voice is
     * unavailable reads it here rather than mapping an error code back to a guess.
     */
    fun unavailableReason(): String? =
        if (recognizer == null && capability.backend != VoiceRecognitionBackend.SHERPA_PRIMARY) {
            capability.unavailableReason
                ?: when (capability.backend) {
                    VoiceRecognitionBackend.SHERPA_PRIMARY_REQUIRED ->
                        "this Android version needs a speech runtime VAN does not ship"
                    else -> "VAN could not start the device's speech recognizer"
                }
        } else null

    /** Evidence is the actual local RMS endpointing path or the on-device recognizer. */
    fun localVadReady(): Boolean = recognizer != null || capability.backend == VoiceRecognitionBackend.SHERPA_PRIMARY

    /** Main-thread publication after background asset/native initialization; never changes an active turn. */
    fun bindLocalModels(
        coordinator: VoiceSecondPassCoordinator?,
        speaker: SpeakerSimilarityScorer?,
    ): Boolean {
        check(Looper.myLooper() == Looper.getMainLooper()) { "voice_models_bind_requires_main_thread" }
        if (_ownerTurnActive.value) return false
        secondPassCoordinator = coordinator
        updateSpeakerEvidence(speaker)
        return true
    }

    /** Reserve the shared capture before enrollment; manual and wake turns then fail closed. */
    fun isSpeakerEnrollmentCaptureActive(): Boolean = speakerEnrollmentCapture

    fun beginSpeakerEnrollmentCapture(): Boolean {
        check(Looper.myLooper() == Looper.getMainLooper())
        if (_ownerTurnActive.value || speakerEnrollmentCapture) return false
        speakerEnrollmentCapture = true
        return true
    }

    fun endSpeakerEnrollmentCapture() {
        check(Looper.myLooper() == Looper.getMainLooper())
        speakerEnrollmentCapture = false
    }

    /** May clear evidence during a turn; late workers cannot republish the old profile score. */
    fun updateSpeakerEvidence(speaker: SpeakerSimilarityScorer?) {
        check(Looper.myLooper() == Looper.getMainLooper()) { "voice_models_require_main_thread" }
        speakerEvidenceRevision.changed()
        speakerSimilarityScorer = speaker
    }

    private fun startOfflineTurn(token: VoiceTurnLifecycle.Token) {
        if (!audioArbiter.start()) {
            cleanupTurn(preserveCapture = true)
            callback.onError(ERROR_AUDIO_ARBITER_UNAVAILABLE)
            return
        }
        val endpoint = OfflineVoiceTurn(sampleRateHz = audioArbiter.sampleRateHz)
        val vad = EnergyVadGate()
        turnAudioCapture = VoiceTurnAudioCapture(audioArbiter, maxDurationMs = 32_000)
        offlineToken = token
        offlineEndpoint = endpoint
        val sink: (ByteArray) -> Unit = { frame ->
            when (endpoint.accept(frame.size, vad.isSpeech(frame))) {
                OfflineVoiceTurn.State.CAPTURING -> Unit
                OfflineVoiceTurn.State.FINALIZE -> mainHandler.post {
                    finishOfflineTurn(token, preserveCapture = true)
                }
                OfflineVoiceTurn.State.NO_SPEECH -> mainHandler.post {
                    finishOfflineTurn(token, preserveCapture = true, rejection = SpeechRecognizer.ERROR_SPEECH_TIMEOUT)
                }
                OfflineVoiceTurn.State.TOO_LONG -> mainHandler.post {
                    finishOfflineTurn(token, preserveCapture = true, rejection = ERROR_OFFLINE_TURN_TOO_LONG)
                }
            }
        }
        offlineSink = sink
        audioArbiter.registerSink(sink)
        val timeout = Runnable {
            finishOfflineTurn(token, preserveCapture = true, rejection = ERROR_OFFLINE_TURN_TOO_LONG)
        }
        offlineTimeout = timeout
        mainHandler.postDelayed(timeout, 30_000)
        listening.set(true)
        callback.onListeningChanged(true)
    }

    private fun finishOfflineTurn(
        token: VoiceTurnLifecycle.Token,
        preserveCapture: Boolean,
        rejection: Int? = null,
    ) {
        if (!turnLifecycle.claimFinal(token)) return
        val refused = rejection ?: if (offlineEndpoint?.heardSpeech() != true) SpeechRecognizer.ERROR_NO_MATCH else null
        val pcm = turnAudioCapture?.snapshot() ?: ByteArray(0)
        val startedAt = activeTurnStartedAtMs
        val bias = biasingStringsProvider()
        cleanupTurn(preserveCapture, discardResult = false)
        listening.set(false)
        callback.onListeningChanged(false)
        if (refused != null) {
            if (turnLifecycle.finish(token)) {
                _ownerTurnActive.value = false
                callback.onError(refused)
            }
            return
        }
        val speakerForTurn = speakerSimilarityScorer
        val speakerRevision = speakerEvidenceRevision.snapshot()
        evidenceExecutor.execute {
            val local = runCatching { secondPassCoordinator!!.transcribePrimary(pcm, bias) }.getOrNull()
            val text = local?.text?.trim().orEmpty()
            val score = runCatching { speakerForTurn?.similarity(pcm) }.getOrNull()
                ?.takeIf { it.isFinite() }?.coerceIn(0f, 1f)
            mainHandler.post {
                if (text.isBlank()) {
                    if (turnLifecycle.finish(token)) {
                        _ownerTurnActive.value = false
                        callback.onError(SpeechRecognizer.ERROR_NO_MATCH)
                    }
                } else {
                    finishRecognition(token, VoiceRecognitionResult(
                        turnId = token.turnId,
                        text = text,
                        hypotheses = listOf(text),
                        // OfflineRecognizer exposes no calibrated confidence; do not invent one.
                        hypothesisConfidence = emptyList(),
                        words = emptyList(), alternatives = emptyList(),
                        backend = VoiceRecognitionBackend.SHERPA_PRIMARY,
                        callerAudioInjected = false,
                        startedAtMs = startedAt, finalizedAtMs = System.currentTimeMillis(),
                        speakerSimilarity = speakerEvidenceRevision.admit(speakerRevision, score),
                    ))
                }
                pcm.fill(0)
            }
        }
    }

    private fun closeOfflineTurn() {
        offlineSink?.let(audioArbiter::unregisterSink)
        offlineSink = null
        offlineTimeout?.let(mainHandler::removeCallbacks)
        offlineTimeout = null
        offlineToken = null
        offlineEndpoint = null
    }

    companion object {
        const val ERROR_SHERPA_PRIMARY_REQUIRED = -10_001
        const val ERROR_LOCAL_ASR_UNAVAILABLE = -10_002
        const val ERROR_AUDIO_ARBITER_UNAVAILABLE = -10_003
        const val ERROR_LOCAL_ASR_START_FAILED = -10_004
        const val ERROR_OFFLINE_TURN_TOO_LONG = -10_005
        private const val MAX_HYPOTHESES = 5
        private const val MAX_BIAS_STRINGS = 40
        private const val MAX_BIAS_STRING_LENGTH = 64
    }
}

/**
 * TTS output with barge-in support and speech sync frames for avatar animation.
 *
 * GAP-F-013 now has two explicit playback paths. Sherpa synthesis is PCM owned by VAN
 * through AudioTrack, so RMS/mouth-open frames come from the samples actually being played.
 * Android TextToSpeech remains the fallback; because Android does not expose its playback
 * samples, that path uses the Gateway's [SegmentCueTiming] estimate and then onRangeStart
 * when no cue track exists. The active engine is tracked explicitly so the output layer
 * cannot silently ignore LocalTtsRouter's selection.
 */
class TtsOutputManager(
    context: Context,
    private val callback: TtsOutputCallback,
) : BargeInHook, TextToSpeech.OnInitListener {

    private val androidLock = Any()
    private var tts: TextToSpeech? = null
    private var pendingAndroidInitStatus: Int? = null
    private var androidInitSucceeded = false
    private var androidShutDown = false
    private val sherpa = SherpaLocalTtsRuntime(context.applicationContext)
    private val speaking = AtomicBoolean(false)
    @Volatile private var activeEngine: TtsEngineKind? = null
    private val main by lazy(LazyThreadSafetyMode.SYNCHRONIZED) { Handler(Looper.getMainLooper()) }

    /** Set by [speak] just before Android TextToSpeech.speak, read once in onStart. */
    private var pendingCueTiming: SegmentCueTiming = SegmentCueTiming.EMPTY
    private var activeCueTiming: SegmentCueTiming? = null
    private var cueStartAtMs: Long = 0L
    private var cueGeneration = 0L

    private val _visualState = MutableStateFlow(VanVisualState())
    val visualState: StateFlow<VanVisualState> = _visualState.asStateFlow()
    private val _androidOfflineReadiness = MutableStateFlow(
        AndroidOfflineTtsReadiness(AndroidOfflineTtsStatus.INITIALIZING),
    )
    val androidOfflineState: StateFlow<AndroidOfflineTtsReadiness> = _androidOfflineReadiness.asStateFlow()

    init {
        // Some engines report initialization before their constructor returns. All
        // readiness/listener fields exist first, and that callback is replayed after
        // the engine reference has been assigned.
        synchronized(androidLock) {
            try {
                tts = TextToSpeech(context.applicationContext, this)
                pendingAndroidInitStatus?.let { configureAndroid(it) }
                pendingAndroidInitStatus = null
            } catch (_: Exception) {
                _androidOfflineReadiness.value = AndroidOfflineTtsReadiness(
                    AndroidOfflineTtsStatus.INITIALIZATION_FAILED,
                )
            }
        }
    }

    /** Load and self-test VAN's checksum-pinned sherpa OfflineTts model. */
    fun prepareSherpa(): Boolean = sherpa.prepare()

    fun sherpaReady(): Boolean = sherpa.ready
    fun sherpaCanSpeak(text: String): Boolean = sherpa.canSpeak(text)

    fun sherpaPreparationError(): String? = sherpa.lastPreparationError

    override fun onInit(status: Int) = synchronized(androidLock) {
        if (androidShutDown) return@synchronized
        if (tts == null) {
            pendingAndroidInitStatus = status
        } else {
            configureAndroid(status)
        }
    }

    private fun configureAndroid(status: Int) {
        androidInitSucceeded = status == TextToSpeech.SUCCESS
        val engine = tts ?: return
        _androidOfflineReadiness.value = AndroidOfflineTtsProbe.initialize(
            androidInitSucceeded, platform(engine), Locale.getDefault(),
        )
        if (!androidInitSucceeded) {
            return
        }
        val listenerInstalled = try {
            engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {
                markStarted(TtsEngineKind.ANDROID_OFFLINE, pendingCueTiming)
            }

            override fun onDone(utteranceId: String?) {
                markDone(TtsEngineKind.ANDROID_OFFLINE, utteranceId.orEmpty())
            }

            @Deprecated("Deprecated in API")
            override fun onError(utteranceId: String?) {
                markError(TtsEngineKind.ANDROID_OFFLINE)
            }

            override fun onRangeStart(utteranceId: String?, start: Int, end: Int, frame: Int) {
                if (activeEngine != TtsEngineKind.ANDROID_OFFLINE || activeCueTiming != null) return
                val open = ((frame % 10) / 10f).coerceIn(0f, 1f)
                val viseme = frame % 15
                val sync = SpeechSyncFrame(
                    System.currentTimeMillis(),
                    rmsDb = open,
                    mouthOpen = open,
                    viseme = viseme,
                )
                callback.onSpeechFrame(sync)
                _visualState.value = _visualState.value.copy(mouthOpen = open, viseme = viseme)
            }
            }) == TextToSpeech.SUCCESS
        } catch (_: Exception) {
            false
        }
        if (!listenerInstalled) {
            androidInitSucceeded = false
            _androidOfflineReadiness.value = AndroidOfflineTtsReadiness(
                AndroidOfflineTtsStatus.PROBE_FAILED, initialized = true,
            )
        }
    }

    /** Current platform voice metadata; physical audio still requires device acceptance. */
    fun androidOfflineReadiness(): AndroidOfflineTtsReadiness = synchronized(androidLock) {
        val engine = tts
        if (androidInitSucceeded && !androidShutDown && engine != null) {
            _androidOfflineReadiness.value = AndroidOfflineTtsProbe.read(platform(engine), Locale.getDefault())
        }
        _androidOfflineReadiness.value
    }

    private fun platform(engine: TextToSpeech) = object : AndroidTtsVoicePlatform {
        private fun evidence(voice: android.speech.tts.Voice) = AndroidTtsVoiceEvidence(
            name = voice.name,
            locale = voice.locale,
            networkRequired = voice.isNetworkConnectionRequired,
            dataInstalled = voice.features?.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED) != true,
            quality = voice.quality,
            latency = voice.latency,
        )

        override fun setLanguage(locale: Locale): Boolean = engine.setLanguage(locale) >= 0
        override fun selectedVoice(): AndroidTtsVoiceEvidence? = engine.voice?.let(::evidence)
        override fun voices(): List<AndroidTtsVoiceEvidence> = engine.voices.orEmpty().map(::evidence)
        override fun selectVoice(name: String): Boolean {
            val voice = engine.voices.orEmpty().firstOrNull { it.name == name } ?: return false
            return engine.setVoice(voice) == TextToSpeech.SUCCESS
        }
    }

    /**
     * Speak through the engine selected by LocalTtsRouter.
     *
     * Returns false when the selected engine cannot actually start; callers can then show
     * the answer on screen rather than claiming speech that never happened.
     */
    fun speak(
        text: String,
        utteranceId: String = "van-tts-${System.currentTimeMillis()}",
        cueTiming: SegmentCueTiming = SegmentCueTiming.EMPTY,
        engine: TtsEngineKind = TtsEngineKind.ANDROID_OFFLINE,
    ): Boolean = when (engine) {
        TtsEngineKind.SHERPA_ONNX -> {
            if (!sherpa.ready) {
                false
            } else {
                activeEngine = TtsEngineKind.SHERPA_ONNX
                activeCueTiming = null
                sherpa.speak(
                    text = text,
                    utteranceId = utteranceId,
                    onStart = {
                        // PCM frames from SherpaLocalTtsRuntime own mouth-open while this
                        // engine speaks; estimated text cues are intentionally not started.
                        markStarted(TtsEngineKind.SHERPA_ONNX, SegmentCueTiming.EMPTY)
                    },
                    onFrame = { frame ->
                        if (activeEngine == TtsEngineKind.SHERPA_ONNX && speaking.get()) {
                            callback.onSpeechFrame(frame)
                            _visualState.value = _visualState.value.copy(
                                mouthOpen = frame.mouthOpen,
                                viseme = frame.viseme,
                            )
                        }
                    },
                    onDone = { id -> markDone(TtsEngineKind.SHERPA_ONNX, id) },
                    onError = { markError(TtsEngineKind.SHERPA_ONNX) },
                )
            }
        }

        TtsEngineKind.ANDROID_OFFLINE -> {
            synchronized(androidLock) {
                if (!androidOfflineReadiness().usableOffline) {
                    false
                } else {
                    activeEngine = TtsEngineKind.ANDROID_OFFLINE
                    pendingCueTiming = cueTiming
                    val started = try {
                        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, utteranceId) == TextToSpeech.SUCCESS
                    } catch (_: Exception) {
                        false
                    }
                    if (!started) markError(TtsEngineKind.ANDROID_OFFLINE)
                    started
                }
            }
        }

        // Phrase-bank playback is owned by WakeAcknowledgementManager, not by a synthesiser.
        TtsEngineKind.CRITICAL_PHRASE_BANK -> false
    }

    private fun markStarted(engine: TtsEngineKind, cueTiming: SegmentCueTiming) {
        if (activeEngine != engine) return
        speaking.set(true)
        callback.onSpeakingChanged(true)
        _visualState.value = _visualState.value.copy(
            durableState = VanDurableState.SPEAKING,
            speaking = true,
        )
        val timing = cueTiming.takeIf { it.cues.isNotEmpty() }
        activeCueTiming = timing
        if (timing != null) {
            cueStartAtMs = System.currentTimeMillis()
            cueGeneration += 1L
            tickCues(cueGeneration, timing)
        }
    }

    private fun markDone(engine: TtsEngineKind, utteranceId: String) {
        if (activeEngine != engine) return
        speaking.set(false)
        activeEngine = null
        callback.onSpeakingChanged(false)
        callback.onUtteranceDone(utteranceId)
        activeCueTiming = null
        cueGeneration += 1L
        _visualState.value = _visualState.value.copy(
            durableState = VanDurableState.IDLE,
            speaking = false,
            mouthOpen = 0f,
        )
    }

    private fun markError(engine: TtsEngineKind) {
        if (activeEngine != engine) return
        speaking.set(false)
        activeEngine = null
        callback.onSpeakingChanged(false)
        activeCueTiming = null
        cueGeneration += 1L
        _visualState.value = _visualState.value.copy(
            durableState = VanDurableState.IDLE,
            speaking = false,
            mouthOpen = 0f,
        )
    }

    /**
     * Android fallback: walks the Gateway cue estimate when the platform TTS does not expose
     * PCM. Sherpa does not use this because its AudioTrack path emits measured PCM RMS.
     */
    private fun tickCues(token: Long, timing: SegmentCueTiming) {
        if (
            token != cueGeneration ||
            !speaking.get() ||
            activeEngine != TtsEngineKind.ANDROID_OFFLINE
        ) return
        val elapsed = System.currentTimeMillis() - cueStartAtMs
        val (viseme, mouthOpen) = VanCueWalker.cueAt(timing.cues, elapsed)
        callback.onSpeechFrame(
            SpeechSyncFrame(
                System.currentTimeMillis(),
                rmsDb = mouthOpen,
                mouthOpen = mouthOpen,
                viseme = viseme,
            ),
        )
        _visualState.value = _visualState.value.copy(mouthOpen = mouthOpen, viseme = viseme)
        if (elapsed < timing.estimatedDurationMs + CUE_TAIL_MS) {
            main.postDelayed({ tickCues(token, timing) }, CUE_TICK_INTERVAL_MS)
        }
    }

    override fun onBargeInRequested() {
        if (speaking.get()) {
            sherpa.stop()
            tts?.stop()
            speaking.set(false)
            activeEngine = null
            activeCueTiming = null
            cueGeneration += 1L
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
        sherpa.release()
        synchronized(androidLock) {
            androidShutDown = true
            androidInitSucceeded = false
            _androidOfflineReadiness.value = AndroidOfflineTtsReadiness(AndroidOfflineTtsStatus.SHUT_DOWN)
            tts?.shutdown()
            tts = null
        }
    }

    private companion object {
        /** Fine enough to read as continuous lip movement; coarse enough to be cheap. */
        const val CUE_TICK_INTERVAL_MS = 60L

        /** Grace past the estimated duration before the ticker gives up on its own. */
        const val CUE_TAIL_MS = 250L
    }
}

/** Bridges manual voice I/O barge-in. Wake acknowledgement playback is a separate local path. */
class VoiceSessionCoordinator(
    private val input: VoiceInputManager,
    private val output: TtsOutputManager,
) {
    val ownerTurnActive: StateFlow<Boolean> = input.ownerTurnActive
    fun beginOwnerTurn(turnId: String = UUID.randomUUID().toString()): String {
        if (output.isSpeaking()) output.onBargeInRequested()
        return input.startListening(turnId)
    }

    fun endOwnerTurn(preserveCapture: Boolean = false) {
        input.stopListening(preserveCapture = preserveCapture)
    }

    fun cancelOwnerTurn(preserveCapture: Boolean = false) {
        input.cancelListening(preserveCapture = preserveCapture)
    }
}
