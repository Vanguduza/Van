package com.dial.van.voice

import android.content.Context
import android.media.AudioAttributes
import android.media.SoundPool
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

object WakeAcknowledgementPolicy {
    const val TEXT = "hie van"
    const val ASSET_REVISION = 1
    const val UTTERANCE_ID = "van-wake-ack-v1"
}

data class WakeAcknowledgementStatus(
    val ready: Boolean,
    val text: String,
    val assetRevision: Int,
    val assetSha256: String?,
    val ttsEngine: String?,
)

/**
 * Pre-renders the canonical wake acknowledgement into app-private storage and keeps it loaded
 * in SoundPool. Wake acceptance therefore does not wait on a cold TTS engine or network.
 */
class WakeAcknowledgementManager(
    context: Context,
    private val onReadyChanged: (WakeAcknowledgementStatus) -> Unit = {},
) : TextToSpeech.OnInitListener {
    private val appContext = context.applicationContext
    private val assetFile = File(appContext.filesDir, "voice/wake_ack_v${WakeAcknowledgementPolicy.ASSET_REVISION}.wav")
    private val ready = AtomicBoolean(false)
    private val soundPool = SoundPool.Builder()
        .setMaxStreams(1)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build(),
        )
        .build()
    private var soundId: Int? = null
    private var tts: TextToSpeech? = null
    private var ttsEngine: String? = null

    init {
        soundPool.setOnLoadCompleteListener { _, sampleId, status ->
            if (sampleId == soundId && status == 0) {
                ready.set(true)
                publishStatus()
            }
        }
        if (assetFile.isFile && assetFile.length() > MIN_ASSET_BYTES) {
            loadAsset()
        } else {
            assetFile.parentFile?.mkdirs()
            tts = TextToSpeech(appContext, this)
        }
    }

    override fun onInit(status: Int) {
        if (status != TextToSpeech.SUCCESS) {
            publishStatus()
            return
        }
        ttsEngine = tts?.defaultEngine
        tts?.language = Locale.getDefault()
        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = Unit
            override fun onDone(utteranceId: String?) {
                if (utteranceId == WakeAcknowledgementPolicy.UTTERANCE_ID && assetFile.isFile) {
                    loadAsset()
                    tts?.shutdown()
                    tts = null
                }
            }
            @Deprecated("Deprecated in API")
            override fun onError(utteranceId: String?) {
                publishStatus()
            }
        })
        val params = Bundle().apply {
            putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f)
        }
        val result = tts?.synthesizeToFile(
            WakeAcknowledgementPolicy.TEXT,
            params,
            assetFile,
            WakeAcknowledgementPolicy.UTTERANCE_ID,
        ) ?: TextToSpeech.ERROR
        if (result == TextToSpeech.ERROR) publishStatus()
    }

    @Synchronized
    private fun loadAsset() {
        if (!assetFile.isFile || assetFile.length() <= MIN_ASSET_BYTES) {
            publishStatus()
            return
        }
        ready.set(false)
        soundId?.let { soundPool.unload(it) }
        soundId = soundPool.load(assetFile.absolutePath, 1)
    }

    fun play(): Boolean {
        val id = soundId ?: return false
        if (!ready.get()) return false
        val streamId = soundPool.play(id, 1f, 1f, 1, 0, 1f)
        return streamId != 0
    }

    fun isReady(): Boolean = ready.get()

    fun status(): WakeAcknowledgementStatus = WakeAcknowledgementStatus(
        ready = ready.get(),
        text = WakeAcknowledgementPolicy.TEXT,
        assetRevision = WakeAcknowledgementPolicy.ASSET_REVISION,
        assetSha256 = assetFile.takeIf { it.isFile }?.let(::sha256),
        ttsEngine = ttsEngine,
    )

    private fun publishStatus() {
        onReadyChanged(status())
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(8192)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    fun shutdown() {
        ready.set(false)
        soundId?.let { soundPool.unload(it) }
        soundId = null
        soundPool.release()
        tts?.shutdown()
        tts = null
    }

    companion object {
        private const val MIN_ASSET_BYTES = 128L
    }
}
