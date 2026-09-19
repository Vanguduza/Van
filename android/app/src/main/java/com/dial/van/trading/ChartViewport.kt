package com.dial.van.trading

import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * Pan, zoom and a crosshair for the candlestick chart.
 *
 * P4-AND-013 — the canvas rendered a fixed window of the most recent bars with no
 * interaction, so an owner looking at a trade could not see what happened before it. A chart
 * you cannot move is a picture of a chart.
 *
 * P4-AND-012 — text was sized in raw pixels, so the owner's font scale did nothing to it. An
 * owner who has enlarged their system font has done so because they need it, and a chart
 * that ignores that is a chart they cannot read.
 *
 * Pure Kotlin: the windowing arithmetic is the part that is easy to get wrong — off-by-one
 * at the edges, a zoom that drifts the window, a crosshair that snaps to the wrong bar — and
 * it is executed in `android/verification` rather than tested by eye.
 */
data class ChartViewport(
    /** Index of the newest bar shown, counting from the end of the series. 0 = the latest. */
    val offsetFromEnd: Int = 0,
    /** How many bars are shown. */
    val visibleBars: Int = DEFAULT_VISIBLE,
) {
    companion object {
        const val DEFAULT_VISIBLE = 120
        const val MIN_VISIBLE = 12
        const val MAX_VISIBLE = 600

        /** Zoom steps, so pinch and the buttons agree about what a step is. */
        const val ZOOM_STEP = 1.25f
    }
}

/** What the crosshair is over. Null when the pointer is outside the plot. */
data class ChartCrosshair(
    val barIndex: Int,
    val x: Float,
    val price: Double,
    val y: Float,
)

object ChartViewports {

    /** Clamp a viewport to a series. The only place the edges are reasoned about. */
    fun clamp(viewport: ChartViewport, barCount: Int): ChartViewport {
        if (barCount <= 0) return ChartViewport(0, ChartViewport.MIN_VISIBLE)
        val visible = viewport.visibleBars
            .coerceIn(ChartViewport.MIN_VISIBLE, ChartViewport.MAX_VISIBLE)
            .coerceAtMost(barCount)
        // The window cannot be dragged past the start of the series, and cannot be dragged
        // forward past the latest bar: scrolling into empty space on either side is how a
        // chart ends up blank and looking broken.
        val maxOffset = (barCount - visible).coerceAtLeast(0)
        return ChartViewport(
            offsetFromEnd = viewport.offsetFromEnd.coerceIn(0, maxOffset),
            visibleBars = visible,
        )
    }

    /** The slice of the series a viewport shows, as `[from, until)`. */
    fun window(viewport: ChartViewport, barCount: Int): IntRange {
        val clamped = clamp(viewport, barCount)
        val until = barCount - clamped.offsetFromEnd
        val from = (until - clamped.visibleBars).coerceAtLeast(0)
        return from until until
    }

    /**
     * Pan by a horizontal drag.
     *
     * Converted through the bar width rather than a fixed pixel-per-bar constant, so the
     * chart moves with the owner's finger at any zoom level — a drag that moves two bars
     * when zoomed in and two hundred when zoomed out is a chart that feels broken.
     */
    fun pan(
        viewport: ChartViewport,
        dragPx: Float,
        plotWidthPx: Float,
        barCount: Int,
    ): ChartViewport {
        val clamped = clamp(viewport, barCount)
        if (plotWidthPx <= 0f || clamped.visibleBars <= 0) return clamped
        val barWidth = plotWidthPx / clamped.visibleBars
        if (barWidth <= 0f) return clamped
        // Dragging right moves the window back in time, which is the direction a finger on
        // a map expects.
        val bars = (dragPx / barWidth).roundToInt()
        return clamp(clamped.copy(offsetFromEnd = clamped.offsetFromEnd + bars), barCount)
    }

    /**
     * Zoom about the right edge — the latest bar.
     *
     * Anchoring at the newest bar rather than the centre keeps "now" where it was, which is
     * what a trader is actually looking at. Zooming about the centre makes the latest candle
     * slide off screen, which is the one thing they never want to lose.
     */
    fun zoom(viewport: ChartViewport, factor: Float, barCount: Int): ChartViewport {
        if (factor <= 0f || !factor.isFinite()) return clamp(viewport, barCount)
        val clamped = clamp(viewport, barCount)
        val visible = (clamped.visibleBars / factor).roundToInt()
        return clamp(clamped.copy(visibleBars = visible), barCount)
    }

    fun zoomIn(viewport: ChartViewport, barCount: Int): ChartViewport =
        zoom(viewport, ChartViewport.ZOOM_STEP, barCount)

    fun zoomOut(viewport: ChartViewport, barCount: Int): ChartViewport =
        zoom(viewport, 1f / ChartViewport.ZOOM_STEP, barCount)

    /**
     * Which bar the pointer is over, and the price at that height.
     *
     * Snapped to a bar centre rather than reporting a continuous x: a crosshair between two
     * candles tells the owner about a moment that has no data, and a readout that changes
     * while hovering one candle reads as noise.
     */
    fun crosshair(
        pointerX: Float,
        pointerY: Float,
        plotLeft: Float,
        plotRight: Float,
        plotTop: Float,
        plotBottom: Float,
        viewport: ChartViewport,
        barCount: Int,
        highPrice: Double,
        lowPrice: Double,
    ): ChartCrosshair? {
        if (pointerX < plotLeft || pointerX > plotRight) return null
        if (pointerY < plotTop || pointerY > plotBottom) return null
        val plotWidth = plotRight - plotLeft
        val plotHeight = plotBottom - plotTop
        if (plotWidth <= 0f || plotHeight <= 0f) return null
        val range = window(viewport, barCount)
        val count = range.count()
        if (count <= 0) return null

        val barWidth = plotWidth / count
        val slot = ((pointerX - plotLeft) / barWidth).toInt().coerceIn(0, count - 1)
        val barIndex = range.first + slot
        val centreX = plotLeft + barWidth * (slot + 0.5f)

        // Prices run bottom-up on screen and top-down in pixels.
        val fraction = ((pointerY - plotTop) / plotHeight).coerceIn(0f, 1f)
        val price = highPrice - (highPrice - lowPrice) * fraction
        return ChartCrosshair(barIndex = barIndex, x = centreX, price = price, y = pointerY)
    }
}

/**
 * Chart text sizes, in scaled pixels (P4-AND-012).
 *
 * `android.graphics.Paint.textSize` is in raw pixels, so the chart's labels ignored the
 * owner's font scale entirely — an owner who had enlarged their system font got the same
 * unreadable 26px axis labels as everybody else.
 *
 * The scale is also clamped. A 2x font scale on a 220dp chart would produce labels taller
 * than the candles they annotate, and an axis whose numbers overlap is less readable than
 * one whose numbers are slightly small.
 */
object ChartTextScale {
    const val AXIS_SP = 11f
    const val LEVEL_SP = 10f
    const val CROSSHAIR_SP = 12f

    /** Chart labels follow the owner's font scale, within a band that keeps them legible. */
    const val MIN_SCALE = 0.85f
    const val MAX_SCALE = 1.45f

    fun pixels(sp: Float, density: Float, fontScale: Float): Float {
        val scale = if (fontScale.isFinite() && fontScale > 0f) {
            fontScale.coerceIn(MIN_SCALE, MAX_SCALE)
        } else {
            1f
        }
        val safeDensity = if (density.isFinite() && density > 0f) density else 1f
        return sp * safeDensity * scale
    }
}
