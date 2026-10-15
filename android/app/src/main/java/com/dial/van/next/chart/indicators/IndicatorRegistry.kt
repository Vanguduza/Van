package com.dial.van.next.chart.indicators

import com.dial.van.next.chart.core.BarSeries
import java.util.concurrent.TimeUnit

/** Where an indicator's numbers come from and what they may be used for (§7.3, §7.8.4). */
enum class ProvenanceTier {
    /** Drawn for the owner's eyes. Never an input to VATI risk or execution. */
    PRESENTATION,
    /** A value VATI itself computed and certified, displayed as received. */
    VATI_SOURCE,
    /** Research or model output, labelled as such. */
    RESEARCH,
}

enum class Pane { OVERLAY, SEPARATE }

enum class IndicatorType(val pane: Pane, val defaults: Map<String, Double>) {
    SMA(Pane.OVERLAY, mapOf("period" to 20.0)),
    EMA(Pane.OVERLAY, mapOf("period" to 20.0)),
    BOLLINGER(Pane.OVERLAY, mapOf("period" to 20.0, "k" to 2.0)),
    VWAP(Pane.OVERLAY, emptyMap()),
    RSI(Pane.SEPARATE, mapOf("period" to 14.0)),
    MACD(Pane.SEPARATE, mapOf("fast" to 12.0, "slow" to 26.0, "signal" to 9.0)),
    ATR(Pane.SEPARATE, mapOf("period" to 14.0)),
}

/**
 * One indicator on one chart: typed, versioned parameters (MT5's IndicatorCollection and
 * TradingView's indicator API both keep instances, not pixels — §7.8.4). [version] bumps
 * on every parameter change, so a saved workspace and an undo history refer to exact
 * settings rather than "whatever the panel shows now".
 */
data class IndicatorInstance(
    val id: String,
    val type: IndicatorType,
    val params: Map<String, Double> = type.defaults,
    val version: Int = 1,
    val tier: ProvenanceTier = ProvenanceTier.PRESENTATION,
    val visible: Boolean = true,
) {
    init {
        val unknown = params.keys - type.defaults.keys
        require(unknown.isEmpty()) { "unknown parameters for $type: $unknown" }
        params.forEach { (k, v) -> require(v.isFinite() && v > 0) { "parameter $k must be positive" } }
        if (type == IndicatorType.MACD) require(param("fast") < param("slow")) { "MACD fast must be < slow" }
    }

    fun param(name: String): Double = params[name] ?: type.defaults.getValue(name)
    private fun intParam(name: String) = param(name).toInt()

    fun withParams(changes: Map<String, Double>) = copy(params = params + changes, version = version + 1)
    fun resetToDefaults() = copy(params = type.defaults, version = version + 1)

    /** Named output lines, each the same length as the series. */
    fun compute(series: BarSeries): Map<String, DoubleArray> {
        val bars = series.bars
        val close = DoubleArray(bars.size) { bars[it].close }
        return when (type) {
            IndicatorType.SMA -> mapOf("sma" to Indicators.sma(close, intParam("period")))
            IndicatorType.EMA -> mapOf("ema" to Indicators.ema(close, intParam("period")))
            IndicatorType.BOLLINGER -> Indicators.bollinger(close, intParam("period"), param("k"))
                .let { mapOf("middle" to it.middle, "upper" to it.upper, "lower" to it.lower) }
            IndicatorType.VWAP -> mapOf("vwap" to Indicators.vwap(bars) { TimeUnit.MILLISECONDS.toDays(it) })
            IndicatorType.RSI -> mapOf("rsi" to Indicators.rsi(close, intParam("period")))
            IndicatorType.MACD -> Indicators.macd(close, intParam("fast"), intParam("slow"), intParam("signal"))
                .let { mapOf("macd" to it.macd, "signal" to it.signal, "histogram" to it.histogram) }
            IndicatorType.ATR -> mapOf("atr" to Indicators.atr(bars, intParam("period")))
        }
    }
}
