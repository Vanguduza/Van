package com.dial.van.telemetry

/**
 * Rev 1.5 §28.1 — the four browser measurements only the phone can take.
 *
 * The Gateway is deliberately not in the media path (§6.4), and the Stream Host can say
 * what it *sent*. Neither can say what arrived, and what arrived is the whole of the
 * owner's experience. `browser_last_frame_age_ms` is the sharp one: from the owner's side
 * a stalled stream and a slow page look identical, and this is the only number that tells
 * them apart.
 *
 * Pure, so it runs in `android/verification`. The WebRTC frame callback that feeds it
 * cannot, which is exactly why the arithmetic is separated out of it: everything that can
 * be wrong here — a window anchored in the future after a clock step, a cumulative drop
 * counter differenced across a decoder restart, a cursor that reports a current picture
 * for a stream that has shown none — is wrong in a way a test can see.
 */
class BrowserStreamTelemetry(
    /** How long a window of frames is averaged over before an fps reading is emitted. */
    private val windowMillis: Long = 1_000L,
) {

    /**
     * Whether any frame has arrived, held separately from the timestamp.
     *
     * A first version used `lastFrameAtMillis == 0L` as the sentinel, which is wrong for
     * the ordinary reason: zero is a legal timestamp. On a monotonic clock that starts
     * near zero every frame looked like the first one, so the fps window restarted on
     * every frame and no reading was ever emitted — a metric that is silent rather than
     * wrong, which is the harder kind to notice.
     */
    private var seenAFrame: Boolean = false

    private var windowStartedAtMillis: Long = 0L
    private var framesInWindow: Int = 0
    private var lastFrameAtMillis: Long = 0L
    private var pendingDrops: Long = 0L
    private var pendingReconnects: Long = 0L

    /** The decoder's own cumulative drop count at the last poll. -1 before the first. */
    private var lastCumulativeDrops: Long = -1L

    /** One decoded frame arrived. Returns an fps reading when a window has closed. */
    fun onFrame(atMillis: Long): Double? {
        if (!seenAFrame || atMillis < lastFrameAtMillis) {
            // First frame, or a clock that moved backwards. Restarting the window is the
            // point rather than suppressing one reading: left anchored to the old clock,
            // `windowStartedAtMillis` sits in the future, every reading is suppressed
            // until real time catches up, and the one that finally arrives counts every
            // frame since the step as if they had all landed in the last second.
            seenAFrame = true
            windowStartedAtMillis = atMillis
            framesInWindow = 1
            lastFrameAtMillis = atMillis
            return null
        }
        lastFrameAtMillis = atMillis
        framesInWindow += 1
        val elapsed = atMillis - windowStartedAtMillis
        if (elapsed < windowMillis) return null
        windowStartedAtMillis = atMillis
        val frames = framesInWindow
        framesInWindow = 0
        return frames * 1_000.0 / elapsed
    }

    /**
     * How old the picture is, or null before any frame has been drawn.
     *
     * Null rather than zero. Zero would mean "the frame is current", and reporting that
     * for a session that has never shown one is the single most misleading value this
     * metric could carry.
     */
    fun frameAgeMillis(nowMillis: Long): Double? {
        if (!seenAFrame) return null
        return maxOf(0L, nowMillis - lastFrameAtMillis).toDouble()
    }

    /**
     * Frames the decoder reported it could not render.
     *
     * A non-positive count is discarded rather than added. WebRTC's drop statistic is a
     * cumulative counter, and a caller computing a delta across a decoder restart gets a
     * negative number: adding it would subtract drops that really happened, and a
     * sufficiently negative one takes the whole flush below zero so nothing is reported
     * at all. The metric would go quiet exactly when the stream was at its worst.
     */
    fun onFramesDropped(count: Long) {
        if (count > 0) pendingDrops += count
    }

    /**
     * WebRTC reports `framesDropped` as a total since the decoder started. This turns it
     * into the delta the Gateway's counter wants.
     *
     * The first poll contributes nothing: its total covers everything since the stream
     * began, and adding it would credit the whole history to whichever minute the first
     * flush happened to land in. A total that went *down* is a decoder restart, and the
     * negative delta it produces is discarded by `onFramesDropped` rather than subtracting
     * drops that really happened — the baseline moves to the new total, so the readings
     * after it are right again.
     */
    fun onDecoderFramesDropped(cumulative: Long) {
        if (cumulative < 0) return
        val delta = if (lastCumulativeDrops < 0) 0L else cumulative - lastCumulativeDrops
        lastCumulativeDrops = cumulative
        onFramesDropped(delta)
    }

    /** One transport recovery the owner did not have to ask for. */
    fun onReconnect() {
        pendingReconnects += 1
    }

    /**
     * Everything accumulated since the last call, as samples, and reset.
     *
     * Counters are drained rather than reported cumulatively because the Gateway's
     * counters add what they are given: posting a running total would make every flush
     * re-count every earlier drop, and the chart would curve upwards on a session that
     * was dropping nothing.
     */
    fun drain(nowMillis: Long, fps: Double? = null): List<DeviceSample> {
        val samples = mutableListOf<DeviceSample>()
        if (fps != null && fps.isFinite() && fps >= 0.0) {
            samples += DeviceSample(DeviceMetric.BROWSER_DECODE_FPS, fps)
        }
        frameAgeMillis(nowMillis)?.let {
            samples += DeviceSample(DeviceMetric.BROWSER_LAST_FRAME_AGE_MS, it)
        }
        if (pendingDrops > 0) {
            samples += DeviceSample(DeviceMetric.BROWSER_FRAME_DROP_COUNT, pendingDrops.toDouble())
            pendingDrops = 0
        }
        if (pendingReconnects > 0) {
            samples += DeviceSample(
                DeviceMetric.BROWSER_RECONNECT_COUNT, pendingReconnects.toDouble(),
            )
            pendingReconnects = 0
        }
        return samples
    }

    /** A new session, or a reattached one. The picture is gone, so its age is not a number. */
    fun onStreamClosed() {
        seenAFrame = false
        // The next stream's decoder starts its own count from zero, so the old baseline
        // would make its first poll look like a large negative and then be discarded.
        lastCumulativeDrops = -1L
        lastFrameAtMillis = 0L
        windowStartedAtMillis = 0L
        framesInWindow = 0
    }
}

/**
 * Pulling one number out of a WebRTC stats report, expressed over plain maps so it runs
 * in the harness.
 *
 * `RTCStatsReport` is a WebRTC type and this repository has no WebRTC runtime, so the
 * client converts the report into `(type, members)` pairs and this decides what to read.
 * The deciding is the part worth testing: a report contains several `inbound-rtp` entries
 * — audio and video — and reading the wrong one reports the audio decoder's drops as the
 * picture's.
 */
object DecoderStats {

    /** The video decoder's cumulative dropped-frame count, or null if it is not there. */
    fun framesDropped(entries: List<Pair<String, Map<String, Any?>>>): Long? {
        for ((type, members) in entries) {
            if (type != "inbound-rtp") continue
            if (members["kind"] != "video" && members["mediaType"] != "video") continue
            val value = members["framesDropped"] ?: continue
            return when (value) {
                is Number -> value.toLong()
                // WebRTC's Java bindings hand some counters back as strings.
                is String -> value.toLongOrNull()
                else -> null
            }
        }
        return null
    }
}
