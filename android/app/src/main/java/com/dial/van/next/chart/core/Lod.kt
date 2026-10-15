package com.dial.van.next.chart.core

import kotlin.math.max
import kotlin.math.min

/**
 * Level of detail. When the owner zooms out until several bars share one pixel column,
 * drawing every bar wastes the frame budget and draws nothing extra. Bars are merged per
 * column into one candle that keeps the true open, high, low and close of the group, so
 * a spike is never lost by decimation — dropping bars ("every Nth") would hide exactly the
 * wicks a trader zoomed out to find.
 */
data class DrawBar(
    val firstIndex: Int,
    val lastIndex: Int,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volume: Double,
) {
    val centerIndex: Double get() = (firstIndex + lastIndex) / 2.0
}

object Lod {
    /**
     * Group the visible bars so each group spans at least [minPxPerGroup] pixels at the
     * current [barSpacingPx]. Groups are aligned to absolute indices (not to the window
     * edge), so panning does not make candles flicker as group boundaries shift.
     */
    fun group(series: BarSeries, range: IntRange, barSpacingPx: Float, minPxPerGroup: Float = 2f): List<DrawBar> {
        if (range.isEmpty()) return emptyList()
        val per = max(1, kotlin.math.ceil(minPxPerGroup / barSpacingPx).toInt())
        val out = ArrayList<DrawBar>((range.last - range.first) / per + 2)
        var start = (range.first / per) * per
        while (start <= range.last) {
            val end = min(start + per - 1, series.size - 1)
            val a = max(start, 0)
            if (a <= end) {
                var hi = Double.NEGATIVE_INFINITY
                var lo = Double.POSITIVE_INFINITY
                var vol = 0.0
                for (i in a..end) {
                    val b = series[i]
                    if (b.high > hi) hi = b.high
                    if (b.low < lo) lo = b.low
                    vol += b.volume
                }
                out += DrawBar(a, end, series[a].open, hi, lo, series[end].close, vol)
            }
            start += per
        }
        return out
    }

    /** Price extent of the visible bars, for autoscale. */
    fun extent(series: BarSeries, range: IntRange): Pair<Double, Double>? {
        if (range.isEmpty()) return null
        var hi = Double.NEGATIVE_INFINITY
        var lo = Double.POSITIVE_INFINITY
        for (i in range) {
            val b = series[i]
            if (b.high > hi) hi = b.high
            if (b.low < lo) lo = b.low
        }
        return lo to hi
    }
}
