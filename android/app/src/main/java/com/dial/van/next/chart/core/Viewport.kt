package com.dial.van.next.chart.core

import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/** Pixel rectangle. */
data class RectF(val left: Float, val top: Float, val right: Float, val bottom: Float) {
    val width: Float get() = right - left
    val height: Float get() = bottom - top
    fun contains(x: Float, y: Float) = x in left..right && y in top..bottom
}

/**
 * Continuous time viewport, in bar-index space.
 *
 * [rightIndex] is the (fractional) bar index at the right edge of the plot; values beyond
 * the last bar leave a right margin for the forming bar. [barSpacingPx] is the distance
 * between bar centres. Zoom keeps the bar under the owner's fingers still — a zoom that
 * drifts the chart away from what they were looking at is the most common chart bug.
 */
data class TimeViewport(val rightIndex: Double, val barSpacingPx: Float) {
    fun indexToX(index: Double, plot: RectF): Float =
        (plot.right - (rightIndex - index) * barSpacingPx).toFloat()

    fun xToIndex(x: Float, plot: RectF): Double = rightIndex - (plot.right - x) / barSpacingPx

    /** Bars at least partly visible, clamped to the series. */
    fun visibleRange(plot: RectF, size: Int): IntRange {
        if (size == 0) return IntRange.EMPTY
        val first = floor(xToIndex(plot.left, plot)).toInt().coerceAtLeast(0)
        val last = ceil(rightIndex).toInt().coerceAtMost(size - 1)
        return if (first > last) IntRange.EMPTY else first..last
    }

    fun pan(dxPx: Float): TimeViewport = copy(rightIndex = rightIndex - dxPx / barSpacingPx)

    /** Zoom by [factor] (>1 = closer) keeping the bar at [focusX] fixed on screen. */
    fun zoom(factor: Float, focusX: Float, plot: RectF): TimeViewport {
        val focusIndex = xToIndex(focusX, plot)
        val spacing = (barSpacingPx * factor).coerceIn(MIN_SPACING, MAX_SPACING)
        val right = focusIndex + (plot.right - focusX) / spacing
        return TimeViewport(right, spacing)
    }

    /** Keep at least [minVisibleBars] of data on screen and no more than [MAX_RIGHT_MARGIN] bars of empty future. */
    fun clamp(size: Int, plot: RectF, minVisibleBars: Int = 2): TimeViewport {
        if (size == 0) return this
        val visible = plot.width / barSpacingPx
        val maxRight = (size - 1) + MAX_RIGHT_MARGIN
        val minRight = min(maxRight, (minVisibleBars - 1).toDouble().coerceAtMost(visible - 1.0).coerceAtLeast(0.0))
        return copy(rightIndex = rightIndex.coerceIn(minRight, maxRight))
    }

    companion object {
        const val MIN_SPACING = 1.5f
        const val MAX_SPACING = 80f
        const val MAX_RIGHT_MARGIN = 12.0

        fun latest(size: Int, barSpacingPx: Float = 8f, rightMarginBars: Double = 3.0) =
            TimeViewport((size - 1) + rightMarginBars, barSpacingPx.coerceIn(MIN_SPACING, MAX_SPACING))
    }
}

/** Price axis mapping: linear or logarithmic, with padding so extremes are not glued to the edges. */
data class PriceScale(val min: Double, val max: Double, val log: Boolean = false) {
    init { require(max > min) { "price scale max must exceed min" } }

    private fun t(v: Double) = if (log) ln(v) else v

    fun priceToY(price: Double, plot: RectF): Float {
        val f = (t(price) - t(min)) / (t(max) - t(min))
        return (plot.bottom - f * plot.height).toFloat()
    }

    fun yToPrice(y: Float, plot: RectF): Double {
        val f = (plot.bottom - y) / plot.height
        val v = t(min) + f * (t(max) - t(min))
        return if (log) exp(v) else v
    }

    companion object {
        /** Fit [lo]..[hi] with [padding] of the range above and below; flat series get a tick-sized band. */
        fun fit(lo: Double, hi: Double, tickSize: Double, padding: Double = 0.08, log: Boolean = false): PriceScale {
            require(lo.isFinite() && hi.isFinite() && hi >= lo)
            val range = max(hi - lo, tickSize * 10)
            val mid = (hi + lo) / 2
            val half = range / 2 * (1 + 2 * padding)
            val mn = mid - half
            return PriceScale(if (log) max(mn, tickSize) else mn, mid + half, log)
        }
    }
}

/** Human axis ticks: 1, 2, 2.5, 5 × 10^n steps, aligned to the step. */
object NiceTicks {
    fun step(range: Double, maxTicks: Int): Double {
        require(range > 0 && maxTicks >= 2)
        val raw = range / (maxTicks - 1)
        val mag = 10.0.pow(floor(log10(raw)))
        val norm = raw / mag
        val nice = when {
            norm <= 1.0 -> 1.0
            norm <= 2.0 -> 2.0
            norm <= 2.5 -> 2.5
            norm <= 5.0 -> 5.0
            else -> 10.0
        }
        return nice * mag
    }

    fun ticks(min: Double, max: Double, maxTicks: Int): List<Double> {
        if (max <= min) return emptyList()
        val s = step(max - min, maxTicks)
        val first = ceil(min / s - 1e-9) * s
        val out = ArrayList<Double>()
        var v = first
        while (v <= max + s * 1e-9) {
            out += if (abs(v) < s * 1e-9) 0.0 else v
            v += s
        }
        return out
    }
}
