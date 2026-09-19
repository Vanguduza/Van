package com.dial.van.trading

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P4-AND-013 (a chart you cannot move is a picture of a chart) and P4-AND-012 (text sized in
 * raw pixels ignores the owner's font scale entirely).
 */
class ChartViewportTest {

    private val bars = 500

    @Test
    fun `the default window shows the most recent bars`() {
        val range = ChartViewports.window(ChartViewport(), bars)
        assertEquals(bars, range.last + 1)
        assertEquals(ChartViewport.DEFAULT_VISIBLE, range.count())
    }

    @Test
    fun `the window cannot be dragged off either end`() {
        // Scrolling into empty space is how a chart ends up blank and looking broken.
        val past = ChartViewports.clamp(ChartViewport(offsetFromEnd = 10_000), bars)
        assertEquals(bars - past.visibleBars, past.offsetFromEnd)
        val future = ChartViewports.clamp(ChartViewport(offsetFromEnd = -50), bars)
        assertEquals(0, future.offsetFromEnd)

        for (offset in listOf(0, 1, 100, 380, 10_000)) {
            val range = ChartViewports.window(ChartViewport(offsetFromEnd = offset), bars)
            assertTrue(range.first >= 0, "$offset -> $range")
            assertTrue(range.last < bars, "$offset -> $range")
        }
    }

    @Test
    fun `a short series is shown whole rather than padded`() {
        val range = ChartViewports.window(ChartViewport(), barCount = 7)
        assertEquals(0..6, range)
    }

    @Test
    fun `an empty series produces an empty window instead of a crash`() {
        assertEquals(0, ChartViewports.window(ChartViewport(), 0).count())
        assertNull(
            ChartViewports.crosshair(
                10f, 10f, 0f, 100f, 0f, 100f, ChartViewport(), 0, 1.0, 0.5,
            ),
        )
    }

    @Test
    fun `a drag moves the chart with the finger at any zoom`() {
        // A drag that moves two bars zoomed in and two hundred zoomed out is a chart that
        // feels broken, so the conversion goes through the bar width.
        val wide = ChartViewport(offsetFromEnd = 100, visibleBars = 100)
        val panned = ChartViewports.pan(wide, dragPx = 200f, plotWidthPx = 1000f, barCount = bars)
        assertEquals(120, panned.offsetFromEnd)

        val narrow = ChartViewport(offsetFromEnd = 100, visibleBars = 20)
        val pannedNarrow =
            ChartViewports.pan(narrow, dragPx = 200f, plotWidthPx = 1000f, barCount = bars)
        assertEquals(104, pannedNarrow.offsetFromEnd)
    }

    @Test
    fun `dragging the other way walks forward in time and stops at the latest bar`() {
        val start = ChartViewport(offsetFromEnd = 30, visibleBars = 100)
        val back = ChartViewports.pan(start, -500f, 1000f, bars)
        assertEquals(0, back.offsetFromEnd)
    }

    @Test
    fun `a pan with no plot to pan over is a no-op`() {
        val start = ChartViewport(offsetFromEnd = 30, visibleBars = 100)
        assertEquals(start, ChartViewports.pan(start, 200f, 0f, bars))
    }

    @Test
    fun `zoom is bounded and reversible about the latest bar`() {
        var v = ChartViewport()
        repeat(30) { v = ChartViewports.zoomIn(v, bars) }
        assertEquals(ChartViewport.MIN_VISIBLE, v.visibleBars)
        repeat(60) { v = ChartViewports.zoomOut(v, bars) }
        assertEquals(minOf(ChartViewport.MAX_VISIBLE, bars), v.visibleBars)
    }

    @Test
    fun `zooming keeps now on screen`() {
        // Zooming about the centre slides the latest candle off, which is the one thing a
        // trader never wants to lose.
        var v = ChartViewport(offsetFromEnd = 0)
        repeat(5) { v = ChartViewports.zoomIn(v, bars) }
        assertEquals(bars, ChartViewports.window(v, bars).last + 1)
    }

    @Test
    fun `a nonsense zoom factor changes nothing`() {
        val v = ChartViewport(offsetFromEnd = 10, visibleBars = 100)
        assertEquals(ChartViewports.clamp(v, bars), ChartViewports.zoom(v, 0f, bars))
        assertEquals(ChartViewports.clamp(v, bars), ChartViewports.zoom(v, Float.NaN, bars))
    }

    @Test
    fun `the crosshair snaps to a bar the series actually has`() {
        val viewport = ChartViewport(offsetFromEnd = 0, visibleBars = 100)
        val range = ChartViewports.window(viewport, bars)
        for (x in listOf(0f, 1f, 250f, 499f, 999f, 1000f)) {
            val hit = ChartViewports.crosshair(
                pointerX = x, pointerY = 50f,
                plotLeft = 0f, plotRight = 1000f, plotTop = 0f, plotBottom = 100f,
                viewport = viewport, barCount = bars, highPrice = 2.0, lowPrice = 1.0,
            )
            assertNotNull(hit, "x=$x")
            assertTrue(hit.barIndex in range, "x=$x -> ${hit.barIndex} outside $range")
        }
    }

    @Test
    fun `the crosshair reads the price at the pointer, the right way up`() {
        val top = ChartViewports.crosshair(
            500f, 0f, 0f, 1000f, 0f, 100f, ChartViewport(), bars, 2.0, 1.0,
        )
        val bottom = ChartViewports.crosshair(
            500f, 100f, 0f, 1000f, 0f, 100f, ChartViewport(), bars, 2.0, 1.0,
        )
        assertNotNull(top)
        assertNotNull(bottom)
        assertEquals(2.0, top.price, 1e-9)
        assertEquals(1.0, bottom.price, 1e-9)
    }

    @Test
    fun `a pointer outside the plot has nothing under it`() {
        val outside = listOf(-1f to 50f, 1001f to 50f, 500f to -1f, 500f to 101f)
        for ((x, y) in outside) {
            assertNull(
                ChartViewports.crosshair(x, y, 0f, 1000f, 0f, 100f, ChartViewport(), bars, 2.0, 1.0),
                "$x,$y",
            )
        }
    }

    @Test
    fun `chart text follows the owner's font scale`() {
        // P4-AND-012: the old code passed a raw pixel value to Paint.textSize, so an owner
        // who had enlarged their system font because they need it got the same labels.
        val small = ChartTextScale.pixels(ChartTextScale.AXIS_SP, density = 2f, fontScale = 1f)
        val large = ChartTextScale.pixels(ChartTextScale.AXIS_SP, density = 2f, fontScale = 1.3f)
        assertTrue(large > small, "$large !> $small")
        assertEquals(ChartTextScale.AXIS_SP * 2f, small, 1e-4f)
    }

    @Test
    fun `the scale is banded so the labels do not eat the candles`() {
        val huge = ChartTextScale.pixels(ChartTextScale.AXIS_SP, 2f, fontScale = 4f)
        assertEquals(ChartTextScale.AXIS_SP * 2f * ChartTextScale.MAX_SCALE, huge, 1e-4f)
        val tiny = ChartTextScale.pixels(ChartTextScale.AXIS_SP, 2f, fontScale = 0.2f)
        assertEquals(ChartTextScale.AXIS_SP * 2f * ChartTextScale.MIN_SCALE, tiny, 1e-4f)
    }

    @Test
    fun `a nonsense density or scale still produces readable text`() {
        for (density in listOf(0f, -2f, Float.NaN)) {
            val px = ChartTextScale.pixels(ChartTextScale.AXIS_SP, density, 1f)
            assertTrue(px > 0f, "density=$density gave $px")
        }
        assertTrue(ChartTextScale.pixels(ChartTextScale.AXIS_SP, 2f, Float.NaN) > 0f)
    }
}
