package com.dial.van.design.charts

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChartAxesTest {

    @Test
    fun `ticks of a flat series is the single value`() {
        assertEquals(listOf(42.0), ChartAxes.ticks(42.0, 42.0))
    }

    @Test
    fun `ticks span the requested range`() {
        val ticks = ChartAxes.ticks(0.0, 97.0, targetCount = 5)
        assertTrue(ticks.first() <= 0.0)
        assertTrue(ticks.last() >= 97.0)
    }

    @Test
    fun `timeTicks of an instant returns the single instant`() {
        assertEquals(listOf(1_000L), ChartAxes.timeTicks(1_000L, 1_000L))
    }

    @Test
    fun `timeLabel granularity depends on the overall span`() {
        val oneDayMs = 24L * 60 * 60 * 1000
        val epoch = 3_600_000L
        assertEquals(
            "01:00",
            ChartAxes.timeLabel(epoch, spanMs = oneDayMs, zone = java.time.ZoneOffset.UTC),
        )
    }
}
