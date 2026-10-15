package com.dial.van.next.chart.indicators

import com.dial.van.next.chart.core.Bar
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Technical indicators for the chart (§7.8.4). Every output array has the same length as
 * the input, with `Double.NaN` where the indicator is not yet defined (warm-up), so a
 * renderer never has to guess an offset — an off-by-one shift of a moving average against
 * its candles is invisible on a phone and wrong on every decision made from it.
 *
 * These are PRESENTATION-tier indicators. A VATI decision input is computed on the trading
 * server under its own certification; the chart never feeds one of these to risk or
 * execution (§7.3, provenance tiers).
 */
object Indicators {

    fun sma(values: DoubleArray, period: Int): DoubleArray {
        require(period >= 1)
        val out = DoubleArray(values.size) { Double.NaN }
        var sum = 0.0
        for (i in values.indices) {
            sum += values[i]
            if (i >= period) sum -= values[i - period]
            if (i >= period - 1) out[i] = sum / period
        }
        return out
    }

    /** EMA seeded with the SMA of the first [period] values (the conventional definition). */
    fun ema(values: DoubleArray, period: Int): DoubleArray {
        require(period >= 1)
        val out = DoubleArray(values.size) { Double.NaN }
        if (values.size < period) return out
        val k = 2.0 / (period + 1)
        var prev = values.take(period).average()
        out[period - 1] = prev
        for (i in period until values.size) {
            prev = values[i] * k + prev * (1 - k)
            out[i] = prev
        }
        return out
    }

    /** Wilder's RSI. */
    fun rsi(close: DoubleArray, period: Int = 14): DoubleArray {
        require(period >= 1)
        val out = DoubleArray(close.size) { Double.NaN }
        if (close.size <= period) return out
        var gain = 0.0
        var loss = 0.0
        for (i in 1..period) {
            val d = close[i] - close[i - 1]
            if (d > 0) gain += d else loss -= d
        }
        var avgG = gain / period
        var avgL = loss / period
        out[period] = rsiOf(avgG, avgL)
        for (i in period + 1 until close.size) {
            val d = close[i] - close[i - 1]
            avgG = (avgG * (period - 1) + max(d, 0.0)) / period
            avgL = (avgL * (period - 1) + max(-d, 0.0)) / period
            out[i] = rsiOf(avgG, avgL)
        }
        return out
    }

    private fun rsiOf(g: Double, l: Double) = when {
        l == 0.0 && g == 0.0 -> 50.0
        l == 0.0 -> 100.0
        else -> 100.0 - 100.0 / (1.0 + g / l)
    }

    data class Macd(val macd: DoubleArray, val signal: DoubleArray, val histogram: DoubleArray)

    fun macd(close: DoubleArray, fast: Int = 12, slow: Int = 26, signal: Int = 9): Macd {
        require(fast < slow)
        val f = ema(close, fast)
        val s = ema(close, slow)
        val line = DoubleArray(close.size) { f[it] - s[it] }
        val firstValid = line.indexOfFirst { !it.isNaN() }
        val sig = DoubleArray(close.size) { Double.NaN }
        if (firstValid >= 0) {
            val tail = ema(line.copyOfRange(firstValid, line.size), signal)
            for (i in tail.indices) sig[firstValid + i] = tail[i]
        }
        val hist = DoubleArray(close.size) { line[it] - sig[it] }
        return Macd(line, sig, hist)
    }

    fun trueRange(bars: List<Bar>): DoubleArray = DoubleArray(bars.size) { i ->
        val b = bars[i]
        if (i == 0) b.high - b.low
        else {
            val pc = bars[i - 1].close
            maxOf(b.high - b.low, abs(b.high - pc), abs(b.low - pc))
        }
    }

    /** Wilder's ATR, seeded with the mean true range of the first [period] bars. */
    fun atr(bars: List<Bar>, period: Int = 14): DoubleArray {
        val tr = trueRange(bars)
        val out = DoubleArray(bars.size) { Double.NaN }
        if (bars.size < period) return out
        var prev = tr.take(period).average()
        out[period - 1] = prev
        for (i in period until bars.size) {
            prev = (prev * (period - 1) + tr[i]) / period
            out[i] = prev
        }
        return out
    }

    data class Bands(val middle: DoubleArray, val upper: DoubleArray, val lower: DoubleArray)

    /** Bollinger bands with population standard deviation (the usual charting convention). */
    fun bollinger(close: DoubleArray, period: Int = 20, k: Double = 2.0): Bands {
        val mid = sma(close, period)
        val up = DoubleArray(close.size) { Double.NaN }
        val lo = DoubleArray(close.size) { Double.NaN }
        for (i in period - 1 until close.size) {
            var ss = 0.0
            for (j in i - period + 1..i) { val d = close[j] - mid[i]; ss += d * d }
            val sd = sqrt(ss / period)
            up[i] = mid[i] + k * sd
            lo[i] = mid[i] - k * sd
        }
        return Bands(mid, up, lo)
    }

    /**
     * Volume-weighted average price on typical price, resetting at each session start. A
     * session boundary comes from [sessionKey] (e.g. the UTC trading day), never from a
     * guess about gaps in the data.
     */
    fun vwap(bars: List<Bar>, sessionKey: (Long) -> Long): DoubleArray {
        val out = DoubleArray(bars.size) { Double.NaN }
        var pv = 0.0
        var vol = 0.0
        var session = Long.MIN_VALUE
        for (i in bars.indices) {
            val b = bars[i]
            val s = sessionKey(b.timeMs)
            if (s != session) { session = s; pv = 0.0; vol = 0.0 }
            val tp = (b.high + b.low + b.close) / 3
            pv += tp * b.volume
            vol += b.volume
            out[i] = if (vol > 0) pv / vol else Double.NaN
        }
        return out
    }

    /** Heikin-Ashi candles derived from regular bars. */
    fun heikinAshi(bars: List<Bar>): List<Bar> {
        val out = ArrayList<Bar>(bars.size)
        for (i in bars.indices) {
            val b = bars[i]
            val c = (b.open + b.high + b.low + b.close) / 4
            val o = if (i == 0) (b.open + b.close) / 2 else (out[i - 1].open + out[i - 1].close) / 2
            out += Bar(b.timeMs, o, maxOf(b.high, o, c), minOf(b.low, o, c), c, b.volume)
        }
        return out
    }
}
