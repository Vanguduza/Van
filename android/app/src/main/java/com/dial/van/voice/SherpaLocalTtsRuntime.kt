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
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
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
    private val assets = appContext.assets
    private val main = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "van-sherpa-tts").apply { isDaemon = true }
    }

    @Volatile private var engine: OfflineTts? = null
    @Volatile private var preparationError: String? = null
    @Volatile private var track: AudioTrack? = null
    private val cancelled = AtomicBoolean(false)
    private var speakerId: Int = 0
    private var speed: Float = 1.0f

    val ready: Boolean get() = engine != null
    val lastPreparationError: String? get() = preparationError

    /**
     * Load and self-test the model. Call from a background thread; model initialisation is
     * intentionally not hidden on the UI thread.
     */
    fun prepare(): Boolean {
        if (engine != null) return true
        return runCatching {
            val cfg = assets.open(CONFIG_PATH).bufferedReader().use { JSONObject(it.readText()) }
            val model = when (val family = cfg.getString("family").lowercase()) {
                "kokoro" -> OfflineTtsModelConfig(
                    kokoro = OfflineTtsKokoroModelConfig(
                        model = cfg.getString("model"),
                        voices = cfg.getString("voices"),
                        tokens = cfg.getString("tokens"),
                        dataDir = cfg.optString("data_dir"),
                        lexicon = cfg.optString("lexicon"),
                        lang = cfg.optString("lang", "en-us"),
                        lengthScale = cfg.optDouble("length_scale", 1.0).toFloat(),
                    ),
                    numThreads = cfg.optInt("num_threads", 2).coerceIn(1, 4),
                    provider = "cpu",
                )
                "vits" -> OfflineTtsModelConfig(
                    vits = OfflineTtsVitsModelConfig(
                        model = cfg.getString("model"),
                        lexicon = cfg.optString("lexicon"),
                        tokens = cfg.getString("tokens"),
                        dataDir = cfg.optString("data_dir"),
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
            val created = OfflineTts(
                assetManager = assets,
                config = OfflineTtsConfig(
                    model = model,
                    maxNumSentences = 1,
                    silenceScale = cfg.optDouble("silence_scale", 0.2).toFloat(),
                ),
            )
            require(created.sampleRate() > 0) { "sherpa_tts_invalid_sample_rate" }
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
        cancelled.set(false)
        executor.execute {
            try {
                val audio = localEngine.generate(text = text, sid = speakerId, speed = speed)
                if (cancelled.get() || audio.samples.isEmpty()) {
                    if (!cancelled.get()) main.post { onError("sherpa_tts_empty_audio") }
                    return@execute
                }
                val player = newTrack(audio.sampleRate)
                track = player
                main.post(onStart)
                player.play()

                var offset = 0
                while (offset < audio.samples.size && !cancelled.get()) {
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
                    main.post { onFrame(frame) }
                    offset += written
                }

                if (!cancelled.get()) {
                    player.stop()
                    main.post { onDone(utteranceId) }
                }
            } catch (t: Throwable) {
                if (!cancelled.get()) {
                    main.post { onError(t.message ?: "sherpa_tts_failed") }
                }
            } finally {
                runCatching { track?.release() }
                track = null
            }
        }
        return true
    }

    fun stop() {
        cancelled.set(true)
        val current = track
        track = null
        runCatching { current?.pause() }
        runCatching { current?.flush() }
        runCatching { current?.stop() }
        runCatching { current?.release() }
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
