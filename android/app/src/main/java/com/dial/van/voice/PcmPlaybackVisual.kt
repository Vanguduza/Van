package com.dial.van.voice

import kotlin.math.sqrt

/** Measured amplitude of PCM already played; not phoneme recognition or submitted-buffer time. */
data class PcmPlaybackVisual(val rms: Float = 0f, val mouthOpen: Float = 0f, val viseme: Int = 0)

class PcmPlaybackVisualClock {
    private var previousHead = -1L
    private var progressedAt = 0L

    fun sample(samples: FloatArray, sampleRate: Int, playedFrames: Long, submittedFrames: Int, nowMs: Long): PcmPlaybackVisual {
        if (sampleRate !in 8_000..192_000 || playedFrames < 0 || submittedFrames < 0 || nowMs < 0) return PcmPlaybackVisual()
        if (playedFrames < previousHead || nowMs < progressedAt) {
            previousHead = playedFrames; progressedAt = nowMs; return PcmPlaybackVisual()
        }
        if (playedFrames != previousHead) { previousHead = playedFrames; progressedAt = nowMs }
        else if (nowMs - progressedAt > 120L) return PcmPlaybackVisual()
        val end = minOf(playedFrames, samples.size.toLong(), submittedFrames.toLong()).toInt()
        if (end <= 0) return PcmPlaybackVisual()
        val start = (end - sampleRate / 50).coerceAtLeast(0)
        var energy = 0.0
        for (i in start until end) {
            val value = if (samples[i].isFinite()) samples[i].coerceIn(-1f, 1f).toDouble() else 0.0
            energy += value * value
        }
        val rms = sqrt(energy / (end - start)).toFloat()
        val opening = (rms * 5.5f).coerceIn(0f, 1f)
        // No cycling through imaginary phonemes. Shape1 is the canonical generic
        // open mouth; cue/word-timed engines retain their separate five-shape path.
        return PcmPlaybackVisual(rms, opening, if (opening > .02f) 1 else 0)
    }
}
