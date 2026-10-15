package com.dial.van.next.chart.contract

import com.dial.van.next.chart.drawings.Anchor
import com.dial.van.next.chart.drawings.DrawingKind
import com.dial.van.next.chart.indicators.IndicatorType
import com.dial.van.next.chart.scene.SeriesStyle
import com.dial.van.next.chart.scene.Side
import com.dial.van.next.chart.tools.Measurement

/**
 * The renderer-independent chart capability contract (§7.8.2, REA-VAN-003). Navigation,
 * research and trading talk to a chart only through these commands and events, so the
 * renderer behind them can be the native engine in this package or any other qualified
 * engine without rewriting the screens around it.
 *
 * Every command has `authorityEffect = NONE`: nothing a chart does changes risk, places,
 * modifies or cancels an order. The only trade-shaped output is [ChartEvent.DraftProposed],
 * which opens the §7.4 review flow.
 */
enum class Capability(val id: String) {
    SYMBOL("chart.symbol"), INTERVAL("chart.interval"), STYLE("chart.style"), LOG_SCALE("chart.scale.log"),
    ZOOM("chart.zoom"), PAN("chart.pan"), FIT("chart.fit"),
    INDICATOR_ADD("chart.indicator.add"), INDICATOR_EDIT("chart.indicator.edit"), INDICATOR_REMOVE("chart.indicator.remove"),
    DRAWING_ADD("chart.drawing.add"), DRAWING_MOVE("chart.drawing.move"), DRAWING_REMOVE("chart.drawing.remove"),
    UNDO("chart.undo"), REDO("chart.redo"),
    REPLAY("chart.replay"), CROSSHAIR("chart.crosshair"),
    DRAFT_TRADE("chart.draft.trade"), OBSERVE("chart.observation"),
    INDICATOR_LEVELS("chart.indicator.levels"), MEASURE("chart.measure"), MAGNET("chart.magnet"),
    LAYERS("chart.layers"), DRAWING_LOCK("chart.drawing.lock"), GOTO("chart.goto"),
    ;
    companion object {
        private val byId = entries.associateBy { it.id }
        fun of(id: String): Capability? = byId[id]

        /** Never part of the contract, whatever a renderer or bundle claims (§14.3). */
        val FORBIDDEN = setOf(
            "placeOrder", "modifyOrder", "cancelOrder", "closePosition", "setLeverage",
            "changeRiskLimit", "sendBrokerCommand", "chart.order.place", "chart.order.modify",
            "chart.order.cancel", "chart.position.close",
        )
    }
}

sealed interface ChartCommand {
    val capability: Capability
    data class SetSymbol(val venue: String, val symbol: String) : ChartCommand { override val capability get() = Capability.SYMBOL }
    data class SetInterval(val timeframeMs: Long) : ChartCommand { override val capability get() = Capability.INTERVAL }
    data class SetStyle(val style: SeriesStyle) : ChartCommand { override val capability get() = Capability.STYLE }
    data class SetLogScale(val on: Boolean) : ChartCommand { override val capability get() = Capability.LOG_SCALE }
    data class Zoom(val factor: Float, val focusX: Float) : ChartCommand { override val capability get() = Capability.ZOOM }
    data class Pan(val dxPx: Float) : ChartCommand { override val capability get() = Capability.PAN }
    data object FitLatest : ChartCommand { override val capability get() = Capability.FIT }
    /** [params] null = the settings last used for this type on this chart, else the type's defaults. */
    data class AddIndicator(val id: String, val type: IndicatorType, val params: Map<String, Double>? = null) : ChartCommand { override val capability get() = Capability.INDICATOR_ADD }
    data class EditIndicator(val id: String, val params: Map<String, Double>) : ChartCommand { override val capability get() = Capability.INDICATOR_EDIT }
    data class RemoveIndicator(val id: String) : ChartCommand { override val capability get() = Capability.INDICATOR_REMOVE }
    data class SetIndicatorLevels(val id: String, val levels: List<Double>) : ChartCommand { override val capability get() = Capability.INDICATOR_LEVELS }
    data class ResetIndicator(val id: String) : ChartCommand { override val capability get() = Capability.INDICATOR_EDIT }
    data class AddDrawing(val id: String, val kind: DrawingKind, val anchors: List<Anchor>, val note: String = "") : ChartCommand { override val capability get() = Capability.DRAWING_ADD }
    data class MoveDrawing(val id: String, val anchors: List<Anchor>) : ChartCommand { override val capability get() = Capability.DRAWING_MOVE }
    data class RemoveDrawing(val id: String) : ChartCommand { override val capability get() = Capability.DRAWING_REMOVE }
    data object Undo : ChartCommand { override val capability get() = Capability.UNDO }
    data object Redo : ChartCommand { override val capability get() = Capability.REDO }
    data class StartReplay(val fromIndex: Int) : ChartCommand { override val capability get() = Capability.REPLAY }
    data class StepReplay(val bars: Int) : ChartCommand { override val capability get() = Capability.REPLAY }
    data object StopReplay : ChartCommand { override val capability get() = Capability.REPLAY }
    data class Crosshair(val x: Float, val y: Float) : ChartCommand { override val capability get() = Capability.CROSSHAIR }
    data object ClearCrosshair : ChartCommand { override val capability get() = Capability.CROSSHAIR }
    data class RulerStart(val x: Float, val y: Float) : ChartCommand { override val capability get() = Capability.MEASURE }
    data class RulerMove(val x: Float, val y: Float) : ChartCommand { override val capability get() = Capability.MEASURE }
    data object RulerStop : ChartCommand { override val capability get() = Capability.MEASURE }
    data class SetMagnet(val on: Boolean) : ChartCommand { override val capability get() = Capability.MAGNET }
    data class SetLayerVisible(val layer: Layer, val visible: Boolean) : ChartCommand { override val capability get() = Capability.LAYERS }
    data class LockAllDrawings(val locked: Boolean) : ChartCommand { override val capability get() = Capability.DRAWING_LOCK }
    data class GoToTime(val timeMs: Long) : ChartCommand { override val capability get() = Capability.GOTO }
}

/** Layers the owner can hide to declutter (§7.8.11). An unconfirmed stop is drawn even when trades are hidden. */
enum class Layer { DRAWINGS, INDICATORS, TRADES }

sealed interface ChartEvent {
    data class ViewportChanged(val firstIndex: Int, val lastIndex: Int) : ChartEvent
    data class DrawingChanged(val id: String, val revision: Int) : ChartEvent
    data class IndicatorChanged(val id: String, val version: Int) : ChartEvent
    data class ReplayPosition(val index: Int, val atEnd: Boolean) : ChartEvent
    /** The chart needs a new snapshot (symbol or interval change). The host loads it with [ChartEngine.loadSnapshot]. */
    data class SnapshotRequested(val venue: String, val symbol: String, val timeframeMs: Long) : ChartEvent
    data class Measured(val measurement: Measurement, val final: Boolean) : ChartEvent
    /** The owner dragged a trade handle. A proposal for the §7.4 review sheet — never an order. */
    data class DraftProposed(val draftId: String, val side: Side, val entry: Double?, val stop: Double?, val target: Double?) : ChartEvent
    data class Rejected(val reason: String) : ChartEvent
}
