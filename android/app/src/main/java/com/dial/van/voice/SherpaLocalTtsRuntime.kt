package com.dial.van.voice

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Handler
import android.os.Looper
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsKokoroModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
import kotlin.math.sqrt

/**
 * Real sherpa-onnx local synthesis and PCM playback.
 *
 * The previous code classified LOCAL_TTS assets but deliberately never created an
 * OfflineTts instance. This class is the missing runtime backend. The bundle supplies
 * voice/tts/runtime.json; that file selects a supported model family and names the
 * checksum-pinned assets already admitted by VoiceAssetManifest.
 *
 * Synthesis uses OfflineTts.generate() rather than the JNI callback path. Playback is
 * owned by VAN through AudioTrack, so barge-in stops the actual audio and RMS frames come
 * from the PCM VAN is playing rather than from a text-length approximation.
 */
class SherpaLocalTtsRuntime(context: Context) {
    private val appContext = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "van-sherpa-tts").apply { isDaemon = true }
    }

    @Volatile private var engine: OfflineTts? = null
    @Volatile private var preparationError: String? = null
    @Volatile private var track: AudioTrack? = null
    private val playback = SpeechPlaybackEpoch()
    private val playbackLock = Any()
    private var speakerId: Int = 0
    private var speed: Float = 1.0f
    private var vocabulary: VitsLexiconCoverage? = null

    val ready: Boolean get() = engine != null
    val lastPreparationError: String? get() = preparationError
    fun canSpeak(text: String): Boolean = ready && vocabulary?.canSpeak(text) == true

    /**
     * Load and self-test the model. Call from a background thread; model initialisation is
     * intentionally not hidden on the UI thread.
     */
    @Synchronized
    fun prepare(): Boolean {
        if (engine != null) return true
        return runCatching {
            val installed = VoiceAssetInstaller.installedOrNull()
                ?: error("voice_bundle_unavailable")
            val root = installed.root
            val cfg = File(root, "tts/runtime.json").readText().let(::JSONObject)
            fun path(name: String, required: Boolean = true): String {
                val value = cfg.optString(name).trim()
                if (value.isEmpty() && !required) return ""
                val file = EmbeddedVoiceAssetInstaller.confined(root, value)
                require(file.exists()) { "sherpa_tts_asset_missing:$name" }
                if (file.isFile) require(installed.bundle.entries.any { it.path == value }) {
                    "sherpa_tts_asset_not_admitted:$name"
                }
                return file.absolutePath
            }
            val model = when (val family = cfg.getString("family").lowercase()) {
                "kokoro" -> OfflineTtsModelConfig(
                    kokoro = OfflineTtsKokoroModelConfig(
                        model = path("model"),
                        voices = path("voices"),
                        tokens = path("tokens"),
                        dataDir = path("data_dir", false),
                        lexicon = path("lexicon", false),
                        lang = cfg.optString("lang", "en-us"),
                        lengthScale = cfg.optDouble("length_scale", 1.0).toFloat(),
                    ),
                    numThreads = cfg.optInt("num_threads", 2).coerceIn(1, 4),
                    provider = "cpu",
                )
                "vits" -> OfflineTtsModelConfig(
                    vits = OfflineTtsVitsModelConfig(
                        model = path("model"),
                        lexicon = path("lexicon", false),
                        tokens = path("tokens"),
                        dataDir = path("data_dir", false),
                        noiseScale = cfg.optDouble("noise_scale", 0.667).toFloat(),
                        noiseScaleW = cfg.optDouble("noise_scale_w", 0.8).toFloat(),
                        lengthScale = cfg.optDouble("length_scale", 1.0).toFloat(),
                    ),
                    numThreads = cfg.optInt("num_threads", 2).coerceIn(1, 4),
                    provider = "cpu",
                )
                else -> error("unsupported_sherpa_tts_family:$family")
            }
            speakerId = cfg.optInt("speaker_id", 0).coerceAtLeast(0)
            speed = cfg.optDouble("speed", 1.0).toFloat().coerceIn(0.5f, 2.0f)
            // The admitted fixed English voice uses the lexicon-only frontend. That frontend
            // drops OOV words, so validate coverage before ever claiming an answer was spoken.
            require(cfg.getString("family").lowercase() == "vits" && cfg.optString("data_dir").isEmpty()) {
                "sherpa_tts_frontend_not_admitted"
            }
            vocabulary = File(path("tokens")).useLines { tokens ->
                File(path("lexicon")).useLines { lexicon -> VitsLexiconCoverage.parse(tokens, lexicon) }
            }
            require(vocabulary!!.canSpeak(WakeAcknowledgementPolicy.TEXT)) { "sherpa_tts_self_test_vocabulary_missing" }
            val created = OfflineTts(
                assetManager = null,
                config = OfflineTtsConfig(
                    model = model,
                    maxNumSentences = 1,
                    silenceScale = cfg.optDouble("silence_scale", 0.2).toFloat(),
                ),
            )
            try {
                require(created.sampleRate() > 0 && speakerId < created.numSpeakers()) {
                    "sherpa_tts_invalid_voice"
                }
                val probe = created.generate(WakeAcknowledgementPolicy.TEXT, speakerId, speed)
                require(probe.samples.isNotEmpty() && probe.samples.all { it.isFinite() }) {
                    "sherpa_tts_self_test_failed"
                }
            } catch (failure: Throwable) {
                created.release()
                throw failure
            }
            engine = created
            preparationError = null
            true
        }.getOrElse {
            preparationError = it.message ?: it::class.java.simpleName
            false
        }
    }

    fun speak(
        text: String,
        utteranceId: String,
        onStart: () -> Unit,
        onFrame: (SpeechSyncFrame) -> Unit,
        onDone: (String) -> Unit,
        onError: (String) -> Unit,
    ): Boolean {
        val localEngine = engine ?: return false
        if (!canSpeak(text)) return false
        val epoch = playback.snapshot()
        executor.execute {
            try {
                if (!playback.isCurrent(epoch)) return@execute
                val audio = localEngine.generate(text = text, sid = speakerId, speed = speed)
                if (!playback.isCurrent(epoch) || audio.samples.isEmpty()) {
                    if (playback.isCurrent(epoch)) main.post {
                        if (playback.isCurrent(epoch)) onError("sherpa_tts_empty_audio")
                    }
                    return@execute
                }
                val player = newTrack(audio.sampleRate)
                val started = synchronized(playbackLock) {
                    if (!playback.isCurrent(epoch)) false else {
                        track = player
                        player.play()
                        true
                    }
                }
                if (!started) { player.release(); return@execute }
                main.post { if (playback.isCurrent(epoch)) onStart() }

                var offset = 0
                while (offset < audio.samples.size && playback.isCurrent(epoch)) {
                    val count = minOf(CHUNK_SAMPLES, audio.samples.size - offset)
                    val written = player.write(
                        audio.samples,
                        offset,
                        count,
                        AudioTrack.WRITE_BLOCKING,
                    )
                    if (written <= 0) error("sherpa_tts_audio_write_failed:$written")
                    val rms = rms(audio.samples, offset, written)
                    val open = (rms * RMS_GAIN).coerceIn(0f, 1f)
                    val frame = SpeechSyncFrame(
                        timestampMs = System.currentTimeMillis(),
                        rmsDb = rms,
                        mouthOpen = open,
                        viseme = ((offset / CHUNK_SAMPLES) % 15),
                    )
                    main.post { if (playback.isCurrent(epoch)) onFrame(frame) }
                    offset += written
                }

                if (playback.isCurrent(epoch)) {
                    player.stop()
                    main.post { if (playback.isCurrent(epoch)) onDone(utteranceId) }
                }
            } catch (t: Throwable) {
                if (playback.isCurrent(epoch)) {
                    main.post { if (playback.isCurrent(epoch)) onError(t.message ?: "sherpa_tts_failed") }
                }
            } finally {
                synchronized(playbackLock) {
                    runCatching { track?.release() }
                    track = null
                }
            }
        }
        return true
    }

    fun stop() {
        playback.cancel()
        synchronized(playbackLock) {
            val current = track
            track = null
            runCatching { current?.pause() }
            runCatching { current?.flush() }
            runCatching { current?.stop() }
            runCatching { current?.release() }
        }
    }

    fun release() {
        stop()
        executor.shutdownNow()
        runCatching { engine?.release() }
        engine = null
    }

    private fun newTrack(sampleRate: Int): AudioTrack {
        val minBytes = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_FLOAT,
        ).coerceAtLeast(CHUNK_SAMPLES * 4)
        return AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(sampleRate)
                    .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setBufferSizeInBytes(minBytes * 2)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
    }

    private fun rms(samples: FloatArray, offset: Int, count: Int): Float {
        if (count <= 0) return 0f
        var sum = 0.0
        for (i in offset until offset + count) {
            val value = samples[i].toDouble()
            sum += value * value
        }
        return sqrt(sum / count).toFloat()
    }

    companion object {
        const val CONFIG_PATH = "voice/tts/runtime.json"
        private const val CHUNK_SAMPLES = 1024
        private const val RMS_GAIN = 5.5f
    }
}
