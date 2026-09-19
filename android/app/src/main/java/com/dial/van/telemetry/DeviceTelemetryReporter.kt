package com.dial.van.telemetry

import com.dial.van.runtime.DeviceRuntimeReadings
import com.dial.van.runtime.VanResourceEnvelope
import com.dial.van.runtime.VanSubsystem
import android.content.Context
import android.os.BatteryManager
import android.os.Debug
import com.dial.van.gateway.VanGatewayClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * The producer for the six device-sourced metrics (P3-OBS-002).
 *
 * The gateway declared them, the ingest route existed, and nothing on the phone had ever
 * posted to it. This is that nothing, filled in.
 *
 * Deliberately cheap. Frame times arrive on the frame callback of the surface this metric
 * measures, so [recordFrame] does one bounds check and one array write behind a lock that
 * is never contended for long — anything heavier and the telemetry becomes the jank.
 * Battery and memory are sampled once per flush rather than continuously, because reading
 * them is a binder call and a poll of either is a poll that shows up in the other.
 *
 * It honours the gateway's circuit breaker: a phone that cannot reach its gateway should
 * spend its radio on the owner's queued commands, not on frame times.
 */
class DeviceTelemetryReporter(
    private val context: Context,
    private val gateway: VanGatewayClient,
    private val scope: CoroutineScope,
    private val buffer: DeviceTelemetryBuffer = DeviceTelemetryBuffer(),
) {
    private val lock = Any()

    fun recordFrame(surface: String, frameMillis: Float) {
        add(DeviceSample(DeviceMetric.AURA_FRAME_TIME_MS, frameMillis.toDouble(), surface))
    }

    fun recordWake(startNanos: Long, endNanos: Long) =
        addLatency(DeviceMetric.WAKE_LATENCY_MS, startNanos, endNanos)

    fun recordAsr(startNanos: Long, endNanos: Long) =
        addLatency(DeviceMetric.ASR_LATENCY_MS, startNanos, endNanos)

    fun recordTts(startNanos: Long, endNanos: Long) =
        addLatency(DeviceMetric.TTS_LATENCY_MS, startNanos, endNanos)

    private fun addLatency(metric: DeviceMetric, startNanos: Long, endNanos: Long) {
        val millis = DeviceTelemetry.latencyMillis(startNanos, endNanos) ?: return
        add(DeviceSample(metric, millis))
    }

    private fun add(sample: DeviceSample) {
        synchronized(lock) { buffer.add(sample) }
    }

    /**
     * The flush loop, paced by the whole-runtime envelope.
     *
     * P3-PERF-003 — this used to be a fixed minute whatever the phone was doing. Telemetry
     * is VAN watching itself: useful, and the first thing an owner would trade for battery,
     * which is why it is the subsystem that stops earliest. The interval is re-read every
     * iteration rather than captured once, so a device that cools down speeds back up
     * without waiting for a restart.
     */
    fun start() {
        scope.launch(Dispatchers.IO) {
            while (isActive) {
                val allowance = VanResourceEnvelope.allowance(
                    VanSubsystem.TELEMETRY,
                    DeviceRuntimeReadings.pressure(context),
                )
                if (!allowance.running) {
                    // Not a stop: the loop keeps checking, because the phone will recover and
                    // a reporter that exits here would stay silent until the app restarted.
                    // Buffered samples survive; DeviceTelemetryBuffer drops the oldest when
                    // full, so a long constrained spell costs the stalest frame times rather
                    // than unbounded memory.
                    delay(STOPPED_RECHECK_MS)
                    continue
                }
                delay((FLUSH_INTERVAL_MS * allowance.cadenceScale).toLong())
                runCatching { flush() }
            }
        }
    }

    suspend fun flush(): Int {
        if (!gateway.isPaired()) return 0
        // The breaker is advisory and this is the caller it is for: background telemetry is
        // exactly the traffic that should stand down while the gateway is unreachable.
        if (!gateway.backgroundCallsAdvisable()) return 0
        sampleDeviceIndicators()
        val batch = synchronized(lock) { buffer.drain() }
        if (batch.isEmpty()) return 0
        gateway.postDeviceTelemetry(DeviceTelemetry.body(batch))
        return batch.size
    }

    private fun sampleDeviceIndicators() {
        val battery = runCatching {
            val manager = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
            manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        }.getOrNull()
        // -1 is BatteryManager's "I do not know", and reporting it as a battery level is
        // how a dashboard ends up showing a phone at minus one percent.
        if (battery != null && battery in 0..100) {
            add(DeviceSample(DeviceMetric.BATTERY_PERCENT, battery.toDouble()))
        }
        val memoryMb = runCatching {
            Debug.MemoryInfo().also(Debug::getMemoryInfo).totalPss / 1024.0
        }.getOrNull()
        if (memoryMb != null && memoryMb > 0.0) {
            add(DeviceSample(DeviceMetric.MEMORY_USED_MB, memoryMb))
        }
    }

    private companion object {
        /** Often enough to see a bad minute, rare enough not to be one. */
        const val FLUSH_INTERVAL_MS = 60_000L

        /** How often to ask whether the device has recovered while telemetry is stood down. */
        const val STOPPED_RECHECK_MS = 120_000L
    }
}
