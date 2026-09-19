package com.dial.van.telemetry

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P3-OBS-002 — the six device-sourced metrics had a catalogue entry, an ingest route, and no
 * producer. The scrape reported them as unobserved, which was honest and still meant nobody
 * could see an owner whose aura was dropping frames.
 */
class DeviceTelemetryTest {

    @Test
    fun `the buffer is bounded and drops the oldest`() {
        // Telemetry that grows without limit on a phone that cannot reach its gateway is a
        // memory leak dressed as observability, and the newest frame times are the useful
        // ones.
        val buffer = DeviceTelemetryBuffer(capacity = 4)
        repeat(10) { buffer.add(DeviceSample(DeviceMetric.AURA_FRAME_TIME_MS, it.toDouble(), "overlay")) }
        assertEquals(4, buffer.size())
        assertEquals(6L, buffer.droppedCount())
        assertEquals(listOf(6.0, 7.0, 8.0, 9.0), buffer.drain().map { it.value })
    }

    @Test
    fun `a nonsense measurement is never buffered`() {
        // A negative latency is a measurement bug. Posting it puts an observation in a
        // histogram that nobody can take back out.
        val buffer = DeviceTelemetryBuffer()
        for (bad in listOf(-1.0, Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)) {
            buffer.add(DeviceSample(DeviceMetric.WAKE_LATENCY_MS, bad))
        }
        assertEquals(0, buffer.size())
        buffer.add(DeviceSample(DeviceMetric.WAKE_LATENCY_MS, 0.0))
        assertEquals(1, buffer.size())
    }

    @Test
    fun `a batch never exceeds what the route will read`() {
        // The gateway slices the body at 200. Sending more is not an error the device sees;
        // it is telemetry silently thrown away.
        val buffer = DeviceTelemetryBuffer(capacity = 1_000)
        repeat(1_000) { buffer.add(DeviceSample(DeviceMetric.ASR_LATENCY_MS, 1.0)) }
        assertEquals(DeviceTelemetryBuffer.BATCH, buffer.drain().size)
        assertTrue(DeviceTelemetryBuffer.BATCH <= 200)
    }

    @Test
    fun `draining removes what it takes`() {
        // A post that fails has already lost these. Re-queueing them is how a phone with no
        // connectivity spends its battery retrying telemetry instead of sending commands.
        val buffer = DeviceTelemetryBuffer()
        repeat(5) { buffer.add(DeviceSample(DeviceMetric.TTS_LATENCY_MS, 2.0)) }
        assertEquals(3, buffer.drain(limit = 3).size)
        assertEquals(2, buffer.size())
    }

    @Test
    fun `the body is the shape the route parses`() {
        val body = DeviceTelemetry.body(
            listOf(
                DeviceSample(DeviceMetric.AURA_FRAME_TIME_MS, 16.667, "overlay"),
                DeviceSample(DeviceMetric.BATTERY_PERCENT, 73.0),
            ),
        )
        assertEquals(
            """{"samples":[{"name":"aura_frame_time_ms","value":16.667,"surface":"overlay"},""" +
                """{"name":"battery_percent","value":73.000}]}""",
            body,
        )
    }

    @Test
    fun `an empty batch still produces valid JSON`() {
        assertEquals("""{"samples":[]}""", DeviceTelemetry.body(emptyList()))
    }

    @Test
    fun `only the labelled metric carries a surface`() {
        // The gateway's catalogue declares `surface` on the frame-time histogram alone, and
        // an undeclared label is a refused sample.
        val body = DeviceTelemetry.body(
            listOf(DeviceSample(DeviceMetric.WAKE_LATENCY_MS, 120.0, surface = "overlay")),
        )
        assertFalse(body.contains("surface"), body)
        assertTrue(DeviceMetric.AURA_FRAME_TIME_MS.surfaced)
        assertEquals(
            listOf(DeviceMetric.AURA_FRAME_TIME_MS),
            DeviceMetric.entries.filter { it.surfaced },
        )
    }

    @Test
    fun `a surface name cannot break out of the body`() {
        val body = DeviceTelemetry.body(
            listOf(DeviceSample(DeviceMetric.AURA_FRAME_TIME_MS, 9.0, "over\"lay\n")),
        )
        assertTrue(body.contains("""over\"lay\n"""), body)
        assertEquals(2, body.count { it == '[' } + body.count { it == ']' })
    }

    @Test
    fun `a non-finite value never reaches the wire`() {
        val body = DeviceTelemetry.body(listOf(DeviceSample(DeviceMetric.MEMORY_USED_MB, 1.0)))
        assertFalse(body.contains("NaN"))
        assertFalse(body.contains("Infinity"))
    }

    @Test
    fun `a latency needs two readings that make sense`() {
        assertEquals(1.5, DeviceTelemetry.latencyMillis(0L, 1_500_000L)!!, 1e-9)
        // Zero would report VAN as instant, which is the one answer a latency histogram
        // must never invent.
        assertNull(DeviceTelemetry.latencyMillis(10L, 10L))
        assertNull(DeviceTelemetry.latencyMillis(100L, 10L))
    }

    @Test
    fun `every wire name round-trips and none collide`() {
        val wires = DeviceMetric.entries.map { it.wire }
        assertEquals(wires.size, wires.toSet().size, "$wires")
        for (metric in DeviceMetric.entries) {
            assertEquals(metric, DeviceMetric.forWire(metric.wire))
            assertFalse(metric.wire.startsWith("van_"), "${metric.wire} is the gateway's name, not the wire name")
        }
        assertNull(DeviceMetric.forWire("something_nobody_declared"))
    }
}
