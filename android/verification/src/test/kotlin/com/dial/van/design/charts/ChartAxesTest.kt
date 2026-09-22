package com.dial.van.design.charts

import java.time.ZoneOffset
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ChartAxesTest {

    // ---- niceNumber / ticks ---------------------------------------------------------------

    @Test
    fun `niceNumber rounds to 1-2-5 times a power of ten`() {
        assertEquals(20.0, ChartAxes.niceNumber(18.0, round = true))
        assertEquals(50.0, ChartAxes.niceNumber(43.0, round = true))
        assertEquals(100.0, ChartAxes.niceNumber(97.0, round = true))
        assertEquals(200.0, ChartAxes.niceNumber(150.0, round = true))
    }

    @Test
    fun `niceNumber non-round mode always rounds up, never clipping the range`() {
        assertEquals(100.0, ChartAxes.niceNumber(97.0, round = false))
        assertEquals(2.0, ChartAxes.niceNumber(1.2, round = false))
    }

    @Test
    fun `ticks of a flat series is the single value`() {
        assertEquals(listOf(42.0), ChartAxes.ticks(42.0, 42.0))
    }

    @Test
    fun `ticks span the requested range with nice values`() {
        val ticks = ChartAxes.ticks(0.0, 97.0, targetCount = 5)
        assertTrue(ticks.first() <= 0.0)
        assertTrue(ticks.last() >= 97.0)
        // Every step between consecutive ticks is the same nice step.
        val steps = ticks.zipWithNext { a, b -> b - a }.map { (it * 1000).let(Math::round) / 1000.0 }
        assertEquals(1, steps.toSet().size, "ticks were not evenly spaced: $ticks")
    }

    @Test
    fun `ticks never produces an unreadable fractional step for a round number range`() {
        val ticks = ChartAxes.ticks(0.0, 100.0, targetCount = 5)
        // 100 / 4 = 25, which niceNumber should round to a clean step (20 or 25-adjacent nice
        // value), not something like 24.999999997 from float drift.
        val step = ticks[1] - ticks[0]
        val roundedStep = (step * 1_000_000).let(Math::round) / 1_000_000.0
        assertEquals(step, roundedStep, "step carried floating point noise: $step")
    }

    @Test
    fun `ticks rejects a target count below 2`() {
        var threw = false
        try {
            ChartAxes.ticks(0.0, 10.0, targetCount = 1)
        } catch (_: IllegalArgumentException) {
            threw = true
        }
        assertTrue(threw, "targetCount below 2 should be rejected")
    }

    @Test
    fun `ticks handles a reversed min and max`() {
        val ticks = ChartAxes.ticks(100.0, 0.0, targetCount = 5)
        assertTrue(ticks.first() <= 0.0)
        assertTrue(ticks.last() >= 100.0)
    }

    @Test
    fun `valueLabel decimal precision follows the step`() {
        assertEquals("20", ChartAxes.valueLabel(20.0, step = 10.0))
        assertEquals("1.5", ChartAxes.valueLabel(1.5, step = 0.5))
        assertEquals("1.25", ChartAxes.valueLabel(1.25, step = 0.05))
    }

    // ---- time ticks -------------------------------------------------------------------

    @Test
    fun `timeTicks of an instant returns the single instant`() {
        assertEquals(listOf(1_000L), ChartAxes.timeTicks(1_000L, 1_000L))
    }

    @Test
    fun `timeTicks stay within the requested span`() {
        val min = 0L
        val max = 6L * 60 * 60 * 1000 // 6 hours
        val ticks = ChartAxes.timeTicks(min, max, targetCount = 5)
        assertTrue(ticks.all { it in min..max })
        assertTrue(ticks.size >= 2)
        assertTrue(ticks == ticks.sorted())
    }

    @Test
    fun `timeTicks snap to human boundaries for an hour-scale span`() {
        val min = 0L
        val max = 6L * 60 * 60 * 1000
        val ticks = ChartAxes.timeTicks(min, max, targetCount = 6)
        val stepMs = ticks[1] - ticks[0]
        // Snapped to one of the ladder's hour-scale steps, not an arbitrary division.
        assertTrue(stepMs % (60 * 1000) == 0L, "step $stepMs is not a whole number of minutes")
    }

    @Test
    fun `timeLabel granularity depends on the overall span, not the individual tick`() {
        val oneDayMs = 24L * 60 * 60 * 1000
        val epoch = 3_600_000L // 1970-01-01T01:00:00Z
        val shortSpanLabel = ChartAxes.timeLabel(epoch, spanMs = oneDayMs, zone = ZoneOffset.UTC)
        val longSpanLabel = ChartAxes.timeLabel(epoch, spanMs = 400L * oneDayMs, zone = ZoneOffset.UTC)
        assertEquals("01:00", shortSpanLabel)
        assertTrue(longSpanLabel.contains("1970"))
    }
}
