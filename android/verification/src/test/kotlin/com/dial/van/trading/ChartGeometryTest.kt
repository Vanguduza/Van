package com.dial.van.trading

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The candlestick chart's pure geometry, now built on `design/charts/ChartAxes`'s "nice
 * numbers" tick arithmetic rather than a second, home-rolled step-and-loop (this file used to
 * duplicate that algorithm by hand). A chart the owner cannot read the axis of is a chart that
 * cannot answer "why is my trade moving."
 */
class ChartGeometryTest {

    private fun bar(t: Long, o: Double, h: Double, l: Double, c: Double) = BarPoint(t, o, h, l, c)

    private val bars = (0 until 20).map { i ->
        val base = 1.1000 + i * 0.0010
        bar(i * 60_000L, base, base + 0.0006, base - 0.0006, base + 0.0002)
    }

    @Test
    fun `grid step is a nice round number, not an arbitrary fraction`() {
        // ChartAxes.ticks always lands on 1/2/5 x 10^n; a range of 0.02 over 5 target lines
        // should never produce something like 0.0037.
        val step = ChartGeometry.gridStep(0.02, targetLines = 5)
        val mantissa = step / Math.pow(10.0, Math.floor(Math.log10(step)))
        assertTrue(
            listOf(1.0, 2.0, 5.0, 10.0).any { kotlin.math.abs(it - mantissa) < 1e-9 },
            "step $step is not a nice 1/2/5 number",
        )
    }

    @Test
    fun `build produces a candle per visible bar and at least one grid line`() {
        val layout = ChartLayout(width = 400f, height = 240f)
        val scene = ChartGeometry.build(bars, layout, maxVisible = 20)
        assertEquals(20, scene.visible)
        assertEquals(20, scene.candles.size)
        assertTrue(scene.ops.filterIsInstance<ChartOp.GridLine>().isNotEmpty())
    }

    @Test
    fun `time ticks are snapped to a human boundary and stay inside the visible span`() {
        val layout = ChartLayout(width = 400f, height = 240f)
        val scene = ChartGeometry.build(bars, layout, maxVisible = 20)
        val ticks = scene.ops.filterIsInstance<ChartOp.TimeTick>()
        assertTrue(ticks.isNotEmpty())
        ticks.forEach { tick ->
            assertTrue(tick.t >= scene.firstT && tick.t <= scene.lastT, "tick ${tick.t} outside [${scene.firstT}, ${scene.lastT}]")
        }
    }

    @Test
    fun `levels and markers widen the price range so nothing draws off-scale`() {
        val layout = ChartLayout(width = 400f, height = 240f)
        val withoutLevels = ChartGeometry.build(bars, layout, maxVisible = 20)
        val farStop = ChartLevel(LevelKind.STOP, 1.0500, "STOP")
        val withLevel = ChartGeometry.build(bars, layout, levels = listOf(farStop), maxVisible = 20)
        assertTrue(withLevel.priceMin < withoutLevels.priceMin)
    }

    @Test
    fun `an empty series produces an empty scene rather than a crash`() {
        val scene = ChartGeometry.build(emptyList(), ChartLayout(width = 100f, height = 100f))
        assertEquals(0, scene.visible)
        assertTrue(scene.ops.isEmpty())
    }

    @Test
    fun `risk reward is the distance to target over the distance to stop`() {
        assertEquals(2.0, ChartGeometry.riskReward(entry = 1.10, stop = 1.09, target = 1.12))
        assertEquals(null, ChartGeometry.riskReward(entry = 1.10, stop = 1.10, target = 1.12))
        assertEquals(null, ChartGeometry.riskReward(null, 1.09, 1.12))
    }
}
