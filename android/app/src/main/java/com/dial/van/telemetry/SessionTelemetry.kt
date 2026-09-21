package com.dial.van.telemetry

/**
 * Rev 1.5 §§20.15, 20.16 — the two session numbers only the phone can produce.
 *
 * The Gateway counts *that* a failover happened and whether the route changed, because a
 * resume is the moment it finds out. It cannot count how long the owner sat looking at a
 * frozen page, because by the time the resume arrives that is over; and it cannot count
 * the store-and-forward queue at all, because the queue is here.
 *
 * Held by the reporter rather than sampled from the session manager, for the same reason
 * [BrowserStreamTelemetry] is: the session may have gone away between one flush and the
 * next, and a reporter that asked a dead session for its depth would post zeros for a
 * queue that still has the owner's work in it.
 *
 * Pure Kotlin, executed in `android/verification`.
 */
class SessionTelemetry {

    private val failovers = mutableListOf<Double>()

    /** The last depth reported for each storability class, by its enum name. */
    private val depths = mutableMapOf<String, Int>()

    /**
     * Every class that has ever had a depth reported.
     *
     * Kept separately from [depths] because of the failure mode a gauge has and a counter
     * does not: the Gateway holds one value per label, and a class that goes from one to
     * zero and then stops being posted keeps reporting one — forever. An operator would
     * be told an owner is waiting to be asked about a command that was sent an hour ago.
     * So once a class has been seen, it is posted on every flush, including as a zero.
     */
    private val everSeen = mutableSetOf<String>()

    /**
     * §20.16 — one completed path switch, measured device-side.
     *
     * From the path being marked suspect to the new path carrying work. Not from the
     * resume request: the owner's interruption starts when the old path stopped working,
     * and a measurement that began at the request would report the healthy half.
     */
    fun onFailoverCompleted(millisecond: Long) {
        if (millisecond < 0) return
        failovers += millisecond.toDouble()
    }

    /**
     * §20.15 — the outbox, as it stands now.
     *
     * Takes the class names rather than the enum so this package does not depend on the
     * session package; the session manager holds the enum and knows its own names.
     */
    fun onOutboxDepth(byStorability: Map<String, Int>) {
        everSeen += byStorability.keys
        depths.clear()
        depths += byStorability
    }

    /**
     * Everything to post this flush.
     *
     * The durations are drained, because a histogram observation posted twice is two
     * failovers. The depths are not, because a gauge is a level and re-posting the same
     * level is what keeps it from going stale.
     */
    fun drain(): List<DeviceSample> {
        val samples = mutableListOf<DeviceSample>()
        for (millis in failovers) {
            samples += DeviceSample(DeviceMetric.SESSION_FAILOVER_MS, millis)
        }
        failovers.clear()
        for (name in everSeen.sorted()) {
            samples += DeviceSample(
                DeviceMetric.SESSION_OUTBOX_DEPTH,
                (depths[name] ?: 0).toDouble(),
                dimension = name,
            )
        }
        return samples
    }
}
