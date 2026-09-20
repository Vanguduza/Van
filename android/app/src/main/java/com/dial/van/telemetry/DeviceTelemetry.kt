package com.dial.van.telemetry

/**
 * The measurements only the device can take, and the buffer that gets them to the gateway.
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
 * Rev 1.5 §28.1 adds four more, all about the picture on the screen. Only the phone can
 * measure them: the Gateway is not in the media path by design (§6.4), and the Stream Host
 * can say what it sent but not what arrived. `browser_last_frame_age_ms` in particular is
 * the number behind a frozen picture — the failure an owner cannot describe any other way,
 * because from their side a stalled stream and a slow page look identical.
 *
 * [DeviceMetric] is closed and its wire names mirror the gateway's `DEVICE_HISTOGRAMS`,
 * `DEVICE_GAUGES` and `DEVICE_COUNTERS` exactly. That is not duplication for its own
 * sake: the route refuses a name it does not know, so a device that invents one is a
 * device whose telemetry silently disappears.
 * `tests/contracts/test_device_telemetry_contract.py` parses this enum and the gateway's
 * catalogue and fails if they drift.
 *
 * Pure Kotlin, executed in `android/verification`.
 */
enum class DeviceMetric(val wire: String, val dimension: String = "") {
    /** "Hey Van" heard to VAN listening. */
    WAKE_LATENCY_MS("wake_latency_ms"),

    /** Speech ended to transcript in hand. */
    ASR_LATENCY_MS("asr_latency_ms"),

    /** Text handed to TTS to the first audible word. */
    TTS_LATENCY_MS("tts_latency_ms"),

    /** Per-frame cost of drawing VAN, labelled by which surface drew it. */
    AURA_FRAME_TIME_MS("aura_frame_time_ms", dimension = "surface"),

    BATTERY_PERCENT("battery_percent"),
    MEMORY_USED_MB("memory_used_mb"),

    /** Frames per second the decoder is actually producing, not what was sent. */
    BROWSER_DECODE_FPS("browser_decode_fps"),

    /** How old the picture on screen is. A frozen stream is a large number here. */
    BROWSER_LAST_FRAME_AGE_MS("browser_last_frame_age_ms"),

    /** Accumulates, which is why the gateway holds it as a counter rather than a gauge. */
    BROWSER_FRAME_DROP_COUNT("browser_frame_drop_count"),

    /** Each transport recovery the owner did not have to ask for. */
    BROWSER_RECONNECT_COUNT("browser_reconnect_count"),

    /**
     * §20.16 — the gap the owner actually experienced during a path switch.
     *
     * Measured here because the Gateway cannot: it learns a path died when the resume
     * arrives, which is after the gap is over. What the Gateway counts is that a
     * failover happened and whether the route changed; how long it took is this.
     */
    SESSION_FAILOVER_MS("session_failover_ms"),

    /**
     * §20.15 — how much is waiting in store-and-forward, by what may be done with it.
     *
     * The queue is on the phone, so this is the only place it can be counted. Note what
     * that means for anyone reading the series: the deepest outbox is the one that has
     * not been reported, because a phone with no path cannot post telemetry either.
     */
    SESSION_OUTBOX_DEPTH("session_outbox_depth", dimension = "storability"),
    ;

    /** Whether this metric's dimension is the aura surface, which has its own wire field. */
    val surfaced: Boolean
        get() = dimension == "surface"

    companion object {
        fun forWire(wire: String): DeviceMetric? = entries.firstOrNull { it.wire == wire }
    }
}

/**
 * One measurement.
 *
 * `surface` and `dimension` are two slots for one idea, and the split is on the wire
 * rather than in taste: `surface` is the field shipped devices already post for the aura,
 * and folding it into a generic name here would have dropped the label from every phone
 * that had not been updated. A metric declaring any other dimension uses `dimension`.
 */
data class DeviceSample(
    val metric: DeviceMetric,
    val value: Double,
    val surface: String? = null,
    val dimension: String? = null,
)

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
            val dimension = sample.dimension
                ?.takeIf { it.isNotBlank() && sample.metric.dimension.isNotEmpty() && !sample.metric.surfaced }
                ?.let { ",\"dimension\":${quote(it)}" }
                .orEmpty()
            "{\"name\":${quote(sample.metric.wire)},\"value\":${number(sample.value)}" +
                "$surface$dimension}"
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
