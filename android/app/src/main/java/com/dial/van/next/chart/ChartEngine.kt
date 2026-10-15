package com.dial.van.next.chart

import com.dial.van.next.chart.contract.ChartCommand
import com.dial.van.next.chart.contract.ChartEvent
import com.dial.van.next.chart.core.Bar
import com.dial.van.next.chart.core.BarSeries
import com.dial.van.next.chart.core.DataQuality
import com.dial.van.next.chart.core.RectF
import com.dial.van.next.chart.core.SeriesGap
import com.dial.van.next.chart.core.TimeViewport
import com.dial.van.next.chart.drawings.Drawing
import com.dial.van.next.chart.drawings.DrawingHistory
import com.dial.van.next.chart.indicators.IndicatorInstance
import com.dial.van.next.chart.runtime.FrameScheduler
import com.dial.van.next.chart.scene.ChartLayout
import com.dial.van.next.chart.scene.ChartState
import com.dial.van.next.chart.scene.DraftOverlay
import com.dial.van.next.chart.scene.SceneBuilder
import com.dial.van.next.chart.scene.Side
import com.dial.van.next.chart.scene.TradeOverlays

/**
 * VAN Next chart engine (§7.8). Owns one chart's state and turns commands, streamed bars and
 * gestures into frames and events. It has no network, no broker and no order path: its only
 * trade-shaped output is a [ChartEvent.DraftProposed] for the §7.4 review sheet.
 *
 * Threading: the engine is not thread-safe by itself. The Android host confines it to the
 * main thread and hands immutable [SceneBuilder.Frame]s to its render thread.
 */
class ChartEngine(initial: BarSeries, private var layout: ChartLayout) {

    var state: ChartState = ChartState(initial, TimeViewport.latest(initial.size))
        private set
    private val history = DrawingHistory()
    val scheduler = FrameScheduler()
    private var lastFrame: SceneBuilder.Frame? = null
    private var draftSeq = 0

    /** Called when the host must resync (series gap, wrong instrument). */
    var onResyncNeeded: (reason: String) -> Unit = {}

    fun resize(newLayout: ChartLayout) { layout = newLayout; scheduler.invalidate() }

    /** Layout for a surface of [width]×[height] pixels at [density]; keeps sizing rules in the engine. */
    fun layoutFor(width: Float, height: Float, density: Float) = ChartLayout(width, height, density)

    fun frame(): SceneBuilder.Frame = SceneBuilder.build(state.copy(drawings = history.current.values), layout).also { lastFrame = it }

    private fun plot(): RectF = lastFrame?.mainPlot ?: RectF(0f, 0f, layout.width - layout.axisWidth, layout.height - layout.timeAxisHeight)

    private fun update(s: ChartState) { state = s; scheduler.invalidate() }

    /** Replace the series (snapshot load or resync). Keeps the viewport pinned to the latest bar if it was. */
    fun loadSnapshot(series: BarSeries) {
        val followLatest = state.viewport.rightIndex >= state.series.size - 1
        val vp = if (followLatest) TimeViewport.latest(series.size, state.viewport.barSpacingPx) else state.viewport.clamp(series.size, plot())
        update(state.copy(series = series, viewport = vp, replayCursor = state.replayCursor?.coerceAtMost(series.size - 1)))
    }

    /** One streamed bar. On a gap the engine marks the data stale and asks for a snapshot. */
    fun onBar(bar: Bar, revision: Long, receivedMs: Long) {
        val before = state.series
        try {
            val next = before.apply(bar, revision, receivedMs)
            val opened = next.size > before.size
            val vp = if (opened && state.viewport.rightIndex >= before.size - 1) state.viewport.copy(rightIndex = state.viewport.rightIndex + 1) else state.viewport
            update(state.copy(series = next, viewport = vp))
        } catch (g: SeriesGap) {
            update(state.copy(series = before.withQuality(DataQuality.STALE)))
            onResyncNeeded(g.message ?: "gap")
        }
    }

    fun setQuality(q: DataQuality, asOfMs: Long) = update(state.copy(series = state.series.withQuality(q, asOfMs)))

    fun setOverlays(o: TradeOverlays) = update(state.copy(overlays = o))

    fun apply(cmd: ChartCommand): List<ChartEvent> {
        val p = plot()
        val n = state.series.size
        return when (cmd) {
            is ChartCommand.Pan -> viewport(state.viewport.pan(cmd.dxPx).clamp(n, p))
            is ChartCommand.Zoom -> viewport(state.viewport.zoom(cmd.factor, cmd.focusX, p).clamp(n, p))
            ChartCommand.FitLatest -> viewport(TimeViewport.latest(n, state.viewport.barSpacingPx))
            is ChartCommand.SetStyle -> { update(state.copy(style = cmd.style)); emptyList() }
            is ChartCommand.SetLogScale -> { update(state.copy(logScale = cmd.on)); emptyList() }
            is ChartCommand.Crosshair -> { update(state.copy(crosshair = cmd.x to cmd.y)); emptyList() }
            ChartCommand.ClearCrosshair -> { update(state.copy(crosshair = null)); emptyList() }
            is ChartCommand.AddIndicator -> {
                if (state.indicators.any { it.id == cmd.id }) return listOf(ChartEvent.Rejected("indicator ${cmd.id} exists"))
                val ind = runCatching { IndicatorInstance(cmd.id, cmd.type, cmd.params) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "bad indicator")) }
                update(state.copy(indicators = state.indicators + ind)); listOf(ChartEvent.IndicatorChanged(ind.id, ind.version))
            }
            is ChartCommand.EditIndicator -> {
                val cur = state.indicators.find { it.id == cmd.id } ?: return listOf(ChartEvent.Rejected("no indicator ${cmd.id}"))
                val ed = runCatching { cur.withParams(cmd.params) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "bad parameters")) }
                update(state.copy(indicators = state.indicators.map { if (it.id == cmd.id) ed else it })); listOf(ChartEvent.IndicatorChanged(ed.id, ed.version))
            }
            is ChartCommand.RemoveIndicator -> { update(state.copy(indicators = state.indicators.filterNot { it.id == cmd.id })); emptyList() }
            is ChartCommand.AddDrawing -> {
                if (cmd.id in history.current) return listOf(ChartEvent.Rejected("drawing ${cmd.id} exists"))
                val d = runCatching { Drawing(cmd.id, cmd.kind, cmd.anchors, note = cmd.note) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "bad drawing")) }
                history.put(d); scheduler.invalidate(); listOf(ChartEvent.DrawingChanged(d.id, d.revision))
            }
            is ChartCommand.MoveDrawing -> {
                val cur = history.current[cmd.id] ?: return listOf(ChartEvent.Rejected("no drawing ${cmd.id}"))
                val m = runCatching { cur.moved(cmd.anchors) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "cannot move")) }
                history.put(m); scheduler.invalidate(); listOf(ChartEvent.DrawingChanged(m.id, m.revision))
            }
            is ChartCommand.RemoveDrawing -> { history.remove(cmd.id); scheduler.invalidate(); emptyList() }
            ChartCommand.Undo -> { history.undo(); scheduler.invalidate(); emptyList() }
            ChartCommand.Redo -> { history.redo(); scheduler.invalidate(); emptyList() }
            is ChartCommand.StartReplay -> {
                if (n == 0) return listOf(ChartEvent.Rejected("no bars"))
                val c = cmd.fromIndex.coerceIn(0, n - 1)
                update(state.copy(replayCursor = c, viewport = TimeViewport.latest(c + 1, state.viewport.barSpacingPx)))
                listOf(ChartEvent.ReplayPosition(c, c == n - 1))
            }
            is ChartCommand.StepReplay -> {
                val cur = state.replayCursor ?: return listOf(ChartEvent.Rejected("replay not active"))
                val c = (cur + cmd.bars).coerceIn(0, n - 1)
                val vp = if (state.viewport.rightIndex >= cur) state.viewport.copy(rightIndex = state.viewport.rightIndex + (c - cur)) else state.viewport
                update(state.copy(replayCursor = c, viewport = vp)); listOf(ChartEvent.ReplayPosition(c, c == n - 1))
            }
            ChartCommand.StopReplay -> { update(state.copy(replayCursor = null)); emptyList() }
            is ChartCommand.SetSymbol, is ChartCommand.SetInterval ->
                // Symbol and interval changes are fulfilled by the host loading a new snapshot.
                listOf(ChartEvent.Rejected("host must load a snapshot for ${cmd::class.simpleName}"))
        }
    }

    private fun viewport(vp: TimeViewport): List<ChartEvent> {
        update(state.copy(viewport = vp))
        val r = vp.visibleRange(plot(), state.series.size)
        return if (r.isEmpty()) emptyList() else listOf(ChartEvent.ViewportChanged(r.first, r.last))
    }

    /**
     * The owner dragged a stop, target or entry handle to price-space y. Produces a draft,
     * rounded to the instrument's tick, drawn in the draft style, and an event for the §7.4
     * review sheet. Nothing is sent anywhere.
     */
    fun dragTradeHandle(side: Side, handle: Handle, y: Float, base: DraftOverlay?): List<ChartEvent> {
        if (state.replayCursor != null) return listOf(ChartEvent.Rejected("replay has no trading"))
        val scale = lastFrame?.scale ?: return listOf(ChartEvent.Rejected("no frame yet"))
        val price = state.series.instrument.roundToTick(scale.yToPrice(y, plot()))
        val id = base?.draftId ?: "draft-${++draftSeq}"
        val d = when (handle) {
            Handle.ENTRY -> DraftOverlay(id, side, price, base?.stop, base?.target)
            Handle.STOP -> DraftOverlay(id, side, base?.entry, price, base?.target)
            Handle.TARGET -> DraftOverlay(id, side, base?.entry, base?.stop, price)
        }
        update(state.copy(overlays = state.overlays.copy(draft = d)))
        return listOf(ChartEvent.DraftProposed(d.draftId, d.side, d.entry, d.stop, d.target))
    }

    fun clearDraft() = update(state.copy(overlays = state.overlays.copy(draft = null)))

    val drawings: Map<String, Drawing> get() = history.current

    enum class Handle { ENTRY, STOP, TARGET }
}
