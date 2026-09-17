package com.dial.van.voice

import java.io.Closeable
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Bounded in-memory audio evidence for one owner turn. It attaches as a sink to the existing
 * VoiceAudioArbiter and never opens another microphone. Audio is process-local and is discarded
 * when the turn closes; it is not persisted as owner memory.
 */
class VoiceTurnAudioCapture(
    private val arbiter: VoiceAudioArbiter,
    maxDurationMs: Int = DEFAULT_MAX_DURATION_MS,
) : Closeable {
    private val closed = AtomicBoolean(false)
    private val lock = Any()
    private val ring = PcmRingBuffer(
        capacityBytes = (
            arbiter.sampleRateHz * VoiceAudioArbiter.PCM_BYTES_PER_SAMPLE *
                maxDurationMs.coerceIn(MIN_DURATION_MS, MAX_DURATION_MS) / 1000
            ).coerceAtLeast(1),
    )
    private val sink: (ByteArray) -> Unit = { frame ->
        if (!closed.get()) synchronized(lock) { ring.append(frame) }
    }

    init {
        val preRoll = arbiter.registerSink(sink)
        if (preRoll.isNotEmpty()) synchronized(lock) { ring.append(preRoll) }
    }

    fun snapshot(): ByteArray = synchronized(lock) { ring.snapshot() }

    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        arbiter.unregisterSink(sink)
        synchronized(lock) { ring.clear() }
    }

    companion object {
        const val DEFAULT_MAX_DURATION_MS = 30_000
        private const val MIN_DURATION_MS = 2_000
        private const val MAX_DURATION_MS = 60_000
    }
}
