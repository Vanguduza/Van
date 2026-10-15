package com.dial.van.next.chart.scene

import com.dial.van.next.chart.contract.Layer
import com.dial.van.next.chart.core.BarSeries
import com.dial.van.next.chart.core.DataQuality
import com.dial.van.next.chart.core.Lod
import com.dial.van.next.chart.core.NiceTicks
import com.dial.van.next.chart.core.PriceScale
import com.dial.van.next.chart.core.RectF
import com.dial.van.next.chart.core.TimeViewport
import com.dial.van.next.chart.drawings.Drawing
import com.dial.van.next.chart.drawings.DrawingKind
import com.dial.van.next.chart.drawings.DrawingProjector
import com.dial.van.next.chart.indicators.IndicatorInstance
import com.dial.van.next.chart.indicators.IndicatorType
import com.dial.van.next.chart.indicators.Indicators
import com.dial.van.next.chart.indicators.Pane
import com.dial.van.next.chart.tools.Measurement
import kotlin.math.max
import kotlin.math.min

enum class SeriesStyle { CANDLES, HEIKIN_ASHI, LINE, AREA }

/** Everything one frame depends on. Immutable; a new frame is a new state. */
data class ChartState(
    val series: BarSeries,
    val viewport: TimeViewport,
    val style: SeriesStyle = SeriesStyle.CANDLES,
    val indicators: List<IndicatorInstance> = emptyList(),
    val drawings: Collection<Drawing> = emptyList(),
    val selectedDrawingId: String? = null,
    val overlays: TradeOverlays = TradeOverlays(),
    val crosshair: Pair<Float, Float>? = null,
    val showVolume: Boolean = true,
    val logScale: Boolean = false,
    /** Replay cursor (bar index) — bars after it are hidden. Null when live. */
    val replayCursor: Int? = null,
    val hiddenLayers: Set<Layer> = emptySet(),
    val magnet: Boolean = false,
    val drawingsLocked: Boolean = false,
    val ruler: Measurement? = null,
    /** A snapshot the chart is waiting for. While set, no trade drafts are accepted. */
    val loading: LoadRequest? = null,
)

/**
 * A pending symbol/interval load. MT5's renderer tracks the same lifecycle explicitly
 * (REA evidence: `ChartRenderer.CHART_REQUESTING/CHART_READY/CHART_SYMBOL_CHANGED`).
 */
data class LoadRequest(val venue: String, val symbol: String, val timeframeMs: Long) {
    fun matches(s: BarSeries) = s.instrument.venue == venue && s.instrument.symbol == symbol && s.timeframeMs == timeframeMs
    fun label(): String = "$symbol ${tfLabel(timeframeMs)}"
    companion object {
        fun tfLabel(ms: Long): String = when {
            ms % 86_400_000L == 0L -> "D${ms / 86_400_000L}"
            ms % 3_600_000L == 0L -> "H${ms / 3_600_000L}"
            ms % 60_000L == 0L -> "M${ms / 60_000L}"
            else -> "${ms / 1000}s"
        }
    }
}

/** Layout constants in density-independent units, scaled by [density]. */
data class ChartLayout(val width: Float, val height: Float, val density: Float = 1f) {
    val axisWidth get() = 64f * density
    val timeAxisHeight get() = 20f * density
    val paneGap get() = 6f * density
    val textSize get() = 11f * density
}

/**
 * Builds the frame. Pure: same state and layout always give the same display list.
 * The main plot shrinks to make room for separate-pane indicators (RSI, MACD, ATR); volume
 * sits in the bottom quarter of the main plot.
 */
object SceneBuilder {

    data class Frame(val list: DisplayList, val mainPlot: RectF, val scale: PriceScale?, val panes: Map<String, RectF>)

    fun build(state: ChartState, layout: ChartLayout): Frame {
        val out = ArrayList<DrawCmd>(1024)
        val series = state.series
        val visibleLimit = state.replayCursor?.coerceIn(-1, series.size - 1) ?: (series.size - 1)
        val showIndicators = Layer.INDICATORS !in state.hiddenLayers
        val separate = if (showIndicators) state.indicators.filter { it.visible && it.type.pane == Pane.SEPARATE } else emptyList()
        val plotRight = layout.width - layout.axisWidth
        val bottom = layout.height - layout.timeAxisHeight
        val paneH = if (separate.isEmpty()) 0f else min(bottom * 0.22f, 120f * layout.density)
        val mainBottom = bottom - separate.size * (paneH + layout.paneGap)
        val main = RectF(0f, 0f, plotRight, max(mainBottom, bottom * 0.4f))
        val panes = LinkedHashMap<String, RectF>()
        separate.forEachIndexed { i, ind ->
            val top = main.bottom + layout.paneGap + i * (paneH + layout.paneGap)
            panes[ind.id] = RectF(0f, top, plotRight, top + paneH)
        }

        val vp = state.viewport
        val full = vp.visibleRange(main, series.size)
        val range = if (full.isEmpty() || visibleLimit < full.first) IntRange.EMPTY else full.first..min(full.last, visibleLimit)
        val extent = Lod.extent(series, range)

        // Switching instrument: never show the old instrument's candles under the new name.
        val switching = state.loading?.let { it.symbol != series.instrument.symbol || it.venue != series.instrument.venue } ?: false
        if (switching) {
            out += DrawCmd.Text(main.width / 2, main.height / 2, "Loading ${state.loading!!.label()}…", StyleRole.NOTICE, Align.CENTER)
            return Frame(DisplayList(out), main, null, panes)
        }

        if (extent == null) {
            out += DrawCmd.Text(main.width / 2, main.height / 2, emptyMessage(series.quality), StyleRole.AXIS_TEXT, Align.CENTER)
            qualityBadge(series.quality)?.let { out += DrawCmd.Text(4f * layout.density, layout.textSize + 4f, it, StyleRole.QUALITY_BADGE) }
            return Frame(DisplayList(out), main, null, panes)
        }

        val overlayLines = if (!showIndicators) emptyList() else state.indicators.filter { it.visible && it.type.pane == Pane.OVERLAY }.map { it to it.compute(series) }
        var lo = extent.first
        var hi = extent.second
        for ((_, lines) in overlayLines) for (arr in lines.values) for (i in range) {
            val v = arr[i]; if (!v.isNaN()) { lo = min(lo, v); hi = max(hi, v) }
        }
        val scale = PriceScale.fit(lo, hi, series.instrument.tickSize, log = state.logScale)

        // Grid + price axis.
        for (p in NiceTicks.ticks(scale.min, scale.max, 7)) {
            val y = scale.priceToY(p, main)
            out += DrawCmd.Line(main.left, y, main.right, y, StyleRole.GRID)
            out += DrawCmd.Text(main.right + 4f * layout.density, y + layout.textSize / 3, fmt(p, series.instrument.digits), StyleRole.AXIS_TEXT)
        }
        timeTicks(series, range, vp, main, layout, out)

        out += DrawCmd.Clip(main.left, main.top, main.right, main.bottom)
        val groups = Lod.group(series, range, vp.barSpacingPx)
        val drawBars = if (state.style == SeriesStyle.HEIKIN_ASHI) heikin(series, groups) else groups
        if (state.showVolume) volume(drawBars, vp, main, out)
        when (state.style) {
            SeriesStyle.CANDLES, SeriesStyle.HEIKIN_ASHI -> candles(drawBars, vp, scale, main, out)
            SeriesStyle.LINE, SeriesStyle.AREA -> {
                val xs = FloatArray(drawBars.size) { vp.indexToX(drawBars[it].centerIndex, main) }
                val ys = FloatArray(drawBars.size) { scale.priceToY(drawBars[it].close, main) }
                out += DrawCmd.Polyline(xs, ys, if (state.style == SeriesStyle.AREA) StyleRole.AREA_FILL else StyleRole.LINE_PRIMARY)
            }
        }
        // Colour slot = the indicator's position in the chart's list, whatever pane it is in,
        // so an overlay line and a separate-pane line never share a colour by accident.
        overlayLines.forEach { (ind, lines) ->
            val slot = state.indicators.indexOf(ind)
            lines.forEach { (name, arr) ->
                val role = if (name == "upper" || name == "lower") StyleRole.INDICATOR_BAND else indicatorRole(slot)
                polylines(arr, range, vp, main) { scale.priceToY(it, main) }.forEach { (xs, ys) -> out += DrawCmd.Polyline(xs, ys, role) }
            }
        }
        if (Layer.DRAWINGS !in state.hiddenLayers) drawings(state, scale, main, out)
        tradeOverlays(state.overlays, scale, main, series.instrument.digits, Layer.TRADES in state.hiddenLayers, out)
        state.ruler?.let { ruler(it, state, scale, main, layout, out) }
        out += DrawCmd.Unclip

        // Last price line: from the newest bar actually shown (replay hides the future).
        val lastShown = series[range.last]
        val ly = scale.priceToY(lastShown.close, main)
        out += DrawCmd.Line(main.left, ly, main.right, ly, StyleRole.LAST_PRICE, dashed = true)
        out += DrawCmd.Text(main.right + 4f * layout.density, ly + layout.textSize / 3, fmt(lastShown.close, series.instrument.digits), StyleRole.LAST_PRICE)

        separate.forEach { ind -> separatePane(ind, series, range, vp, panes.getValue(ind.id), layout, state.indicators.indexOf(ind), out) }

        state.replayCursor?.let {
            val x = vp.indexToX(min(it, series.size - 1).toDouble(), main)
            out += DrawCmd.Line(x, main.top, x, bottom, StyleRole.REPLAY_CURSOR, dashed = true)
        }
        state.crosshair?.let { (cx, cy) -> crosshair(cx, cy, vp, scale, main, bottom, series, layout, out) }
        qualityBadge(series.quality)?.let { out += DrawCmd.Text(4f * layout.density, layout.textSize + 4f, it, StyleRole.QUALITY_BADGE) }
        notices(state)?.let { out += DrawCmd.Text(main.right - 4f * layout.density, layout.textSize + 4f, it, StyleRole.NOTICE, Align.RIGHT) }
        return Frame(DisplayList(out), main, scale, panes)
    }

    /** Words, not colour, carry the data quality (accessibility; §13.4). LIVE draws no badge. */
    fun qualityBadge(q: DataQuality): String? = when (q) {
        DataQuality.LIVE -> null
        DataQuality.DELAYED -> "Delayed"
        DataQuality.STALE -> "Stale — not live"
        DataQuality.CACHED -> "Cached — not live"
        DataQuality.OFFLINE -> "Offline — last known"
        DataQuality.UNKNOWN -> "Feed status unknown"
    }

    /** Hidden layers and interval loads are said in words, so a decluttered chart is never mistaken for an empty account. */
    internal fun notices(state: ChartState): String? {
        val parts = ArrayList<String>()
        state.loading?.let { parts += "Loading ${it.label()}…" }
        if (Layer.TRADES in state.hiddenLayers) parts += "Trades hidden"
        if (Layer.DRAWINGS in state.hiddenLayers) parts += "Drawings hidden"
        if (Layer.INDICATORS in state.hiddenLayers) parts += "Indicators hidden"
        return parts.takeIf { it.isNotEmpty() }?.joinToString(" · ")
    }

    private fun ruler(m: Measurement, state: ChartState, scale: PriceScale, plot: RectF, layout: ChartLayout, out: MutableList<DrawCmd>) {
        val proj = DrawingProjector(state.viewport, scale, plot) { t -> state.series.indexAtOrBefore(t).toDouble() }
        val x1 = proj.x(m.from); val y1 = proj.y(m.from); val x2 = proj.x(m.to); val y2 = proj.y(m.to)
        out += DrawCmd.Line(x1, y1, x2, y2, StyleRole.MEASURE, dashed = true)
        out += DrawCmd.Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2), StyleRole.MEASURE, filled = false)
        out += DrawCmd.Text(x2 + 4f * layout.density, y2 - 4f * layout.density, m.label(state.series.instrument.digits), StyleRole.MEASURE)
    }

    private fun emptyMessage(q: DataQuality) = if (q == DataQuality.OFFLINE) "Offline — no bars cached" else "No bars to show"

    private fun indicatorRole(n: Int) = when (n % 3) { 0 -> StyleRole.INDICATOR_1; 1 -> StyleRole.INDICATOR_2; else -> StyleRole.INDICATOR_3 }

    private fun candles(bars: List<com.dial.van.next.chart.core.DrawBar>, vp: TimeViewport, scale: PriceScale, plot: RectF, out: MutableList<DrawCmd>) {
        val groupBars = if (bars.isEmpty()) 1 else bars.first().lastIndex - bars.first().firstIndex + 1
        val bodyHalf = max(0.5f, vp.barSpacingPx * groupBars * 0.35f)
        for (b in bars) {
            val x = vp.indexToX(b.centerIndex, plot)
            val up = b.close >= b.open
            out += DrawCmd.Line(x, scale.priceToY(b.high, plot), x, scale.priceToY(b.low, plot), if (up) StyleRole.WICK_UP else StyleRole.WICK_DOWN)
            val yo = scale.priceToY(b.open, plot); val yc = scale.priceToY(b.close, plot)
            out += DrawCmd.Rect(x - bodyHalf, min(yo, yc), x + bodyHalf, max(max(yo, yc), min(yo, yc) + 1f), if (up) StyleRole.CANDLE_UP else StyleRole.CANDLE_DOWN)
        }
    }

    private fun heikin(series: BarSeries, groups: List<com.dial.van.next.chart.core.DrawBar>): List<com.dial.van.next.chart.core.DrawBar> {
        if (groups.isEmpty()) return groups
        val from = max(0, groups.first().firstIndex - 50) // warm-up so the first visible HA candle is settled
        val ha = Indicators.heikinAshi(series.bars.subList(from, groups.last().lastIndex + 1))
        return groups.map { g ->
            val seg = ha.subList(g.firstIndex - from, g.lastIndex - from + 1)
            com.dial.van.next.chart.core.DrawBar(g.firstIndex, g.lastIndex, seg.first().open, seg.maxOf { it.high }, seg.minOf { it.low }, seg.last().close, g.volume)
        }
    }

    private fun volume(bars: List<com.dial.van.next.chart.core.DrawBar>, vp: TimeViewport, plot: RectF, out: MutableList<DrawCmd>) {
        val maxV = bars.maxOfOrNull { it.volume } ?: 0.0
        if (maxV <= 0) return
        val h = plot.height * 0.22f
        val half = max(0.5f, vp.barSpacingPx * 0.35f)
        for (b in bars) {
            val x = vp.indexToX(b.centerIndex, plot)
            val top = plot.bottom - (b.volume / maxV * h).toFloat()
            out += DrawCmd.Rect(x - half, top, x + half, plot.bottom, if (b.close >= b.open) StyleRole.VOLUME_UP else StyleRole.VOLUME_DOWN)
        }
    }

    /** Split an indicator line at NaN gaps so warm-up periods are not drawn as zero. */
    internal fun polylines(arr: DoubleArray, range: IntRange, vp: TimeViewport, plot: RectF, y: (Double) -> Float): List<Pair<FloatArray, FloatArray>> {
        val out = ArrayList<Pair<FloatArray, FloatArray>>()
        val xs = ArrayList<Float>(); val ys = ArrayList<Float>()
        fun flush() { if (xs.size >= 2) out += xs.toFloatArray() to ys.toFloatArray(); xs.clear(); ys.clear() }
        for (i in range) {
            val v = arr[i]
            if (v.isNaN()) { flush(); continue }
            xs += vp.indexToX(i.toDouble(), plot); ys += y(v)
        }
        flush()
        return out
    }

    private fun separatePane(ind: IndicatorInstance, series: BarSeries, range: IntRange, vp: TimeViewport, pane: RectF, layout: ChartLayout, n: Int, out: MutableList<DrawCmd>) {
        val lines = ind.compute(series)
        var lo = Double.POSITIVE_INFINITY; var hi = Double.NEGATIVE_INFINITY
        for (arr in lines.values) for (i in range) { val v = arr[i]; if (!v.isNaN()) { lo = min(lo, v); hi = max(hi, v) } }
        if (ind.type == IndicatorType.RSI) { lo = 0.0; hi = 100.0 }
        if (lo == Double.POSITIVE_INFINITY) { out += DrawCmd.Text(pane.left + 4f, pane.top + layout.textSize, "${ind.type.name}: warming up", StyleRole.AXIS_TEXT); return }
        if (hi <= lo) { hi = lo + 1.0 }
        val s = PriceScale(lo, hi)
        out += DrawCmd.Line(pane.left, pane.top, pane.right, pane.top, StyleRole.GRID)
        for (lvl in ind.levels) if (lvl in s.min..s.max) {
            val y = s.priceToY(lvl, pane); out += DrawCmd.Line(pane.left, y, pane.right, y, StyleRole.GRID, dashed = true)
        }
        out += DrawCmd.Clip(pane.left, pane.top, pane.right, pane.bottom)
        lines.entries.forEachIndexed { k, (name, arr) ->
            if (name == "histogram") {
                val zero = s.priceToY(0.0, pane); val half = max(0.5f, vp.barSpacingPx * 0.3f)
                for (i in range) { val v = arr[i]; if (v.isNaN()) continue
                    val x = vp.indexToX(i.toDouble(), pane); val y = s.priceToY(v, pane)
                    out += DrawCmd.Rect(x - half, min(y, zero), x + half, max(y, zero), StyleRole.INDICATOR_BAND) }
            } else polylines(arr, range, vp, pane) { s.priceToY(it, pane) }.forEach { (xs, ys) -> out += DrawCmd.Polyline(xs, ys, indicatorRole(n + k)) }
        }
        out += DrawCmd.Unclip
        out += DrawCmd.Text(pane.left + 4f, pane.top + layout.textSize, label(ind), StyleRole.AXIS_TEXT)
    }

    private fun label(ind: IndicatorInstance) = ind.type.name + ind.params.values.joinToString(",", " (", ")") { if (it % 1.0 == 0.0) it.toInt().toString() else it.toString() }

    private fun drawings(state: ChartState, scale: PriceScale, plot: RectF, out: MutableList<DrawCmd>) {
        val proj = DrawingProjector(state.viewport, scale, plot) { t -> state.series.indexAtOrBefore(t).toDouble() }
        for (d in state.drawings) {
            val role = if (d.id == state.selectedDrawingId) StyleRole.DRAWING_SELECTED else StyleRole.DRAWING
            val a = d.anchors
            when (d.kind) {
                DrawingKind.HORIZONTAL_LINE -> { val y = proj.y(a[0]); out += DrawCmd.Line(plot.left, y, plot.right, y, role) }
                DrawingKind.TREND_LINE -> out += DrawCmd.Line(proj.x(a[0]), proj.y(a[0]), proj.x(a[1]), proj.y(a[1]), role)
                DrawingKind.RAY -> {
                    val x1 = proj.x(a[0]); val y1 = proj.y(a[0]); val x2 = proj.x(a[1]); val y2 = proj.y(a[1])
                    val t = if (x2 == x1) 1f else (plot.right - x1) / (x2 - x1)
                    out += DrawCmd.Line(x1, y1, if (x2 >= x1) plot.right else x2, if (x2 >= x1) y1 + (y2 - y1) * t else y2, role)
                }
                DrawingKind.RECTANGLE -> out += DrawCmd.Rect(min(proj.x(a[0]), proj.x(a[1])), min(proj.y(a[0]), proj.y(a[1])), max(proj.x(a[0]), proj.x(a[1])), max(proj.y(a[0]), proj.y(a[1])), role, filled = false)
                DrawingKind.FIB_RETRACEMENT -> for (lvl in Drawing.FIB_LEVELS) {
                    val p = a[1].price + (a[0].price - a[1].price) * lvl
                    val y = scale.priceToY(p, plot)
                    out += DrawCmd.Line(min(proj.x(a[0]), proj.x(a[1])), y, plot.right, y, role)
                    out += DrawCmd.Text(plot.right - 4f, y - 2f, "${(lvl * 100).let { if (it % 1.0 == 0.0) it.toInt() else it }}%", role, Align.RIGHT)
                }
                DrawingKind.RISK_REWARD -> {
                    val x = proj.x(a[0])
                    for (an in a) { val y = proj.y(an); out += DrawCmd.Line(x, y, plot.right, y, role) }
                    d.rewardToRisk()?.let { out += DrawCmd.Text(x + 4f, proj.y(a[0]) - 4f, "R:R ${"%.2f".format(it)}", role) }
                }
                DrawingKind.NOTE -> out += DrawCmd.Text(proj.x(a[0]), proj.y(a[0]), d.note.ifBlank { "Note" }, role)
            }
        }
    }

    private fun tradeOverlays(o: TradeOverlays, scale: PriceScale, plot: RectF, digits: Int, hidden: Boolean, out: MutableList<DrawCmd>) {
        fun hline(price: Double, role: StyleRole, text: String, dashed: Boolean = false) {
            val y = scale.priceToY(price, plot)
            out += DrawCmd.Line(plot.left, y, plot.right, y, role, dashed)
            out += DrawCmd.Text(plot.left + 4f, y - 3f, "$text ${fmt(price, digits)}", role)
        }
        if (hidden) {
            // Decluttering never hides a stop the broker has not confirmed (§7.4.3), nor the owner's own draft.
            for (p in o.positions) p.stop?.takeIf { !p.stopConfirmed }?.let { hline(it, StyleRole.POSITION_STOP_UNCONFIRMED, "SL not confirmed", dashed = true) }
        } else for (p in o.positions) {
            hline(p.entry, StyleRole.POSITION_ENTRY, p.label)
            p.stop?.let {
                if (p.stopConfirmed) hline(it, StyleRole.POSITION_STOP_CONFIRMED, "SL")
                else hline(it, StyleRole.POSITION_STOP_UNCONFIRMED, "SL not confirmed", dashed = true)
            }
            p.target?.let { hline(it, StyleRole.POSITION_TARGET, "TP") }
        }
        if (!hidden) for (ord in o.orders) if (ord.drawn) hline(ord.price, StyleRole.PENDING_ORDER, "${ord.label} ${ord.state.name.lowercase().replace('_', ' ')}", dashed = true)
        o.draft?.let { d ->
            d.entry?.let { hline(it, StyleRole.DRAFT_PROPOSAL, "Draft entry", dashed = true) }
            d.stop?.let { hline(it, StyleRole.DRAFT_PROPOSAL, "Draft SL", dashed = true) }
            d.target?.let { hline(it, StyleRole.DRAFT_PROPOSAL, "Draft TP", dashed = true) }
        }
    }

    private fun timeTicks(series: BarSeries, range: IntRange, vp: TimeViewport, plot: RectF, layout: ChartLayout, out: MutableList<DrawCmd>) {
        if (range.isEmpty()) return
        val minGapPx = 90f * layout.density
        val every = max(1, kotlin.math.ceil(minGapPx / vp.barSpacingPx).toInt())
        var i = (range.first / every) * every
        while (i <= range.last) {
            if (i >= range.first) {
                val x = vp.indexToX(i.toDouble(), plot)
                out += DrawCmd.Line(x, plot.top, x, plot.bottom, StyleRole.GRID)
                out += DrawCmd.Text(x, layout.height - 4f * layout.density, timeLabel(series[i].timeMs, series.timeframeMs), StyleRole.AXIS_TEXT, Align.CENTER)
            }
            i += every
        }
    }

    private fun crosshair(cx: Float, cy: Float, vp: TimeViewport, scale: PriceScale, plot: RectF, bottom: Float, series: BarSeries, layout: ChartLayout, out: MutableList<DrawCmd>) {
        if (!plot.contains(cx, cy)) return
        val idx = kotlin.math.round(vp.xToIndex(cx, plot)).toInt().coerceIn(0, series.size - 1)
        val x = vp.indexToX(idx.toDouble(), plot)
        out += DrawCmd.Line(x, plot.top, x, bottom, StyleRole.CROSSHAIR, dashed = true)
        out += DrawCmd.Line(plot.left, cy, plot.right, cy, StyleRole.CROSSHAIR, dashed = true)
        val price = series.instrument.roundToTick(scale.yToPrice(cy, plot))
        out += DrawCmd.Text(plot.right + 4f * layout.density, cy + layout.textSize / 3, fmt(price, series.instrument.digits), StyleRole.CROSSHAIR_LABEL)
        val b = series[idx]
        out += DrawCmd.Text(plot.left + 4f, plot.top + layout.textSize * 2.4f,
            "O ${fmt(b.open, series.instrument.digits)}  H ${fmt(b.high, series.instrument.digits)}  L ${fmt(b.low, series.instrument.digits)}  C ${fmt(b.close, series.instrument.digits)}",
            StyleRole.CROSSHAIR_LABEL)
    }

    fun fmt(v: Double, digits: Int): String = String.format(java.util.Locale.ROOT, "%.${digits}f", v)

    fun timeLabel(ms: Long, tfMs: Long): String {
        val t = java.time.Instant.ofEpochMilli(ms).atZone(java.time.ZoneOffset.UTC)
        return when {
            tfMs >= 86_400_000L -> "%02d %s".format(t.dayOfMonth, t.month.name.take(3).lowercase().replaceFirstChar { it.uppercase() })
            else -> "%02d:%02d".format(t.hour, t.minute)
        }
    }
}
