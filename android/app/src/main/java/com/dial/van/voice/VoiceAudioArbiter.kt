package com.dial.van.voice

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.ParcelFileDescriptor
import androidx.core.content.ContextCompat
import java.io.Closeable
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingDeque
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.max

/**
 * The only AudioRecord owner inside VAN. Speech, wake and later speaker/KWS consumers
 * receive PCM from this arbiter rather than opening competing microphone captures.
 * System/telephony capture wins: [yieldToSystemCapture] releases the microphone.
 */
class VoiceAudioArbiter(
    private val context: Context,
    val sampleRateHz: Int = SAMPLE_RATE_HZ,
    preRollMs: Int = DEFAULT_PRE_ROLL_MS,
) : Closeable {
    private val lock = Any()
    private val captureExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "van-voice-capture").apply { isDaemon = true }
    }
    private val sinks = CopyOnWriteArraySet<(ByteArray) -> Unit>()
    private val ring = PcmRingBuffer(
        capacityBytes = ((sampleRateHz * PCM_BYTES_PER_SAMPLE * preRollMs) / 1000)
            .coerceIn(MIN_PRE_ROLL_BYTES, MAX_PRE_ROLL_BYTES),
    )

    @Volatile private var captureRunning = false
    @Volatile private var recorder: AudioRecord? = null
    @Volatile private var echoCanceler: AcousticEchoCanceler? = null
    @Volatile private var noiseSuppressor: NoiseSuppressor? = null

    fun hasRecordPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    fun start(): Boolean {
        synchronized(lock) {
            if (captureRunning && recorder != null) return true
            if (recorder != null || !hasRecordPermission()) return false

            val minBuffer = AudioRecord.getMinBufferSize(
                sampleRateHz,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
            )
            if (minBuffer <= 0) return false
            val record = AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                sampleRateHz,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                max(minBuffer * 2, FRAME_BYTES * 4),
            )
            if (record.state != AudioRecord.STATE_INITIALIZED) {
                record.release()
                return false
            }
            enableCaptureEffects(record)
            recorder = record
            captureRunning = true
            captureExecutor.execute { captureLoop(record) }
            return true
        }
    }

    private fun enableCaptureEffects(record: AudioRecord) {
        echoCanceler = if (AcousticEchoCanceler.isAvailable()) {
            runCatching { AcousticEchoCanceler.create(record.audioSessionId)?.apply { enabled = true } }.getOrNull()
        } else null
        noiseSuppressor = if (NoiseSuppressor.isAvailable()) {
            runCatching { NoiseSuppressor.create(record.audioSessionId)?.apply { enabled = true } }.getOrNull()
        } else null
    }

    private fun releaseCaptureEffects() {
        runCatching { echoCanceler?.release() }
        runCatching { noiseSuppressor?.release() }
        echoCanceler = null
        noiseSuppressor = null
    }

    private fun captureLoop(record: AudioRecord) {
        val buffer = ByteArray(FRAME_BYTES)
        try {
            record.startRecording()
            while (captureRunning && !Thread.currentThread().isInterrupted) {
                val read = record.read(buffer, 0, buffer.size, AudioRecord.READ_BLOCKING)
                if (read <= 0) continue
                val frame = buffer.copyOf(read)
                synchronized(lock) { ring.append(frame) }
                sinks.forEach { sink -> runCatching { sink(frame) } }
            }
        } catch (_: Throwable) {
            // Runtime state is surfaced by the consumer; the capture loop itself fails closed.
        } finally {
            runCatching { if (record.recordingState == AudioRecord.RECORDSTATE_RECORDING) record.stop() }
            releaseCaptureEffects()
            runCatching { record.release() }
            synchronized(lock) {
                if (recorder === record) recorder = null
                captureRunning = false
            }
        }
    }

    /** Release VAN microphone ownership before a system recognizer/telephony owner takes it. */
    fun yieldToSystemCapture() {
        stopCapture(clearPreRoll = false)
    }

    fun stopCapture(clearPreRoll: Boolean = false) {
        captureRunning = false
        runCatching { recorder?.stop() }
        if (clearPreRoll) synchronized(lock) { ring.clear() }
    }

    /**
     * Attach a non-blocking PCM pipe. Capture never writes to the pipe directly: frames enter a
     * bounded queue and a dedicated writer thread drains them, so a slow recognizer cannot block
     * wake/capture processing. The returned session includes the rolling pre-buffer first.
     */
    fun openRecognitionPipe(): VoiceAudioPipeSession {
        check(start()) { "voice_audio_capture_unavailable" }
        return VoiceAudioPipeSession(this)
    }

    internal fun registerSink(sink: (ByteArray) -> Unit): ByteArray = synchronized(lock) {
        sinks.add(sink)
        ring.snapshot()
    }

    internal fun unregisterSink(sink: (ByteArray) -> Unit) {
        sinks.remove(sink)
    }

    fun isCapturing(): Boolean = captureRunning
    fun echoCancellationActive(): Boolean = echoCanceler?.enabled == true
    fun noiseSuppressionActive(): Boolean = noiseSuppressor?.enabled == true

    override fun close() {
        sinks.clear()
        stopCapture(clearPreRoll = true)
        releaseCaptureEffects()
        captureExecutor.shutdownNow()
    }

    companion object {
        const val SAMPLE_RATE_HZ = 16_000
        const val PCM_BYTES_PER_SAMPLE = 2
        const val DEFAULT_PRE_ROLL_MS = 750
        const val FRAME_BYTES = 3_200 // ~100 ms at 16 kHz mono PCM16
        private const val MIN_PRE_ROLL_BYTES = 16_000 // 500 ms
        private const val MAX_PRE_ROLL_BYTES = 32_000 // 1 s
    }
}

class VoiceAudioPipeSession internal constructor(
    private val arbiter: VoiceAudioArbiter,
) : Closeable {
    private val pipe = ParcelFileDescriptor.createPipe()
    val readFd: ParcelFileDescriptor = pipe[0]
    private val writeFd: ParcelFileDescriptor = pipe[1]
    private val closed = AtomicBoolean(false)
    private val queue = LinkedBlockingDeque<ByteArray>(MAX_QUEUED_FRAMES)
    private val writer = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "van-stt-pcm-writer").apply { isDaemon = true }
    }

    private val sink: (ByteArray) -> Unit = { frame ->
        if (!closed.get()) {
            if (!queue.offerLast(frame)) {
                queue.pollFirst()
                queue.offerLast(frame)
            }
        }
    }

    init {
        val preRoll = arbiter.registerSink(sink)
        writer.execute {
            try {
                ParcelFileDescriptor.AutoCloseOutputStream(writeFd).use { out ->
                    if (preRoll.isNotEmpty()) out.write(preRoll)
                    while (!closed.get() && !Thread.currentThread().isInterrupted) {
                        val frame = queue.poll(100, TimeUnit.MILLISECONDS) ?: continue
                        out.write(frame)
                    }
                    out.flush()
                }
            } catch (_: Throwable) {
                // Closing a recognition session deliberately breaks the pipe.
            }
        }
    }

    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        arbiter.unregisterSink(sink)
        queue.clear()
        writer.shutdownNow()
        runCatching { writeFd.close() }
        runCatching { readFd.close() }
    }

    companion object {
        private const val MAX_QUEUED_FRAMES = 24
    }
}

/** Fixed-capacity byte ring used for the 0.5-1 s speech pre-roll. */
class PcmRingBuffer(capacityBytes: Int) {
    private val buffer = ByteArray(capacityBytes.coerceAtLeast(1))
    private var writeIndex = 0
    private var size = 0

    fun append(bytes: ByteArray) {
        bytes.forEach { byte ->
            buffer[writeIndex] = byte
            writeIndex = (writeIndex + 1) % buffer.size
            if (size < buffer.size) size++
        }
    }

    fun snapshot(): ByteArray {
        if (size == 0) return ByteArray(0)
        val result = ByteArray(size)
        val start = (writeIndex - size + buffer.size) % buffer.size
        for (i in 0 until size) result[i] = buffer[(start + i) % buffer.size]
        return result
    }

    fun clear() {
        writeIndex = 0
        size = 0
    }
}
