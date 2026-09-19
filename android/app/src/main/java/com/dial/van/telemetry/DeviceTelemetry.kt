package com.dial.van.telemetry

/**
 * The six measurements only the device can take, and the buffer that gets them to the
 * gateway.
 *
 * P3-OBS-002. The gateway's metric catalogue declares `van_wake_latency_ms`,
 * `van_asr_latency_ms`, `van_tts_latency_ms`, `van_aura_frame_time_ms`,
 * `van_device_battery_percent` and `van_device_memory_used_mb` with
 * `MetricSource.DEVICE`, and `POST /v1/observability/device-telemetry` has existed to
 * receive them since Gate 11. Nothing posted to it. The scrape reported them as
 * `van_metric_unobserved` — honestly, which was the point of that mechanism — but honest
 * silence is still silence: an owner whose aura is dropping frames or whose wake word takes
 * two seconds had no way for anyone to know.
 *
 * [DeviceMetric] is closed and its wire names mirror the gateway's `DEVICE_HISTOGRAMS` and
 * `DEVICE_GAUGES` exactly. That is not duplication for its own sake: the route refuses a
 * name it does not know, so a device that invents one is a device whose telemetry silently
 * disappears. `tests/contracts/test_device_telemetry_contract.py` parses this enum and the
 * gateway's catalogue and fails if they drift.
 *
 * Pure Kotlin, executed in `android/verification`.
 */
enum class DeviceMetric(val wire: String, val surfaced: Boolean = false) {
    /** "Hey Van" heard to VAN listening. */
    WAKE_LATENCY_MS("wake_latency_ms"),

    /** Speech ended to transcript in hand. */
    ASR_LATENCY_MS("asr_latency_ms"),

    /** Text handed to TTS to the first audible word. */
    TTS_LATENCY_MS("tts_latency_ms"),

    /** Per-frame cost of drawing VAN, labelled by which surface drew it. */
    AURA_FRAME_TIME_MS("aura_frame_time_ms", surfaced = true),

    BATTERY_PERCENT("battery_percent"),
    MEMORY_USED_MB("memory_used_mb"),
    ;

    companion object {
        fun forWire(wire: String): DeviceMetric? = entries.firstOrNull { it.wire == wire }
    }
}

data class DeviceSample(val metric: DeviceMetric, val value: Double, val surface: String? = null)

/**
 * A bounded buffer of samples waiting to be posted.
 *
 * Bounded, and it drops the *oldest* when full. Telemetry that grows without limit on a
 * phone that cannot reach its gateway is a memory leak dressed as observability, and the
 * newest frame times are the ones worth having.
 *
 * Not thread-safe by itself: the reporter owns the lock, because the frame callback and the
 * voice pipeline post from different threads and a synchronized method per sample would put
 * a monitor in the frame loop this metric exists to measure.
 */
class DeviceTelemetryBuffer(val capacity: Int = CAPACITY) {

    private val samples = ArrayDeque<DeviceSample>()
    private var dropped = 0L

    /** Samples discarded because the buffer was full, so the gap is reportable. */
    fun droppedCount(): Long = dropped

    fun size(): Int = samples.size

    fun add(sample: DeviceSample) {
        // A negative latency or a battery over 100 is a measurement bug, not a data point;
        // posting it would put a nonsense observation in a histogram nobody can clean.
        if (!sample.value.isFinite() || sample.value < 0.0) return
        if (samples.size >= capacity) {
            samples.removeFirst()
            dropped += 1
        }
        samples.addLast(sample)
    }

    /**
     * Take up to [BATCH] samples for one post.
     *
     * They leave the buffer: a post that fails has already lost them, and re-queueing on
     * failure is how a phone with no connectivity spends its battery retrying telemetry
     * instead of sending the owner's commands.
     */
    fun drain(limit: Int = BATCH): List<DeviceSample> {
        val take = minOf(limit, samples.size)
        return List(take) { samples.removeFirst() }
    }

    companion object {
        /** Roughly a minute of frame times plus everything else, then the oldest go. */
        const val CAPACITY = 512

        /** The gateway slices the body at 200; sending more would be silently truncated. */
        const val BATCH = 200
    }
}

object DeviceTelemetry {

    /**
     * The request body, as the route's `DeviceTelemetryBody` expects it.
     *
     * Built here rather than in the Android layer so the shape is executed rather than
     * assumed: `samples`, each with `name`, `value` and an optional `surface`.
     */
    fun body(samples: List<DeviceSample>): String {
        val rows = samples.joinToString(",") { sample ->
            val surface = sample.surface
                ?.takeIf { it.isNotBlank() && sample.metric.surfaced }
                ?.let { ",\"surface\":${quote(it)}" }
                .orEmpty()
            "{\"name\":${quote(sample.metric.wire)},\"value\":${number(sample.value)}$surface}"
        }
        return "{\"samples\":[$rows]}"
    }

    /** Milliseconds between two monotonic readings, or null when the pair is nonsense. */
    fun latencyMillis(startNanos: Long, endNanos: Long): Double? {
        val delta = endNanos - startNanos
        // Zero or negative means the clock went backwards or the start was never taken.
        // Reporting it as a zero-latency wake would make the histogram say VAN is instant.
        if (delta <= 0L) return null
        return delta / 1_000_000.0
    }

    private fun quote(text: String): String {
        val escaped = buildString {
            for (ch in text) {
                when (ch) {
                    '"' -> append("\\\"")
                    '\\' -> append("\\\\")
                    '\n' -> append("\\n")
                    '\r' -> append("\\r")
                    '\t' -> append("\\t")
                    else -> if (ch < ' ') append("\\u%04x".format(ch.code)) else append(ch)
                }
            }
        }
        return "\"$escaped\""
    }

    /** Finite decimals only: NaN and Infinity are not JSON and the route would reject them. */
    private fun number(value: Double): String =
        if (!value.isFinite()) "0" else String.format(java.util.Locale.ROOT, "%.3f", value)
}
