package com.dial.van.next.chart.tools

import com.dial.van.next.chart.core.BarSeries
import com.dial.van.next.chart.core.PriceScale
import com.dial.van.next.chart.core.RectF
import com.dial.van.next.chart.core.TimeViewport
import com.dial.van.next.chart.drawings.Anchor
import kotlin.math.abs
import kotlin.math.round

/**
 * The ruler (§7.8.11). MT5's chart renderer carries a start/move/stop ruler gesture
 * (REA evidence: `ChartRenderer.CA_RULER_*`). VAN's answer is in instrument units, not
 * pixels: bars, price change, ticks and percent, so "how far is the stop" reads the same
 * on every zoom level and every phone.
 */
data class Measurement(
    val from: Anchor,
    val to: Anchor,
    val bars: Int,
    val priceDelta: Double,
    val ticks: Long,
    val percent: Double,
) {
    fun label(digits: Int): String {
        val sign = if (priceDelta >= 0) "+" else "−"
        val d = String.format(java.util.Locale.ROOT, "%.${digits}f", abs(priceDelta))
        val p = String.format(java.util.Locale.ROOT, "%.2f", abs(percent))
        return "$sign$d ($sign$p%) · ${abs(ticks)} ticks · $bars bars"
    }
}

object Measure {
    fun of(series: BarSeries, from: Anchor, to: Anchor): Measurement {
        val i0 = series.indexAtOrBefore(from.timeMs).coerceAtLeast(0)
        val i1 = series.indexAtOrBefore(to.timeMs).coerceAtLeast(0)
        val delta = to.price - from.price
        val tick = series.instrument.tickSize
        return Measurement(
            from = from,
            to = to,
            bars = abs(i1 - i0),
            priceDelta = delta,
            ticks = round(delta / tick).toLong(),
            percent = if (from.price == 0.0) 0.0 else delta / from.price * 100.0,
        )
    }
}

/**
 * Screen point → durable anchor, with optional magnet (§7.8.11). TradingView exposes a
 * magnet mode for its drawing tools (REA evidence: `ChartBridge.magnetMode/magnetEnabled`).
 * With the magnet on, a point within [radiusPx] of the bar's open, high, low or close snaps
 * to that exact price, so a level drawn "on the high" is on the high, not a pixel away.
 * Without it, the price is rounded to the instrument's tick.
 */
object AnchorPicker {
    const val DEFAULT_RADIUS_DP = 14f

    fun pick(series: BarSeries, vp: TimeViewport, scale: PriceScale, plot: RectF, x: Float, y: Float, magnet: Boolean, radiusPx: Float): Anchor? {
        if (series.size == 0) return null
        val idx = round(vp.xToIndex(x, plot)).toInt().coerceIn(0, series.size - 1)
        val bar = series[idx]
        val raw = series.instrument.roundToTick(scale.yToPrice(y, plot))
        if (!magnet) return Anchor(bar.timeMs, raw)
        val nearest = listOf(bar.open, bar.high, bar.low, bar.close).minBy { abs(scale.priceToY(it, plot) - y) }
        val snapped = abs(scale.priceToY(nearest, plot) - y) <= radiusPx
        return Anchor(bar.timeMs, if (snapped) nearest else raw)
    }
}
