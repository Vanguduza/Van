package com.dial.van.trading

import kotlin.math.max
import kotlin.math.min

/**
 * Renderer-independent chart geometry (blueprint §10, §22). Bars, levels and markers become
 * pixel-space ops that a Compose Canvas or a JVM test can consume identically. No Android
 * imports: the same source of truth for on-device rendering and for off-device evidence.
 */
sealed interface ChartOp {
    data class Candle(val x: Float, val halfWidth: Float, val yOpen: Float, val yHigh: Float, val yLow: Float, val yClose: Float, val up: Boolean, val t: Long) : ChartOp
    data class HLine(val y: Float, val label: String, val kind: LevelKind, val price: Double) : ChartOp
    data class Marker(val x: Float, val y: Float, val kind: String, val up: Boolean) : ChartOp
    data class Zone(val yTop: Float, val yBottom: Float, val kind: LevelKind) : ChartOp
    data class GridLine(val y: Float, val price: Double) : ChartOp
    data class TimeTick(val x: Float, val t: Long) : ChartOp
}

enum class LevelKind(val argb: Long) { ENTRY(0xFF00E5FFL), STOP(0xFFFF5252L), TARGET(0xFF69F0AEL), EXIT(0xFFFFB300L), CURRENT(0xFFE7ECF2L) }

data class ChartLevel(val kind: LevelKind, val price: Double, val label: String = kind.name)

data class ChartLayout(val width: Float, val height: Float, val padLeft: Float = 6f, val padRight: Float = 54f, val padTop: Float = 10f, val padBottom: Float = 18f) {
    val plotLeft get() = padLeft
    val plotRight get() = width - padRight
    val plotTop get() = padTop
    val plotBottom get() = height - padBottom
}

data class ChartScene(val ops: List<ChartOp>, val priceMin: Double, val priceMax: Double, val firstT: Long, val lastT: Long, val visible: Int) {
    val candles get() = ops.filterIsInstance<ChartOp.Candle>()
}

object ChartGeometry {
    const val UP = 0xFF69F0AEL
    const val DOWN = 0xFFFF5252L

    /** Nice grid step so price labels land on round numbers. */
    fun gridStep(range: Double, targetLines: Int = 5): Double {
        if (range <= 0) return 1.0
        val raw = range / targetLines
        val mag = Math.pow(10.0, Math.floor(Math.log10(raw)))
        val norm = raw / mag
        val nice = when { norm < 1.5 -> 1.0; norm < 3.5 -> 2.0; norm < 7.5 -> 5.0; else -> 10.0 }
        return nice * mag
    }

    fun build(bars: List<BarPoint>, layout: ChartLayout, levels: List<ChartLevel> = emptyList(), markers: List<ChartMarker> = emptyList(), maxVisible: Int = 120): ChartScene {
        val visible = bars.takeLast(maxVisible)
        if (visible.isEmpty()) return ChartScene(emptyList(), 0.0, 0.0, 0L, 0L, 0)
        var lo = visible.minOf { it.l }; var hi = visible.maxOf { it.h }
        levels.forEach { lo = min(lo, it.price); hi = max(hi, it.price) }
        markers.mapNotNull { it.price }.forEach { lo = min(lo, it); hi = max(hi, it) }
        val pad = (hi - lo).takeIf { it > 0 }?.times(0.08) ?: (hi.takeIf { it != 0.0 }?.times(0.001) ?: 1.0)
        lo -= pad; hi += pad
        val plotW = layout.plotRight - layout.plotLeft; val plotH = layout.plotBottom - layout.plotTop
        val slot = plotW / visible.size
        val half = (slot * 0.36f).coerceAtLeast(0.5f)
        fun y(p: Double): Float = (layout.plotBottom - ((p - lo) / (hi - lo)).toFloat() * plotH)
        fun xAt(i: Int): Float = layout.plotLeft + slot * i + slot / 2f
        val ops = mutableListOf<ChartOp>()
        val step = gridStep(hi - lo)
        var g = Math.ceil(lo / step) * step
        while (g < hi) { ops += ChartOp.GridLine(y(g), g); g += step }
        visible.forEachIndexed { i, b -> ops += ChartOp.Candle(xAt(i), half, y(b.o), y(b.h), y(b.l), y(b.c), b.c >= b.o, b.t) }
        val tickEvery = max(1, visible.size / 4)
        visible.forEachIndexed { i, b -> if (i % tickEvery == 0) ops += ChartOp.TimeTick(xAt(i), b.t) }
        levels.forEach { ops += ChartOp.HLine(y(it.price), it.label, it.kind, it.price) }
        val entry = levels.firstOrNull { it.kind == LevelKind.ENTRY }; val stop = levels.firstOrNull { it.kind == LevelKind.STOP }; val target = levels.firstOrNull { it.kind == LevelKind.TARGET }
        if (entry != null && stop != null) ops += ChartOp.Zone(y(max(entry.price, stop.price)), y(min(entry.price, stop.price)), LevelKind.STOP)
        if (entry != null && target != null) ops += ChartOp.Zone(y(max(entry.price, target.price)), y(min(entry.price, target.price)), LevelKind.TARGET)
        markers.forEach { m ->
            val idx = visible.indexOfFirst { it.t + (visible.getOrNull(1)?.t?.minus(visible[0].t) ?: 0L) > m.atMs }.takeIf { it >= 0 } ?: (visible.size - 1)
            val price = m.price ?: visible[idx].c
            ops += ChartOp.Marker(xAt(idx), y(price), m.kind, m.kind == "ENTRY")
        }
        return ChartScene(ops, lo, hi, visible.first().t, visible.last().t, visible.size)
    }

    /** Equity-curve / sparkline polyline in pixel space, oldest → newest. */
    fun sparkline(values: List<Double>, width: Float, height: Float): List<Pair<Float, Float>> {
        if (values.size < 2) return emptyList()
        val lo = values.min(); val hi = values.max(); val span = (hi - lo).takeIf { it > 0 } ?: 1.0
        return values.mapIndexed { i, v -> (width * i / (values.size - 1)) to (height - ((v - lo) / span).toFloat() * height) }
    }

    /** Risk/reward of a level set: distance to target over distance to stop. */
    fun riskReward(entry: Double?, stop: Double?, target: Double?): Double? {
        if (entry == null || stop == null || target == null) return null
        val risk = Math.abs(entry - stop); if (risk <= 0) return null
        return Math.abs(target - entry) / risk
    }
}
