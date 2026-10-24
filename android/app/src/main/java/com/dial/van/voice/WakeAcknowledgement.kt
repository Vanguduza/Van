package com.dial.van.voice

import android.content.Context
import android.media.AudioAttributes
import android.media.SoundPool
import java.io.File
import java.security.MessageDigest
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
 * Loads the genuine pre-rendered canonical acknowledgement from the admitted APK bundle.
 * Wake acceptance never initializes a synthesizer or uses a cloud-capable platform voice.
 */
class WakeAcknowledgementManager(
    context: Context,
    private val onReadyChanged: (WakeAcknowledgementStatus) -> Unit = {},
) {
    private val appContext = context.applicationContext
    private val assetFile: File?
        get() = VoiceAssetInstaller.installedOrNull()?.root?.let {
            File(it, "critical_phrases/wake_acknowledgement.wav")
        }
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

    init {
        soundPool.setOnLoadCompleteListener { _, sampleId, status ->
            if (sampleId == soundId && status == 0) {
                ready.set(true)
                publishStatus()
            }
        }
        prepare()
    }

    /** Refresh after background APK bundle installation; SoundPool loads the real audio asynchronously. */
    fun prepare(): Boolean {
        val file = assetFile ?: return false
        if (!file.isFile || file.length() <= MIN_ASSET_BYTES) return false
        loadAsset()
        return true
    }

    @Synchronized
    private fun loadAsset() {
        val file = assetFile
        if (file == null || !file.isFile || file.length() <= MIN_ASSET_BYTES) {
            publishStatus()
            return
        }
        ready.set(false)
        soundId?.let { soundPool.unload(it) }
        soundId = soundPool.load(file.absolutePath, 1)
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
        assetSha256 = assetFile?.takeIf { it.isFile }?.let(::sha256),
        ttsEngine = if (assetFile?.isFile == true) "bundled-sherpa-onnx-1.13.8" else null,
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
    }

    companion object {
        private const val MIN_ASSET_BYTES = 128L
    }
}
