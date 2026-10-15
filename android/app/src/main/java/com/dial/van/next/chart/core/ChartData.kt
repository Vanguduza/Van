package com.dial.van.next.chart.core

/**
 * VAN Next chart engine — data model (blueprint Rev 1.5 §7.8, VAN-NX-041/042).
 *
 * Pure Kotlin: no Android, no Compose, no legacy VAN UI imports. Everything here is
 * executed in `android/verification`, because the mistakes a chart makes — a bar out of
 * order, a stale feed drawn as live, a price rounded to the wrong tick — are arithmetic,
 * and arithmetic is tested, not eyeballed.
 */

/** Canonical instrument identity. A ticker string alone is not an identity (§7.8.1). */
data class InstrumentSpec(
    val venue: String,
    val symbol: String,
    val digits: Int,
    val tickSize: Double,
) {
    init {
        require(symbol.isNotBlank()) { "symbol is required" }
        require(digits in 0..10) { "digits out of range: $digits" }
        require(tickSize > 0.0 && tickSize.isFinite()) { "tickSize must be positive" }
    }

    val key: String get() = "$venue:$symbol"

    /** Round a price to the instrument's own tick, never to an arbitrary decimal. */
    fun roundToTick(price: Double): Double = kotlin.math.round(price / tickSize) * tickSize
}

/** One OHLCV bar. [timeMs] is the bar's open time in UTC milliseconds. */
data class Bar(
    val timeMs: Long,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volume: Double = 0.0,
) {
    init {
        require(high >= low) { "high < low at $timeMs" }
        require(high >= maxOf(open, close) && low <= minOf(open, close)) { "OHLC inconsistent at $timeMs" }
    }
}

/** How much the owner may trust what is drawn. Never inferred from the absence of an error. */
enum class DataQuality { LIVE, DELAYED, STALE, CACHED, OFFLINE, UNKNOWN }

/**
 * An immutable, strictly time-ordered bar series with a revision counter.
 *
 * Updates follow a feed's two real shapes: the forming bar changes in place, or a new bar
 * opens. Anything else — a bar older than the last, a gap in revision — is refused, so the
 * caller reloads a snapshot instead of drawing a quietly corrupted history (§7.8.1).
 */
class BarSeries private constructor(
    val instrument: InstrumentSpec,
    val timeframeMs: Long,
    private val data: List<Bar>,
    val revision: Long,
    val quality: DataQuality,
    val asOfMs: Long,
) {
    val size: Int get() = data.size
    operator fun get(index: Int): Bar = data[index]
    val bars: List<Bar> get() = data
    val last: Bar? get() = data.lastOrNull()

    fun withQuality(q: DataQuality, asOfMs: Long = this.asOfMs) =
        BarSeries(instrument, timeframeMs, data, revision, q, asOfMs)

    /** Apply one streamed bar. Returns the new series or throws [SeriesGap] if the caller must resync. */
    fun apply(bar: Bar, newRevision: Long, receivedMs: Long): BarSeries {
        if (newRevision != revision + 1) throw SeriesGap("revision $revision -> $newRevision")
        val tail = data.lastOrNull()
        val next = when {
            tail == null -> listOf(bar)
            bar.timeMs == tail.timeMs -> data.dropLast(1) + bar
            bar.timeMs > tail.timeMs -> data + bar
            else -> throw SeriesGap("bar ${bar.timeMs} older than last ${tail.timeMs}")
        }
        return BarSeries(instrument, timeframeMs, next, newRevision, DataQuality.LIVE, receivedMs)
    }

    /** Index of the bar whose open time is at or before [timeMs]; -1 if before the series. */
    fun indexAtOrBefore(timeMs: Long): Int {
        var lo = 0
        var hi = data.size - 1
        var ans = -1
        while (lo <= hi) {
            val mid = (lo + hi) ushr 1
            if (data[mid].timeMs <= timeMs) { ans = mid; lo = mid + 1 } else hi = mid - 1
        }
        return ans
    }

    companion object {
        fun of(
            instrument: InstrumentSpec,
            timeframeMs: Long,
            bars: List<Bar>,
            revision: Long = 0,
            quality: DataQuality = DataQuality.UNKNOWN,
            asOfMs: Long = 0,
        ): BarSeries {
            require(timeframeMs > 0) { "timeframe must be positive" }
            for (i in 1 until bars.size) {
                require(bars[i].timeMs > bars[i - 1].timeMs) { "bars not strictly increasing at index $i" }
            }
            return BarSeries(instrument, timeframeMs, bars.toList(), revision, quality, asOfMs)
        }
    }
}

class SeriesGap(message: String) : IllegalStateException(message)
