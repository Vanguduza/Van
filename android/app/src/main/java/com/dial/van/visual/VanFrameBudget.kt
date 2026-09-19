package com.dial.van.visual

/**
 * The producer `VanEffectConditions.frameBudgetMissed` never had.
 *
 * P2-PERF-001. The effect ladder already knew what to do about a device that cannot keep
 * up — drop to LOW, shed filaments, stop refraction — and `frameBudgetMissed` was the
 * signal meant to trigger it. Nothing ever set it. The overlay could miss every frame on a
 * cold device and the ladder would never notice, because the only inputs it actually
 * received were battery saver and thermal status, both of which are about the device's
 * *state* rather than about whether VAN is in fact rendering acceptably on it.
 *
 * Two properties this sampler has that a naive "was the last frame slow" check does not:
 *
 * **It needs sustained misses, not one.** A single long frame happens on every device for
 * reasons that have nothing to do with the aura — a GC, a layout pass, the system drawing
 * something else. Degrading the visuals on one slow frame would make VAN flicker between
 * effect budgets. [MISS_RATIO] of a rolling window has to miss before it reports.
 *
 * **It recovers.** A device that was thermally throttled and then cooled should get its
 * field back. The window rolls, so the signal clears once frames are meeting budget again,
 * with hysteresis so it does not oscillate at the boundary.
 */
class VanFrameBudgetSampler(
    /** 16.67 ms at 60Hz. Set from the display's real refresh rate where it is known. */
    val budgetMillis: Float = DEFAULT_BUDGET_MS,
    val windowSize: Int = DEFAULT_WINDOW,
) {
    private val durations = FloatArray(windowSize)
    private var count = 0
    private var cursor = 0
    private var missing = false

    /** Frames recorded since construction. */
    var frames: Long = 0L
        private set

    fun record(frameDurationMillis: Float) {
        if (frameDurationMillis < 0f) return
        durations[cursor] = frameDurationMillis
        cursor = (cursor + 1) % windowSize
        if (count < windowSize) count += 1
        frames += 1L
        missing = evaluate()
    }

    /** Convenience for a `withFrameNanos` driver that has two timestamps. */
    fun recordNanos(previousNanos: Long, frameNanos: Long) {
        val delta = frameNanos - previousNanos
        if (delta <= 0L) return
        // A pause (screen off, backgrounded) is not a missed frame. Counting it would
        // degrade the field of a device that was doing nothing wrong.
        if (delta > VanAnimationClock.MAX_FRAME_DELTA_NANOS) return
        record(delta / 1_000_000f)
    }

    /** The value to feed `VanEffectConditions.frameBudgetMissed`. */
    fun budgetMissed(): Boolean = missing

    /** Fraction of the window that missed. Reported so the signal is inspectable. */
    fun missRatio(): Float {
        if (count == 0) return 0f
        var missed = 0
        for (index in 0 until count) if (durations[index] > budgetMillis) missed += 1
        return missed.toFloat() / count.toFloat()
    }

    fun p95Millis(): Float {
        if (count == 0) return 0f
        val sorted = durations.copyOf(count).sortedArray()
        val index = ((sorted.size - 1) * 0.95f).toInt()
        return sorted[index]
    }

    fun reset() {
        count = 0
        cursor = 0
        missing = false
    }

    private fun evaluate(): Boolean {
        // Do not judge a device before there is a window to judge it on.
        if (count < windowSize) return missing
        val ratio = missRatio()
        // Hysteresis: it takes MISS_RATIO to start reporting and RECOVER_RATIO to stop,
        // so a device sitting exactly on the threshold does not flip every frame.
        return if (missing) ratio > RECOVER_RATIO else ratio >= MISS_RATIO
    }

    companion object {
        const val DEFAULT_BUDGET_MS = 16.67f
        const val DEFAULT_WINDOW = 60
        const val MISS_RATIO = 0.20f
        const val RECOVER_RATIO = 0.08f
    }
}
