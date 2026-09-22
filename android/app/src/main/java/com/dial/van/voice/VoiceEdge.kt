package com.dial.van.voice

import android.content.Context
import android.media.AudioManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Rev 1.5 §21 — the local voice edge, assembled.
 *
 * The policies in this package decide things; this is the object that asks them, and it
 * exists because a policy nobody calls is a policy that is not in force. Every decision
 * below is delegated:
 *
 *     what VAN can do offline      VoiceAssetManifest
 *     which engine speaks          LocalTtsRouter
 *     what happens to other audio  AudioFocusPolicy
 *     where a spoken request goes  OfflineCommandClassifier
 *     what a barge-in does         BargeInPolicy + SpeechQueue
 *     a late answer                DelayedAnswerPolicy
 *
 * None of that logic is repeated here. This is the wiring, and the wiring is the part that
 * cannot be executed in the JVM harness — which is exactly why it holds no rules.
 */
class VoiceEdge(
    context: Context,
    private val tts: TtsOutputManager,
    private val scope: CoroutineScope,
) {

    data class Readiness(
        val capabilities: Map<VoiceCapability, VoiceAssetStatus> = emptyMap(),
        val bundleVersion: String? = null,
        val localTtsRuntimeReady: Boolean = false,
        val localTtsRuntimeError: String? = null,
    ) {
        fun ready(capability: VoiceCapability): Boolean =
            capabilities[capability]?.ready == true

        /**
         * What VAN tells the owner about its own hearing and speaking.
         *
         * Asset readiness and executable readiness are deliberately separate. A verified
         * LOCAL_TTS bundle whose OfflineTts runtime failed to initialise is not a working
         * offline voice and must never be reported as one.
         */
        val ownerSentences: List<String>
            get() = buildList {
                capabilities.values.filterNot { it.ready }.forEach { add(it.sentence) }
                if (ready(VoiceCapability.LOCAL_TTS) && !localTtsRuntimeReady) {
                    add(
                        "My offline voice files are present, but I could not start the local voice engine" +
                            (localTtsRuntimeError?.takeIf { it.isNotBlank() }?.let { ": $it" } ?: "."),
                    )
                }
            }
    }

    private val audio = context.applicationContext
        .getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    private val assets = context.applicationContext.assets

    private val _readiness = MutableStateFlow(Readiness())
    val readiness: StateFlow<Readiness> = _readiness.asStateFlow()

    private val speech = SpeechQueue()
    private var currentDucking: DuckingAction = DuckingAction.NONE

    /**
     * §21.4 — read the manifest and classify every capability, at startup.
     *
     * Failure here is not an exception. A phone with no voice bundle is the expected state
     * until the owner supplies one, and it has to come up and say what it cannot do rather
     * than refuse to start.
     */
    fun loadAssets() {
        scope.launch(Dispatchers.IO) {
            val manifestJson = runCatching {
                assets.open(MANIFEST_PATH).bufferedReader().use { it.readText() }
            }.getOrNull()

            val bundle = manifestJson
                ?.let { VoiceAssetManifest.parse(it) }
                ?.let { it as? VoiceManifestVerdict.Accepted }
                ?.bundle

            val observed = buildMap {
                bundle?.entries?.forEach { entry ->
                    runCatching {
                        assets.open(entry.path).use { stream ->
                            val bytes = stream.readBytes()
                            put(entry.path, sha256(bytes) to bytes.size.toLong())
                        }
                    }
                }
            }

            val capabilities = VoiceAssetManifest.classifyAll(bundle, observed)
            // LOCAL_TTS is not READY merely because files exist. The runtime is prepared and
            // self-tested on this IO dispatcher before the router is allowed to select it.
            val localTtsRuntimeReady =
                if (capabilities[VoiceCapability.LOCAL_TTS]?.ready == true) {
                    tts.prepareSherpa()
                } else {
                    false
                }
            _readiness.value = Readiness(
                capabilities = capabilities,
                bundleVersion = bundle?.bundleVersion,
                localTtsRuntimeReady = localTtsRuntimeReady,
                localTtsRuntimeError =
                    if (localTtsRuntimeReady) null else tts.sherpaPreparationError(),
            )
        }
    }

    /** Which engines can currently speak, as the router needs to see them. */
    private fun engines(): Map<TtsEngineKind, TtsEngineReadiness> {
        val state = _readiness.value
        return mapOf(
            TtsEngineKind.SHERPA_ONNX to TtsEngineReadiness(
                TtsEngineKind.SHERPA_ONNX,
                installed = state.ready(VoiceCapability.LOCAL_TTS),
                selfTestPassed = state.localTtsRuntimeReady && tts.sherpaReady(),
            ),
            // Android's engine is present on every device this build supports. Whether its
            // *offline* data is there is the question §21.18 is about, and `isSpeaking` is
            // not an answer to it — this reports what the platform says, and a device run
            // is what settles it (RB-085).
            TtsEngineKind.ANDROID_OFFLINE to TtsEngineReadiness(
                TtsEngineKind.ANDROID_OFFLINE, installed = true,
                offlineDataVerified = androidOfflineVoiceVerified,
            ),
            TtsEngineKind.CRITICAL_PHRASE_BANK to TtsEngineReadiness(
                TtsEngineKind.CRITICAL_PHRASE_BANK,
                installed = state.ready(VoiceCapability.CRITICAL_PHRASES),
            ),
        )
    }

    /**
     * Set once the platform has reported whether its offline voice data is installed.
     *
     * Defaults to false, which is the fail-closed direction: an engine assumed to work
     * offline and then failing is §21.18's exact complaint.
     */
    var androidOfflineVoiceVerified: Boolean = false

    /** §21.5 — the acknowledgement, which must not wait for a synthesiser. */
    fun acknowledgeWake(): Boolean {
        val selection = LocalTtsRouter.select(
            SpeechKind.CRITICAL_PHRASE, engines(), phraseKey = "wake_ack",
        )
        return when (selection) {
            is TtsSelection.Engine -> {
                // The phrase bank is played by WakeAcknowledgementManager. Any synthesiser
                // here is a late fallback, but it must be the engine the router selected.
                if (selection.kind == TtsEngineKind.CRITICAL_PHRASE_BANK) {
                    true
                } else {
                    tts.speak(
                        LocalTtsRouter.CRITICAL_PHRASES.getValue("wake_ack"),
                        engine = selection.kind,
                    )
                }
            }
            is TtsSelection.Silent -> false
        }
    }

    /**
     * Speak one segment, taking the audio from whatever else has it first.
     *
     * Returns the sentence to show instead when nothing can speak — the owner gets the
     * answer either way, which is the point of §21.18's fallback chain ending in text.
     */
    fun speak(segment: SpeechSegment, browserAudioPlaying: Boolean): String? {
        val selection = LocalTtsRouter.select(SpeechKind.ASSISTANT_ANSWER, engines())
        if (selection is TtsSelection.Silent) return selection.ownerSentence
        selection as TtsSelection.Engine

        currentDucking = AudioFocusPolicy.decide(
            vanIsSpeaking = true,
            browserAudioPlaying = browserAudioPlaying,
            callInProgress = audio?.mode == AudioManager.MODE_IN_CALL,
            otherMediaHasFocus = audio?.isMusicActive == true,
        )
        if (currentDucking == DuckingAction.YIELD) {
            // Something with more right to the audio is using it. Not an error, and not a
            // failure to answer: the segment stays queued.
            return null
        }
        val started = tts.speak(
            segment.text,
            utteranceId = segment.segmentId,
            cueTiming = segment.cueTiming,
            engine = selection.kind,
        )
        if (!started) {
            return "I can't answer aloud right now — it's on the screen instead."
        }
        speech.mark(segment.segmentId, SpeechSegmentState.SPEAKING)
        return null
    }

    /** §21.21 — the owner spoke. Local first, always. */
    fun bargeIn(): Int {
        for (step in BargeInPolicy.sequence()) {
            when (step) {
                BargeInStep.STOP_PLAYBACK -> tts.onBargeInRequested()
                BargeInStep.MARK_SEGMENTS_INTERRUPTED -> return speech.bargeIn()
                else -> Unit
            }
        }
        return 0
    }

    /** §21.22 — give back what VAN took, and only what VAN took. */
    fun releaseAudio() {
        if (AudioFocusPolicy.shouldRestore(currentDucking)) {
            currentDucking = DuckingAction.NONE
        }
    }

    /**
     * §21.11 — where a spoken request goes, decided before VAN knows if it can get there.
     *
     * Returns the routing and, when VAN cannot reach Hermes, the true sentence it says
     * instead. It never invents an answer: §21.24 is explicit that VAN must not fabricate
     * a remote answer, and every sentence here is about VAN's own state.
     */
    fun route(transcript: String, actionClass: String?, hermesReachable: Boolean): Pair<CommandRouting, String?> {
        val routing = OfflineCommandClassifier.classify(transcript, actionClass)
        if (hermesReachable || routing == CommandRouting.LOCAL_EXECUTABLE) return routing to null
        return routing to OfflineCommandClassifier.offlineSentence(routing)
    }

    fun queue(): SpeechQueue = speech

    private fun sha256(bytes: ByteArray): String =
        java.security.MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it) }

    private companion object {
        const val MANIFEST_PATH = "voice/voice_asset_manifest.json"
    }
}
