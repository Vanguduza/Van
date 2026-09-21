package com.dial.van.design.charts

import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.roundToInt

/**
 * Axis-tick arithmetic for the trading charts (`CandlestickChart` and friends), factored out
 * so it is pure Kotlin: the geometry a chart draws is a `Canvas` concern the trading worker
 * owns, but "where do the gridlines fall" and "what does this timestamp read as" are pure
 * functions with one right answer per input, and belong here rather than re-derived per chart.
 *
 * Value ticks use the classic "nice numbers" algorithm (Heckbert, *Graphics Gems*): round the
 * requested step to 1, 2 or 5 × a power of ten, so labels read `20, 40, 60` rather than
 * `19.7, 39.4, 59.1`.
 */
object ChartAxes {

    /**
     * A "nice" round number close to `value`: the nearest 1/2/5×10^n, so axis steps read as
     * numbers an owner would actually choose.
     *
     * `round = true` picks the nearest nice number (used for the *step*); `round = false*
     * always rounds up (used for the axis *range*, which must not clip the data it was
     * computed from).
     */
    fun niceNumber(value: Double, round: Boolean): Double {
        if (value == 0.0) return 0.0
        val exponent = floor(log10(value))
        val fraction = value / 10.0.pow(exponent)
        val niceFraction = if (round) {
            when {
                fraction < 1.5 -> 1.0
                fraction < 3.0 -> 2.0
                fraction < 7.0 -> 5.0
                else -> 10.0
            }
        } else {
            when {
                fraction <= 1.0 -> 1.0
                fraction <= 2.0 -> 2.0
                fraction <= 5.0 -> 5.0
                else -> 10.0
            }
        }
        return niceFraction * 10.0.pow(exponent)
    }

    /**
     * Tick values spanning `[min, max]`, at a "nice" step, targeting roughly [targetCount]
     * ticks (Heckbert's algorithm always includes both a tick at or below `min` and one at or
     * above `max`, so the count is approximate by design — a chart with a target of 5 may draw
     * 4 or 6, never a step that produces an unreadable value like `33.3`).
     *
     * `min == max` (a flat series, or a single point) returns the single value: there is no
     * step to compute, and a chart drawing one horizontal line needs exactly one label.
     */
    fun ticks(min: Double, max: Double, targetCount: Int = 5): List<Double> {
        require(targetCount >= 2) { "targetCount must be at least 2, was $targetCount" }
        if (min == max) return listOf(min)
        val lo = minOf(min, max)
        val hi = maxOf(min, max)
        val range = niceNumber(hi - lo, round = false)
        val step = niceNumber(range / (targetCount - 1), round = true)
        val niceMin = floor(lo / step) * step
        val niceMax = ceil(hi / step) * step
        val out = mutableListOf<Double>()
        var v = niceMin
        // A fixed iteration cap rather than a `while (v <= niceMax)` alone: floating-point
        // step accumulation can drift enough over many steps to either stop one tick short
        // or spin past `niceMax`, and a chart axis is exactly the place an infinite loop
        // from that drift would freeze the frame it is drawn on.
        var guard = 0
        while (v <= niceMax + step * 1e-9 && guard < 1000) {
            out.add(roundToStepPrecision(v, step))
            v += step
            guard++
        }
        return out
    }

    /** Rounds away the binary floating-point noise a repeated `+= step` accumulates. */
    private fun roundToStepPrecision(value: Double, step: Double): Double {
        val decimals = maxOf(0, -floor(log10(step)).toInt() + 6)
        val factor = 10.0.pow(decimals)
        return (value * factor).roundToInt() / factor
    }

    private fun log10(value: Double): Double = ln(value) / ln(10.0)

    /** A value tick's label: fixed decimals derived from the step, no trailing noise. */
    fun valueLabel(value: Double, step: Double): String {
        val decimals = when {
            step >= 1.0 -> 0
            step >= 0.1 -> 1
            step >= 0.01 -> 2
            else -> 4
        }
        return "%,.${decimals}f".format(value)
    }

    // ---- Time axis --------------------------------------------------------------------

    /** Millisecond spans past which a coarser granularity reads better than the finer one. */
    private const val ONE_MINUTE_MS = 60_000L
    private const val ONE_HOUR_MS = 60L * ONE_MINUTE_MS
    private const val ONE_DAY_MS = 24L * ONE_HOUR_MS

    /**
     * Evenly spaced epoch-millisecond ticks across `[minEpochMs, maxEpochMs]`, snapped to a
     * human boundary (minute/hour/day) appropriate to the span — a 6-hour chart ticks on the
     * hour, a 3-day chart ticks on the day, so gridlines land where an owner would expect a
     * label rather than at an arbitrary offset from the series' first candle.
     */
    fun timeTicks(minEpochMs: Long, maxEpochMs: Long, targetCount: Int = 5): List<Long> {
        require(targetCount >= 2) { "targetCount must be at least 2, was $targetCount" }
        if (minEpochMs >= maxEpochMs) return listOf(minEpochMs)
        val span = maxEpochMs - minEpochMs
        val rawStep = span / (targetCount - 1)
        val stepMs = snapStep(rawStep)
        val firstTick = (minEpochMs / stepMs) * stepMs
        val out = mutableListOf<Long>()
        var t = firstTick
        var guard = 0
        while (t <= maxEpochMs && guard < 1000) {
            if (t >= minEpochMs) out.add(t)
            t += stepMs
            guard++
        }
        if (out.isEmpty()) out.add(minEpochMs)
        return out
    }

    /** Snaps a raw millisecond step to one of a fixed ladder of human-legible steps. */
    private fun snapStep(rawStepMs: Long): Long {
        val ladder = longArrayOf(
            1_000L, 5_000L, 15_000L, 30_000L,
            ONE_MINUTE_MS, 5 * ONE_MINUTE_MS, 15 * ONE_MINUTE_MS, 30 * ONE_MINUTE_MS,
            ONE_HOUR_MS, 2 * ONE_HOUR_MS, 4 * ONE_HOUR_MS, 6 * ONE_HOUR_MS, 12 * ONE_HOUR_MS,
            ONE_DAY_MS, 2 * ONE_DAY_MS, 7 * ONE_DAY_MS, 30 * ONE_DAY_MS,
        )
        return ladder.firstOrNull { it >= rawStepMs } ?: run {
            // Beyond the ladder's top: round up to whole months of 30 days.
            val months = ceil(rawStepMs.toDouble() / (30 * ONE_DAY_MS)).toLong().coerceAtLeast(1)
            months * 30 * ONE_DAY_MS
        }
    }

    /**
     * The label for one time tick, at a granularity chosen from `spanMs` (the whole chart's
     * span, not the step) — every label on one axis uses the same format, so ticks read as a
     * sequence (`09:00, 10:00, 11:00`) rather than each guessing its own precision.
     */
    fun timeLabel(epochMs: Long, spanMs: Long, zone: ZoneId = ZoneOffset.UTC): String {
        val instant = Instant.ofEpochMilli(epochMs)
        val formatter = when {
            spanMs <= ONE_DAY_MS -> TIME_ONLY
            spanMs <= 30L * ONE_DAY_MS -> DAY_AND_TIME
            spanMs <= 366L * ONE_DAY_MS -> MONTH_AND_DAY
            else -> YEAR_AND_MONTH
        }
        return formatter.withZone(zone).format(instant)
    }

    private val TIME_ONLY: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")
    private val DAY_AND_TIME: DateTimeFormatter = DateTimeFormatter.ofPattern("d MMM HH:mm")
    private val MONTH_AND_DAY: DateTimeFormatter = DateTimeFormatter.ofPattern("d MMM")
    private val YEAR_AND_MONTH: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM yyyy")
}
