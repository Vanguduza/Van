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
import com.dial.van.next.chart.drawings.Anchor
import com.dial.van.next.chart.indicators.IndicatorInstance
import com.dial.van.next.chart.indicators.IndicatorType
import com.dial.van.next.chart.runtime.FrameScheduler
import com.dial.van.next.chart.scene.ChartLayout
import com.dial.van.next.chart.scene.ChartState
import com.dial.van.next.chart.scene.DraftOverlay
import com.dial.van.next.chart.scene.LoadRequest
import com.dial.van.next.chart.scene.SceneBuilder
import com.dial.van.next.chart.scene.Side
import com.dial.van.next.chart.scene.TradeOverlays
import com.dial.van.next.chart.tools.AnchorPicker
import com.dial.van.next.chart.tools.Measure

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
    private var lastFrameState: ChartState? = null
    private var draftSeq = 0
    private var rulerFrom: Anchor? = null
    /** Settings last used per indicator type on this chart (MT5 keeps "previous settings" the same way). */
    private val lastParams = HashMap<IndicatorType, Map<String, Double>>()
    private val lastLevels = HashMap<IndicatorType, List<Double>>()

    /** Bumps on every change a saved workspace would lose; compare with [markSaved]. */
    var workspaceRevision = 0L
        private set
    private var savedRevision = 0L
    val hasUnsavedChanges: Boolean get() = workspaceRevision != savedRevision
    fun markSaved() { savedRevision = workspaceRevision }
    private fun touched() { workspaceRevision++ }

    /** Called when the host must resync (series gap, wrong instrument). */
    var onResyncNeeded: (reason: String) -> Unit = {}

    fun resize(newLayout: ChartLayout) { layout = newLayout; lastFrameState = null; scheduler.invalidate() }

    /** Layout for a surface of [width]×[height] pixels at [density]; keeps sizing rules in the engine. */
    fun layoutFor(width: Float, height: Float, density: Float) = ChartLayout(width, height, density)

    fun frame(): SceneBuilder.Frame {
        val s = state
        return SceneBuilder.build(s.copy(drawings = history.current.values), layout).also { lastFrame = it; lastFrameState = s }
    }

    private fun plot(): RectF = lastFrame?.mainPlot ?: RectF(0f, 0f, layout.width - layout.axisWidth, layout.height - layout.timeAxisHeight)

    private fun update(s: ChartState) { state = s; scheduler.invalidate() }

    /**
     * Replace the series (snapshot load, resync, or the answer to a [ChartEvent.SnapshotRequested]).
     *
     * A snapshot must be for what the chart asked for: while a load is pending, only the
     * requested venue/symbol/interval is accepted, so a slow answer for the previous symbol
     * cannot land under the new one. With nothing pending, only the current instrument and
     * interval are accepted (a resync). On an instrument change, [drawings] replaces the
     * drawing set (drawings belong to an instrument) and undo history starts afresh.
     */
    fun loadSnapshot(series: BarSeries, drawings: Collection<Drawing> = emptyList()): List<ChartEvent> {
        val cur = state.series
        val want = state.loading ?: LoadRequest(cur.instrument.venue, cur.instrument.symbol, cur.timeframeMs)
        if (!want.matches(series)) {
            return listOf(ChartEvent.Rejected("snapshot ${series.instrument.symbol} ${LoadRequest.tfLabel(series.timeframeMs)} does not match ${want.label()}"))
        }
        val instrumentChanged = series.instrument.symbol != cur.instrument.symbol || series.instrument.venue != cur.instrument.venue
        if (instrumentChanged) history.reset(drawings.associateBy { it.id })
        val followLatest = instrumentChanged || state.loading != null || state.viewport.rightIndex >= cur.size - 1
        val vp = if (followLatest) TimeViewport.latest(series.size, state.viewport.barSpacingPx) else state.viewport.clamp(series.size, plot())
        update(state.copy(series = series, viewport = vp, loading = null,
            replayCursor = if (instrumentChanged) null else state.replayCursor?.coerceAtMost(series.size - 1)))
        return emptyList()
    }

    /** One streamed bar. On a gap the engine marks the data stale and asks for a snapshot. */
    fun onBar(bar: Bar, revision: Long, receivedMs: Long) {
        if (state.loading != null) return // bars for the series being replaced; the snapshot supersedes them
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
            is ChartCommand.SetStyle -> { update(state.copy(style = cmd.style)); touched(); emptyList() }
            is ChartCommand.SetLogScale -> { update(state.copy(logScale = cmd.on)); touched(); emptyList() }
            is ChartCommand.Crosshair -> { update(state.copy(crosshair = cmd.x to cmd.y)); emptyList() }
            ChartCommand.ClearCrosshair -> { update(state.copy(crosshair = null)); emptyList() }
            is ChartCommand.AddIndicator -> {
                if (state.indicators.any { it.id == cmd.id }) return listOf(ChartEvent.Rejected("indicator ${cmd.id} exists"))
                val params = cmd.params ?: lastParams[cmd.type] ?: cmd.type.defaults
                val levels = lastLevels[cmd.type] ?: cmd.type.defaultLevels
                val ind = runCatching { IndicatorInstance(cmd.id, cmd.type, params, levels = levels) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "bad indicator")) }
                remember(ind); touched(); update(state.copy(indicators = state.indicators + ind)); listOf(ChartEvent.IndicatorChanged(ind.id, ind.version))
            }
            is ChartCommand.EditIndicator -> {
                val cur = state.indicators.find { it.id == cmd.id } ?: return listOf(ChartEvent.Rejected("no indicator ${cmd.id}"))
                val ed = runCatching { cur.withParams(cmd.params) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "bad parameters")) }
                replaceIndicator(ed)
            }
            is ChartCommand.SetIndicatorLevels -> {
                val cur = state.indicators.find { it.id == cmd.id } ?: return listOf(ChartEvent.Rejected("no indicator ${cmd.id}"))
                val ed = runCatching { cur.withLevels(cmd.levels) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "bad levels")) }
                replaceIndicator(ed)
            }
            is ChartCommand.ResetIndicator -> {
                val cur = state.indicators.find { it.id == cmd.id } ?: return listOf(ChartEvent.Rejected("no indicator ${cmd.id}"))
                replaceIndicator(cur.resetToDefaults())
            }
            is ChartCommand.RemoveIndicator -> {
                if (state.indicators.none { it.id == cmd.id }) return emptyList()
                update(state.copy(indicators = state.indicators.filterNot { it.id == cmd.id })); touched(); emptyList()
            }
            is ChartCommand.AddDrawing -> {
                if (cmd.id in history.current) return listOf(ChartEvent.Rejected("drawing ${cmd.id} exists"))
                val d = runCatching { Drawing(cmd.id, cmd.kind, cmd.anchors, note = cmd.note) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "bad drawing")) }
                history.put(d); drawingsChanged(); listOf(ChartEvent.DrawingChanged(d.id, d.revision))
            }
            is ChartCommand.MoveDrawing -> {
                if (state.drawingsLocked) return listOf(ChartEvent.Rejected("drawings are locked"))
                val cur = history.current[cmd.id] ?: return listOf(ChartEvent.Rejected("no drawing ${cmd.id}"))
                val m = runCatching { cur.moved(cmd.anchors) }.getOrElse { return listOf(ChartEvent.Rejected(it.message ?: "cannot move")) }
                history.put(m); drawingsChanged(); listOf(ChartEvent.DrawingChanged(m.id, m.revision))
            }
            is ChartCommand.RemoveDrawing -> {
                if (state.drawingsLocked) return listOf(ChartEvent.Rejected("drawings are locked"))
                if (cmd.id in history.current) { history.remove(cmd.id); drawingsChanged() }
                emptyList()
            }
            ChartCommand.Undo -> {
                if (state.drawingsLocked) return listOf(ChartEvent.Rejected("drawings are locked"))
                if (history.canUndo()) { history.undo(); drawingsChanged() }
                emptyList()
            }
            ChartCommand.Redo -> {
                if (state.drawingsLocked) return listOf(ChartEvent.Rejected("drawings are locked"))
                if (history.canRedo()) { history.redo(); drawingsChanged() }
                emptyList()
            }
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
            is ChartCommand.SetSymbol -> requestLoad(LoadRequest(cmd.venue, cmd.symbol, state.series.timeframeMs))
            is ChartCommand.SetInterval -> {
                if (cmd.timeframeMs <= 0) return listOf(ChartEvent.Rejected("interval must be positive"))
                val i = state.series.instrument
                val base = state.loading ?: LoadRequest(i.venue, i.symbol, state.series.timeframeMs)
                requestLoad(base.copy(timeframeMs = cmd.timeframeMs))
            }
            is ChartCommand.RulerStart -> {
                val a = anchorAt(cmd.x, cmd.y) ?: return listOf(ChartEvent.Rejected("nothing to measure"))
                rulerFrom = a
                val m = Measure.of(state.series, a, a)
                update(state.copy(ruler = m)); listOf(ChartEvent.Measured(m, final = false))
            }
            is ChartCommand.RulerMove -> {
                val from = rulerFrom ?: return listOf(ChartEvent.Rejected("ruler not started"))
                val to = anchorAt(cmd.x, cmd.y) ?: return emptyList()
                val m = Measure.of(state.series, from, to)
                update(state.copy(ruler = m)); listOf(ChartEvent.Measured(m, final = false))
            }
            ChartCommand.RulerStop -> {
                val m = state.ruler ?: return emptyList()
                rulerFrom = null
                update(state.copy(ruler = null)); listOf(ChartEvent.Measured(m, final = true))
            }
            is ChartCommand.SetMagnet -> { update(state.copy(magnet = cmd.on)); emptyList() }
            is ChartCommand.SetLayerVisible -> {
                val hidden = if (cmd.visible) state.hiddenLayers - cmd.layer else state.hiddenLayers + cmd.layer
                update(state.copy(hiddenLayers = hidden)); emptyList()
            }
            is ChartCommand.LockAllDrawings -> { update(state.copy(drawingsLocked = cmd.locked)); emptyList() }
            is ChartCommand.GoToTime -> {
                if (n == 0) return listOf(ChartEvent.Rejected("no bars"))
                val idx = state.series.indexAtOrBefore(cmd.timeMs).coerceAtLeast(0)
                val half = (p.width / state.viewport.barSpacingPx / 2).toDouble()
                viewport(state.viewport.copy(rightIndex = idx + half).clamp(n, p))
            }
        }
    }

    private fun requestLoad(req: LoadRequest): List<ChartEvent> {
        rulerFrom = null
        update(state.copy(loading = req, overlays = state.overlays.copy(draft = null), ruler = null, crosshair = null))
        return listOf(ChartEvent.SnapshotRequested(req.venue, req.symbol, req.timeframeMs))
    }

    private fun remember(ind: IndicatorInstance) { lastParams[ind.type] = ind.params; lastLevels[ind.type] = ind.levels }

    private fun replaceIndicator(ed: IndicatorInstance): List<ChartEvent> {
        remember(ed); update(state.copy(indicators = state.indicators.map { if (it.id == ed.id) ed else it })); touched()
        return listOf(ChartEvent.IndicatorChanged(ed.id, ed.version))
    }

    private fun drawingsChanged() { scheduler.invalidate(); touched() }

    /**
     * Screen point → durable (time, price) anchor for drawings and the ruler, snapping to the
     * bar's OHLC when the magnet is on. Null before the first frame or on an empty series.
     */
    fun anchorAt(x: Float, y: Float): Anchor? {
        // The scale depends on the viewport and series, so a frame built from an older state could misplace the anchor.
        val f = lastFrame?.takeIf { lastFrameState === state } ?: frame()
        val scale = f.scale ?: return null
        return AnchorPicker.pick(state.series, state.viewport, scale, f.mainPlot, x, y, state.magnet, AnchorPicker.DEFAULT_RADIUS_DP * layout.density)
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
        state.loading?.let { return listOf(ChartEvent.Rejected("chart is loading ${it.label()}; no drafts until it is ready")) }
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
