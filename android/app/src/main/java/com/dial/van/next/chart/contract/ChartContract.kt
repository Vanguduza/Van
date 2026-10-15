package com.dial.van.next.chart.contract

import com.dial.van.next.chart.drawings.Anchor
import com.dial.van.next.chart.drawings.DrawingKind
import com.dial.van.next.chart.indicators.IndicatorType
import com.dial.van.next.chart.scene.SeriesStyle
import com.dial.van.next.chart.scene.Side

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
    data class AddIndicator(val id: String, val type: IndicatorType, val params: Map<String, Double> = type.defaults) : ChartCommand { override val capability get() = Capability.INDICATOR_ADD }
    data class EditIndicator(val id: String, val params: Map<String, Double>) : ChartCommand { override val capability get() = Capability.INDICATOR_EDIT }
    data class RemoveIndicator(val id: String) : ChartCommand { override val capability get() = Capability.INDICATOR_REMOVE }
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
}

sealed interface ChartEvent {
    data class ViewportChanged(val firstIndex: Int, val lastIndex: Int) : ChartEvent
    data class DrawingChanged(val id: String, val revision: Int) : ChartEvent
    data class IndicatorChanged(val id: String, val version: Int) : ChartEvent
    data class ReplayPosition(val index: Int, val atEnd: Boolean) : ChartEvent
    /** The owner dragged a trade handle. A proposal for the §7.4 review sheet — never an order. */
    data class DraftProposed(val draftId: String, val side: Side, val entry: Double?, val stop: Double?, val target: Double?) : ChartEvent
    data class Rejected(val reason: String) : ChartEvent
}
