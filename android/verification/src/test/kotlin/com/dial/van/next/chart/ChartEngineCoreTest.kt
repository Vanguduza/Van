package com.dial.van.next.chart

import com.dial.van.next.chart.core.Bar
import com.dial.van.next.chart.core.BarSeries
import com.dial.van.next.chart.core.DataQuality
import com.dial.van.next.chart.core.InstrumentSpec
import com.dial.van.next.chart.core.Lod
import com.dial.van.next.chart.core.NiceTicks
import com.dial.van.next.chart.core.PriceScale
import com.dial.van.next.chart.core.RectF
import com.dial.van.next.chart.core.SeriesGap
import com.dial.van.next.chart.core.TimeViewport
import com.dial.van.next.chart.indicators.IndicatorInstance
import com.dial.van.next.chart.indicators.IndicatorType
import com.dial.van.next.chart.indicators.Indicators
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

internal val EURUSD = InstrumentSpec("TEST", "EURUSD", 5, 0.00001)
internal const val M1 = 60_000L

internal fun bars(closes: List<Double>, start: Long = 1_700_000_000_000L, spread: Double = 0.0002, volume: Double = 100.0): List<Bar> =
    closes.mapIndexed { i, c ->
        val o = if (i == 0) c else closes[i - 1]
        Bar(start + i * M1, o, maxOf(o, c) + spread, minOf(o, c) - spread, c, volume)
    }

internal fun series(n: Int, quality: DataQuality = DataQuality.LIVE): BarSeries =
    BarSeries.of(EURUSD, M1, bars(List(n) { 1.08 + 0.001 * kotlin.math.sin(it / 7.0) + it * 0.00001 }), revision = 0, quality = quality)

private fun close(a: Double, b: Double, eps: Double = 1e-9) = assertTrue(abs(a - b) <= eps, "expected $b, got $a")

class SeriesTest {
    @Test fun `bars must be strictly time ordered`() {
        val b = bars(listOf(1.0, 1.1))
        assertFailsWith<IllegalArgumentException> { BarSeries.of(EURUSD, M1, listOf(b[1], b[0])) }
    }

    @Test fun `a forming bar updates in place and a new bar appends`() {
        var s = BarSeries.of(EURUSD, M1, bars(listOf(1.0, 1.1)))
        val last = s.last!!
        s = s.apply(last.copy(close = 1.12, high = 1.13), 1, 10)
        assertEquals(2, s.size); assertEquals(1.12, s.last!!.close)
        s = s.apply(Bar(last.timeMs + M1, 1.12, 1.13, 1.11, 1.125), 2, 20)
        assertEquals(3, s.size); assertEquals(DataQuality.LIVE, s.quality)
    }

    @Test fun `a skipped revision or an older bar forces a resync instead of corrupting history`() {
        val s = BarSeries.of(EURUSD, M1, bars(listOf(1.0, 1.1)))
        assertFailsWith<SeriesGap> { s.apply(s.last!!, 2, 0) }
        assertFailsWith<SeriesGap> { s.apply(s[0], 1, 0) }
    }

    @Test fun `prices round to the instrument tick`() {
        val jpy = InstrumentSpec("TEST", "USDJPY", 3, 0.001)
        close(jpy.roundToTick(151.23456), 151.235, 1e-9)
    }
}

class ViewportTest {
    private val plot = RectF(0f, 0f, 800f, 400f)

    @Test fun `zoom keeps the bar under the fingers still`() {
        val vp = TimeViewport(rightIndex = 499.0, barSpacingPx = 8f)
        val focusX = 300f
        val before = vp.xToIndex(focusX, plot)
        val z = vp.zoom(1.8f, focusX, plot)
        close(z.xToIndex(focusX, plot), before, 1e-6)
    }

    @Test fun `zoom is bounded`() {
        val vp = TimeViewport(499.0, 8f)
        assertEquals(TimeViewport.MAX_SPACING, vp.zoom(1000f, 400f, plot).barSpacingPx)
        assertEquals(TimeViewport.MIN_SPACING, vp.zoom(0.0001f, 400f, plot).barSpacingPx)
    }

    @Test fun `panning cannot leave the data`() {
        val vp = TimeViewport(499.0, 8f)
        assertTrue(vp.pan(-1e6f).clamp(500, plot).rightIndex <= 499 + TimeViewport.MAX_RIGHT_MARGIN)
        assertTrue(vp.pan(1e6f).clamp(500, plot).rightIndex >= 0.0)
    }

    @Test fun `visible range matches pixels`() {
        val vp = TimeViewport(99.0, 8f)
        val r = vp.visibleRange(plot, 100)
        assertEquals(99, r.last); assertEquals(0, r.first) // 800px / 8px = 100 bars
    }

    @Test fun `price scale round trips and log scale is monotonic`() {
        val s = PriceScale(1.0, 2.0)
        close(s.yToPrice(s.priceToY(1.37, plot), plot), 1.37, 1e-6)
        val l = PriceScale(1.0, 100.0, log = true)
        assertTrue(l.priceToY(10.0, plot) > l.priceToY(50.0, plot))
        close(l.yToPrice(l.priceToY(10.0, plot), plot), 10.0, 1e-4)
    }

    @Test fun `axis ticks use nice steps`() {
        val t = NiceTicks.ticks(1.0812, 1.0897, 7)
        assertTrue(t.size in 4..9, "got ${t.size}")
        val step = t[1] - t[0]
        assertTrue(listOf(1.0, 2.0, 2.5, 5.0).any { m -> abs(step / (m * 0.001) - 1) < 1e-6 }, "step $step")
    }
}

class LodTest {
    @Test fun `merged candles keep the true extremes of the group`() {
        val closes = MutableList(100) { 1.0 }
        closes[37] = 1.5 // one spike
        val s = BarSeries.of(EURUSD, M1, bars(closes, spread = 0.0))
        val groups = Lod.group(s, 0..99, barSpacingPx = 0.25f, minPxPerGroup = 2f) // 8 bars per group
        assertEquals(1.5, groups.maxOf { it.high })
        assertTrue(groups.all { it.lastIndex - it.firstIndex + 1 <= 8 })
    }

    @Test fun `group boundaries do not move when panning`() {
        val s = series(300)
        val a = Lod.group(s, 40..200, 0.5f).map { it.firstIndex }
        val b = Lod.group(s, 41..201, 0.5f).map { it.firstIndex }
        assertTrue(a.drop(1).dropLast(1).all { it in b }, "boundaries shifted")
    }

    @Test fun `one bar per group when there is room`() {
        val g = Lod.group(series(50), 0..49, 8f)
        assertEquals(50, g.size)
    }
}

class IndicatorTest {
    @Test fun `sma and its warm up`() {
        val r = Indicators.sma(doubleArrayOf(1.0, 2.0, 3.0, 4.0, 5.0), 3)
        assertTrue(r[0].isNaN() && r[1].isNaN()); close(r[2], 2.0); close(r[4], 4.0)
    }

    @Test fun `ema is seeded with the sma and follows the recurrence`() {
        val v = doubleArrayOf(2.0, 4.0, 6.0, 8.0, 10.0)
        val r = Indicators.ema(v, 3)
        close(r[2], 4.0)
        close(r[3], 8.0 * 0.5 + 4.0 * 0.5)
        close(r[4], 10.0 * 0.5 + r[3] * 0.5)
    }

    @Test fun `rsi extremes and balance`() {
        assertEquals(100.0, Indicators.rsi(DoubleArray(30) { it.toDouble() }, 14).last())
        assertEquals(50.0, Indicators.rsi(DoubleArray(30) { 1.0 }, 14).last())
        val alt = Indicators.rsi(DoubleArray(200) { if (it % 2 == 0) 1.0 else 2.0 }, 14).last()
        assertTrue(abs(alt - 50.0) < 5.0, "alternating series RSI $alt")
        assertTrue(Indicators.rsi(DoubleArray(30) { it.toDouble() }, 14)[13].isNaN())
    }

    @Test fun `atr of constant range bars is that range`() {
        val b = (0 until 40).map { Bar(it * M1, 1.0, 1.01, 0.99, 1.0) }
        close(Indicators.atr(b, 14).last(), 0.02, 1e-12)
    }

    @Test fun `bollinger collapses on a flat series`() {
        val bb = Indicators.bollinger(DoubleArray(30) { 1.5 }, 20, 2.0)
        close(bb.upper.last(), 1.5); close(bb.lower.last(), 1.5)
    }

    @Test fun `macd signal starts after the slow ema exists`() {
        val m = Indicators.macd(DoubleArray(80) { it * 0.1 }, 12, 26, 9)
        assertTrue(m.macd[24].isNaN() && !m.macd[25].isNaN())
        assertTrue(m.signal[32].isNaN() && !m.signal[33].isNaN())
    }

    @Test fun `vwap resets each session`() {
        val day = 86_400_000L
        val b = listOf(Bar(0, 1.0, 1.0, 1.0, 1.0, 10.0), Bar(1, 2.0, 2.0, 2.0, 2.0, 10.0), Bar(day, 5.0, 5.0, 5.0, 5.0, 1.0))
        val v = Indicators.vwap(b) { it / day }
        close(v[1], 1.5); close(v[2], 5.0)
    }

    @Test fun `indicator parameters are typed and versioned`() {
        val i = IndicatorInstance("rsi", IndicatorType.RSI)
        val e = i.withParams(mapOf("period" to 21.0))
        assertEquals(2, e.version); assertEquals(21.0, e.param("period"))
        assertFailsWith<IllegalArgumentException> { IndicatorInstance("x", IndicatorType.RSI, mapOf("bogus" to 1.0)) }
        assertFailsWith<IllegalArgumentException> { IndicatorInstance("m", IndicatorType.MACD, mapOf("fast" to 30.0, "slow" to 26.0, "signal" to 9.0)) }
        assertEquals(series(60).size, i.compute(series(60)).getValue("rsi").size)
    }

    @Test fun `heikin ashi candles stay consistent`() {
        val ha = Indicators.heikinAshi(series(50).bars)
        assertTrue(ha.all { it.high >= maxOf(it.open, it.close) && it.low <= minOf(it.open, it.close) })
    }
}
