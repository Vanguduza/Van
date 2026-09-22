package com.dial.van.trading

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChartGeometryTest {
    private fun bars(n: Int) = (0 until n).map { i -> val base = 1.1 + i * 0.001; BarPoint(1_000L + i * 60_000L, base, base + 0.002, base - 0.002, base + if (i % 2 == 0) 0.001 else -0.001) }
    private val layout = ChartLayout(width = 400f, height = 200f)

    @Test
    fun candlesFillThePlotAndPricesMapMonotonically() {
        val scene = ChartGeometry.build(bars(40), layout)
        assertEquals(40, scene.candles.size)
        val c = scene.candles
        assertTrue(c.first().x > layout.plotLeft && c.last().x < layout.plotRight)
        c.forEach { assertTrue("high above low on screen", it.yHigh < it.yLow); assertTrue(it.yHigh >= layout.plotTop - 0.01f && it.yLow <= layout.plotBottom + 0.01f) }
        assertTrue("later bar with higher close sits higher", c.last().yClose < c.first().yClose)
        assertTrue(scene.priceMin < 1.098 && scene.priceMax > 1.141)
    }

    @Test
    fun levelsZonesMarkersAndGridArePresentAndClamped() {
        val levels = listOf(ChartLevel(LevelKind.ENTRY, 1.12), ChartLevel(LevelKind.STOP, 1.118), ChartLevel(LevelKind.TARGET, 1.126))
        val scene = ChartGeometry.build(bars(40), layout, levels, listOf(ChartMarker(1_000L + 10 * 60_000L, "ENTRY", 1.12), ChartMarker(1_000L + 30 * 60_000L, "EXIT", 1.125)))
        val lines = scene.ops.filterIsInstance<ChartOp.HLine>()
        assertEquals(3, lines.size)
        val stop = lines.first { it.kind == LevelKind.STOP }; val entry = lines.first { it.kind == LevelKind.ENTRY }; val target = lines.first { it.kind == LevelKind.TARGET }
        assertTrue("stop below entry below target on a long", stop.y > entry.y && entry.y > target.y)
        val zones = scene.ops.filterIsInstance<ChartOp.Zone>()
        assertEquals(setOf(LevelKind.STOP, LevelKind.TARGET), zones.map { it.kind }.toSet())
        zones.forEach { assertTrue(it.yTop < it.yBottom) }
        val markers = scene.ops.filterIsInstance<ChartOp.Marker>()
        assertEquals(listOf("ENTRY", "EXIT"), markers.map { it.kind })
        assertTrue(markers[0].x < markers[1].x)
        assertTrue(scene.ops.filterIsInstance<ChartOp.GridLine>().size in 3..8)
        // Time ticks snap to human boundaries through ChartAxes.timeTicks (a 39-minute span
        // steps at 15 minutes → 2 ticks), not to "every Nth bar"; they must still be ordered.
        val ticks = scene.ops.filterIsInstance<ChartOp.TimeTick>()
        assertTrue("ticks: ${ticks.size}", ticks.size in 2..5)
        assertTrue(ticks.zipWithNext().all { (a, b) -> a.x < b.x })
        // an off-scale level widens the price range instead of being clipped away
        val wide = ChartGeometry.build(bars(40), layout, listOf(ChartLevel(LevelKind.STOP, 1.0)))
        assertTrue(wide.priceMin < 1.0)
    }

    @Test
    fun emptyAndFlatSeriesDoNotDivideByZero() {
        assertEquals(0, ChartGeometry.build(emptyList(), layout).ops.size)
        val flat = ChartGeometry.build(List(5) { BarPoint(it.toLong(), 1.0, 1.0, 1.0, 1.0) }, layout)
        assertEquals(5, flat.candles.size)
        flat.candles.forEach { assertTrue(it.yHigh.isFinite() && it.yLow.isFinite()) }
        // gridStep delegates to ChartAxes.ticks (Heckbert "nice numbers": the range is niced
        // first, so 2300 → 5000 / 4 → 1000), not the old 1/2/5 rounding of range/lines (500).
        assertEquals(0.02, ChartGeometry.gridStep(0.1), 1e-12); assertEquals(1000.0, ChartGeometry.gridStep(2300.0), 1e-9); assertEquals(1.0, ChartGeometry.gridStep(0.0), 1e-9)
        val spark = ChartGeometry.sparkline(listOf(1.0, 2.0, 1.5), 100f, 50f)
        assertEquals(3, spark.size); assertEquals(0f, spark[1].second, 1e-6f); assertEquals(50f, spark[0].second, 1e-6f)
        assertEquals(0, ChartGeometry.sparkline(listOf(1.0), 10f, 10f).size)
    }

    @Test
    fun visibleWindowIsTheTail() {
        val scene = ChartGeometry.build(bars(300), layout, maxVisible = 120)
        assertEquals(120, scene.visible); assertEquals(1_000L + 299 * 60_000L, scene.lastT); assertEquals(1_000L + 180 * 60_000L, scene.firstT)
    }
}
