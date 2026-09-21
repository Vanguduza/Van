package com.dial.van.telemetry

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Rev 1.5 §§20.15, 20.16 — the two session numbers the phone produces.
 *
 * The test that matters here is the gauge one, and it is about a failure nobody sees in a
 * diff: a Prometheus gauge holds its last value per label set. A reporter that posts only
 * the non-empty storability classes leaves the last non-zero value standing forever, so an
 * operator is told an owner is waiting to be asked about a command that was sent an hour
 * ago. It reads as a stuck queue, on a phone whose queue is empty.
 */
class SessionTelemetryTest {

    private fun depthOf(samples: List<DeviceSample>, name: String): Double? =
        samples.firstOrNull {
            it.metric == DeviceMetric.SESSION_OUTBOX_DEPTH && it.dimension == name
        }?.value

    @Test
    fun `a class that empties is posted as a zero rather than left behind`() {
        val telemetry = SessionTelemetry()
        telemetry.onOutboxDepth(mapOf("REQUIRE_RECONFIRM_ON_RECONNECT" to 1))
        assertEquals(1.0, depthOf(telemetry.drain(), "REQUIRE_RECONFIRM_ON_RECONNECT"))

        // The owner answered and it went. The class is absent from the new reading.
        telemetry.onOutboxDepth(mapOf("SAFE_TO_RETRY" to 2))
        val second = telemetry.drain()
        assertEquals(0.0, depthOf(second, "REQUIRE_RECONFIRM_ON_RECONNECT"))
        assertEquals(2.0, depthOf(second, "SAFE_TO_RETRY"))
    }

    @Test
    fun `a class nobody has ever reported is not invented`() {
        val telemetry = SessionTelemetry()
        telemetry.onOutboxDepth(mapOf("SAFE_TO_RETRY" to 1))
        val names = telemetry.drain()
            .filter { it.metric == DeviceMetric.SESSION_OUTBOX_DEPTH }
            .map { it.dimension }
        assertEquals(listOf("SAFE_TO_RETRY"), names)
    }

    @Test
    fun `nothing is posted before an outbox has ever been seen`() {
        assertTrue(SessionTelemetry().drain().isEmpty())
    }

    @Test
    fun `the depth is re-posted on every flush so the gauge does not go stale`() {
        val telemetry = SessionTelemetry()
        telemetry.onOutboxDepth(mapOf("STORE_UNTIL_TTL" to 3))
        assertEquals(3.0, depthOf(telemetry.drain(), "STORE_UNTIL_TTL"))
        // No new reading in between. The level has not changed, and a gauge that stopped
        // being posted would be indistinguishable from a phone that stopped reporting.
        assertEquals(3.0, depthOf(telemetry.drain(), "STORE_UNTIL_TTL"))
    }

    @Test
    fun `a failover duration is reported once and not again`() {
        val telemetry = SessionTelemetry()
        telemetry.onFailoverCompleted(1_200)
        val first = telemetry.drain().filter { it.metric == DeviceMetric.SESSION_FAILOVER_MS }
        assertEquals(listOf(1_200.0), first.map { it.value })
        // A histogram observation posted twice is two failovers.
        assertTrue(
            telemetry.drain().none { it.metric == DeviceMetric.SESSION_FAILOVER_MS },
        )
    }

    @Test
    fun `two failovers in one flush are two observations`() {
        val telemetry = SessionTelemetry()
        telemetry.onFailoverCompleted(400)
        telemetry.onFailoverCompleted(900)
        val values = telemetry.drain()
            .filter { it.metric == DeviceMetric.SESSION_FAILOVER_MS }
            .map { it.value }
        assertEquals(listOf(400.0, 900.0), values)
    }

    @Test
    fun `a negative duration is dropped rather than observed`() {
        // A monotonic clock cannot go backwards, but the caller passes a computed
        // difference and a zeroed start would produce a large negative. A negative sample
        // in a latency histogram silently drags the percentile everyone reads.
        val telemetry = SessionTelemetry()
        telemetry.onFailoverCompleted(-1)
        assertTrue(telemetry.drain().isEmpty())
    }

    @Test
    fun `the outbox depth carries its label in the dimension field not the surface`() {
        // The ingest resolves `surface` only for the aura. A depth posted in the surface
        // field would be refused by the route with nothing on either side saying why.
        val telemetry = SessionTelemetry()
        telemetry.onOutboxDepth(mapOf("SAFE_TO_RETRY" to 1))
        val sample = telemetry.drain().first()
        assertEquals(null, sample.surface)
        assertEquals("SAFE_TO_RETRY", sample.dimension)
        assertTrue(DeviceTelemetry.body(listOf(sample)).contains("\"dimension\":\"SAFE_TO_RETRY\""))
    }
}
