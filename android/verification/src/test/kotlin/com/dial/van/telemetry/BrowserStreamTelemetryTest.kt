package com.dial.van.telemetry

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Rev 1.5 §28.1 — the four measurements only the phone can take.
 *
 * All of the arithmetic, none of the WebRTC. The frame callback that drives this cannot
 * run here and never will; what can run is every way the arithmetic goes wrong, and the
 * ways it goes wrong all produce a number that looks plausible on a dashboard.
 */
class BrowserStreamTelemetryTest {

    @Test
    fun `a stream that has shown nothing has no frame age`() {
        // Null, not zero. Zero reads as "the picture is current", which is the single most
        // misleading thing this metric could say about a session showing a black rectangle.
        assertNull(BrowserStreamTelemetry().frameAgeMillis(1_000L))
    }

    @Test
    fun `frame age is how long ago the last frame arrived`() {
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        assertEquals(500.0, telemetry.frameAgeMillis(1_500L))
    }

    @Test
    fun `a frozen stream reports a large age rather than going quiet`() {
        // §7's failure. The owner sees a picture; nothing else on the phone or the gateway
        // can tell anyone it is four seconds old.
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        assertEquals(4_000.0, telemetry.frameAgeMillis(5_000L))
    }

    @Test
    fun `a closed stream stops claiming an age`() {
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        telemetry.onStreamClosed()
        assertNull(telemetry.frameAgeMillis(2_000L))
    }

    @Test
    fun `fps is emitted once a window has closed and not before`() {
        val telemetry = BrowserStreamTelemetry(windowMillis = 1_000L)
        telemetry.onFrame(0L)
        for (frame in 1..29) {
            assertNull(telemetry.onFrame(frame * 33L), "no reading before the window closes")
        }
        val fps = telemetry.onFrame(1_000L)
        assertNotNull(fps)
        assertTrue(fps in 29.0..31.0, "$fps")
    }

    @Test
    fun `a clock that went backwards restarts the window rather than stalling it`() {
        // The first version of this test asserted that the backwards frame emits nothing
        // and that the age is measured from it. Both are true with the guard *removed*,
        // so it proved nothing. What the guard actually decides is whether the fps window
        // is anchored to the old clock: without it, `windowStartedAtMillis` stays in the
        // future, every reading is suppressed until real time catches up, and the one that
        // finally arrives counts every frame since the step. The metric goes quiet for
        // four seconds and then reports a rate the decoder never achieved.
        val telemetry = BrowserStreamTelemetry(windowMillis = 1_000L)
        telemetry.onFrame(5_000L)

        assertNull(telemetry.onFrame(1_000L), "the step itself is not a reading")
        var emitted: Double? = null
        for (at in 1_100L..2_000L step 100L) {
            telemetry.onFrame(at)?.let { emitted = it }
        }

        assertNotNull(emitted, "a reading has to arrive on the new clock's own timeline")
        assertTrue(emitted!! in 5.0..20.0, "and it has to be a rate, not an accumulation: $emitted")
        // And the age is measured from the restart, not from the future reading.
        assertEquals(0.0, telemetry.frameAgeMillis(2_000L))
    }

    @Test
    fun `counters are deltas and drain to nothing`() {
        // The gateway's counters add what they are given. A running total would make every
        // flush re-add every earlier drop, and a session dropping nothing would still draw
        // a rising line.
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        telemetry.onFramesDropped(3)
        telemetry.onReconnect()

        val first = telemetry.drain(1_100L)
        assertEquals(3.0, first.single { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT }.value)
        assertEquals(1.0, first.single { it.metric == DeviceMetric.BROWSER_RECONNECT_COUNT }.value)

        val second = telemetry.drain(1_200L)
        assertTrue(second.none { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT }, "$second")
        assertTrue(second.none { it.metric == DeviceMetric.BROWSER_RECONNECT_COUNT }, "$second")
    }

    @Test
    fun `a drain before any frame reports nothing at all`() {
        // Not zeros. A gateway that received a zero fps and a zero frame age for a session
        // that never connected would show a stream that is running perfectly badly, rather
        // than one that is not running.
        assertEquals(emptyList(), BrowserStreamTelemetry().drain(1_000L))
    }

    @Test
    fun `a negative or non-finite fps never becomes a sample`() {
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        for (bad in listOf(-1.0, Double.NaN, Double.POSITIVE_INFINITY)) {
            val samples = telemetry.drain(1_100L, fps = bad)
            assertTrue(samples.none { it.metric == DeviceMetric.BROWSER_DECODE_FPS }, "$bad")
        }
    }

    @Test
    fun `dropping zero frames is not an event`() {
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        telemetry.onFramesDropped(0)
        val samples = telemetry.drain(1_100L)
        assertTrue(samples.none { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT }, "$samples")
    }

    @Test
    fun `a counter that went backwards does not erase drops that really happened`() {
        // The real reason `onFramesDropped` guards its argument, which the zero case above
        // does not reach: WebRTC's drop statistic is cumulative, so a caller differencing it
        // across a decoder restart hands this a negative number. Adding it subtracts drops
        // that happened, and a large enough negative takes the flush below zero and
        // reports nothing — the metric goes quiet exactly when the stream is at its worst.
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        telemetry.onFramesDropped(4)
        telemetry.onFramesDropped(-10)

        val samples = telemetry.drain(1_100L)
        val drops = samples.single { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT }
        assertEquals(4.0, drops.value)
    }

    @Test
    fun `the decoder's first total is not credited to the first flush`() {
        // WebRTC reports drops as a total since the decoder started. The first poll may
        // arrive a minute in, carrying every drop since then; adding it would put the
        // whole history into whichever minute the first flush happened to land in and
        // show a spike that never occurred.
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        telemetry.onDecoderFramesDropped(120)

        val samples = telemetry.drain(1_100L)
        assertTrue(samples.none { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT }, "$samples")
    }

    @Test
    fun `later totals are reported as the delta between them`() {
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        telemetry.onDecoderFramesDropped(120)
        telemetry.onDecoderFramesDropped(127)

        val drops = telemetry.drain(1_100L)
            .single { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT }
        assertEquals(7.0, drops.value)
    }

    @Test
    fun `a decoder restart does not subtract, and the readings after it are right`() {
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        telemetry.onDecoderFramesDropped(120)
        telemetry.onDecoderFramesDropped(127)
        // The decoder restarted: its total begins again from a small number.
        telemetry.onDecoderFramesDropped(2)
        telemetry.onDecoderFramesDropped(5)

        val drops = telemetry.drain(1_100L)
            .single { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT }
        // 7 from before the restart, 3 after it, and nothing subtracted in between.
        assertEquals(10.0, drops.value)
    }

    @Test
    fun `a new stream does not inherit the old decoder's baseline`() {
        // The old stream's decoder barely dropped anything; the new one has dropped a
        // lot by the time it is first polled. Without the reset, that first total is
        // differenced against the old baseline and the whole of it — 496 frames the new
        // decoder dropped before anyone looked — lands in the next flush as if it had
        // happened in that minute.
        //
        // The reverse case, a new total *below* the old baseline, is already absorbed by
        // the negative guard, which is why the first version of this test proved nothing:
        // it used a smaller total and passed with the reset removed.
        val telemetry = BrowserStreamTelemetry()
        telemetry.onFrame(1_000L)
        telemetry.onDecoderFramesDropped(4)
        telemetry.onStreamClosed()

        telemetry.onFrame(2_000L)
        telemetry.onDecoderFramesDropped(500)

        val samples = telemetry.drain(2_100L)
        assertTrue(
            samples.none { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT },
            "the new stream's first total is its own baseline, not a delta: $samples",
        )

        telemetry.onDecoderFramesDropped(505)
        val drops = telemetry.drain(2_200L)
            .single { it.metric == DeviceMetric.BROWSER_FRAME_DROP_COUNT }
        assertEquals(5.0, drops.value)
    }
}

class DecoderStatsTest {

    private fun inbound(kind: String, dropped: Any?) =
        "inbound-rtp" to mapOf<String, Any?>("kind" to kind, "framesDropped" to dropped)

    @Test
    fun `the video decoder's drops are read and the audio decoder's are not`() {
        // A report carries an `inbound-rtp` entry per media kind. Reading the first one
        // would report the audio decoder's drops as the picture's, and the picture is the
        // only one of the two the owner can see.
        val entries = listOf(inbound("audio", 900), inbound("video", 17))
        assertEquals(17L, DecoderStats.framesDropped(entries))
    }

    @Test
    fun `mediaType is accepted as well as kind`() {
        // Older report shapes spell it `mediaType`. Both appear in the wild and reading
        // only one means the metric is silent on whichever runtime uses the other.
        val entries = listOf<Pair<String, Map<String, Any?>>>(
            "inbound-rtp" to mapOf("mediaType" to "video", "framesDropped" to 3),
        )
        assertEquals(3L, DecoderStats.framesDropped(entries))
    }

    @Test
    fun `a counter handed back as a string is still a number`() {
        assertEquals(42L, DecoderStats.framesDropped(listOf(inbound("video", "42"))))
    }

    @Test
    fun `a report without the counter yields null rather than zero`() {
        // Null means "the decoder did not say". Zero means "it said none", and reporting
        // the second for the first would make a stream whose stats are unavailable look
        // like one that is dropping nothing.
        assertNull(DecoderStats.framesDropped(listOf(inbound("video", null))))
        assertNull(DecoderStats.framesDropped(emptyList()))
        assertNull(DecoderStats.framesDropped(listOf(inbound("audio", 5))))
        assertNull(DecoderStats.framesDropped(listOf(inbound("video", "not a number"))))
    }

    @Test
    fun `an outbound entry is not an inbound one`() {
        val entries = listOf<Pair<String, Map<String, Any?>>>(
            "outbound-rtp" to mapOf("kind" to "video", "framesDropped" to 99),
        )
        assertNull(DecoderStats.framesDropped(entries))
    }
}
